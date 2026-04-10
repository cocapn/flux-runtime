"""Live Coding Support — tempo-synced, real-time creative coding.

Manages live coding performance sessions with:
- Tempo-synced evaluation (code runs on beat)
- Visual feedback (which tiles are active, which are hot)
- Undo/redo stack
- Version history (every change is timestamped)
- Export recordings
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Any, TYPE_CHECKING

from flux.tiles.tile import Tile, TileInstance

if TYPE_CHECKING:
    from flux.synthesis.synthesizer import FluxSynthesizer


# ── Supporting Types ────────────────────────────────────────────────────────

@dataclass
class ChangeRecord:
    """A record of a change made during a live session."""
    timestamp: float
    action: str              # "inject", "remove", "modify"
    tile_name: str
    params_before: dict = field(default_factory=dict)
    params_after: dict = field(default_factory=dict)
    tile_ref: Optional[Tile] = None

    def __repr__(self) -> str:
        return (
            f"ChangeRecord({self.action!r}, {self.tile_name!r}, "
            f"t={self.timestamp:.3f})"
        )


@dataclass
class VersionRecord:
    """A version snapshot of the live session state."""
    timestamp: float
    beat: int
    active_tiles: dict[str, dict]
    description: str = ""

    def __repr__(self) -> str:
        return (
            f"VersionRecord(beat={self.beat}, tiles={len(self.active_tiles)}, "
            f"t={self.timestamp:.3f})"
        )


@dataclass
class BeatResult:
    """Result of processing a single beat."""
    beat_number: int
    timestamp: float
    active_count: int
    notes_generated: int = 0
    tile_outputs: dict = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"BeatResult(beat={self.beat_number}, active={self.active_count}, "
            f"notes={self.notes_generated})"
        )


@dataclass
class PerformanceState:
    """Current state for visualization."""
    active_tiles: dict[str, dict] = field(default_factory=dict)
    current_beat: int = 0
    bpm: int = 120
    heatmap: dict[str, str] = field(default_factory=dict)
    last_output: dict = field(default_factory=dict)
    total_changes: int = 0

    def __repr__(self) -> str:
        return (
            f"PerformanceState(beat={self.current_beat}, bpm={self.bpm}, "
            f"tiles={len(self.active_tiles)}, changes={self.total_changes})"
        )


@dataclass
class Recording:
    """Exported recording of a live session."""
    bpm: int
    start_time: float
    end_time: float
    total_beats: int
    changes: list[ChangeRecord] = field(default_factory=list)
    versions: list[VersionRecord] = field(default_factory=list)
    beat_results: list[BeatResult] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def changes_per_beat(self) -> float:
        if self.total_beats == 0:
            return 0.0
        return len(self.changes) / self.total_beats

    def __repr__(self) -> str:
        return (
            f"Recording(beats={self.total_beats}, bpm={self.bpm}, "
            f"duration={self.duration:.2f}s, changes={len(self.changes)})"
        )


# ── Live Coding Session ─────────────────────────────────────────────────────

class LiveCodingSession:
    """Manages a live coding performance session.

    Features:
    - Tempo-synced evaluation (code runs on beat)
    - Visual feedback (which tiles are active, which are hot)
    - Undo/redo stack
    - Version history (every change is timestamped)
    - Export recordings
    """

    def __init__(self, synthesizer: FluxSynthesizer | None = None) -> None:
        self.synth = synthesizer
        self.bpm: int = 120
        self.beat_clock: int = 0
        self._start_time: float = time.time()
        self._last_beat_time: float = 0.0
        self._active_tiles: dict[str, TileInstance] = {}
        self._active_tile_params: dict[str, dict] = {}
        self._undo_stack: list[ChangeRecord] = []
        self._redo_stack: list[ChangeRecord] = []
        self._history: list[VersionRecord] = []
        self._beat_results: list[BeatResult] = []
        self._total_changes: int = 0
        self._heatmap: dict[str, str] = {}

    @property
    def beat_duration(self) -> float:
        """Duration of one beat in seconds."""
        return 60.0 / max(1, self.bpm)

    @property
    def active_tile_count(self) -> int:
        return len(self._active_tiles)

    @property
    def undo_depth(self) -> int:
        return len(self._undo_stack)

    @property
    def redo_depth(self) -> int:
        return len(self._redo_stack)

    def set_tempo(self, bpm: int) -> None:
        """Set the tempo in BPM."""
        self.bpm = max(20, min(300, bpm))

    def on_beat(self) -> BeatResult:
        """Called on each beat. Processes active tiles, generates output.

        Returns:
            BeatResult with information about what happened on this beat.
        """
        self.beat_clock += 1
        self._last_beat_time = time.time()

        # Collect outputs from active tiles
        outputs = {}
        notes_count = 0

        for name, instance in self._active_tiles.items():
            tile_type = instance.tile_type.value
            outputs[name] = {
                "type": tile_type,
                "beat": self.beat_clock,
                "active": True,
            }
            # Simulate note generation for creative tiles
            if "generative" in instance.tile.tags:
                notes_count += 1

        result = BeatResult(
            beat_number=self.beat_clock,
            timestamp=self._last_beat_time,
            active_count=len(self._active_tiles),
            notes_generated=notes_count,
            tile_outputs=outputs,
        )

        self._beat_results.append(result)

        # Auto-save version every 16 beats
        if self.beat_clock % 16 == 0:
            self._save_version("auto-save")

        return result

    def inject_tile(
        self,
        name: str,
        tile: Tile,
        params: dict | None = None,
    ) -> None:
        """Add a tile to the live session (hot-loaded).

        Args:
            name: Unique name for the tile in this session
            tile: The Tile to add
            params: Optional parameter overrides
        """
        if name in self._active_tiles:
            # Remove existing first, recording the change
            old_instance = self._active_tiles[name]
            old_params = dict(self._active_tile_params.get(name, {}))
            self._record_change("remove", name, old_params, {}, old_instance.tile)

        instance = tile.instantiate(**(params or {}))
        self._active_tiles[name] = instance
        self._active_tile_params[name] = params or {}

        self._record_change("inject", name, {}, params or {}, tile)
        self._redo_stack.clear()  # Clear redo on new action
        self._total_changes += 1

    def remove_tile(self, name: str) -> None:
        """Remove a tile from the live session.

        Args:
            name: Name of the tile to remove

        Raises:
            KeyError if tile not found
        """
        if name not in self._active_tiles:
            raise KeyError(f"Tile '{name}' not in session")

        instance = self._active_tiles[name]
        old_params = dict(self._active_tile_params.get(name, {}))

        self._record_change("remove", name, old_params, {}, instance.tile)

        del self._active_tiles[name]
        self._active_tile_params.pop(name, None)
        self._redo_stack.clear()
        self._total_changes += 1

    def modify_tile(self, name: str, params: dict) -> None:
        """Modify a tile's parameters (instant effect).

        Args:
            name: Name of the tile to modify
            params: New parameters to apply

        Raises:
            KeyError if tile not found
        """
        if name not in self._active_tiles:
            raise KeyError(f"Tile '{name}' not in session")

        instance = self._active_tiles[name]
        old_params = dict(self._active_tile_params.get(name, {}))
        new_params = {**old_params, **params}

        self._record_change("modify", name, old_params, new_params, instance.tile)

        # Re-instantiate with new params
        self._active_tiles[name] = instance.tile.instantiate(**new_params)
        self._active_tile_params[name] = new_params
        self._redo_stack.clear()
        self._total_changes += 1

    def undo(self) -> Optional[ChangeRecord]:
        """Undo the last change.

        Returns:
            The ChangeRecord that was undone, or None if nothing to undo
        """
        if not self._undo_stack:
            return None

        record = self._undo_stack.pop()

        if record.action == "inject":
            # Undo injection = remove the tile
            if record.tile_name in self._active_tiles:
                del self._active_tiles[record.tile_name]
                self._active_tile_params.pop(record.tile_name, None)

        elif record.action == "remove":
            # Undo removal = re-inject the tile
            if record.tile_ref is not None:
                instance = record.tile_ref.instantiate(**record.params_before)
                self._active_tiles[record.tile_name] = instance
                self._active_tile_params[record.tile_name] = record.params_before

        elif record.action == "modify":
            # Undo modification = restore old params
            if record.tile_name in self._active_tiles and record.tile_ref is not None:
                instance = record.tile_ref.instantiate(**record.params_before)
                self._active_tiles[record.tile_name] = instance
                self._active_tile_params[record.tile_name] = record.params_before

        self._redo_stack.append(record)
        self._total_changes = max(0, self._total_changes - 1)
        return record

    def redo(self) -> Optional[ChangeRecord]:
        """Redo the last undone change.

        Returns:
            The ChangeRecord that was redone, or None if nothing to redo
        """
        if not self._redo_stack:
            return None

        record = self._redo_stack.pop()

        if record.action == "inject":
            if record.tile_ref is not None:
                instance = record.tile_ref.instantiate(**record.params_after)
                self._active_tiles[record.tile_name] = instance
                self._active_tile_params[record.tile_name] = record.params_after

        elif record.action == "remove":
            if record.tile_name in self._active_tiles:
                del self._active_tiles[record.tile_name]
                self._active_tile_params.pop(record.tile_name, None)

        elif record.action == "modify":
            if record.tile_name in self._active_tiles and record.tile_ref is not None:
                instance = record.tile_ref.instantiate(**record.params_after)
                self._active_tiles[record.tile_name] = instance
                self._active_tile_params[record.tile_name] = record.params_after

        self._undo_stack.append(record)
        self._total_changes += 1
        return record

    def get_performance_state(self) -> PerformanceState:
        """Get current state for visualization.

        Returns:
            PerformanceState with all current session data
        """
        tile_info = {}
        for name, instance in self._active_tiles.items():
            tile_info[name] = {
                "type": instance.tile_type.value,
                "tags": list(instance.tile.tags),
                "params": dict(self._active_tile_params.get(name, {})),
            }

        last_output = {}
        if self._beat_results:
            last_output = self._beat_results[-1].tile_outputs

        return PerformanceState(
            active_tiles=tile_info,
            current_beat=self.beat_clock,
            bpm=self.bpm,
            heatmap=dict(self._heatmap),
            last_output=last_output,
            total_changes=self._total_changes,
        )

    def set_heatmap(self, heatmap: dict[str, str]) -> None:
        """Set the heatmap data for visualization."""
        self._heatmap = dict(heatmap)

    def export_recording(self) -> Recording:
        """Export the session as a recording.

        Returns:
            Recording with timeline of changes, versions, and beat results
        """
        return Recording(
            bpm=self.bpm,
            start_time=self._start_time,
            end_time=time.time(),
            total_beats=self.beat_clock,
            changes=list(self._undo_stack) + list(self._redo_stack),
            versions=list(self._history),
            beat_results=list(self._beat_results),
        )

    def _record_change(
        self,
        action: str,
        tile_name: str,
        params_before: dict,
        params_after: dict,
        tile_ref: Tile | None = None,
    ) -> None:
        """Record a change for undo/redo tracking."""
        record = ChangeRecord(
            timestamp=time.time(),
            action=action,
            tile_name=tile_name,
            params_before=params_before,
            params_after=params_after,
            tile_ref=tile_ref,
        )
        self._undo_stack.append(record)

    def _save_version(self, description: str = "") -> None:
        """Save a version snapshot."""
        tile_info = {}
        for name, instance in self._active_tiles.items():
            tile_info[name] = {
                "type": instance.tile_type.value,
                "params": dict(self._active_tile_params.get(name, {})),
            }

        self._history.append(VersionRecord(
            timestamp=time.time(),
            beat=self.beat_clock,
            active_tiles=tile_info,
            description=description,
        ))

    @property
    def version_count(self) -> int:
        return len(self._history)

    def __repr__(self) -> str:
        return (
            f"LiveCodingSession(bpm={self.bpm}, beat={self.beat_clock}, "
            f"tiles={len(self._active_tiles)}, "
            f"undo={len(self._undo_stack)}, redo={len(self._redo_stack)})"
        )
