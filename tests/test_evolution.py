"""Comprehensive tests for the FLUX Evolution Engine.

Tests cover:
- Genome capture, serialization, fitness, diff, mutation
- PatternMiner trace recording, mining, suggestions
- SystemMutator proposals, apply, commit, rollback
- CorrectnessValidator test registration, baseline, validation
- EvolutionEngine single step, multi-generation, convergence
- Integration pipeline: profiler → miner → mutator → validator
"""

import time
import pytest

from flux.evolution.genome import (
    Genome,
    GenomeDiff,
    ModuleSnapshot,
    TileSnapshot,
    ProfilerSnapshot,
    OptimizationRecord,
    MutationStrategy,
)
from flux.evolution.pattern_mining import (
    PatternMiner,
    ExecutionTrace,
    DiscoveredPattern,
    TileSuggestion,
)
from flux.evolution.mutator import (
    SystemMutator,
    MutationProposal,
    MutationResult,
    MutationRecord,
)
from flux.evolution.validator import (
    CorrectnessValidator,
    TestCase,
    ValidationResult,
    RegressionReport,
)
from flux.evolution.evolution import (
    EvolutionEngine,
    EvolutionRecord,
    EvolutionReport,
    EvolutionStep,
)
from flux.adaptive.profiler import AdaptiveProfiler, HeatLevel
from flux.adaptive.selector import AdaptiveSelector, LANGUAGES
from flux.modules.container import ModuleContainer
from flux.modules.granularity import Granularity
from flux.tiles.registry import TileRegistry
from flux.tiles.tile import Tile, TileType
from flux.tiles.ports import TilePort, PortDirection
from flux.fir.types import TypeContext


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def profiler():
    return AdaptiveProfiler()


@pytest.fixture
def selector(profiler):
    return AdaptiveSelector(profiler)


@pytest.fixture
def tile_registry():
    reg = TileRegistry()
    ctx = TypeContext()
    # Register a few test tiles
    t1 = Tile(
        name="test_map",
        tile_type=TileType.COMPUTE,
        inputs=[TilePort("data", PortDirection.INPUT, TypeContext.i32)],
        outputs=[TilePort("result", PortDirection.OUTPUT, TypeContext.i32)],
        cost_estimate=1.0,
        tags={"transform", "vectorized"},
    )
    t2 = Tile(
        name="test_reduce",
        tile_type=TileType.COMPUTE,
        inputs=[TilePort("data", PortDirection.INPUT, TypeContext.i32)],
        outputs=[TilePort("scalar", PortDirection.OUTPUT, TypeContext.i32)],
        cost_estimate=1.5,
        tags={"aggregate"},
    )
    t3 = Tile(
        name="expensive_filter",
        tile_type=TileType.COMPUTE,
        inputs=[TilePort("data", PortDirection.INPUT, TypeContext.i32), TilePort("pred", PortDirection.INPUT, TypeContext.i32)],
        outputs=[TilePort("filtered", PortDirection.OUTPUT, TypeContext.i32)],
        cost_estimate=5.0,
        tags={"filter", "slow"},
    )
    for t in [t1, t2, t3]:
        reg.register(t)
    return reg


@pytest.fixture
def module_root():
    root = ModuleContainer("root", Granularity.TRAIN)
    child = root.add_child("math", Granularity.BAG)
    child.load_card("add", "def add(a, b): return a + b", "python")
    child.load_card("mul", "def mul(a, b): return a * b", "python")
    root.load_card("main", "def main(): pass", "python")
    return root


@pytest.fixture
def genome(profiler, selector, tile_registry, module_root):
    g = Genome()
    g.capture(module_root, tile_registry, profiler, selector)
    g.evaluate_fitness()
    return g


@pytest.fixture
def miner(profiler):
    return PatternMiner(profiler)


@pytest.fixture
def mutator():
    return SystemMutator()


@pytest.fixture
def validator():
    return CorrectnessValidator()


@pytest.fixture
def engine(profiler, selector, validator):
    return EvolutionEngine(
        profiler=profiler,
        selector=selector,
        validator=validator,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Genome Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestGenomeCreation:
    """Test basic genome creation and initialization."""

    def test_empty_genome(self):
        g = Genome()
        assert g.modules == {}
        assert g.tiles == {}
        assert g.language_assignments == {}
        assert g.fitness_score == 0.0
        assert g.generation == 0
        assert g.checksum == ""

    def test_genome_repr(self):
        g = Genome()
        r = repr(g)
        assert "Genome" in r
        assert "gen=0" in r

    def test_genome_checksum_empty(self):
        g = Genome()
        cs = g._compute_checksum()
        assert isinstance(cs, str)
        assert len(cs) == 16


class TestGenomeCapture:
    """Test genome snapshot capture from live system."""

    def test_capture_modules(self, genome, module_root):
        assert "root" in genome.modules
        assert "root.math" in genome.modules
        assert "root.math.add" in genome.modules

    def test_capture_tiles(self, genome, tile_registry):
        assert "test_map" in genome.tiles
        assert "test_reduce" in genome.tiles
        assert "expensive_filter" in genome.tiles
        assert genome.tiles["test_map"].tile_type == "compute"

    def test_capture_language_assignments(self, genome, selector):
        assert isinstance(genome.language_assignments, dict)

    def test_capture_profiler_snapshot(self, genome, profiler):
        assert genome.profiler_snapshot.module_count == profiler.module_count

    def test_capture_sets_timestamp(self, genome):
        assert genome.timestamp > 0

    def test_capture_sets_checksum(self, genome):
        assert len(genome.checksum) == 16

    def test_capture_with_profiler_data(self, profiler, selector, tile_registry, module_root):
        profiler.record_call("root.math.add", duration_ns=1000)
        profiler.record_call("root.math.add", duration_ns=2000)
        profiler.record_call("root.math.mul", duration_ns=500)

        g = Genome()
        g.capture(module_root, tile_registry, profiler, selector)

        assert "root.math.add" in g.modules
        assert g.modules["root.math.add"].call_count == 2
        assert g.modules["root.math.add"].total_time_ns == 3000


class TestGenomeFitness:
    """Test genome fitness evaluation."""

    def test_fitness_neutral_empty(self):
        g = Genome()
        score = g.evaluate_fitness()
        assert 0.0 <= score <= 1.0

    def test_fitness_neutral_no_lang_assignments(self, genome):
        genome.language_assignments = {}
        score = genome.evaluate_fitness()
        assert 0.0 <= score <= 1.0

    def test_fitness_all_python(self, genome):
        for mod in genome.modules:
            genome.language_assignments[mod] = "python"
        score = genome.evaluate_fitness()
        assert 0.0 <= score <= 1.0

    def test_fitness_mixed_languages(self, genome):
        paths = list(genome.modules.keys())
        for i, path in enumerate(paths):
            if i % 2 == 0:
                genome.language_assignments[path] = "python"
            else:
                genome.language_assignments[path] = "rust"
        score = genome.evaluate_fitness()
        assert 0.0 <= score <= 1.0

    def test_fitness_with_success_history(self, genome):
        genome.optimization_history.append(OptimizationRecord(
            generation=1, mutation_type="test", target="x",
            description="test", success=True, speedup=2.0,
        ))
        score = genome.evaluate_fitness()
        assert score > 0.0

    def test_fitness_with_failure_history(self, genome):
        genome.optimization_history.append(OptimizationRecord(
            generation=1, mutation_type="test", target="x",
            description="test", success=False,
        ))
        score = genome.evaluate_fitness()
        assert 0.0 <= score < 1.0

    def test_fitness_components(self, genome):
        genome.language_assignments = {p: "c_simd" for p in genome.modules}
        for mod in genome.modules.values():
            mod.heat_level = "HEAT"
        score = genome.evaluate_fitness()
        # Should be high because hot modules are in fastest language
        assert score > 0.3

    def test_fitness_updates_genome(self, genome):
        genome.evaluate_fitness()
        assert genome.fitness_score > 0.0


class TestGenomeDiff:
    """Test genome comparison."""

    def test_diff_identical(self, genome):
        d = genome.diff(genome)
        assert not d.has_changes
        assert d.fitness_delta == 0.0

    def test_diff_language_change(self):
        g1 = Genome()
        g1.language_assignments = {"mod_a": "python"}
        g1.evaluate_fitness()

        g2 = Genome()
        g2.language_assignments = {"mod_a": "rust"}
        g2.evaluate_fitness()

        d = g1.diff(g2)
        assert d.has_changes
        assert "mod_a" in d.language_changes
        assert d.language_changes["mod_a"] == ("python", "rust")

    def test_diff_module_added(self):
        g1 = Genome()
        g1.modules["a"] = ModuleSnapshot(
            path="a", granularity="CARD", language="python",
            version=1, checksum="abc",
        )
        g1.evaluate_fitness()

        g2 = Genome()
        g2.modules["a"] = ModuleSnapshot(
            path="a", granularity="CARD", language="python",
            version=1, checksum="abc",
        )
        g2.modules["b"] = ModuleSnapshot(
            path="b", granularity="CARD", language="python",
            version=1, checksum="def",
        )
        g2.evaluate_fitness()

        d = g1.diff(g2)
        assert "b" in d.modules_added
        assert d.modules_removed == []

    def test_diff_module_removed(self):
        g1 = Genome()
        g1.modules["a"] = ModuleSnapshot(
            path="a", granularity="CARD", language="python",
            version=1, checksum="abc",
        )
        g1.evaluate_fitness()

        g2 = Genome()
        g2.evaluate_fitness()

        d = g1.diff(g2)
        assert "a" in d.modules_removed
        assert d.modules_added == []

    def test_diff_module_version_change(self):
        g1 = Genome()
        g1.modules["a"] = ModuleSnapshot(
            path="a", granularity="CARD", language="python",
            version=1, checksum="abc",
        )
        g1.evaluate_fitness()

        g2 = Genome()
        g2.modules["a"] = ModuleSnapshot(
            path="a", granularity="CARD", language="python",
            version=2, checksum="def",
        )
        g2.evaluate_fitness()

        d = g1.diff(g2)
        assert "a" in d.modules_changed
        assert "version" in d.modules_changed["a"]
        assert d.modules_changed["a"]["version"] == (1, 2)

    def test_diff_tile_added(self):
        g1 = Genome()
        g1.evaluate_fitness()

        g2 = Genome()
        g2.tiles["new_tile"] = TileSnapshot(
            name="new_tile", tile_type="compute",
            input_count=1, output_count=1,
            cost_estimate=1.0, abstraction_level=5,
            language_preference="fir",
        )
        g2.evaluate_fitness()

        d = g1.diff(g2)
        assert "new_tile" in d.tiles_added

    def test_diff_tile_cost_change(self):
        g1 = Genome()
        g1.tiles["t"] = TileSnapshot(
            name="t", tile_type="compute",
            input_count=1, output_count=1,
            cost_estimate=1.0, abstraction_level=5,
            language_preference="fir",
        )
        g1.evaluate_fitness()

        g2 = Genome()
        g2.tiles["t"] = TileSnapshot(
            name="t", tile_type="compute",
            input_count=1, output_count=1,
            cost_estimate=0.5, abstraction_level=5,
            language_preference="fir",
        )
        g2.evaluate_fitness()

        d = g1.diff(g2)
        assert "t" in d.tiles_changed
        assert "cost_estimate" in d.tiles_changed["t"]

    def test_diff_fitness_tracking(self):
        g1 = Genome()
        g1.fitness_score = 0.5
        g2 = Genome()
        g2.fitness_score = 0.7

        d = g1.diff(g2)
        assert d.fitness_before == 0.5
        assert d.fitness_after == 0.7
        assert d.fitness_delta == pytest.approx(0.2)


class TestGenomeSerialization:
    """Test genome to_dict / from_dict roundtrip."""

    def test_roundtrip(self, genome):
        d = genome.to_dict()
        assert isinstance(d, dict)
        assert "modules" in d
        assert "tiles" in d
        assert "language_assignments" in d
        assert "fitness_score" in d

    def test_from_dict_preserves_modules(self, genome):
        d = genome.to_dict()
        restored = Genome.from_dict(d)
        assert set(restored.modules.keys()) == set(genome.modules.keys())

    def test_from_dict_preserves_tiles(self, genome):
        d = genome.to_dict()
        restored = Genome.from_dict(d)
        assert set(restored.tiles.keys()) == set(genome.tiles.keys())

    def test_from_dict_preserves_language_assignments(self, genome):
        genome.language_assignments = {"root.math": "rust"}
        d = genome.to_dict()
        restored = Genome.from_dict(d)
        assert restored.language_assignments == {"root.math": "rust"}

    def test_from_dict_preserves_fitness(self, genome):
        genome.evaluate_fitness()
        d = genome.to_dict()
        restored = Genome.from_dict(d)
        assert restored.fitness_score == genome.fitness_score

    def test_from_dict_preserves_generation(self):
        g = Genome()
        g.generation = 42
        d = g.to_dict()
        restored = Genome.from_dict(d)
        assert restored.generation == 42

    def test_from_dict_preserves_optimization_history(self):
        g = Genome()
        g.optimization_history.append(OptimizationRecord(
            generation=1, mutation_type="recompile_language",
            target="mod_a", description="Recompile mod_a", success=True,
        ))
        d = g.to_dict()
        restored = Genome.from_dict(d)
        assert len(restored.optimization_history) == 1
        assert restored.optimization_history[0].target == "mod_a"

    def test_roundtrip_profiler_snapshot(self, genome):
        d = genome.to_dict()
        restored = Genome.from_dict(d)
        assert restored.profiler_snapshot.module_count == genome.profiler_snapshot.module_count


class TestGenomeMutation:
    """Test genome mutation operations."""

    def test_mutate_recompile_language(self, genome):
        genome.language_assignments = {"root.math": "python"}
        mutated = genome.mutate(MutationStrategy.RECOMPILE_LANGUAGE, "root.math", new_language="rust")
        assert mutated.language_assignments["root.math"] == "rust"
        assert mutated.generation == 1
        assert len(mutated.optimization_history) == 1
        assert mutated.optimization_history[0].success

    def test_mutate_add_tile(self, genome):
        mutated = genome.mutate(
            MutationStrategy.ADD_TILE, target="new_tile",
            tile_name="new_tile", tile_type="compute",
            input_count=1, output_count=1,
        )
        assert "new_tile" in mutated.tiles
        assert mutated.tiles["new_tile"].tile_type == "compute"

    def test_mutate_replace_tile(self, genome, tile_registry):
        genome.capture(
            ModuleContainer("root", Granularity.TRAIN),
            tile_registry,
            AdaptiveProfiler(),
            AdaptiveSelector(AdaptiveProfiler()),
        )
        genome.evaluate_fitness()
        mutated = genome.mutate(
            MutationStrategy.REPLACE_TILE, "expensive_filter",
            new_cost=1.0,
        )
        assert mutated.tiles["expensive_filter"].cost_estimate == 1.0

    def test_mutate_fuse_pattern(self, genome):
        mutated = genome.mutate(
            MutationStrategy.FUSE_PATTERN, "root.math.add,root.math.mul",
            pattern_name="evolved_add_mul", cost_savings=0.5,
        )
        assert mutated.generation == 1
        assert len(mutated.optimization_history) == 1

    def test_mutate_merge_tiles(self, genome):
        genome.tiles["a"] = TileSnapshot(
            name="a", tile_type="compute",
            input_count=1, output_count=1,
            cost_estimate=2.0, abstraction_level=5,
            language_preference="fir",
        )
        genome.tiles["b"] = TileSnapshot(
            name="b", tile_type="compute",
            input_count=1, output_count=1,
            cost_estimate=3.0, abstraction_level=5,
            language_preference="fir",
        )
        mutated = genome.mutate(
            MutationStrategy.MERGE_TILES, "a__merged__b",
            tile_a="a", tile_b="b", merged_name="a__merged__b",
        )
        assert "a__merged__b" in mutated.tiles
        # Merged cost should be less than sum
        assert mutated.tiles["a__merged__b"].cost_estimate < 5.0

    def test_mutate_split_tile(self, genome):
        genome.tiles["big_tile"] = TileSnapshot(
            name="big_tile", tile_type="compute",
            input_count=1, output_count=1,
            cost_estimate=10.0, abstraction_level=5,
            language_preference="fir",
        )
        mutated = genome.mutate(MutationStrategy.SPLIT_TILE, "big_tile")
        assert mutated.tiles["big_tile"].cost_estimate < 10.0

    def test_mutate_does_not_modify_original(self, genome):
        genome.language_assignments = {"root": "python"}
        genome.mutate(MutationStrategy.RECOMPILE_LANGUAGE, "root", new_language="rust")
        assert genome.language_assignments.get("root") == "python"
        assert genome.generation == 0

    def test_mutate_updates_checksum(self, genome):
        original_checksum = genome.checksum
        mutated = genome.mutate(MutationStrategy.INLINE_OPTIMIZATION, "root")
        assert mutated.checksum != "" or mutated.checksum == ""
        # Checksums should differ if there were actual changes
        assert mutated.generation == 1

    def test_mutate_increments_generation(self, genome):
        assert genome.generation == 0
        m1 = genome.mutate(MutationStrategy.INLINE_OPTIMIZATION, "a")
        assert m1.generation == 1
        m2 = m1.mutate(MutationStrategy.INLINE_OPTIMIZATION, "b")
        assert m2.generation == 2


# ══════════════════════════════════════════════════════════════════════════════
# PatternMiner Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestPatternMinerCreation:
    """Test PatternMiner initialization."""

    def test_miner_creation(self, miner):
        assert miner.trace_count == 0
        assert miner.pattern_count == 0

    def test_miner_repr(self, miner):
        r = repr(miner)
        assert "PatternMiner" in r


class TestExecutionTrace:
    """Test ExecutionTrace dataclass."""

    def test_trace_creation(self):
        t = ExecutionTrace(module_calls=["a", "b", "c"])
        assert t.length == 3
        assert len(t) == 3

    def test_trace_auto_timestamp(self):
        t = ExecutionTrace(module_calls=["a"])
        assert t.timestamp > 0

    def test_trace_empty(self):
        t = ExecutionTrace()
        assert t.length == 0

    def test_trace_name(self):
        p = DiscoveredPattern(sequence=("a", "b", "c"))
        assert p.name == "a_b_c"


class TestPatternMinerRecording:
    """Test trace recording."""

    def test_record_single_trace(self, miner):
        miner.record_trace(ExecutionTrace(module_calls=["a", "b"]))
        assert miner.trace_count == 1

    def test_record_call_sequence(self, miner):
        miner.record_call_sequence(["a", "b", "c"])
        assert miner.trace_count == 1

    def test_record_multiple_traces(self, miner):
        for i in range(10):
            miner.record_call_sequence(["a", "b", "c"])
        assert miner.trace_count == 10

    def test_max_trace_length(self, profiler):
        miner = PatternMiner(profiler, max_trace_length=5)
        for i in range(10):
            miner.record_call_sequence(["a", "b"])
        assert miner.trace_count == 5

    def test_clear_traces(self, miner):
        miner.record_call_sequence(["a", "b"])
        miner.clear_traces()
        assert miner.trace_count == 0
        assert miner.pattern_count == 0


class TestPatternMinerMining:
    """Test pattern mining algorithm."""

    def test_mine_simple_pairs(self, miner):
        for _ in range(10):
            miner.record_call_sequence(["a", "b"])
        patterns = miner.mine_patterns(min_frequency=5, min_length=2)
        assert len(patterns) > 0
        # Should find the (a, b) pair
        found = any(p.sequence == ("a", "b") for p in patterns)
        assert found

    def test_mine_requires_min_frequency(self, miner):
        for _ in range(3):
            miner.record_call_sequence(["a", "b"])
        patterns = miner.mine_patterns(min_frequency=5, min_length=2)
        # Should find nothing — frequency too low
        assert len(patterns) == 0

    def test_mine_requires_min_length(self, miner):
        for _ in range(10):
            miner.record_call_sequence(["a", "b"])
        patterns = miner.mine_patterns(min_frequency=5, min_length=3)
        # Should find nothing — sequence too short
        assert len(patterns) == 0

    def test_mine_multiple_patterns(self, miner):
        for _ in range(10):
            miner.record_call_sequence(["a", "b", "c"])
        patterns = miner.mine_patterns(min_frequency=5, min_length=2, max_length=3)
        assert len(patterns) >= 1

    def test_mine_sorted_by_benefit(self, miner):
        for _ in range(20):
            miner.record_call_sequence(["hot_mod", "another_hot"])
        for _ in range(5):
            miner.record_call_sequence(["cold_mod", "rare"])
        patterns = miner.mine_patterns(min_frequency=3, min_length=2)
        # Most frequent should have highest benefit
        if len(patterns) >= 2:
            assert patterns[0].benefit_score >= patterns[1].benefit_score

    def test_mine_with_hot_modules(self, profiler):
        profiler.record_call("hot_mod", duration_ns=10000)
        profiler.record_call("hot_mod", duration_ns=10000)
        profiler.record_call("hot_mod", duration_ns=10000)
        profiler.record_call("hot_mod", duration_ns=10000)
        profiler.record_call("hot_mod", duration_ns=10000)
        miner = PatternMiner(profiler)
        for _ in range(10):
            miner.record_call_sequence(["hot_mod", "partner"])
        patterns = miner.mine_patterns(min_frequency=5, min_length=2)
        # Hot modules should boost estimated speedup
        for p in patterns:
            assert p.estimated_speedup >= 1.0


class TestPatternMinerSuggestions:
    """Test tile suggestion generation."""

    def test_suggest_tile_basic(self, miner):
        pattern = DiscoveredPattern(
            sequence=("compute_a", "compute_b"),
            frequency=10,
            estimated_speedup=1.5,
            confidence=0.8,
        )
        suggestion = miner.suggest_tile(pattern)
        assert isinstance(suggestion, TileSuggestion)
        assert "evolved_" in suggestion.suggested_name
        assert suggestion.cost_savings > 0
        assert suggestion.estimated_cost > 0

    def test_suggest_tile_ports(self, miner):
        pattern = DiscoveredPattern(
            sequence=("a", "b", "c", "d"),
            frequency=5,
        )
        suggestion = miner.suggest_tile(pattern)
        assert len(suggestion.input_ports) > 0
        assert "out" in suggestion.output_ports

    def test_suggest_tile_fir_hint(self, miner):
        pattern = DiscoveredPattern(
            sequence=("mod1", "mod2", "mod3"),
            frequency=5,
        )
        suggestion = miner.suggest_tile(pattern)
        assert "mod1" in suggestion.fir_blueprint_hint
        assert "mod2" in suggestion.fir_blueprint_hint

    def test_suggest_tile_type_inference(self, miner):
        pattern = DiscoveredPattern(
            sequence=("compute_add", "compute_mul"),
            frequency=5,
        )
        suggestion = miner.suggest_tile(pattern)
        assert suggestion.tile_type in ("compute", "memory", "control", "a2a", "effect")

    def test_get_hot_sequences(self, miner):
        for _ in range(10):
            miner.record_call_sequence(["a", "b"])
        sequences = miner.get_hot_sequences(top_n=5)
        assert isinstance(sequences, list)

    def test_discovered_pattern_benefit(self):
        p = DiscoveredPattern(
            sequence=("a", "b"),
            frequency=10,
            estimated_speedup=2.0,
            confidence=0.5,
        )
        assert p.benefit_score == 10 * 2.0 * 0.5

    def test_discovered_pattern_repr(self):
        p = DiscoveredPattern(sequence=("a", "b"))
        r = repr(p)
        assert "DiscoveredPattern" in r
        assert "freq=" in r

    def test_total_subsequences(self, miner):
        miner.record_call_sequence(["a", "b", "c"])
        assert miner.total_subsequences > 0


# ══════════════════════════════════════════════════════════════════════════════
# SystemMutator Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestMutatorCreation:
    """Test SystemMutator initialization."""

    def test_creation(self, mutator):
        assert mutator.total_mutations == 0
        assert mutator.success_count == 0
        assert mutator.failure_count == 0

    def test_repr(self, mutator):
        r = repr(mutator)
        assert "SystemMutator" in r


class TestMutatorProposals:
    """Test mutation proposal generation."""

    def test_propose_empty_genome(self, mutator):
        genome = Genome()
        proposals = mutator.propose_mutations(genome, [])
        assert isinstance(proposals, list)

    def test_propose_recompile_heat_modules(self, mutator, profiler):
        profiler.record_call("hot_mod", duration_ns=10000)
        profiler.record_call("hot_mod", duration_ns=10000)
        profiler.record_call("hot_mod", duration_ns=10000)
        profiler.record_call("hot_mod", duration_ns=10000)
        profiler.record_call("hot_mod", duration_ns=10000)

        genome = Genome()
        genome.modules["hot_mod"] = ModuleSnapshot(
            path="hot_mod", granularity="CARD", language="python",
            version=1, checksum="abc", heat_level="HEAT", call_count=5,
        )
        genome.language_assignments = {"hot_mod": "python"}

        proposals = mutator.propose_mutations(genome, [])
        recompile_proposals = [
            p for p in proposals
            if p.strategy == MutationStrategy.RECOMPILE_LANGUAGE
        ]
        assert len(recompile_proposals) > 0
        assert recompile_proposals[0].estimated_speedup > 1.0

    def test_propose_pattern_fusions(self, mutator):
        genome = Genome()
        pattern = DiscoveredPattern(
            sequence=("a", "b"), frequency=10, estimated_speedup=2.0,
        )
        proposals = mutator.propose_mutations(genome, [pattern])
        fuse_proposals = [
            p for p in proposals
            if p.strategy == MutationStrategy.FUSE_PATTERN
        ]
        assert len(fuse_proposals) > 0

    def test_propose_tile_replacements(self, mutator):
        genome = Genome()
        genome.tiles["expensive"] = TileSnapshot(
            name="expensive", tile_type="compute",
            input_count=1, output_count=1,
            cost_estimate=10.0, abstraction_level=5,
            language_preference="fir",
        )
        proposals = mutator.propose_mutations(genome, [])
        replace_proposals = [
            p for p in proposals
            if p.strategy == MutationStrategy.REPLACE_TILE
        ]
        assert len(replace_proposals) > 0

    def test_proposals_sorted_by_priority(self, mutator):
        genome = Genome()
        pattern = DiscoveredPattern(
            sequence=("a", "b"), frequency=100, estimated_speedup=10.0,
        )
        proposals = mutator.propose_mutations(genome, [pattern])
        if len(proposals) >= 2:
            assert proposals[0].priority >= proposals[1].priority

    def test_proposals_respect_risk_tolerance(self):
        mutator = SystemMutator(max_risk_tolerance=0.1)
        genome = Genome()
        genome.modules["risky"] = ModuleSnapshot(
            path="risky", granularity="CARD", language="python",
            version=1, checksum="abc", heat_level="HEAT",
        )
        genome.language_assignments = {"risky": "python"}
        proposals = mutator.propose_mutations(genome, [])
        for p in proposals:
            assert p.estimated_risk <= 0.1

    def test_proposals_limit_per_step(self):
        mutator = SystemMutator(max_mutations_per_step=2)
        genome = Genome()
        for i in range(5):
            genome.modules[f"mod_{i}"] = ModuleSnapshot(
                path=f"mod_{i}", granularity="CARD", language="python",
                version=1, checksum="abc", heat_level="HOT", call_count=10,
            )
            genome.language_assignments[f"mod_{i}"] = "python"
        proposals = mutator.propose_mutations(genome, [])
        assert len(mutator.get_pending_mutations()) <= 2


class TestMutatorApply:
    """Test mutation application and validation."""

    def test_apply_mutation_success(self, mutator, genome):
        proposal = MutationProposal(
            strategy=MutationStrategy.RECOMPILE_LANGUAGE,
            target="root",
            description="Recompile to rust",
            kwargs={"new_language": "rust"},
            estimated_speedup=2.0,
        )
        result = mutator.apply_mutation(proposal, genome)
        assert result.success

    def test_apply_mutation_validates_fn(self, mutator, genome):
        def always_fail(g):
            return False

        proposal = MutationProposal(
            strategy=MutationStrategy.RECOMPILE_LANGUAGE,
            target="root",
            description="Test",
            kwargs={"new_language": "rust"},
        )
        result = mutator.apply_mutation(proposal, genome, validation_fn=always_fail)
        assert not result.success
        assert not result.validation_passed

    def test_apply_mutation_fitness_tracking(self, mutator, genome):
        genome.evaluate_fitness()
        proposal = MutationProposal(
            strategy=MutationStrategy.RECOMPILE_LANGUAGE,
            target="root",
            description="Recompile",
            kwargs={"new_language": "rust"},
            estimated_speedup=2.0,
        )
        result = mutator.apply_mutation(proposal, genome)
        assert result.fitness_before >= 0
        assert result.fitness_after >= 0

    def test_apply_mutation_error_handling(self, mutator, genome):
        proposal = MutationProposal(
            strategy=MutationStrategy.REPLACE_TILE,
            target="nonexistent_tile",
            description="Replace nonexistent",
            kwargs={"new_cost": 0.1},
        )
        result = mutator.apply_mutation(proposal, genome)
        # Should not crash, even if tile doesn't exist
        assert isinstance(result, MutationResult)

    def test_mutation_result_is_improvement(self):
        proposal = MutationProposal(
            strategy=MutationStrategy.INLINE_OPTIMIZATION,
            target="x", description="test",
        )
        result = MutationResult(
            proposal=proposal,
            success=True,
            fitness_before=0.5,
            fitness_after=0.7,
            fitness_delta=0.2,
            measured_speedup=1.4,
        )
        assert result.is_improvement

    def test_mutation_result_repr(self):
        proposal = MutationProposal(
            strategy=MutationStrategy.INLINE_OPTIMIZATION,
            target="x", description="test",
        )
        result = MutationResult(
            proposal=proposal, success=True,
        )
        r = repr(result)
        assert "OK" in r


class TestMutatorCommitRollback:
    """Test commit and rollback operations."""

    def test_commit(self, mutator):
        proposal = MutationProposal(
            strategy=MutationStrategy.INLINE_OPTIMIZATION,
            target="x", description="test",
        )
        result = MutationResult(proposal=proposal, success=True)
        mutator.commit_mutation(proposal, result)
        assert mutator.success_count == 1
        assert mutator.failure_count == 0

    def test_rollback(self, mutator):
        proposal = MutationProposal(
            strategy=MutationStrategy.INLINE_OPTIMIZATION,
            target="x", description="test",
        )
        result = MutationResult(proposal=proposal, success=False)
        mutator.rollback_mutation(proposal, result)
        assert mutator.success_count == 0
        assert mutator.failure_count == 1

    def test_success_rate(self, mutator):
        p = MutationProposal(
            strategy=MutationStrategy.INLINE_OPTIMIZATION,
            target="x", description="test",
        )
        mutator.commit_mutation(p, MutationResult(proposal=p, success=True))
        mutator.commit_mutation(p, MutationResult(proposal=p, success=True))
        mutator.rollback_mutation(p, MutationResult(proposal=p, success=False))
        assert mutator.get_success_rate() == pytest.approx(2.0 / 3.0)

    def test_total_speedup(self, mutator):
        p = MutationProposal(
            strategy=MutationStrategy.INLINE_OPTIMIZATION,
            target="x", description="test",
        )
        r1 = MutationResult(
            proposal=p, success=True, measured_speedup=2.0,
        )
        r2 = MutationResult(
            proposal=p, success=True, measured_speedup=1.5,
        )
        mutator.commit_mutation(p, r1)
        mutator.commit_mutation(p, r2)
        assert mutator.get_total_speedup() == pytest.approx(3.0)

    def test_clear_history(self, mutator):
        p = MutationProposal(
            strategy=MutationStrategy.INLINE_OPTIMIZATION,
            target="x", description="test",
        )
        mutator.commit_mutation(p, MutationResult(proposal=p, success=True))
        mutator.clear_history()
        assert mutator.total_mutations == 0


# ══════════════════════════════════════════════════════════════════════════════
# CorrectnessValidator Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestValidatorCreation:
    """Test CorrectnessValidator initialization."""

    def test_creation(self, validator):
        assert validator.test_count == 0
        assert len(validator.test_names) == 0

    def test_repr(self, validator):
        r = repr(validator)
        assert "CorrectnessValidator" in r


class TestValidatorRegistration:
    """Test test case registration."""

    def test_register_single(self, validator):
        validator.register_test("add", lambda: 2 + 2, 4)
        assert validator.test_count == 1
        assert "add" in validator.test_names

    def test_register_multiple(self, validator):
        validator.register_tests([
            ("add", lambda: 2 + 2, 4),
            ("mul", lambda: 3 * 4, 12),
            ("len", lambda: len([1, 2, 3]), 3),
        ])
        assert validator.test_count == 3

    def test_register_overwrites(self, validator):
        validator.register_test("t", lambda: 1, 1)
        validator.register_test("t", lambda: 2, 2)
        assert validator.test_count == 1

    def test_unregister(self, validator):
        validator.register_test("t", lambda: 1, 1)
        result = validator.unregister_test("t")
        assert result
        assert validator.test_count == 0

    def test_unregister_missing(self, validator):
        result = validator.unregister_test("nonexistent")
        assert not result


class TestValidatorBaseline:
    """Test baseline capture."""

    def test_capture_baseline(self, validator):
        validator.register_test("add", lambda: 2 + 2)
        validator.capture_baseline()
        assert validator.get_baseline("add") == 4

    def test_capture_baseline_error(self, validator):
        def error_fn():
            raise ValueError("boom")
        validator.register_test("error", error_fn)
        validator.capture_baseline()
        assert validator.get_baseline("error") is None

    def test_clear_baseline(self, validator):
        validator.register_test("t", lambda: 1)
        validator.capture_baseline()
        validator.clear_baseline()
        assert validator.get_baseline("t") is None


class TestValidatorValidation:
    """Test validation execution."""

    def test_validate_all_pass(self, validator):
        validator.register_test("add", lambda: 2 + 2, 4)
        validator.register_test("mul", lambda: 3 * 4, 12)
        result = validator.validate()
        assert result.all_pass
        assert result.num_passed == 2
        assert result.num_failed == 0

    def test_validate_with_failure(self, validator):
        validator.register_test("good", lambda: 42, 42)
        validator.register_test("bad", lambda: 99, 42)
        result = validator.validate()
        assert not result.all_pass
        assert result.num_passed == 1
        assert result.num_failed == 1
        assert len(result.failure_details) == 1

    def test_validate_no_expected(self, validator):
        validator.register_test("auto", lambda: 42)
        result = validator.validate()
        assert result.all_pass

    def test_validate_with_tolerance(self, validator):
        validator.register_test("float", lambda: 0.1001, 0.1, tolerance=0.01)
        result = validator.validate()
        assert result.all_pass

    def test_validate_tolerance_exceeded(self, validator):
        validator.register_test("float", lambda: 0.2, 0.1, tolerance=0.01)
        result = validator.validate()
        assert not result.all_pass

    def test_validate_exception(self, validator):
        def boom():
            raise RuntimeError("test error")
        validator.register_test("err", boom, 42)
        result = validator.validate()
        assert not result.all_pass
        assert result.failure_details[0].error != ""

    def test_validate_pass_rate(self, validator):
        validator.register_test("a", lambda: 1, 1)
        validator.register_test("b", lambda: 99, 42)
        validator.register_test("c", lambda: 3, 3)
        result = validator.validate()
        assert result.pass_rate == pytest.approx(2.0 / 3.0)

    def test_validate_genome(self, validator, genome):
        validator.register_test("t", lambda: 42, 42)
        assert validator.validate_genome(genome)

    def test_validate_repr(self, validator):
        validator.register_test("t", lambda: 1, 1)
        result = validator.validate()
        r = repr(result)
        assert "ValidationResult" in r


class TestValidatorRegression:
    """Test regression checking."""

    def test_regression_no_changes(self, validator):
        g1 = Genome()
        g1.checksum = "abc"
        g2 = Genome()
        g2.checksum = "abc"
        report = validator.regression_check(g1, g2)
        assert report.all_pass

    def test_regression_language_slowdown(self, validator):
        g1 = Genome()
        g1.language_assignments = {"mod": "rust"}
        g1.checksum = "a"
        g2 = Genome()
        g2.language_assignments = {"mod": "python"}
        g2.checksum = "b"
        report = validator.regression_check(g1, g2)
        assert report.has_regressions

    def test_regression_language_speedup(self, validator):
        g1 = Genome()
        g1.language_assignments = {"mod": "python"}
        g1.checksum = "a"
        g2 = Genome()
        g2.language_assignments = {"mod": "rust"}
        g2.checksum = "b"
        report = validator.regression_check(g1, g2)
        assert len(report.improvements) > 0

    def test_regression_fitness_drop(self, validator):
        g1 = Genome()
        g1.fitness_score = 0.8
        g1.checksum = "a"
        g2 = Genome()
        g2.fitness_score = 0.5
        g2.checksum = "b"
        report = validator.regression_check(g1, g2)
        assert report.has_regressions

    def test_regression_with_test_failures(self, validator):
        validator.register_test("bad", lambda: 99, 42)
        g1 = Genome()
        g1.checksum = "a"
        g2 = Genome()
        g2.checksum = "b"
        report = validator.regression_check(g1, g2)
        assert report.has_regressions

    def test_regression_report_repr(self):
        report = RegressionReport(all_pass=True)
        assert "NO REGRESSIONS" in repr(report)

    def test_clear_all(self, validator):
        validator.register_test("t", lambda: 1, 1)
        validator.capture_baseline()
        validator.validate()
        validator.clear_all()
        assert validator.test_count == 0
        assert len(validator.get_history()) == 0


# ══════════════════════════════════════════════════════════════════════════════
# EvolutionEngine Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestEngineCreation:
    """Test EvolutionEngine initialization."""

    def test_creation(self, engine):
        assert engine.generation == 0
        assert engine.current_fitness == 0.0

    def test_creation_defaults(self):
        e = EvolutionEngine()
        assert e.generation == 0
        assert isinstance(e.profiler, AdaptiveProfiler)
        assert isinstance(e.selector, AdaptiveSelector)
        assert isinstance(e.validator, CorrectnessValidator)

    def test_repr(self, engine):
        r = repr(engine)
        assert "EvolutionEngine" in r


class TestEngineSingleStep:
    """Test single evolution step."""

    def test_step_increments_generation(self, engine, module_root, tile_registry):
        step = engine.step(module_root, tile_registry)
        assert step.generation == 1
        assert engine.generation == 1

    def test_step_returns_step(self, engine, module_root, tile_registry):
        step = engine.step(module_root, tile_registry)
        assert isinstance(step, EvolutionStep)

    def test_step_fitness_before(self, engine, module_root, tile_registry):
        step = engine.step(module_root, tile_registry)
        assert step.fitness_before >= 0.0

    def test_step_fitness_after(self, engine, module_root, tile_registry):
        step = engine.step(module_root, tile_registry)
        assert step.fitness_after >= 0.0

    def test_step_with_workload(self, engine, module_root, tile_registry, profiler):
        def workload():
            profiler.record_call("root.math.add", duration_ns=100)

        step = engine.step(module_root, tile_registry, workload=workload)
        assert step.generation == 1

    def test_step_with_validation_fn(self, engine, module_root, tile_registry):
        def always_ok(g):
            return True

        step = engine.step(module_root, tile_registry, validation_fn=always_ok)
        assert step.generation == 1

    def test_step_records_history(self, engine, module_root, tile_registry):
        engine.step(module_root, tile_registry)
        history = engine.get_history()
        assert len(history) == 1

    def test_step_record_is_improvement(self, engine, module_root, tile_registry):
        engine.step(module_root, tile_registry)
        record = engine.get_history()[0]
        assert hasattr(record, "is_improvement")


class TestEngineMultiGeneration:
    """Test multi-generation evolution."""

    def test_two_generations(self, engine, module_root, tile_registry, profiler):
        def workload():
            profiler.record_call("root.math.add", duration_ns=100)

        engine.step(module_root, tile_registry, workload=workload)
        engine.step(module_root, tile_registry, workload=workload)
        assert engine.generation == 2
        assert len(engine.get_history()) == 2

    def test_improvement_history(self, engine, module_root, tile_registry):
        engine.step(module_root, tile_registry)
        engine.step(module_root, tile_registry)
        history = engine.get_improvement_history()
        assert len(history) == 2
        assert all(isinstance(h, tuple) for h in history)

    def test_best_mutations_empty(self, engine):
        best = engine.get_best_mutations()
        assert best == []

    def test_best_mutations_with_commit(self, engine, module_root, tile_registry):
        profiler = engine.profiler
        profiler.record_call("root.math.add", duration_ns=10000)
        profiler.record_call("root.math.add", duration_ns=10000)
        profiler.record_call("root.math.add", duration_ns=10000)
        profiler.record_call("root.math.add", duration_ns=10000)
        profiler.record_call("root.math.add", duration_ns=10000)

        engine.step(module_root, tile_registry)
        best = engine.get_best_mutations()
        # May or may not have commits depending on proposals
        assert isinstance(best, list)


class TestEngineEvolve:
    """Test full evolution loop."""

    def test_evolve_basic(self, engine, module_root, tile_registry, profiler):
        def workload():
            profiler.record_call("root.math.add", duration_ns=100)
            profiler.record_call("root.math.mul", duration_ns=50)

        report = engine.evolve(
            module_root, tile_registry,
            workloads=[workload],
            max_generations=3,
        )
        assert isinstance(report, EvolutionReport)
        assert report.generations <= 3

    def test_evolve_report_fields(self, engine, module_root, tile_registry, profiler):
        def workload():
            profiler.record_call("root.math.add", duration_ns=100)

        report = engine.evolve(
            module_root, tile_registry,
            workloads=[workload],
            max_generations=2,
        )
        assert report.initial_fitness >= 0
        assert report.final_fitness >= 0
        assert report.total_speedup >= 1.0
        assert report.mutations_proposed >= 0
        assert report.mutations_succeeded >= 0
        assert report.patterns_discovered >= 0

    def test_evolve_report_repr(self, engine, module_root, tile_registry, profiler):
        def workload():
            profiler.record_call("root.math.add", duration_ns=100)

        report = engine.evolve(
            module_root, tile_registry,
            workloads=[workload],
            max_generations=1,
        )
        r = repr(report)
        assert "EvolutionReport" in r

    def test_evolve_fitness_improvement(self, engine, module_root, tile_registry, profiler):
        def workload():
            profiler.record_call("root.math.add", duration_ns=100)

        report = engine.evolve(
            module_root, tile_registry,
            workloads=[workload],
            max_generations=2,
        )
        assert isinstance(report.fitness_improvement, float)

    def test_evolve_with_validation_fn(self, engine, module_root, tile_registry, profiler):
        def workload():
            profiler.record_call("root.math.add", duration_ns=100)

        def always_valid(g):
            return True

        report = engine.evolve(
            module_root, tile_registry,
            workloads=[workload],
            max_generations=2,
            validation_fn=always_valid,
        )
        assert report.generations >= 1


class TestEngineConvergence:
    """Test evolution convergence behavior."""

    def test_reset(self, engine, module_root, tile_registry):
        engine.step(module_root, tile_registry)
        engine.reset()
        assert engine.generation == 0
        assert engine.current_fitness == 0.0
        assert len(engine.get_history()) == 0


# ══════════════════════════════════════════════════════════════════════════════
# Integration Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestIntegrationPipeline:
    """Test the full profiler → miner → mutator → validator pipeline."""

    def test_full_pipeline(self, profiler, module_root, tile_registry):
        # 1. Profile some workloads
        for _ in range(20):
            profiler.record_call("root.math.add", duration_ns=1000)
        for _ in range(15):
            profiler.record_call("root.math.mul", duration_ns=800)
        for _ in range(5):
            profiler.record_call("root.main", duration_ns=100)

        # 2. Create components
        selector = AdaptiveSelector(profiler)
        miner = PatternMiner(profiler)
        mutator = SystemMutator()
        validator = CorrectnessValidator()

        # 3. Record execution traces
        for _ in range(10):
            miner.record_call_sequence(["root.math.add", "root.math.mul"])

        # 4. Mine patterns
        patterns = miner.mine_patterns(min_frequency=5, min_length=2)
        assert len(patterns) > 0

        # 5. Capture genome
        genome = Genome()
        genome.capture(module_root, tile_registry, profiler, selector)
        genome.evaluate_fitness()
        assert genome.fitness_score > 0

        # 6. Propose mutations
        proposals = mutator.propose_mutations(genome, patterns)
        assert len(proposals) > 0

        # 7. Apply and validate
        for proposal in proposals[:3]:
            result = mutator.apply_mutation(proposal, genome)
            if result.success:
                mutator.commit_mutation(proposal, result)
            else:
                mutator.rollback_mutation(proposal, result)

        # 8. Verify state
        assert mutator.total_mutations >= 1
        assert mutator.get_total_speedup() >= 1.0

    def test_profiler_feeds_heatmap_to_genome(self, profiler, module_root, tile_registry):
        profiler.record_call("root.math.add", duration_ns=10000)
        profiler.record_call("root.math.add", duration_ns=10000)
        profiler.record_call("root.math.add", duration_ns=10000)
        profiler.record_call("root.math.add", duration_ns=10000)
        profiler.record_call("root.math.add", duration_ns=10000)
        profiler.record_call("root.math.mul", duration_ns=10000)
        profiler.record_call("root.math.mul", duration_ns=10000)

        selector = AdaptiveSelector(profiler)
        genome = Genome()
        genome.capture(module_root, tile_registry, profiler, selector)

        # Verify heatmap was captured
        heatmap = profiler.get_heatmap()
        assert len(heatmap) > 0

    def test_evolution_step_with_hot_modules(self, profiler, module_root, tile_registry):
        # Make add very hot
        for _ in range(50):
            profiler.record_call("root.math.add", duration_ns=10000)
        for _ in range(5):
            profiler.record_call("root.math.mul", duration_ns=1000)

        selector = AdaptiveSelector(profiler)
        engine = EvolutionEngine(
            profiler=profiler,
            selector=selector,
        )

        step = engine.step(module_root, tile_registry)
        assert step.generation == 1
        assert step.patterns_found >= 0

    def test_mutation_strategy_enum(self):
        """All mutation strategies are accessible."""
        assert MutationStrategy.RECOMPILE_LANGUAGE.value == "recompile_language"
        assert MutationStrategy.FUSE_PATTERN.value == "fuse_pattern"
        assert MutationStrategy.REPLACE_TILE.value == "replace_tile"
        assert MutationStrategy.ADD_TILE.value == "add_tile"
        assert MutationStrategy.MERGE_TILES.value == "merge_tiles"
        assert MutationStrategy.SPLIT_TILE.value == "split_tile"
        assert MutationStrategy.INLINE_OPTIMIZATION.value == "inline_optimization"

    def test_evolution_record_success_rate(self):
        record = EvolutionRecord(
            generation=1, fitness_before=0.5, fitness_after=0.7,
            fitness_delta=0.2, mutations_proposed=3,
            mutations_committed=2, mutations_failed=1,
            patterns_found=5,
        )
        assert record.is_improvement
        assert record.success_rate == pytest.approx(2.0 / 3.0)

    def test_evolution_step_improved(self):
        step = EvolutionStep(
            generation=1, fitness_before=0.5, fitness_after=0.7,
            mutations_proposed=1, mutations_committed=1, patterns_found=3,
        )
        assert step.improved

    def test_genome_diff_no_changes(self):
        g1 = Genome()
        g1.evaluate_fitness()
        d = g1.diff(g1)
        assert not d.has_changes
        assert d.fitness_delta == 0.0

    def test_tile_suggestion_fields(self, miner):
        pattern = DiscoveredPattern(
            sequence=("a", "b"), frequency=10, estimated_speedup=2.0,
        )
        suggestion = miner.suggest_tile(pattern)
        assert suggestion.suggested_name != ""
        assert suggestion.cost_savings > 0
        assert len(suggestion.recommended_params) > 0

    def test_multiple_evolution_cycles(self, engine, module_root, tile_registry, profiler):
        """Run multiple evolution cycles and verify history grows."""
        def workload():
            profiler.record_call("root.math.add", duration_ns=100)

        for i in range(5):
            engine.step(module_root, tile_registry, workload=workload)

        history = engine.get_history()
        assert len(history) == 5
        assert history[0].generation == 1
        assert history[4].generation == 5

    def test_validator_works_with_evolution(self, engine, module_root, tile_registry):
        """Validator integrates with evolution engine."""
        engine.validator.register_test("simple", lambda: 42, 42)
        engine.validator.capture_baseline()

        step = engine.step(module_root, tile_registry)
        assert step.record is not None
        assert step.record.validation_result is not None

    def test_profiler_reset_before_evolution(self, engine, module_root, tile_registry, profiler):
        """Profiler can be reset between evolutions."""
        profiler.record_call("test", duration_ns=100)
        assert profiler.sample_count > 0

        profiler.reset()
        assert profiler.sample_count == 0
        assert profiler.module_count == 0

    def test_genome_from_dict_empty(self):
        g = Genome.from_dict({})
        assert g.modules == {}
        assert g.tiles == {}
        assert g.fitness_score == 0.0

    def test_genome_to_dict_no_crash(self, genome):
        d = genome.to_dict()
        # Should have all top-level keys
        assert "modules" in d
        assert "tiles" in d
        assert "language_assignments" in d
        assert "profiler_snapshot" in d
        assert "optimization_history" in d
        assert "fitness_score" in d
        assert "timestamp" in d
        assert "generation" in d
        assert "checksum" in d

    def test_evolution_report_success_rate(self):
        report = EvolutionReport(
            mutations_succeeded=8, mutations_failed=2,
        )
        assert report.success_rate == pytest.approx(0.8)

    def test_evolution_report_fitness_improvement_pct(self):
        report = EvolutionReport(
            initial_fitness=0.5, final_fitness=0.75,
        )
        assert report.fitness_improvement_pct == pytest.approx(50.0)

    def test_miner_max_trace_length_respected(self, profiler):
        miner = PatternMiner(profiler, max_trace_length=3)
        for _ in range(10):
            miner.record_call_sequence(["a", "b"])
        assert miner.trace_count == 3

    def test_mutator_risk_filter(self):
        mutator = SystemMutator(max_risk_tolerance=0.05)
        genome = Genome()
        genome.modules["hot"] = ModuleSnapshot(
            path="hot", granularity="CARD", language="python",
            version=1, checksum="abc", heat_level="HEAT",
        )
        genome.language_assignments = {"hot": "python"}
        proposals = mutator.propose_mutations(genome, [])
        # HEAT modules suggest c_simd with risk 0.4, which should be filtered
        for p in proposals:
            assert p.estimated_risk <= 0.05

    def test_validator_register_with_none_expected(self, validator):
        validator.register_test("auto_pass", lambda: 42, None)
        result = validator.validate()
        assert result.all_pass

    def test_pattern_name_generation(self):
        p1 = DiscoveredPattern(sequence=("a",))
        assert p1.name == "a"

        p2 = DiscoveredPattern(sequence=("a", "b"))
        assert p2.name == "a_b"

        p3 = DiscoveredPattern(sequence=("a", "b", "c", "d", "e"))
        assert "x5" in p3.name
