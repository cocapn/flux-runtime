"""Genome — the system's DNA — snapshot of all modules, tiles, and configurations.

A genome captures the complete state of the FLUX runtime at a point in time,
enabling comparison, evaluation, mutation, and serialization of system
configurations. Genomes are the fundamental unit of the self-evolution engine:
each generation produces a new genome that can be compared to its predecessor.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any

from flux.adaptive.profiler import (
    AdaptiveProfiler,
    HeatLevel,
    BottleneckReport,
)
from flux.adaptive.selector import AdaptiveSelector, LanguageRecommendation


# ── Snapshot Types ────────────────────────────────────────────────────────────

@dataclass
class ModuleSnapshot:
    """Snapshot of a single module/container state."""
    path: str
    granularity: str  # Granularity enum name
    language: str
    version: int
    checksum: str
    card_count: int = 0
    child_count: int = 0
    heat_level: str = "FROZEN"
    call_count: int = 0
    total_time_ns: int = 0


@dataclass
class TileSnapshot:
    """Snapshot of a registered tile."""
    name: str
    tile_type: str  # TileType enum value
    input_count: int
    output_count: int
    cost_estimate: float
    abstraction_level: int
    language_preference: str
    tags: tuple[str, ...] = ()
    param_count: int = 0


@dataclass
class ProfilerSnapshot:
    """Snapshot of the profiler's state."""
    module_count: int = 0
    sample_count: int = 0
    heatmap: dict[str, str] = field(default_factory=dict)  # path → HeatLevel name
    ranking: list[tuple[str, float]] = field(default_factory=list)  # path, weight
    total_time_ns: int = 0


@dataclass
class OptimizationRecord:
    """Record of an optimization that was applied."""
    generation: int
    mutation_type: str  # MutationStrategy name
    target: str  # module path or tile name
    description: str
    success: bool
    speedup: float = 1.0
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class GenomeDiff:
    """Result of comparing two genomes."""
    modules_added: list[str] = field(default_factory=list)
    modules_removed: list[str] = field(default_factory=list)
    modules_changed: dict[str, dict[str, Any]] = field(default_factory=dict)
    tiles_added: list[str] = field(default_factory=list)
    tiles_removed: list[str] = field(default_factory=list)
    tiles_changed: dict[str, dict[str, Any]] = field(default_factory=dict)
    language_changes: dict[str, tuple[str, str]] = field(default_factory=dict)
    fitness_before: float = 0.0
    fitness_after: float = 0.0
    fitness_delta: float = 0.0

    @property
    def has_changes(self) -> bool:
        return bool(
            self.modules_added or self.modules_removed or
            self.modules_changed or self.tiles_added or
            self.tiles_removed or self.tiles_changed or
            self.language_changes
        )


# ── Mutation Strategies ───────────────────────────────────────────────────────

class MutationStrategy(Enum):
    """Types of mutations the evolution engine can apply."""
    RECOMPILE_LANGUAGE = "recompile_language"     # Change module language
    FUSE_PATTERN = "fuse_pattern"                 # Fuse hot sequence into tile
    REPLACE_TILE = "replace_tile"                 # Swap tile for alternative
    ADD_TILE = "add_tile"                         # Register a new discovered tile
    MERGE_TILES = "merge_tiles"                   # Merge co-occurring tiles
    SPLIT_TILE = "split_tile"                     # Split complex tile
    INLINE_OPTIMIZATION = "inline_optimization"   # Apply inlining/canonicalization


# ── Genome ────────────────────────────────────────────────────────────────────

class Genome:
    """Complete snapshot of the system's current state — its 'DNA'.

    A genome captures:
    - All module containers and their nested structure
    - Which language each module is compiled to
    - All registered tiles and their compositions
    - The current profiler data (heat map, bottlenecks)
    - Optimization decisions made so far

    Genomes can be:
    - Serialized (saved to disk via to_dict)
    - Compared (diff between two genomes)
    - Evaluated (fitness score based on speed + modularity + correctness)
    - Mutated (try an improvement, see if it works)
    """

    def __init__(self) -> None:
        self.modules: dict[str, ModuleSnapshot] = {}
        self.tiles: dict[str, TileSnapshot] = {}
        self.language_assignments: dict[str, str] = {}
        self.profiler_snapshot: ProfilerSnapshot = ProfilerSnapshot()
        self.optimization_history: list[OptimizationRecord] = []
        self.fitness_score: float = 0.0
        self.timestamp: float = 0.0
        self.generation: int = 0
        self.checksum: str = ""

    # ── Capture ─────────────────────────────────────────────────────────

    def capture(
        self,
        module_root: Any,
        tile_registry: Any,
        profiler: AdaptiveProfiler,
        selector: AdaptiveSelector,
    ) -> None:
        """Take a snapshot of the entire system state.

        Args:
            module_root: The root ModuleContainer.
            tile_registry: The TileRegistry.
            profiler: The AdaptiveProfiler with execution data.
            selector: The AdaptiveSelector with language assignments.
        """
        self.timestamp = time.time()
        self._capture_modules(module_root)
        self._capture_tiles(tile_registry)
        self._capture_profiler(profiler)
        self._capture_languages(selector)
        self.checksum = self._compute_checksum()

    def _capture_modules(self, container: Any) -> None:
        """Recursively capture module container state."""
        from flux.modules.card import ModuleCard

        heatmap: dict[str, HeatLevel] = {}
        call_counts: dict[str, int] = {}
        total_times: dict[str, int] = {}

        # Defer to profiler snapshot for heatmap — use empty during capture
        snap = self.modules
        snap[container.path] = ModuleSnapshot(
            path=container.path,
            granularity=container.granularity.name,
            language="python",
            version=container.version,
            checksum=container.checksum,
            card_count=len(container.cards),
            child_count=len(container.children),
        )

        # Capture cards
        for card_name, card in container.cards.items():
            card_path = f"{container.path}.{card_name}"
            snap[card_path] = ModuleSnapshot(
                path=card_path,
                granularity="CARD",
                language=card.language,
                version=card.version,
                checksum=card.checksum,
            )

        # Recurse into children
        for child in container.children.values():
            self._capture_modules(child)

    def _capture_tiles(self, registry: Any) -> None:
        """Capture tile registry state."""
        for tile in registry.all_tiles:
            self.tiles[tile.name] = TileSnapshot(
                name=tile.name,
                tile_type=tile.tile_type.value,
                input_count=len(tile.inputs),
                output_count=len(tile.outputs),
                cost_estimate=tile.cost_estimate,
                abstraction_level=tile.abstraction_level,
                language_preference=tile.language_preference,
                tags=tuple(sorted(tile.tags)),
                param_count=len(tile.params),
            )

    def _capture_profiler(self, profiler: AdaptiveProfiler) -> None:
        """Capture profiler state."""
        heatmap = profiler.get_heatmap()
        ranking = profiler.get_ranking()

        self.profiler_snapshot = ProfilerSnapshot(
            module_count=profiler.module_count,
            sample_count=profiler.sample_count,
            heatmap={path: heat.name for path, heat in heatmap.items()},
            ranking=ranking,
            total_time_ns=sum(profiler.total_time_ns.values()),
        )

        # Enrich module snapshots with profiler data
        for mod_path, mod_snap in self.modules.items():
            if mod_path in heatmap:
                mod_snap.heat_level = heatmap[mod_path].name
            if mod_path in profiler.call_counts:
                mod_snap.call_count = profiler.call_counts[mod_path]
            if mod_path in profiler.total_time_ns:
                mod_snap.total_time_ns = profiler.total_time_ns[mod_path]

    def _capture_languages(self, selector: AdaptiveSelector) -> None:
        """Capture current language assignments."""
        self.language_assignments = dict(selector.current_languages)

    # ── Fitness ─────────────────────────────────────────────────────────

    def evaluate_fitness(self) -> float:
        """Score this genome on speed + modularity + correctness (0-1).

        Components:
        - Speed (0.4 weight): based on profiler data — less time = higher score.
        - Modularity (0.3 weight): more Python = more modular.
        - Correctness (0.3 weight): based on optimization success rate.

        Returns:
            Fitness score between 0.0 and 1.0.
        """
        speed_score = self._speed_score()
        modularity_score = self._modularity_score()
        correctness_score = self._correctness_score()

        self.fitness_score = (
            0.4 * speed_score +
            0.3 * modularity_score +
            0.3 * correctness_score
        )
        return self.fitness_score

    def _speed_score(self) -> float:
        """Score based on execution speed (0-1).

        If there are no modules with profiler data, return neutral 0.5.
        Otherwise, reward modules in faster languages.
        """
        if not self.modules:
            return 0.5

        # Count modules by language tier
        lang_speed = {
            "python": 0.3,
            "typescript": 0.5,
            "csharp": 0.7,
            "rust": 0.9,
            "c": 0.9,
            "c_simd": 1.0,
        }

        total_weight = 0.0
        weighted_speed = 0.0

        for mod_path, snap in self.modules.items():
            lang = self.language_assignments.get(mod_path, snap.language)
            speed = lang_speed.get(lang, 0.3)
            # Weight by how hot the module is
            heat_weight = self._heat_weight(snap.heat_level)
            weighted_speed += speed * heat_weight
            total_weight += heat_weight

        if total_weight == 0:
            return 0.5

        return min(1.0, weighted_speed / total_weight)

    def _heat_weight(self, heat_name: str) -> float:
        """Convert heat level name to weight multiplier."""
        weights = {
            "FROZEN": 0.0,
            "COOL": 0.1,
            "WARM": 0.3,
            "HOT": 0.6,
            "HEAT": 1.0,
        }
        return weights.get(heat_name, 0.0)

    def _modularity_score(self) -> float:
        """Score based on system modularity (0-1).

        More Python modules = higher modularity.
        """
        if not self.language_assignments:
            return 0.5

        lang_modularity = {
            "python": 1.0,
            "typescript": 0.8,
            "csharp": 0.7,
            "rust": 0.8,
            "c": 0.5,
            "c_simd": 0.3,
        }

        total = sum(lang_modularity.get(lang, 0.5)
                    for lang in self.language_assignments.values())
        return total / len(self.language_assignments)

    def _correctness_score(self) -> float:
        """Score based on optimization success rate (0-1).

        1.0 = all optimizations succeeded, 0.0 = all failed.
        If no optimizations have been attempted, return 1.0 (neutral).
        """
        if not self.optimization_history:
            return 1.0

        successes = sum(1 for r in self.optimization_history if r.success)
        return successes / len(self.optimization_history)

    # ── Diff ────────────────────────────────────────────────────────────

    def diff(self, other: Genome) -> GenomeDiff:
        """Compare two genomes, return what changed.

        Args:
            other: The genome to compare against.

        Returns:
            GenomeDiff describing all changes.
        """
        d = GenomeDiff()
        d.fitness_before = self.fitness_score
        d.fitness_after = other.fitness_score
        d.fitness_delta = other.fitness_score - self.fitness_score

        # Modules
        self_mods = set(self.modules.keys())
        other_mods = set(other.modules.keys())

        for path in other_mods - self_mods:
            d.modules_added.append(path)
        for path in self_mods - other_mods:
            d.modules_removed.append(path)
        for path in self_mods & other_mods:
            changes = self._diff_module_snap(self.modules[path], other.modules[path])
            if changes:
                d.modules_changed[path] = changes

        # Tiles
        self_tiles = set(self.tiles.keys())
        other_tiles = set(other.tiles.keys())

        for name in other_tiles - self_tiles:
            d.tiles_added.append(name)
        for name in self_tiles - other_tiles:
            d.tiles_removed.append(name)
        for name in self_tiles & other_tiles:
            changes = self._diff_tile_snap(self.tiles[name], other.tiles[name])
            if changes:
                d.tiles_changed[name] = changes

        # Language changes
        all_paths = set(self.language_assignments) | set(other.language_assignments)
        for path in all_paths:
            old_lang = self.language_assignments.get(path, "python")
            new_lang = other.language_assignments.get(path, "python")
            if old_lang != new_lang:
                d.language_changes[path] = (old_lang, new_lang)

        return d

    @staticmethod
    def _diff_module_snap(a: ModuleSnapshot, b: ModuleSnapshot) -> dict[str, Any]:
        """Diff two module snapshots."""
        changes: dict[str, Any] = {}
        if a.language != b.language:
            changes["language"] = (a.language, b.language)
        if a.version != b.version:
            changes["version"] = (a.version, b.version)
        if a.checksum != b.checksum:
            changes["checksum"] = (a.checksum, b.checksum)
        if a.heat_level != b.heat_level:
            changes["heat_level"] = (a.heat_level, b.heat_level)
        if a.call_count != b.call_count:
            changes["call_count"] = (a.call_count, b.call_count)
        return changes

    @staticmethod
    def _diff_tile_snap(a: TileSnapshot, b: TileSnapshot) -> dict[str, Any]:
        """Diff two tile snapshots."""
        changes: dict[str, Any] = {}
        if a.cost_estimate != b.cost_estimate:
            changes["cost_estimate"] = (a.cost_estimate, b.cost_estimate)
        if a.abstraction_level != b.abstraction_level:
            changes["abstraction_level"] = (a.abstraction_level, b.abstraction_level)
        if a.tags != b.tags:
            changes["tags"] = (a.tags, b.tags)
        return changes

    # ── Mutation ────────────────────────────────────────────────────────

    def mutate(self, strategy: MutationStrategy, target: str = "",
               **kwargs: Any) -> Genome:
        """Create a mutated copy — try a potential improvement.

        Possible mutations:
        1. Change a module's language (Python → C for a hot path)
        2. Replace a tile composition with an alternative
        3. Add a new tile discovered from hot patterns
        4. Merge two frequently-co-occurring tiles into a fused tile
        5. Split a complex tile into simpler components

        Args:
            strategy: The type of mutation to apply.
            target: The module path or tile name to mutate.
            **kwargs: Additional mutation parameters.

        Returns:
            A new Genome with the mutation applied.
        """
        import copy

        mutated = copy.deepcopy(self)
        mutated.generation = self.generation + 1
        mutated.timestamp = time.time()

        if strategy == MutationStrategy.RECOMPILE_LANGUAGE:
            new_lang = kwargs.get("new_language", "rust")
            if target in mutated.language_assignments:
                old_lang = mutated.language_assignments[target]
                mutated.language_assignments[target] = new_lang
                # Update module snapshot language too
                if target in mutated.modules:
                    mutated.modules[target].language = new_lang
                record = OptimizationRecord(
                    generation=mutated.generation,
                    mutation_type=strategy.value,
                    target=target,
                    description=f"Recompile {target} from {old_lang} to {new_lang}",
                    success=True,
                )
                mutated.optimization_history.append(record)

        elif strategy == MutationStrategy.ADD_TILE:
            tile_name = kwargs.get("tile_name", target)
            cost = kwargs.get("cost_estimate", 1.0)
            if tile_name and tile_name not in mutated.tiles:
                mutated.tiles[tile_name] = TileSnapshot(
                    name=tile_name,
                    tile_type=kwargs.get("tile_type", "compute"),
                    input_count=kwargs.get("input_count", 1),
                    output_count=kwargs.get("output_count", 1),
                    cost_estimate=cost,
                    abstraction_level=kwargs.get("abstraction_level", 5),
                    language_preference=kwargs.get("language_preference", "fir"),
                    tags=tuple(kwargs.get("tags", ())),
                )
                record = OptimizationRecord(
                    generation=mutated.generation,
                    mutation_type=strategy.value,
                    target=tile_name,
                    description=f"Add new tile: {tile_name}",
                    success=True,
                )
                mutated.optimization_history.append(record)

        elif strategy == MutationStrategy.REPLACE_TILE:
            new_cost = kwargs.get("new_cost", 0.5)
            if target in mutated.tiles:
                old_cost = mutated.tiles[target].cost_estimate
                mutated.tiles[target].cost_estimate = new_cost
                record = OptimizationRecord(
                    generation=mutated.generation,
                    mutation_type=strategy.value,
                    target=target,
                    description=f"Replace tile {target} (cost {old_cost} → {new_cost})",
                    success=True,
                )
                mutated.optimization_history.append(record)

        elif strategy == MutationStrategy.FUSE_PATTERN:
            pattern_name = kwargs.get("pattern_name", target)
            cost_savings = kwargs.get("cost_savings", 0.3)
            if pattern_name:
                record = OptimizationRecord(
                    generation=mutated.generation,
                    mutation_type=strategy.value,
                    target=target,
                    description=f"Fuse pattern into tile: {pattern_name}",
                    success=True,
                    speedup=1.0 + cost_savings,
                )
                mutated.optimization_history.append(record)

        elif strategy == MutationStrategy.MERGE_TILES:
            tile_a = kwargs.get("tile_a", "")
            tile_b = kwargs.get("tile_b", "")
            merged_name = kwargs.get("merged_name", target)
            if merged_name and merged_name not in mutated.tiles:
                cost_a = mutated.tiles.get(tile_a, TileSnapshot(
                    name="", tile_type="", input_count=0, output_count=0,
                    cost_estimate=1.0, abstraction_level=5, language_preference="fir",
                )).cost_estimate
                cost_b = mutated.tiles.get(tile_b, TileSnapshot(
                    name="", tile_type="", input_count=0, output_count=0,
                    cost_estimate=1.0, abstraction_level=5, language_preference="fir",
                )).cost_estimate
                # Merged tile should be cheaper than running both separately
                merged_cost = (cost_a + cost_b) * 0.7
                mutated.tiles[merged_name] = TileSnapshot(
                    name=merged_name,
                    tile_type="compute",
                    input_count=1,
                    output_count=1,
                    cost_estimate=merged_cost,
                    abstraction_level=5,
                    language_preference="fir",
                )
                record = OptimizationRecord(
                    generation=mutated.generation,
                    mutation_type=strategy.value,
                    target=merged_name,
                    description=f"Merge tiles {tile_a} + {tile_b} → {merged_name}",
                    success=True,
                    speedup=(cost_a + cost_b) / merged_cost if merged_cost > 0 else 1.0,
                )
                mutated.optimization_history.append(record)

        elif strategy == MutationStrategy.SPLIT_TILE:
            if target in mutated.tiles:
                old_cost = mutated.tiles[target].cost_estimate
                mutated.tiles[target].cost_estimate = old_cost * 0.9
                record = OptimizationRecord(
                    generation=mutated.generation,
                    mutation_type=strategy.value,
                    target=target,
                    description=f"Split tile {target} into components",
                    success=True,
                )
                mutated.optimization_history.append(record)

        elif strategy == MutationStrategy.INLINE_OPTIMIZATION:
            speedup = kwargs.get("speedup", 1.2)
            record = OptimizationRecord(
                generation=mutated.generation,
                mutation_type=strategy.value,
                target=target,
                description=f"Inline optimization on {target}",
                success=True,
                speedup=speedup,
            )
            mutated.optimization_history.append(record)

        mutated.checksum = mutated._compute_checksum()
        mutated.evaluate_fitness()
        return mutated

    # ── Serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict."""
        return {
            "modules": {
                path: {
                    "path": snap.path,
                    "granularity": snap.granularity,
                    "language": snap.language,
                    "version": snap.version,
                    "checksum": snap.checksum,
                    "card_count": snap.card_count,
                    "child_count": snap.child_count,
                    "heat_level": snap.heat_level,
                    "call_count": snap.call_count,
                    "total_time_ns": snap.total_time_ns,
                }
                for path, snap in self.modules.items()
            },
            "tiles": {
                name: {
                    "name": snap.name,
                    "tile_type": snap.tile_type,
                    "input_count": snap.input_count,
                    "output_count": snap.output_count,
                    "cost_estimate": snap.cost_estimate,
                    "abstraction_level": snap.abstraction_level,
                    "language_preference": snap.language_preference,
                    "tags": list(snap.tags),
                    "param_count": snap.param_count,
                }
                for name, snap in self.tiles.items()
            },
            "language_assignments": dict(self.language_assignments),
            "profiler_snapshot": {
                "module_count": self.profiler_snapshot.module_count,
                "sample_count": self.profiler_snapshot.sample_count,
                "heatmap": dict(self.profiler_snapshot.heatmap),
                "ranking": self.profiler_snapshot.ranking,
                "total_time_ns": self.profiler_snapshot.total_time_ns,
            },
            "optimization_history": [
                {
                    "generation": r.generation,
                    "mutation_type": r.mutation_type,
                    "target": r.target,
                    "description": r.description,
                    "success": r.success,
                    "speedup": r.speedup,
                    "timestamp": r.timestamp,
                }
                for r in self.optimization_history
            ],
            "fitness_score": self.fitness_score,
            "timestamp": self.timestamp,
            "generation": self.generation,
            "checksum": self.checksum,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Genome:
        """Deserialize from dict."""
        genome = cls()

        for path, mod_data in data.get("modules", {}).items():
            genome.modules[path] = ModuleSnapshot(
                path=mod_data["path"],
                granularity=mod_data["granularity"],
                language=mod_data["language"],
                version=mod_data["version"],
                checksum=mod_data["checksum"],
                card_count=mod_data.get("card_count", 0),
                child_count=mod_data.get("child_count", 0),
                heat_level=mod_data.get("heat_level", "FROZEN"),
                call_count=mod_data.get("call_count", 0),
                total_time_ns=mod_data.get("total_time_ns", 0),
            )

        for name, tile_data in data.get("tiles", {}).items():
            genome.tiles[name] = TileSnapshot(
                name=tile_data["name"],
                tile_type=tile_data["tile_type"],
                input_count=tile_data["input_count"],
                output_count=tile_data["output_count"],
                cost_estimate=tile_data["cost_estimate"],
                abstraction_level=tile_data["abstraction_level"],
                language_preference=tile_data.get("language_preference", "fir"),
                tags=tuple(tile_data.get("tags", [])),
                param_count=tile_data.get("param_count", 0),
            )

        genome.language_assignments = data.get("language_assignments", {})

        ps = data.get("profiler_snapshot", {})
        genome.profiler_snapshot = ProfilerSnapshot(
            module_count=ps.get("module_count", 0),
            sample_count=ps.get("sample_count", 0),
            heatmap=ps.get("heatmap", {}),
            ranking=[(r[0], r[1]) for r in ps.get("ranking", [])],
            total_time_ns=ps.get("total_time_ns", 0),
        )

        for rec_data in data.get("optimization_history", []):
            genome.optimization_history.append(OptimizationRecord(
                generation=rec_data["generation"],
                mutation_type=rec_data["mutation_type"],
                target=rec_data["target"],
                description=rec_data["description"],
                success=rec_data["success"],
                speedup=rec_data.get("speedup", 1.0),
                timestamp=rec_data.get("timestamp", 0.0),
            ))

        genome.fitness_score = data.get("fitness_score", 0.0)
        genome.timestamp = data.get("timestamp", 0.0)
        genome.generation = data.get("generation", 0)
        genome.checksum = data.get("checksum", "")
        return genome

    # ── Internal ────────────────────────────────────────────────────────

    def _compute_checksum(self) -> str:
        """Compute SHA-256 checksum of genome state."""
        import json
        h = hashlib.sha256()
        # Serialize key fields for hashing
        key_data = {
            "modules": sorted(self.modules.keys()),
            "tiles": sorted(self.tiles.keys()),
            "languages": dict(sorted(self.language_assignments.items())),
            "generation": self.generation,
        }
        h.update(json.dumps(key_data, sort_keys=True).encode())
        return h.hexdigest()[:16]

    def __repr__(self) -> str:
        return (
            f"Genome(gen={self.generation}, "
            f"modules={len(self.modules)}, "
            f"tiles={len(self.tiles)}, "
            f"fitness={self.fitness_score:.3f}, "
            f"checksum={self.checksum!r})"
        )
