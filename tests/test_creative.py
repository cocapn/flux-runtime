"""Tests for FLUX Creative module — sonification, generative art, live coding, visualization."""

import pytest

from flux.creative.sonification import (
    Sonifier,
    MusicSequence,
    MusicEvent,
    ExecutionEvent,
)
from flux.creative.generative import (
    LSystemTile,
    CellularAutomatonTile,
    FractalTile,
    ReactionDiffusionTile,
)
from flux.creative.live import (
    LiveCodingSession,
    PerformanceState,
    ChangeRecord,
    VersionRecord,
    BeatResult,
    Recording,
)
from flux.creative.visualization import (
    TileGraphVisualizer,
    ExecutionVisualizer,
    HEAT_COLORS,
    HEAT_CHARS,
)
from flux.tiles.tile import Tile, TileType
from flux.tiles.graph import TileGraph
from flux.fir.types import TypeContext


# ══════════════════════════════════════════════════════════════════════════════
# Sonifier Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestSonifierOpcodeToNote:
    """Test Sonifier opcode-to-note mapping."""

    def test_create_sonifier(self):
        s = Sonifier()
        assert len(s.OPCODE_TO_NOTE) > 0

    def test_opcode_iadd_maps_to_note(self):
        s = Sonifier()
        note = s.opcode_to_note(0x08)  # IADD
        assert isinstance(note, int)
        assert 0 <= note <= 127

    def test_opcode_isub_maps_to_note(self):
        s = Sonifier()
        note = s.opcode_to_note(0x09)  # ISUB
        assert isinstance(note, int)
        assert 0 <= note <= 127

    def test_opcode_fadd_maps_to_note(self):
        s = Sonifier()
        note = s.opcode_to_note(0x40)  # FADD
        assert isinstance(note, int)
        assert 0 <= note <= 127

    def test_opcode_tell_maps_to_note(self):
        s = Sonifier()
        note = s.opcode_to_note(0x60)  # TELL
        assert isinstance(note, int)
        assert 0 <= note <= 127

    def test_unknown_opcode_returns_middle_c(self):
        s = Sonifier()
        note = s.opcode_to_note(9999)
        assert note == 60

    def test_different_opcodes_different_notes(self):
        s = Sonifier()
        notes = [s.opcode_to_note(i) for i in range(20)]
        # Not all notes should be the same
        assert len(set(notes)) > 1

    def test_all_mapped_notes_in_range(self):
        s = Sonifier()
        for opcode, note in s.OPCODE_TO_NOTE.items():
            assert 0 <= note <= 127, f"Opcode {opcode:#x} maps to invalid note {note}"


class TestSonifierRegisterChord:
    """Test Sonifier register-to-chord mapping."""

    def test_empty_values_returns_single_note(self):
        s = Sonifier()
        chord = s.register_values_to_chord([])
        assert chord == [60]

    def test_single_value_returns_chord(self):
        s = Sonifier()
        chord = s.register_values_to_chord([42])
        assert len(chord) == 4
        assert all(0 <= n <= 127 for n in chord)

    def test_multiple_values_returns_chord(self):
        s = Sonifier()
        chord = s.register_values_to_chord([10, 20, 30, 40])
        assert len(chord) == 4

    def test_chord_notes_in_valid_range(self):
        s = Sonifier()
        for val in [0, 127, -100, 999, 42]:
            chord = s.register_values_to_chord([val])
            assert all(0 <= n <= 127 for n in chord)

    def test_chord_has_root_third_fifth_seventh(self):
        s = Sonifier()
        # Use multiple values so higher intervals have no offset applied
        chord = s.register_values_to_chord([100, 100, 100, 100])
        # When all values are identical, normalized = [1.0, ...]
        # offset for normalized[0]=1.0: int((1.0-0.5)*2) = 1
        # chord[0] = root+0+1, chord[1] = root+4+1, chord[2] = root+7+1, chord[3] = root+11+1
        # All intervals shifted by same offset → relative intervals preserved
        assert chord[1] - chord[0] == 4  # major third
        assert chord[2] - chord[0] == 7  # perfect fifth
        assert chord[3] - chord[0] == 11  # major seventh


class TestSonifierHeatmap:
    """Test Sonifier heatmap-to-dynamics mapping."""

    def test_heatmap_to_dynamics_all_levels(self):
        s = Sonifier()
        heatmap = {
            "mod_a": "FROZEN",
            "mod_b": "COOL",
            "mod_c": "WARM",
            "mod_d": "HOT",
            "mod_e": "HEAT",
        }
        dynamics = s.heatmap_to_dynamics(heatmap)
        assert dynamics["mod_a"] == 20
        assert dynamics["mod_b"] == 40
        assert dynamics["mod_c"] == 70
        assert dynamics["mod_d"] == 100
        assert dynamics["mod_e"] == 127

    def test_heatmap_unknown_level_defaults(self):
        s = Sonifier()
        dynamics = s.heatmap_to_dynamics({"mod_x": "UNKNOWN"})
        assert dynamics["mod_x"] == 70

    def test_heatmap_empty(self):
        s = Sonifier()
        dynamics = s.heatmap_to_dynamics({})
        assert dynamics == {}

    def test_get_dynamics_name(self):
        s = Sonifier()
        assert s.get_dynamics_name("COOL") == "pp"
        assert s.get_dynamics_name("WARM") == "mp"
        assert s.get_dynamics_name("HOT") == "mf"
        assert s.get_dynamics_name("HEAT") == "ff"

    def test_a2a_harmony_types(self):
        s = Sonifier()
        assert s.a2a_to_harmony_type(0x60) == "melody"    # TELL
        assert s.a2a_to_harmony_type(0x61) == "question"  # ASK
        assert s.a2a_to_harmony_type(0x78) == "percussion" # BARRIER


class TestSonifierModuleTimbre:
    """Test module-to-timbre mapping."""

    def test_python_gets_warm_pad(self):
        s = Sonifier()
        assert s.module_to_timbre("my_module", "python") == "warm_pad"

    def test_c_gets_bright_lead(self):
        s = Sonifier()
        assert s.module_to_timbre("main.c", "c") == "bright_lead"

    def test_rust_gets_metallic(self):
        s = Sonifier()
        assert s.module_to_timbre("engine.rs", "rust") == "metallic_percussion"

    def test_unknown_language_infers_from_path(self):
        s = Sonifier()
        assert s.module_to_timbre("script.py", "unknown") == "warm_pad"

    def test_unknown_everything_gets_default(self):
        s = Sonifier()
        assert s.module_to_timbre("file.xyz", "haskell") == "default_sine"


class TestSonifierExecutionTrace:
    """Test execution trace to music sequence conversion."""

    def test_empty_trace(self):
        s = Sonifier()
        seq = s.execution_trace_to_sequence([])
        assert len(seq) == 0
        assert seq.duration() == 0.0

    def test_single_event(self):
        s = Sonifier()
        trace = [ExecutionEvent(opcode=0x08, time=0.0)]
        seq = s.execution_trace_to_sequence(trace)
        assert len(seq) == 1
        assert seq.events[0].note == s.opcode_to_note(0x08)

    def test_multiple_events(self):
        s = Sonifier()
        trace = [
            ExecutionEvent(opcode=0x08, time=0.0),
            ExecutionEvent(opcode=0x09, time=0.5),
            ExecutionEvent(opcode=0x40, time=1.0),
        ]
        seq = s.execution_trace_to_sequence(trace)
        assert len(seq) == 3

    def test_heat_affects_velocity(self):
        s = Sonifier()
        trace_cool = [ExecutionEvent(opcode=0x08, heat_level="COOL")]
        trace_heat = [ExecutionEvent(opcode=0x08, heat_level="HEAT")]
        seq_cool = s.execution_trace_to_sequence(trace_cool)
        seq_heat = s.execution_trace_to_sequence(trace_heat)
        assert seq_heat.events[0].velocity > seq_cool.events[0].velocity

    def test_branch_prediction_affects_duration(self):
        s = Sonifier()
        trace_pred = [ExecutionEvent(opcode=0x08, is_branch_predicted=True)]
        trace_mispred = [ExecutionEvent(opcode=0x08, is_branch_predicted=False)]
        seq_pred = s.execution_trace_to_sequence(trace_pred)
        seq_mispred = s.execution_trace_to_sequence(trace_mispred)
        # Predicted (legato) should have longer duration
        assert seq_pred.events[0].duration > seq_mispred.events[0].duration


# ══════════════════════════════════════════════════════════════════════════════
# MusicSequence Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestMusicSequence:
    """Test MusicSequence creation and manipulation."""

    def test_create_empty(self):
        seq = MusicSequence()
        assert len(seq) == 0
        assert seq.duration() == 0.0

    def test_add_note(self):
        seq = MusicSequence()
        seq.add_note(0.0, 60, 100, 0.5, 0)
        assert len(seq) == 1
        assert seq.duration() == 0.5

    def test_add_multiple_notes(self):
        seq = MusicSequence()
        seq.add_note(0.0, 60, 100, 0.25)
        seq.add_note(0.25, 64, 100, 0.25)
        seq.add_note(0.5, 67, 100, 0.25)
        assert len(seq) == 3
        assert seq.duration() == 0.75

    def test_to_note_list(self):
        seq = MusicSequence()
        seq.add_note(0.0, 60, 100, 0.5, 0)
        seq.add_note(0.5, 64, 80, 0.25, 1)
        notes = seq.to_note_list()
        assert len(notes) == 2
        assert notes[0] == (0.0, 60, 100, 0.5)
        assert notes[1] == (0.5, 64, 80, 0.25)

    def test_transpose_up(self):
        seq = MusicSequence()
        seq.add_note(0.0, 60, 100, 0.5)
        transposed = seq.transpose(12)
        assert transposed.events[0].note == 72
        assert len(transposed) == 1

    def test_transpose_down(self):
        seq = MusicSequence()
        seq.add_note(0.0, 60, 100, 0.5)
        transposed = seq.transpose(-5)
        assert transposed.events[0].note == 55

    def test_transpose_does_not_modify_original(self):
        seq = MusicSequence()
        seq.add_note(0.0, 60, 100, 0.5)
        seq.transpose(12)
        assert seq.events[0].note == 60

    def test_transpose_clamps_range(self):
        seq = MusicSequence()
        seq.add_note(0.0, 120, 100, 0.5)
        transposed = seq.transpose(20)
        assert transposed.events[0].note == 127  # Clamped

    def test_reverse(self):
        seq = MusicSequence()
        seq.add_note(0.0, 60, 100, 0.5)
        seq.add_note(0.5, 64, 100, 0.5)
        reversed_seq = seq.reverse()
        assert len(reversed_seq) == 2
        assert reversed_seq.events[0].note == 64
        assert reversed_seq.events[1].note == 60

    def test_reverse_empty(self):
        seq = MusicSequence()
        reversed_seq = seq.reverse()
        assert len(reversed_seq) == 0

    def test_reverse_preserves_tempo(self):
        seq = MusicSequence(tempo=140)
        seq.add_note(0.0, 60, 100, 0.5)
        reversed_seq = seq.reverse()
        assert reversed_seq.tempo == 140

    def test_to_midi_produces_bytes(self):
        seq = MusicSequence()
        seq.add_note(0.0, 60, 100, 0.5)
        midi_data = seq.to_midi()
        assert isinstance(midi_data, bytes)
        assert midi_data[:4] == b'MThd'  # MIDI header magic

    def test_to_midi_empty_sequence(self):
        seq = MusicSequence()
        midi_data = seq.to_midi()
        assert isinstance(midi_data, bytes)
        assert midi_data[:4] == b'MThd'

    def test_repr(self):
        seq = MusicSequence(tempo=120)
        seq.add_note(0.0, 60, 100, 0.25)
        r = repr(seq)
        assert "120" in r
        assert "1" in r  # 1 event

    def test_time_signature(self):
        seq = MusicSequence(time_signature=(3, 4))
        assert seq.time_signature == (3, 4)


class TestMusicEvent:
    """Test MusicEvent dataclass."""

    def test_create_event(self):
        e = MusicEvent(time=0.0, note=60, velocity=100, duration=0.5, channel=0)
        assert e.time == 0.0
        assert e.note == 60
        assert e.velocity == 100
        assert e.duration == 0.5
        assert e.channel == 0

    def test_event_repr(self):
        e = MusicEvent(time=1.5, note=72, velocity=127, duration=0.25, channel=5)
        r = repr(e)
        assert "72" in r
        assert "127" in r


# ══════════════════════════════════════════════════════════════════════════════
# L-System Tile Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestLSystemTile:
    """Test LSystemTile expansion and rules."""

    def test_create_lsystem(self):
        ls = LSystemTile()
        assert ls.axiom == "F"
        assert ls.iterations == 3
        assert ls.tile_type == TileType.COMPUTE

    def test_custom_rules(self):
        ls = LSystemTile(rules={"A": "AB", "B": "A"})
        assert ls.rules == {"A": "AB", "B": "A"}

    def test_expand_single_iteration(self):
        ls = LSystemTile(axiom="F", rules={"F": "FF"}, iterations=1)
        result = ls.expand()
        assert result == "FF"

    def test_expand_two_iterations(self):
        ls = LSystemTile(axiom="F", rules={"F": "F+F-F"}, iterations=2)
        result = ls.expand()
        assert result == "F+F-F+F+F-F-F+F-F"

    def test_expand_preserves_non_rule_chars(self):
        ls = LSystemTile(axiom="F+G", rules={"F": "FF"}, iterations=1)
        result = ls.expand()
        assert result == "FF+G"

    def test_expand_zero_iterations(self):
        ls = LSystemTile(axiom="F+F", iterations=0)
        result = ls.expand()
        assert result == "F+F"

    def test_koch_curve_expansion(self):
        ls = LSystemTile(
            axiom="F",
            rules={"F": "F+F-F-F+F"},
            iterations=2,
        )
        result = ls.expand()
        assert len(result) > 10

    def test_has_generative_tag(self):
        ls = LSystemTile()
        assert "generative" in ls.tags
        assert "lsystem" in ls.tags


# ══════════════════════════════════════════════════════════════════════════════
# Cellular Automaton Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestCellularAutomatonTile:
    """Test CellularAutomatonTile step function."""

    def test_create(self):
        ca = CellularAutomatonTile(rule=110, width=16, generations=5)
        assert ca.rule == 110
        assert ca.width == 16
        assert ca.generations == 5

    def test_step_rule_110(self):
        ca = CellularAutomatonTile(rule=110, width=8)
        state = [0, 0, 0, 1, 0, 0, 0, 0]
        next_state = ca.step(state)
        assert len(next_state) == 8
        assert all(v in (0, 1) for v in next_state)

    def test_step_all_zeros(self):
        ca = CellularAutomatonTile(rule=110, width=8)
        state = [0] * 8
        next_state = ca.step(state)
        assert next_state == [0] * 8

    def test_step_all_ones(self):
        ca = CellularAutomatonTile(rule=110, width=8)
        state = [1] * 8
        next_state = ca.step(state)
        assert len(next_state) == 8

    def test_rule_30(self):
        ca = CellularAutomatonTile(rule=30, width=8)
        state = [0, 0, 0, 1, 0, 0, 0, 0]
        next_state = ca.step(state)
        assert len(next_state) == 8

    def test_run_generations(self):
        ca = CellularAutomatonTile(rule=110, width=8, generations=3)
        history = ca.run()
        assert len(history) == 4  # initial + 3 generations

    def test_run_custom_initial_state(self):
        ca = CellularAutomatonTile(rule=110, width=4, generations=2)
        history = ca.run(initial_state=[1, 0, 1, 0])
        assert len(history) == 3
        assert history[0] == [1, 0, 1, 0]

    def test_named_rules(self):
        assert CellularAutomatonTile.NAMED_RULES["rule110"] == 110
        assert CellularAutomatonTile.NAMED_RULES["rule30"] == 30
        assert CellularAutomatonTile.NAMED_RULES["rule90"] == 90
        assert CellularAutomatonTile.NAMED_RULES["rule184"] == 184

    def test_game_of_life_step(self):
        ca = CellularAutomatonTile(width=8, generations=1)
        # Blinker oscillator
        state = [
            [0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0],
        ]
        next_state = ca.game_of_life_step(state)
        assert len(next_state) == len(state)
        assert len(next_state[0]) == len(state[0])

    def test_game_of_life_empty(self):
        ca = CellularAutomatonTile()
        result = ca.game_of_life_step([])
        assert result == []

    def test_has_generative_tag(self):
        ca = CellularAutomatonTile()
        assert "generative" in ca.tags
        assert "automaton" in ca.tags


# ══════════════════════════════════════════════════════════════════════════════
# Fractal Tile Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestFractalTile:
    """Test FractalTile computation."""

    def test_create_mandelbrot(self):
        ft = FractalTile(fractal_type="mandelbrot", iterations=100)
        assert ft.fractal_type == "mandelbrot"
        assert ft.iterations == 100

    def test_create_julia(self):
        ft = FractalTile(fractal_type="julia")
        assert ft.fractal_type == "julia"

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError):
            FractalTile(fractal_type="invalid")

    def test_mandelbrot_in_set(self):
        ft = FractalTile(iterations=100)
        result = ft.mandelbrot(0.0, 0.0)  # Origin is in the Mandelbrot set
        assert result == 100

    def test_mandelbrot_outside_set(self):
        ft = FractalTile(iterations=100)
        result = ft.mandelbrot(2.0, 2.0)  # Far outside
        assert result < 100

    def test_mandelbrot_custom_max_iter(self):
        ft = FractalTile(iterations=50)
        result = ft.mandelbrot(0.0, 0.0, max_iter=200)
        assert result == 200

    def test_julia_computation(self):
        ft = FractalTile(iterations=100)
        result = ft.julia(0.0, 0.0)
        assert isinstance(result, int)
        assert 0 <= result <= 100

    def test_sierpinski_depth_zero(self):
        ft = FractalTile()
        result = ft.sierpinski_depth(0, 0, 1.0, 0)
        assert len(result) == 1
        assert result[0] == (0, 0, 1.0)

    def test_sierpinski_depth_one(self):
        ft = FractalTile()
        result = ft.sierpinski_depth(0, 0, 1.0, 1)
        assert len(result) == 3

    def test_sierpinski_depth_two(self):
        ft = FractalTile()
        result = ft.sierpinski_depth(0, 0, 1.0, 2)
        assert len(result) == 9

    def test_koch_depth_zero(self):
        ft = FractalTile()
        points = ft.koch_points(0, 0, 1, 0, 0)
        assert len(points) == 2

    def test_koch_depth_one(self):
        ft = FractalTile()
        points = ft.koch_points(0, 0, 3, 0, 1)
        assert len(points) > 2

    def test_compute_point_mandelbrot(self):
        ft = FractalTile(fractal_type="mandelbrot")
        result = ft.compute_point(0.0, 0.0)
        assert result == ft.mandelbrot(0.0, 0.0)

    def test_supported_types(self):
        assert "mandelbrot" in FractalTile.SUPPORTED_TYPES
        assert "julia" in FractalTile.SUPPORTED_TYPES
        assert "sierpinski" in FractalTile.SUPPORTED_TYPES
        assert "koch" in FractalTile.SUPPORTED_TYPES


# ══════════════════════════════════════════════════════════════════════════════
# Reaction-Diffusion Tile Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestReactionDiffusionTile:
    """Test ReactionDiffusionTile."""

    def test_create(self):
        rd = ReactionDiffusionTile(grid_size=8, iterations=5)
        assert rd.grid_size == 8
        assert rd.iterations == 5
        assert rd.feed_rate == 0.035

    def test_initialize_grid(self):
        rd = ReactionDiffusionTile(grid_size=8)
        U, V = rd.initialize_grid()
        assert len(U) == 8
        assert len(V) == 8
        assert all(len(row) == 8 for row in U)

    def test_step_preserves_size(self):
        rd = ReactionDiffusionTile(grid_size=8)
        U, V = rd.initialize_grid()
        U2, V2 = rd.step(U, V)
        assert len(U2) == 8
        assert len(V2) == 8

    def test_step_clamps_values(self):
        rd = ReactionDiffusionTile(grid_size=8)
        U, V = rd.initialize_grid()
        U2, V2 = rd.step(U, V)
        for row in U2:
            for val in row:
                assert 0.0 <= val <= 1.0
        for row in V2:
            for val in row:
                assert 0.0 <= val <= 1.0

    def test_empty_grid_step(self):
        rd = ReactionDiffusionTile(grid_size=0)
        U, V = [], []
        U2, V2 = rd.step(U, V)
        assert U2 == []
        assert V2 == []

    def test_run(self):
        rd = ReactionDiffusionTile(grid_size=8, iterations=3)
        U, V = rd.run()
        assert len(U) == 8
        assert len(V) == 8

    def test_presets(self):
        assert "spots" in ReactionDiffusionTile.PRESETS
        assert "stripes" in ReactionDiffusionTile.PRESETS
        assert "spirals" in ReactionDiffusionTile.PRESETS

    def test_run_with_preset(self):
        rd = ReactionDiffusionTile(grid_size=8, iterations=2)
        U, V = rd.run(preset="stripes")
        assert rd.feed_rate == ReactionDiffusionTile.PRESETS["stripes"]["feed_rate"]

    def test_grid_stats(self):
        rd = ReactionDiffusionTile(grid_size=4)
        V = [
            [0.0, 0.1, 0.2, 0.0],
            [0.0, 0.5, 0.3, 0.0],
            [0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0],
        ]
        stats = rd.grid_stats(V)
        assert "min" in stats
        assert "max" in stats
        assert "mean" in stats
        assert "active_cells" in stats
        assert stats["max"] == 0.5
        assert stats["active_cells"] == 3

    def test_grid_stats_empty(self):
        rd = ReactionDiffusionTile()
        stats = rd.grid_stats([])
        assert stats["min"] == 0.0
        assert stats["active_cells"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# Live Coding Session Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestLiveCodingSession:
    """Test LiveCodingSession beat clock and management."""

    def _make_tile(self, name: str = "test_tile") -> Tile:
        return Tile(
            name=name,
            tile_type=TileType.COMPUTE,
            tags={"generative"},
        )

    def test_create_session(self):
        session = LiveCodingSession()
        assert session.bpm == 120
        assert session.beat_clock == 0
        assert session.active_tile_count == 0

    def test_set_tempo(self):
        session = LiveCodingSession()
        session.set_tempo(160)
        assert session.bpm == 160

    def test_set_tempo_clamps(self):
        session = LiveCodingSession()
        session.set_tempo(10)
        assert session.bpm == 20
        session.set_tempo(500)
        assert session.bpm == 300

    def test_on_beat(self):
        session = LiveCodingSession()
        result = session.on_beat()
        assert result.beat_number == 1
        assert result.active_count == 0

    def test_on_beat_advances_clock(self):
        session = LiveCodingSession()
        session.on_beat()
        session.on_beat()
        session.on_beat()
        assert session.beat_clock == 3

    def test_beat_duration(self):
        session = LiveCodingSession()
        session.set_tempo(120)
        assert abs(session.beat_duration - 0.5) < 0.01

    def test_beat_duration_at_60bpm(self):
        session = LiveCodingSession()
        session.set_tempo(60)
        assert abs(session.beat_duration - 1.0) < 0.01


class TestLiveSessionTileManagement:
    """Test live session tile injection/removal."""

    def _make_tile(self, name: str = "test") -> Tile:
        return Tile(name=name, tile_type=TileType.COMPUTE, tags={"generative"})

    def test_inject_tile(self):
        session = LiveCodingSession()
        tile = self._make_tile("synth")
        session.inject_tile("synth", tile)
        assert session.active_tile_count == 1

    def test_inject_tile_with_params(self):
        session = LiveCodingSession()
        tile = self._make_tile("filter")
        session.inject_tile("filter", tile, {"cutoff": 1000})
        assert session.active_tile_count == 1

    def test_remove_tile(self):
        session = LiveCodingSession()
        tile = self._make_tile("pad")
        session.inject_tile("pad", tile)
        session.remove_tile("pad")
        assert session.active_tile_count == 0

    def test_remove_nonexistent_raises(self):
        session = LiveCodingSession()
        with pytest.raises(KeyError):
            session.remove_tile("nonexistent")

    def test_modify_tile(self):
        session = LiveCodingSession()
        tile = self._make_tile("osc")
        session.inject_tile("osc", tile, {"freq": 440})
        session.modify_tile("osc", {"freq": 880})
        assert session.active_tile_count == 1

    def test_modify_nonexistent_raises(self):
        session = LiveCodingSession()
        with pytest.raises(KeyError):
            session.modify_tile("nonexistent", {"x": 1})

    def test_inject_replaces_existing(self):
        session = LiveCodingSession()
        tile1 = self._make_tile("x")
        tile2 = self._make_tile("x")
        session.inject_tile("x", tile1)
        session.inject_tile("x", tile2)
        assert session.active_tile_count == 1

    def test_on_beat_with_active_tiles(self):
        session = LiveCodingSession()
        tile = self._make_tile("gen")
        session.inject_tile("gen", tile)
        result = session.on_beat()
        assert result.active_count == 1
        assert result.notes_generated == 1


class TestLiveSessionUndoRedo:
    """Test live session undo/redo."""

    def _make_tile(self, name: str = "test") -> Tile:
        return Tile(name=name, tile_type=TileType.COMPUTE, tags={"generative"})

    def test_undo_inject(self):
        session = LiveCodingSession()
        tile = self._make_tile("synth")
        session.inject_tile("synth", tile)
        assert session.active_tile_count == 1
        session.undo()
        assert session.active_tile_count == 0

    def test_undo_remove(self):
        session = LiveCodingSession()
        tile = self._make_tile("pad")
        session.inject_tile("pad", tile)
        session.remove_tile("pad")
        assert session.active_tile_count == 0
        session.undo()
        assert session.active_tile_count == 1

    def test_undo_modify(self):
        session = LiveCodingSession()
        tile = self._make_tile("osc")
        session.inject_tile("osc", tile, {"freq": 440})
        session.modify_tile("osc", {"freq": 880})
        session.undo()
        # After undo, the tile should still exist but with old params
        assert session.active_tile_count == 1

    def test_redo(self):
        session = LiveCodingSession()
        tile = self._make_tile("x")
        session.inject_tile("x", tile)
        session.undo()
        assert session.active_tile_count == 0
        session.redo()
        assert session.active_tile_count == 1

    def test_undo_empty_stack(self):
        session = LiveCodingSession()
        result = session.undo()
        assert result is None

    def test_redo_empty_stack(self):
        session = LiveCodingSession()
        result = session.redo()
        assert result is None

    def test_new_action_clears_redo(self):
        session = LiveCodingSession()
        tile = self._make_tile("a")
        session.inject_tile("a", tile)
        session.undo()
        assert session.redo_depth == 1
        # New action clears redo
        tile2 = self._make_tile("b")
        session.inject_tile("b", tile2)
        assert session.redo_depth == 0

    def test_undo_depth(self):
        session = LiveCodingSession()
        for i in range(5):
            tile = self._make_tile(f"t{i}")
            session.inject_tile(f"t{i}", tile)
        assert session.undo_depth == 5


class TestLiveSessionExport:
    """Test live session export and performance state."""

    def _make_tile(self, name: str = "test") -> Tile:
        return Tile(name=name, tile_type=TileType.COMPUTE, tags={"generative"})

    def test_export_recording(self):
        session = LiveCodingSession()
        tile = self._make_tile("synth")
        session.inject_tile("synth", tile)
        session.on_beat()
        session.on_beat()
        recording = session.export_recording()
        assert recording.bpm == 120
        assert recording.total_beats == 2
        assert recording.duration >= 0

    def test_performance_state(self):
        session = LiveCodingSession()
        session.set_tempo(140)
        tile = self._make_tile("drum")
        session.inject_tile("drum", tile)
        session.on_beat()
        state = session.get_performance_state()
        assert state.current_beat == 1
        assert state.bpm == 140
        assert "drum" in state.active_tiles

    def test_set_heatmap(self):
        session = LiveCodingSession()
        session.set_heatmap({"mod_a": "HOT", "mod_b": "COOL"})
        state = session.get_performance_state()
        assert state.heatmap["mod_a"] == "HOT"

    def test_version_auto_save(self):
        session = LiveCodingSession()
        tile = self._make_tile("x")
        session.inject_tile("x", tile)
        # Process 16 beats to trigger auto-save
        for _ in range(16):
            session.on_beat()
        assert session.version_count >= 1

    def test_recording_changes_per_beat(self):
        session = LiveCodingSession()
        recording = session.export_recording()
        assert recording.changes_per_beat == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# Supporting Type Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestSupportingTypes:
    """Test ChangeRecord, VersionRecord, BeatResult, Recording, PerformanceState."""

    def test_change_record(self):
        cr = ChangeRecord(
            timestamp=1000.0, action="inject",
            tile_name="synth", params_before={}, params_after={"freq": 440},
        )
        assert cr.action == "inject"
        assert cr.tile_name == "synth"

    def test_version_record(self):
        vr = VersionRecord(timestamp=1000.0, beat=4, active_tiles={})
        assert vr.beat == 4

    def test_beat_result(self):
        br = BeatResult(beat_number=1, timestamp=1000.0, active_count=3)
        assert br.beat_number == 1
        assert br.active_count == 3
        assert br.notes_generated == 0

    def test_recording_duration(self):
        rec = Recording(bpm=120, start_time=0.0, end_time=10.0, total_beats=20)
        assert rec.duration == 10.0
        assert rec.changes_per_beat == 0.0

    def test_performance_state(self):
        ps = PerformanceState(current_beat=5, bpm=130, total_changes=3)
        assert ps.current_beat == 5
        assert ps.bpm == 130


# ══════════════════════════════════════════════════════════════════════════════
# Visualization Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestTileGraphVisualizer:
    """Test TileGraphVisualizer ASCII output."""

    def test_empty_graph(self):
        tg = TileGraph()
        result = TileGraphVisualizer.to_ascii(tg)
        assert "empty" in result.lower()

    def test_single_tile_graph(self):
        tg = TileGraph()
        tile = Tile(name="adder", tile_type=TileType.COMPUTE)
        tg.add_tile("adder", tile)
        result = TileGraphVisualizer.to_ascii(tg)
        assert "adder" in result
        assert "COMPUTE" in result

    def test_graph_with_edges(self):
        tg = TileGraph()
        t1 = Tile(name="src", tile_type=TileType.MEMORY)
        t2 = Tile(name="sink", tile_type=TileType.EFFECT)
        tg.add_tile("src", t1)
        tg.add_tile("sink", t2)
        tg.connect("src", "out", "sink", "in")
        result = TileGraphVisualizer.to_ascii(tg)
        assert "src" in result
        assert "sink" in result
        assert "Connections" in result

    def test_colored_text_basic(self):
        tg = TileGraph()
        tile = Tile(name="hot_tile", tile_type=TileType.COMPUTE)
        tg.add_tile("hot_tile", tile)
        result = TileGraphVisualizer.to_colored_text(tg, {"hot_tile": "HOT"})
        assert "hot_tile" in result
        assert "HOT" in result

    def test_colored_text_legend(self):
        tg = TileGraph()
        tile = Tile(name="x", tile_type=TileType.COMPUTE)
        tg.add_tile("x", tile)
        result = TileGraphVisualizer.to_colored_text(tg, {"x": "COOL"})
        assert "Legend" in result

    def test_heatmap_bar_zero(self):
        bar = TileGraphVisualizer.heatmap_bar(0, 100, width=20)
        assert "[░░░░░░░░░░░░░░░░░░░░]" in bar
        assert "0%" in bar

    def test_heatmap_bar_full(self):
        bar = TileGraphVisualizer.heatmap_bar(100, 100, width=20)
        assert "[████████████████████]" in bar
        assert "100%" in bar

    def test_heatmap_bar_half(self):
        bar = TileGraphVisualizer.heatmap_bar(50, 100, width=20)
        assert "50%" in bar

    def test_heatmap_bar_clamps(self):
        bar = TileGraphVisualizer.heatmap_bar(200, 100, width=20)
        assert "100%" in bar

    def test_heatmap_bar_zero_max(self):
        bar = TileGraphVisualizer.heatmap_bar(50, 0, width=20)
        assert "0%" in bar

    def test_heatmap_bar_custom_width(self):
        bar = TileGraphVisualizer.heatmap_bar(50, 100, width=10)
        assert len(bar) > 0


class TestExecutionVisualizer:
    """Test ExecutionVisualizer trace output."""

    def test_empty_trace(self):
        result = ExecutionVisualizer.trace_to_ascii([])
        assert "empty" in result.lower()

    def test_single_event_trace(self):
        trace = [ExecutionEvent(opcode=0x08, time=0.001, register_value=42)]
        result = ExecutionVisualizer.trace_to_ascii(trace)
        assert "0x08" in result
        assert "42" in result

    def test_trace_shows_predictions(self):
        trace = [
            ExecutionEvent(opcode=0x08, is_branch_predicted=True),
            ExecutionEvent(opcode=0x09, is_branch_predicted=False),
        ]
        result = ExecutionVisualizer.trace_to_ascii(trace)
        assert "Total events: 2" in result

    def test_trace_shows_heat(self):
        trace = [ExecutionEvent(opcode=0x08, heat_level="HOT")]
        result = ExecutionVisualizer.trace_to_ascii(trace)
        assert "HOT" in result

    def test_flame_graph_empty(self):
        result = ExecutionVisualizer.trace_to_flame_graph([])
        assert "empty" in result.lower()

    def test_flame_graph_categories(self):
        trace = [
            ExecutionEvent(opcode=0x08),  # INT_ARITH
            ExecutionEvent(opcode=0x08),  # INT_ARITH
            ExecutionEvent(opcode=0x60),  # A2A
        ]
        result = ExecutionVisualizer.trace_to_flame_graph(trace)
        assert "INT_ARITH" in result
        assert "A2A" in result
        assert "Total: 3" in result

    def test_flame_graph_shows_percentages(self):
        trace = [ExecutionEvent(opcode=0x08)] * 10
        result = ExecutionVisualizer.trace_to_flame_graph(trace)
        assert "%" in result

    def test_heat_colors_defined(self):
        assert "HEAT" in HEAT_COLORS
        assert "HOT" in HEAT_COLORS
        assert "WARM" in HEAT_COLORS
        assert "COOL" in HEAT_COLORS
        assert "FROZEN" in HEAT_COLORS

    def test_heat_chars_defined(self):
        for level in ["HEAT", "HOT", "WARM", "COOL", "FROZEN"]:
            assert level in HEAT_CHARS
            assert len(HEAT_CHARS[level]) == 1


# ══════════════════════════════════════════════════════════════════════════════
# Integration Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestCreativeIntegration:
    """Integration tests connecting creative modules."""

    def test_sonifier_with_lsystem(self):
        """L-System generates data, sonifier converts to music."""
        ls = LSystemTile(axiom="F", rules={"F": "F+F-F"}, iterations=2)
        expanded = ls.expand()

        s = Sonifier()
        # Map character codes to "opcodes" for sonification
        trace = [
            ExecutionEvent(opcode=ord(ch) % 128, time=i * 0.1)
            for i, ch in enumerate(expanded)
        ]
        seq = s.execution_trace_to_sequence(trace)
        assert len(seq) > 0
        assert seq.duration() > 0

    def test_automaton_sonification_pipeline(self):
        """Cellular automaton → execution events → music."""
        ca = CellularAutomatonTile(rule=110, width=8, generations=5)
        history = ca.run()

        s = Sonifier()
        # Convert automaton state to musical sequence
        seq = MusicSequence()
        t = 0.0
        for gen in history:
            alive = sum(gen)
            if alive > 0:
                note = 48 + alive * 3  # Higher = more alive cells
                velocity = min(127, 40 + alive * 10)
                seq.add_note(t, note, velocity, 0.25)
            t += 0.25

        assert len(seq) > 0
        midi = seq.to_midi()
        assert midi[:4] == b'MThd'

    def test_fractal_midi_export(self):
        """Fractal computation → MIDI output."""
        ft = FractalTile(fractal_type="mandelbrot", iterations=50)
        seq = MusicSequence(tempo=100)
        t = 0.0
        for i in range(-5, 5):
            for j in range(-5, 5):
                x = i * 0.2
                y = j * 0.2
                iterations = ft.mandelbrot(x, y)
                note = max(0, min(127, 48 + iterations))
                seq.add_note(t, note, 80, 0.1)
                t += 0.1

        midi = seq.to_midi()
        assert len(midi) > 0
        assert midi[:4] == b'MThd'

    def test_live_session_with_creative_tiles(self):
        """Full live session with generative tiles."""
        session = LiveCodingSession()
        session.set_tempo(140)

        ls = LSystemTile(axiom="F", rules={"F": "FF"}, iterations=2)
        ca = CellularAutomatonTile(rule=110, width=8)
        ft = FractalTile(fractal_type="mandelbrot")

        session.inject_tile("lsystem", ls)
        session.inject_tile("automaton", ca)
        session.inject_tile("fractal", ft)

        assert session.active_tile_count == 3

        # Process several beats
        for _ in range(8):
            session.on_beat()

        state = session.get_performance_state()
        assert state.current_beat == 8
        assert state.bpm == 140

        # Export recording
        recording = session.export_recording()
        assert recording.total_beats == 8
        assert recording.bpm == 140

    def test_visualize_active_session(self):
        """Visualize a live session's tile graph."""
        session = LiveCodingSession()
        ls = LSystemTile()
        ca = CellularAutomatonTile()

        session.inject_tile("lsystem", ls)
        session.inject_tile("automaton", ca)

        # Create a tile graph matching the session
        tg = TileGraph()
        tg.add_tile("lsystem", ls)
        tg.add_tile("automaton", ca)
        tg.connect("lsystem", "output", "automaton", "input")

        ascii_out = TileGraphVisualizer.to_ascii(tg)
        assert "lsystem" in ascii_out
        assert "automaton" in ascii_out

        colored_out = TileGraphVisualizer.to_colored_text(
            tg, {"lsystem": "WARM", "automaton": "HOT"}
        )
        assert "WARM" in colored_out
        assert "HOT" in colored_out
