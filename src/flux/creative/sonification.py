"""Sonification — Code-to-Music Mapping.

Maps FLUX execution data to musical parameters:
- Opcodes → notes (IADD=C4, ISUB=D4, FADD=E4, TELL=rest+chord)
- Register values → velocities (0-127)
- Heat levels → dynamics (COOL=pp, WARM=mp, HOT=mf, HEAT=ff)
- Memory access patterns → rhythm (sequential=regular, random=syncopated)
- A2A messages → harmony (TELL=melody, ASK=question motif, BARRIER=percussion hit)
- Branch prediction → articulation (predicted=legato, mispredicted=staccato)
- Execution time → tempo (fast code = fast tempo)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from struct import pack
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass


# ── Music Event ─────────────────────────────────────────────────────────────

@dataclass
class MusicEvent:
    """A single musical event in a sequence."""
    time: float       # seconds from start
    note: int         # MIDI note number (0-127)
    velocity: int     # 0-127
    duration: float   # seconds
    channel: int      # MIDI channel (0-15)

    def __repr__(self) -> str:
        return (
            f"MusicEvent(t={self.time:.3f}, note={self.note}, "
            f"vel={self.velocity}, dur={self.duration:.3f}, ch={self.channel})"
        )


# ── Music Sequence ──────────────────────────────────────────────────────────

@dataclass
class MusicSequence:
    """A sequence of musical events."""
    events: list[MusicEvent] = field(default_factory=list)
    tempo: int = 120                          # BPM
    time_signature: tuple[int, int] = (4, 4)  # (numerator, denominator)

    def add_note(
        self,
        time: float,
        note: int,
        velocity: int = 100,
        duration: float = 0.25,
        channel: int = 0,
    ) -> None:
        """Add a note to the sequence."""
        self.events.append(MusicEvent(
            time=time, note=note, velocity=velocity,
            duration=duration, channel=channel,
        ))

    def to_note_list(self) -> list[tuple[float, int, int, int]]:
        """Returns [(time, note, velocity, duration)] tuples."""
        return [
            (e.time, e.note, e.velocity, e.duration)
            for e in sorted(self.events, key=lambda e: e.time)
        ]

    def transpose(self, semitones: int) -> MusicSequence:
        """Transpose the entire sequence by N semitones."""
        new_events = []
        for e in self.events:
            new_note = max(0, min(127, e.note + semitones))
            new_events.append(MusicEvent(
                time=e.time, note=new_note, velocity=e.velocity,
                duration=e.duration, channel=e.channel,
            ))
        return MusicSequence(
            events=new_events, tempo=self.tempo,
            time_signature=self.time_signature,
        )

    def reverse(self) -> MusicSequence:
        """Reverse the sequence (events play in reverse time order)."""
        if not self.events:
            return MusicSequence(
                events=[], tempo=self.tempo,
                time_signature=self.time_signature,
            )
        total = self.duration()
        new_events = []
        for e in sorted(self.events, key=lambda ev: ev.time, reverse=True):
            new_time = total - e.time - e.duration
            new_events.append(MusicEvent(
                time=max(0.0, new_time), note=e.note,
                velocity=e.velocity, duration=e.duration,
                channel=e.channel,
            ))
        return MusicSequence(
            events=new_events, tempo=self.tempo,
            time_signature=self.time_signature,
        )

    def duration(self) -> float:
        """Total duration in seconds."""
        if not self.events:
            return 0.0
        return max(e.time + e.duration for e in self.events)

    def to_midi(self) -> bytes:
        """Export as basic MIDI data (Format 0 single track).

        Produces a minimal but valid MIDI file with:
        - Header chunk (MThd)
        - Track chunk (MTrk) with tempo event and note on/off events
        """
        # MIDI ticks per beat (ppq)
        ppq = 480
        ticks_per_second = ppq * self.tempo // 60

        def to_ticks(seconds: float) -> int:
            return int(seconds * ticks_per_second)

        def write_varlen(value: int) -> bytes:
            """Encode a MIDI variable-length quantity."""
            if value < 0:
                value = 0
            result = bytearray()
            result.append(value & 0x7F)
            value >>= 7
            while value:
                result.append((value & 0x7F) | 0x80)
                value >>= 7
            result.reverse()
            return bytes(result)

        track_data = bytearray()

        # Tempo meta event: FF 51 03 tt tt tt
        microseconds_per_beat = 60_000_000 // self.tempo
        track_data += b'\x00'  # delta time 0
        track_data += b'\xFF\x51\x03'
        track_data += pack('>I', microseconds_per_beat)[1:]  # 3 bytes

        # Sort events by time
        sorted_events = sorted(self.events, key=lambda e: e.time)
        last_tick = 0

        for event in sorted_events:
            start_tick = to_ticks(event.time)
            end_tick = to_ticks(event.time + event.duration)

            # Note On
            delta = start_tick - last_tick
            track_data += write_varlen(delta)
            track_data += bytes([
                0x90 | (event.channel & 0x0F),
                event.note & 0x7F,
                event.velocity & 0x7F,
            ])
            last_tick = start_tick

            # Note Off
            delta_off = end_tick - last_tick
            track_data += write_varlen(delta_off)
            track_data += bytes([
                0x80 | (event.channel & 0x0F),
                event.note & 0x7F,
                0x00,
            ])
            last_tick = end_tick

        # End of track
        track_data += b'\x00\xFF\x2F\x00'

        # Build complete MIDI file
        header = b'MThd' + pack('>IHHH', 6, 0, 1, ppq)
        track = b'MTrk' + pack('>I', len(track_data)) + bytes(track_data)

        return header + track

    def __len__(self) -> int:
        return len(self.events)

    def __repr__(self) -> str:
        return (
            f"MusicSequence(events={len(self.events)}, tempo={self.tempo}, "
            f"sig={self.time_signature}, duration={self.duration():.2f}s)"
        )


# ── Execution Event (for trace mapping) ─────────────────────────────────────

@dataclass
class ExecutionEvent:
    """An event from a FLUX execution trace."""
    opcode: int
    time: float = 0.0
    register_value: int = 0
    module_path: str = ""
    language: str = ""
    heat_level: str = "COOL"
    is_branch_predicted: bool = True
    memory_address: int = 0


# ── Sonifier ────────────────────────────────────────────────────────────────

class Sonifier:
    """Maps FLUX execution data to musical parameters.

    Mappings:
    - Opcodes → notes (IADD=C4, ISUB=D4, FADD=E4, TELL=rest+chord)
    - Register values → velocities (0-127)
    - Heat levels → dynamics (COOL=pp, WARM=mp, HOT=mf, HEAT=ff)
    - Memory access patterns → rhythm (sequential=regular, random=syncopated)
    - A2A messages → harmony (TELL=melody, ASK=question motif, BARRIER=percussion hit)
    - Branch prediction → articulation (predicted=legato, mispredicted=staccato)
    - Execution time → tempo (fast code = fast tempo)
    """

    # Heat level → MIDI velocity
    HEAT_TO_VELOCITY: dict[str, int] = {
        "FROZEN": 20,
        "COOL": 40,
        "WARM": 70,
        "HOT": 100,
        "HEAT": 127,
    }

    # Heat level → musical dynamics name
    HEAT_TO_DYNAMICS: dict[str, str] = {
        "FROZEN": "pp",
        "COOL": "pp",
        "WARM": "mp",
        "HOT": "mf",
        "HEAT": "ff",
    }

    # Language → synthesizer timbre name
    LANGUAGE_TO_TIMBRE: dict[str, str] = {
        "python": "warm_pad",
        "c": "bright_lead",
        "rust": "metallic_percussion",
        "typescript": "soft_synth",
        "csharp": "electric_piano",
        "cpp": "bright_lead",
        "go": "clean_sine",
        "java": "organ",
        "swift": "bell",
        "kotlin": "soft_synth",
        "fir": "pure_square",
    }

    # A2A message type → harmony mapping
    A2A_TO_HARMONY: dict[int, str] = {
        0x60: "melody",      # TELL
        0x61: "question",    # ASK
        0x66: "chord",       # BROADCAST
        0x67: "unison",      # REDUCE
        0x78: "percussion",  # BARRIER
    }

    # Musical scale: C major scale across octaves (C3-C6)
    # 48 = C3, 60 = C4 (middle C), 72 = C5, 84 = C6
    _SCALE_NOTES = [
        0, 2, 4, 5, 7, 9, 11,  # C major scale intervals
    ]

    def __init__(self) -> None:
        # Build opcode → MIDI note mapping across 104 opcodes
        self.OPCODE_TO_NOTE: dict[int, int] = {}
        self._build_opcode_map()

    def _build_opcode_map(self) -> None:
        """Map all 104 opcodes (0x00-0xA7) to notes across the scale.

        Uses opcode value to select scale degree and octave,
        creating a musically sensible mapping.
        """
        for opcode_val in range(0x00, 0xA8):  # 0 to 167 = 168 values > 104 opcodes
            if opcode_val > 0x84:  # Last opcode is EMERGENCY_STOP=0x7B, HALT=0x80, etc.
                # Handle system opcodes 0x80-0x84
                if opcode_val <= 0x84:
                    degree = opcode_val - 0x80
                    octave_offset = 4  # High register for system ops
                    note = 48 + octave_offset * 12 + degree
                    self.OPCODE_TO_NOTE[opcode_val] = max(0, min(127, note))
                continue
            # Map opcode to scale degree and octave
            degree = opcode_val % len(self._SCALE_NOTES)
            octave = (opcode_val // len(self._SCALE_NOTES)) % 5
            note = 48 + octave * 12 + self._SCALE_NOTES[degree]
            self.OPCODE_TO_NOTE[opcode_val] = max(0, min(127, note))

    def opcode_to_note(self, opcode: int) -> int:
        """Map a bytecode opcode to a MIDI note number.

        Returns middle C (60) for unknown opcodes.
        """
        return self.OPCODE_TO_NOTE.get(opcode, 60)

    def register_values_to_chord(self, values: list[int]) -> list[int]:
        """Map register values to a chord (3-4 notes).

        Takes register values, normalizes them, and maps them to
        notes forming a musically pleasing chord.

        Args:
            values: List of register values (integers)

        Returns:
            List of 3-4 MIDI note numbers forming a chord
        """
        if not values:
            return [60]  # Single C

        # Normalize values to 0-1 range
        max_val = max(abs(v) for v in values) or 1
        normalized = [abs(v) / max_val for v in values]

        # Map to chord tones: root, third, fifth, (seventh)
        chord_intervals = [0, 4, 7, 11]
        root = 48 + int(normalized[0] * 24)  # C3-C5 range

        result = []
        for i, interval in enumerate(chord_intervals):
            if i < len(normalized):
                # Offset the interval slightly based on value for color
                offset = int((normalized[i] - 0.5) * 2)
                note = root + interval + offset
            else:
                note = root + interval
            result.append(max(0, min(127, note)))

        return result

    def execution_trace_to_sequence(
        self,
        trace: list[ExecutionEvent],
        base_tempo: int = 120,
    ) -> MusicSequence:
        """Convert an execution trace to a musical sequence.

        Each execution event maps to a note:
        - Opcode → pitch
        - Register value → velocity
        - Heat → velocity modifier
        - Branch prediction → duration (legato vs staccato)
        """
        seq = MusicSequence(tempo=base_tempo)
        current_time = 0.0
        beat_duration = 60.0 / base_tempo

        for event in trace:
            note = self.opcode_to_note(event.opcode)

            # Velocity from heat level
            base_velocity = self.HEAT_TO_VELOCITY.get(event.heat_level, 70)

            # Modify velocity slightly by register value
            reg_mod = (event.register_value % 21) - 10
            velocity = max(1, min(127, base_velocity + reg_mod))

            # Duration from branch prediction
            if event.is_branch_predicted:
                duration = beat_duration * 0.9   # legato
            else:
                duration = beat_duration * 0.25  # staccato

            # Channel from opcode category
            channel = (event.opcode >> 4) % 16

            seq.add_note(
                time=current_time,
                note=note,
                velocity=velocity,
                duration=duration,
                channel=channel,
            )

            # Advance time
            if event.is_branch_predicted:
                current_time += beat_duration
            else:
                current_time += beat_duration * 0.5  # Syncopated for mispredicted

        return seq

    def module_to_timbre(self, module_path: str, language: str) -> str:
        """Map module properties to a synthesizer timbre.

        Python → warm pad, C → bright lead, Rust → metallic percussion
        """
        # First try exact language match
        lang_lower = language.lower()
        if lang_lower in self.LANGUAGE_TO_TIMBRE:
            return self.LANGUAGE_TO_TIMBRE[lang_lower]

        # Fallback: infer from module path extension
        if module_path.endswith(".py"):
            return "warm_pad"
        if module_path.endswith((".c", ".h")):
            return "bright_lead"
        if module_path.endswith((".rs",)):
            return "metallic_percussion"
        if module_path.endswith((".ts", ".tsx")):
            return "soft_synth"
        if module_path.endswith((".cs",)):
            return "electric_piano"

        return "default_sine"

    def heatmap_to_dynamics(self, heatmap: dict[str, str]) -> dict[str, int]:
        """Map heat classification to musical dynamics (velocity values).

        Args:
            heatmap: Mapping from module_path to heat level name string
                     (e.g., {"audio.engine": "HOT"})

        Returns:
            Mapping from module_path to MIDI velocity (0-127)
        """
        result = {}
        for path, heat in heatmap.items():
            heat_upper = heat.upper()
            velocity = self.HEAT_TO_VELOCITY.get(heat_upper, 70)
            result[path] = velocity
        return result

    def get_dynamics_name(self, heat_level: str) -> str:
        """Get the musical dynamics marking for a heat level."""
        return self.HEAT_TO_DYNAMICS.get(heat_level.upper(), "mp")

    def a2a_to_harmony_type(self, opcode: int) -> str:
        """Get harmony type for an A2A opcode."""
        return self.A2A_TO_HARMONY.get(opcode, "melody")

    def __repr__(self) -> str:
        return (
            f"Sonifier(opcodes_mapped={len(self.OPCODE_TO_NOTE)}, "
            f"heat_levels={len(self.HEAT_TO_VELOCITY)})"
        )
