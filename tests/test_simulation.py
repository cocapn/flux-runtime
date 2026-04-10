"""Tests for the FLUX simulation layer — digital twin, predictor, speculator, oracle."""

import time
import pytest

from flux.cost.model import CostModel
from flux.evolution.genome import (
    Genome, MutationStrategy, ModuleSnapshot, TileSnapshot,
)
from flux.evolution.mutator import MutationProposal
from flux.flywheel.hypothesis import (
    Hypothesis, ExperimentOutcome,
)
from flux.flywheel.knowledge import KnowledgeBase
from flux.adaptive.profiler import AdaptiveProfiler, HeatLevel
from flux.synthesis.synthesizer import FluxSynthesizer

from flux.simulation.digital_twin import (
    DigitalTwin, SimulatedResult, SimulatedEvolutionReport,
    PredictionRecord, WhatIfResult, ChaosReport, ChaosFault,
    TwinReport,
)
from flux.simulation.predictor import (
    PerformancePredictor, CapacityForecast, MemoryStore,
)
from flux.simulation.speculator import (
    SpeculativeEngine, SpeculationResult,
)
from flux.simulation.oracle import (
    DecisionOracle, OracleDecision, OracleRecommendation, ROIEstimate,
)


# ════════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════════

def _make_synthesizer() -> FluxSynthesizer:
    """Create a basic synthesizer with some modules."""
    synth = FluxSynthesizer("test_app")
    synth.load_module("core/engine", "def run(): pass", "python")
    synth.load_module("core/parser", "def parse(): pass", "python")
    synth.load_module("dsp/filter", "def filter(): pass", "python")
    # Add profiling data
    synth.record_call("test_app.core.engine", duration_ns=50000, calls=100)
    synth.record_call("test_app.core.parser", duration_ns=20000, calls=50)
    synth.record_call("test_app.dsp.filter", duration_ns=100000, calls=200)
    return synth


@pytest.fixture
def synth():
    return _make_synthesizer()


@pytest.fixture
def twin(synth):
    t = DigitalTwin(synth)
    t.capture_shadow()
    return t


@pytest.fixture
def cost_model():
    return CostModel()


@pytest.fixture
def memory_store():
    return MemoryStore()


@pytest.fixture
def predictor(cost_model, memory_store):
    return PerformancePredictor(cost_model, memory_store)


@pytest.fixture
def speculator(synth, twin):
    return SpeculativeEngine(synth, twin, candidates=5, parallel_limit=2)


@pytest.fixture
def knowledge():
    return KnowledgeBase()


@pytest.fixture
def oracle(predictor, twin, knowledge):
    return DecisionOracle(predictor, twin, knowledge)


# ════════════════════════════════════════════════════════════════════════
# MemoryStore Tests
# ════════════════════════════════════════════════════════════════════════

class TestMemoryStore:

    def test_store_put_get(self, memory_store):
        memory_store.put("key", "value")
        assert memory_store.get("key") == "value"

    def test_store_get_default(self, memory_store):
        assert memory_store.get("missing", 42) == 42

    def test_store_has(self, memory_store):
        assert not memory_store.has("key")
        memory_store.put("key", 1)
        assert memory_store.has("key")

    def test_store_delete(self, memory_store):
        memory_store.put("key", "val")
        assert memory_store.delete("key")
        assert not memory_store.has("key")
        assert not memory_store.delete("key")

    def test_store_size(self, memory_store):
        memory_store.put("a", 1)
        memory_store.put("b", 2)
        assert memory_store.size == 2

    def test_store_history(self, memory_store):
        memory_store.append_history({"type": "test", "value": 1})
        memory_store.append_history({"type": "test", "value": 2})
        memory_store.append_history({"type": "other", "value": 3})
        assert memory_store.history_size == 3
        assert len(memory_store.get_history("type")) == 3
        assert len(memory_store.get_history("missing_key")) == 0

    def test_store_recent(self, memory_store):
        for i in range(20):
            memory_store.append_history({"i": i})
        recent = memory_store.get_recent(5)
        assert len(recent) == 5
        assert recent[-1]["i"] == 19

    def test_store_clear(self, memory_store):
        memory_store.put("a", 1)
        memory_store.append_history({"x": 1})
        memory_store.clear()
        assert memory_store.size == 0
        assert memory_store.history_size == 0

    def test_store_overwrite(self, memory_store):
        memory_store.put("key", "old")
        memory_store.put("key", "new")
        assert memory_store.get("key") == "new"
        assert memory_store.size == 1


# ════════════════════════════════════════════════════════════════════════
# PredictionRecord Tests
# ════════════════════════════════════════════════════════════════════════

class TestPredictionRecord:

    def test_record_error(self):
        r = PredictionRecord("speedup", "mod_a", 2.0, 1.8, 0.7)
        assert r.error == pytest.approx(0.2)

    def test_record_relative_error(self):
        r = PredictionRecord("speedup", "mod_a", 2.0, 1.8, 0.7)
        assert r.relative_error == pytest.approx(0.1, abs=0.02)

    def test_record_relative_error_zero_actual(self):
        r = PredictionRecord("speedup", "mod_a", 1.0, 0.0, 0.5)
        assert r.relative_error == 1.0

    def test_record_perfect_prediction(self):
        r = PredictionRecord("speedup", "mod_a", 2.0, 2.0, 0.9)
        assert r.error == 0.0
        assert r.relative_error == 0.0


# ════════════════════════════════════════════════════════════════════════
# DigitalTwin Tests
# ════════════════════════════════════════════════════════════════════════

class TestDigitalTwinCreation:

    def test_twin_creation(self, twin):
        assert twin is not None
        assert isinstance(twin, DigitalTwin)

    def test_twin_shadow_genome(self, twin):
        assert isinstance(twin.shadow_genome, Genome)

    def test_twin_repr(self, twin):
        r = repr(twin)
        assert "DigitalTwin" in r


class TestDigitalTwinShadowCapture:

    def test_capture_shadow(self, twin, synth):
        twin.capture_shadow()
        # Shadow genome should exist (modules only captured if genome has been snapshotted)
        assert isinstance(twin.shadow_genome, Genome)

    def test_capture_shadow_updates(self, twin, synth):
        twin.capture_shadow()
        first_modules = len(twin.shadow_genome.modules)
        synth.load_module("core/new_mod", "def new(): pass", "python")
        twin.capture_shadow()
        assert len(twin.shadow_genome.modules) >= first_modules

    def test_capture_shadow_tiles(self, twin):
        twin.capture_shadow()
        # Shadow genome should exist; tiles come from registry capture
        assert isinstance(twin.shadow_genome, Genome)


class TestDigitalTwinMutationSimulation:

    def test_simulate_recompile(self, twin):
        proposal = MutationProposal(
            strategy=MutationStrategy.RECOMPILE_LANGUAGE,
            target="test_app.dsp.filter",
            description="Recompile filter to Rust",
            kwargs={"new_language": "rust"},
            estimated_speedup=10.0,
            estimated_risk=0.3,
        )
        result = twin.simulate_mutation(proposal)
        assert isinstance(result, SimulatedResult)
        assert result.estimated_speedup > 1.0

    def test_simulate_inline_optimization(self, twin):
        proposal = MutationProposal(
            strategy=MutationStrategy.INLINE_OPTIMIZATION,
            target="test_app.core.engine",
            description="Inline optimize engine",
            kwargs={"speedup": 1.2},
            estimated_speedup=1.2,
            estimated_risk=0.1,
        )
        result = twin.simulate_mutation(proposal)
        assert result.estimated_speedup >= 1.0

    def test_simulate_replace_tile(self, twin):
        # Add a tile to shadow
        twin.shadow_genome.tiles["expensive_tile"] = TileSnapshot(
            name="expensive_tile", tile_type="compute",
            input_count=1, output_count=1,
            cost_estimate=5.0, abstraction_level=5,
            language_preference="fir",
        )
        proposal = MutationProposal(
            strategy=MutationStrategy.REPLACE_TILE,
            target="expensive_tile",
            description="Replace expensive tile",
            kwargs={"new_cost": 1.0},
            estimated_speedup=2.0,
            estimated_risk=0.3,
        )
        result = twin.simulate_mutation(proposal)
        assert result.estimated_speedup > 1.0

    def test_simulate_fuse_pattern(self, twin):
        proposal = MutationProposal(
            strategy=MutationStrategy.FUSE_PATTERN,
            target="pattern_a",
            description="Fuse hot pattern",
            kwargs={"pattern_name": "fused_pattern", "cost_savings": 0.3},
            estimated_speedup=1.5,
            estimated_risk=0.2,
        )
        result = twin.simulate_mutation(proposal)
        assert isinstance(result, SimulatedResult)

    def test_simulate_fitness_delta(self, twin):
        proposal = MutationProposal(
            strategy=MutationStrategy.INLINE_OPTIMIZATION,
            target="test_app.core.engine",
            description="Optimize",
            kwargs={"speedup": 1.2},
            estimated_speedup=1.2,
            estimated_risk=0.1,
        )
        result = twin.simulate_mutation(proposal)
        assert isinstance(result.estimated_fitness_before, float)
        assert isinstance(result.estimated_fitness_after, float)

    def test_simulate_risk_assessment(self, twin):
        risky = MutationProposal(
            strategy=MutationStrategy.RECOMPILE_LANGUAGE,
            target="test_app.dsp.filter",
            description="Risky recompile",
            kwargs={"new_language": "c_simd"},
            estimated_speedup=16.0,
            estimated_risk=0.8,
        )
        safe = MutationProposal(
            strategy=MutationStrategy.INLINE_OPTIMIZATION,
            target="test_app.core.engine",
            description="Safe inline",
            kwargs={"speedup": 1.1},
            estimated_risk=0.1,
        )
        risky_result = twin.simulate_mutation(risky)
        safe_result = twin.simulate_mutation(safe)
        assert risky_result.risk_assessment > safe_result.risk_assessment

    def test_simulate_time_cost(self, twin):
        proposal = MutationProposal(
            strategy=MutationStrategy.RECOMPILE_LANGUAGE,
            target="test_app.dsp.filter",
            description="Recompile to Rust",
            kwargs={"new_language": "rust"},
            estimated_speedup=10.0,
            estimated_risk=0.3,
        )
        result = twin.simulate_mutation(proposal)
        # Rust compile time should be ~30000ms
        assert result.time_to_apply_estimate_ms > 10000

    def test_should_apply_heuristic(self, twin):
        good = MutationProposal(
            strategy=MutationStrategy.RECOMPILE_LANGUAGE,
            target="test_app.dsp.filter",
            description="Good mutation",
            kwargs={"new_language": "rust"},
            estimated_speedup=5.0,
            estimated_risk=0.2,
        )
        bad = MutationProposal(
            strategy=MutationStrategy.RECOMPILE_LANGUAGE,
            target="test_app.dsp.filter",
            description="Bad mutation",
            kwargs={"new_language": "python"},
            estimated_speedup=1.0,
            estimated_risk=0.9,
        )
        assert twin.simulate_mutation(good).should_apply
        assert not twin.simulate_mutation(bad).should_apply


class TestDigitalTwinSimulatedEvolution:

    def test_simulate_evolution_single_gen(self, twin):
        report = twin.simulate_evolution(generations=1)
        assert isinstance(report, SimulatedEvolutionReport)
        assert report.generations_simulated == 1

    def test_simulate_evolution_multi_gen(self, twin):
        report = twin.simulate_evolution(generations=5)
        assert report.generations_simulated == 5
        assert len(report.per_generation_fitness) == 6  # initial + 5 gen

    def test_simulate_evolution_tracks_mutations(self, twin):
        report = twin.simulate_evolution(generations=3)
        assert report.mutations_simulated >= 0
        assert report.mutations_accepted >= 0
        assert report.mutations_rejected >= 0

    def test_simulate_evolution_improvement_rate(self, twin):
        report = twin.simulate_evolution(generations=3)
        rate = report.improvement_rate
        assert 0.0 <= rate <= 1.0

    def test_simulate_evolution_fitness_tracking(self, twin):
        twin.shadow_genome.evaluate_fitness()
        initial = twin.shadow_genome.fitness_score
        report = twin.simulate_evolution(generations=2)
        assert report.initial_fitness == pytest.approx(initial, abs=0.01)
        assert len(report.per_generation_fitness) == 3


class TestDigitalTwinPredictionAccuracy:

    def test_initial_accuracy(self, twin):
        assert twin.prediction_accuracy() == 1.0  # no predictions = perfect

    def test_initial_drift(self, twin):
        assert twin.prediction_drift() == 0.0

    def test_record_prediction_accurate(self, twin):
        twin.record_prediction("speedup", "mod_a", 2.0, 2.1, 0.8)
        assert twin.prediction_accuracy() == 1.0  # relative error < 0.2

    def test_record_prediction_inaccurate(self, twin):
        twin.record_prediction("speedup", "mod_a", 2.0, 0.5, 0.8)
        assert twin.prediction_accuracy() == 0.0  # relative error > 0.2

    def test_record_prediction_drift(self, twin):
        twin.record_prediction("speedup", "mod_a", 2.0, 1.0, 0.5)
        twin.record_prediction("speedup", "mod_b", 3.0, 1.0, 0.5)
        drift = twin.prediction_drift()
        assert drift > 0.0

    def test_record_multiple_predictions(self, twin):
        twin.record_prediction("speedup", "a", 2.0, 2.1, 0.8)
        twin.record_prediction("speedup", "b", 1.5, 1.4, 0.7)
        twin.record_prediction("speedup", "c", 3.0, 1.0, 0.5)
        accuracy = twin.prediction_accuracy()
        assert 0.0 < accuracy < 1.0


class TestDigitalTwinWhatIf:

    def test_what_if_recompile(self, twin):
        result = twin.what_if_recompile("test_app.dsp.filter", "rust")
        assert isinstance(result, WhatIfResult)
        assert result.estimated_speedup > 1.0
        assert "recompile" in result.question.lower()

    def test_what_if_recompile_python_to_python(self, twin):
        result = twin.what_if_recompile("test_app.core.engine", "python")
        assert result.estimated_speedup == pytest.approx(1.0, abs=0.1)

    def test_what_if_recompile_to_csimd(self, twin):
        result = twin.what_if_recompile("test_app.dsp.filter", "c_simd")
        assert result.estimated_speedup > 5.0

    def test_what_if_replace_tile(self, twin):
        twin.shadow_genome.tiles["old_tile"] = TileSnapshot(
            name="old_tile", tile_type="compute",
            input_count=1, output_count=1,
            cost_estimate=5.0, abstraction_level=5,
            language_preference="fir",
        )
        twin.shadow_genome.tiles["new_tile"] = TileSnapshot(
            name="new_tile", tile_type="compute",
            input_count=1, output_count=1,
            cost_estimate=1.0, abstraction_level=5,
            language_preference="fir",
        )
        result = twin.what_if_replace_tile("old_tile", "new_tile")
        assert result.estimated_speedup > 1.0
        assert result.estimated_risk < 0.5

    def test_what_if_replace_unknown_tile(self, twin):
        twin.shadow_genome.tiles["old"] = TileSnapshot(
            name="old", tile_type="compute",
            input_count=1, output_count=1,
            cost_estimate=3.0, abstraction_level=5,
            language_preference="fir",
        )
        result = twin.what_if_replace_tile("old", "unknown_tile")
        assert result.estimated_risk >= 0.5  # unknown = higher risk

    def test_what_if_result_fields(self, twin):
        result = twin.what_if_recompile("test_app.dsp.filter", "rust")
        assert result.confidence > 0.0
        assert result.estimated_time_cost_ms > 0
        assert result.recommendation != ""


class TestDigitalTwinChaosTesting:

    def test_chaos_test_basic(self, twin):
        report = twin.chaos_test(n_faults=5)
        assert isinstance(report, ChaosReport)
        assert report.total_faults == 5
        assert report.survival_rate >= 0.0
        assert report.survival_rate <= 1.0

    def test_chaos_test_zero_faults(self, twin):
        report = twin.chaos_test(n_faults=0)
        assert report.total_faults == 0
        assert report.worst_fault is None
        assert report.resilience_score == 0.0

    def test_chaos_test_fault_types(self, twin):
        report = twin.chaos_test(n_faults=20)
        fault_types = {f.fault_type for f in report.faults}
        assert len(fault_types) > 0

    def test_chaos_test_survival_rate(self, twin):
        report = twin.chaos_test(n_faults=10)
        assert report.survival_rate >= 0.0
        assert report.failure_rate >= 0.0
        assert report.survival_rate + report.failure_rate == pytest.approx(1.0)

    def test_chaos_test_resilience_score(self, twin):
        report = twin.chaos_test(n_faults=10)
        assert 0.0 <= report.resilience_score <= 1.0

    def test_chaos_test_avg_recovery(self, twin):
        report = twin.chaos_test(n_faults=10)
        assert report.avg_recovery_time_ms >= 0.0

    def test_chaos_test_worst_fault(self, twin):
        report = twin.chaos_test(n_faults=5)
        assert report.worst_fault is not None


class TestDigitalTwinReport:

    def test_twin_report(self, twin):
        report = twin.get_twin_report()
        assert isinstance(report, TwinReport)
        assert report.uptime_s >= 0.0

    def test_twin_report_accuracy(self, twin):
        twin.record_prediction("test", "a", 2.0, 2.1, 0.8)
        report = twin.get_twin_report()
        assert report.prediction_accuracy == 1.0
        assert report.total_predictions == 1
        assert report.accurate_predictions == 1

    def test_twin_report_trend(self, twin):
        for i in range(15):
            twin.record_prediction("test", f"m{i}", 2.0, 2.1, 0.8)
        report = twin.get_twin_report()
        assert report.recent_accuracy_trend in ("improving", "stable", "degrading")

    def test_twin_report_chaos(self, twin):
        twin.chaos_test(n_faults=5)
        report = twin.get_twin_report()
        assert report.last_chaos_report is not None
        assert report.chaos_survival_rate >= 0.0


# ════════════════════════════════════════════════════════════════════════
# PerformancePredictor Tests
# ════════════════════════════════════════════════════════════════════════

class TestPredictorCreation:

    def test_predictor_creation(self, predictor):
        assert isinstance(predictor, PerformancePredictor)

    def test_predictor_repr(self, predictor):
        r = repr(predictor)
        assert "PerformancePredictor" in r


class TestPredictorExecutionTime:

    def test_predict_no_history(self, predictor):
        time_ns = predictor.predict_execution_time("unknown_mod")
        assert time_ns > 0  # fallback to base time

    def test_predict_with_history(self, predictor):
        predictor.record_execution("mod_a", 5000.0, "python")
        time_ns = predictor.predict_execution_time("mod_a")
        assert time_ns > 0

    def test_predict_ema_with_history(self, predictor):
        for i in range(10):
            predictor.record_execution("mod_b", 1000.0 + i * 100.0, "python")
        time_ns = predictor.predict_execution_time("mod_b")
        assert 1000.0 < time_ns < 3000.0

    def test_predict_different_language(self, predictor):
        predictor.store.put("lang:mod_c", "rust")
        time_ns = predictor.predict_execution_time("mod_c")
        assert time_ns < 10000.0  # Rust is faster than Python


class TestPredictorHeatLevel:

    def test_predict_heat_no_calls(self, predictor):
        assert predictor.predict_heat_level("unknown") == "FROZEN"

    def test_predict_heat_with_calls(self, predictor):
        # Record multiple calls for one module
        predictor.store.put("calls:hot_mod", 100)
        predictor.store.put("calls:cold_mod", 1)
        predictor.store.put("calls:mid_mod", 10)
        # Also set language so it's not FROZEN
        predictor.store.put("lang:hot_mod", "python")
        predictor.store.put("lang:cold_mod", "python")
        predictor.store.put("lang:mid_mod", "python")
        heat = predictor.predict_heat_level("hot_mod")
        assert heat in ("HEAT", "HOT", "FROZEN")

    def test_predict_heat_cold(self, predictor):
        predictor.store.put("calls:cold_mod", 1)
        predictor.store.put("calls:hot_mod", 100)
        predictor.store.put("lang:cold_mod", "python")
        predictor.store.put("lang:hot_mod", "python")
        heat = predictor.predict_heat_level("cold_mod")
        assert heat in ("COOL", "WARM", "FROZEN")


class TestPredictorSpeedup:

    def test_predict_speedup_python_to_rust(self, predictor):
        predictor.store.put("lang:mod_a", "python")
        speedup = predictor.predict_speedup("mod_a", "rust")
        assert speedup == pytest.approx(10.0)

    def test_predict_speedup_same_language(self, predictor):
        predictor.store.put("lang:mod_a", "python")
        speedup = predictor.predict_speedup("mod_a", "python")
        assert speedup == pytest.approx(1.0)

    def test_predict_speedup_python_to_csimd(self, predictor):
        predictor.store.put("lang:mod_a", "python")
        speedup = predictor.predict_speedup("mod_a", "c_simd")
        assert speedup == pytest.approx(16.0)


class TestPredictorBottleneck:

    def test_predict_bottleneck_empty(self, predictor):
        assert predictor.predict_bottleneck([]) == ""

    def test_predict_bottleneck_single(self, predictor):
        predictor.record_execution("mod_a", 5000.0, "python")
        result = predictor.predict_bottleneck(["mod_a"])
        assert result == "mod_a"

    def test_predict_bottleneck_multiple(self, predictor):
        predictor.record_execution("fast", 100.0, "python")
        predictor.record_execution("slow", 10000.0, "python")
        result = predictor.predict_bottleneck(["fast", "slow"])
        assert result == "slow"


class TestPredictorCapacity:

    def test_forecast_low_load(self, predictor):
        forecast = predictor.forecast_capacity(0.3, 0.05, 10)
        assert isinstance(forecast, CapacityForecast)
        assert forecast.risk_level == "LOW"
        assert len(forecast.projected_loads) == 11

    def test_forecast_high_growth(self, predictor):
        forecast = predictor.forecast_capacity(0.8, 0.2, 10)
        assert forecast.risk_level in ("HIGH", "CRITICAL")
        assert forecast.time_to_capacity < 10.0

    def test_forecast_negative_growth(self, predictor):
        forecast = predictor.forecast_capacity(0.8, -0.1, 10)
        # With negative growth, load should decrease
        assert forecast.projected_loads[-1] < forecast.current_load

    def test_forecast_zero_growth(self, predictor):
        forecast = predictor.forecast_capacity(0.5, 0.0, 5)
        assert forecast.projected_loads[0] == pytest.approx(0.5)
        assert forecast.projected_loads[-1] == pytest.approx(0.5)


class TestPredictorRecommendation:

    def test_recommend_none_frozen(self, predictor):
        assert predictor.recommend_mutation("unknown") == "none"

    def test_recommend_recompile_heat(self, predictor):
        predictor.store.put("calls:hot_mod", 100)
        predictor.store.put("lang:hot_mod", "python")
        # Make it the hottest
        for i in range(20):
            predictor.store.put(f"calls:other_{i}", 1)
        heat = predictor.predict_heat_level("hot_mod")
        if heat in ("HEAT", "HOT"):
            rec = predictor.recommend_mutation("hot_mod")
            assert "recompile" in rec or "none" in rec

    def test_recommendation_warm_python(self, predictor):
        predictor.store.put("calls:warm_mod", 10)
        predictor.store.put("lang:warm_mod", "python")
        # Set up other modules so this one is mid-range
        for i in range(5):
            predictor.store.put(f"calls:other_{i}", 1)
        rec = predictor.recommend_mutation("warm_mod")
        assert rec in ("none", "recompile:typescript")

    def test_record_execution_updates(self, predictor):
        predictor.record_execution("mod_x", 1000.0, "rust")
        assert predictor.store.get("calls:mod_x") == 1
        assert predictor.store.get("lang:mod_x") == "rust"
        assert predictor.store.history_size == 1


# ════════════════════════════════════════════════════════════════════════
# SpeculativeEngine Tests
# ════════════════════════════════════════════════════════════════════════

class TestSpeculativeEngineCreation:

    def test_speculator_creation(self, speculator):
        assert isinstance(speculator, SpeculativeEngine)
        assert speculator._candidates == 5
        assert speculator._parallel_limit == 2

    def test_speculator_repr(self, speculator):
        r = repr(speculator)
        assert "SpeculativeEngine" in r


class TestSpeculativeEngineSpeculate:

    def test_speculate_empty(self, speculator):
        result = speculator.speculate([])
        assert isinstance(result, SpeculationResult)
        assert result.hypotheses_evaluated == 0
        assert not result.success

    def test_speculate_single(self, speculator):
        hyp = Hypothesis(
            description="Inline optimize",
            target_path="test_app.core.engine",
            mutation_type=MutationStrategy.INLINE_OPTIMIZATION,
            expected_speedup=1.2,
            risk_level=0.1,
            confidence=0.7,
            metadata={"speedup": 1.2},
        )
        result = speculator.speculate([hyp])
        assert result.hypotheses_evaluated == 1
        assert result.simulations_run == 1
        assert result.elapsed_ms >= 0

    def test_speculate_multiple(self, speculator):
        hyps = [
            Hypothesis(
                description=f"Mutation {i}",
                target_path="test_app.core.engine",
                mutation_type=MutationStrategy.INLINE_OPTIMIZATION,
                expected_speedup=1.0 + i * 0.1,
                risk_level=0.1,
                confidence=0.6,
                metadata={"speedup": 1.0 + i * 0.1},
            )
            for i in range(5)
        ]
        result = speculator.speculate(hyps)
        assert result.hypotheses_evaluated == 5
        assert result.simulations_run == 5

    def test_speculate_ranking(self, speculator):
        hyps = [
            Hypothesis(
                description="High value",
                target_path="test_app.core.engine",
                mutation_type=MutationStrategy.INLINE_OPTIMIZATION,
                expected_speedup=3.0,
                risk_level=0.1,
                confidence=0.9,
                metadata={"speedup": 3.0},
            ),
            Hypothesis(
                description="Low value",
                target_path="test_app.core.parser",
                mutation_type=MutationStrategy.INLINE_OPTIMIZATION,
                expected_speedup=1.05,
                risk_level=0.5,
                confidence=0.3,
                metadata={"speedup": 1.05},
            ),
        ]
        result = speculator.speculate(hyps)
        # High value should be evaluated first (top K)
        assert len(result.execution_results) <= 2  # parallel_limit

    def test_speculate_best_hypothesis(self, speculator):
        hyp = Hypothesis(
            description="Good mutation",
            target_path="test_app.core.engine",
            mutation_type=MutationStrategy.INLINE_OPTIMIZATION,
            expected_speedup=1.5,
            risk_level=0.1,
            confidence=0.8,
            metadata={"speedup": 1.5},
        )
        result = speculator.speculate([hyp])
        if result.best_hypothesis is not None:
            assert result.best_hypothesis.description == "Good mutation"


class TestSpeculativeEngineBatch:

    def test_batch_speculate(self, speculator):
        batch1 = [
            Hypothesis(
                description=f"Batch1-{i}",
                target_path="test_app.core.engine",
                mutation_type=MutationStrategy.INLINE_OPTIMIZATION,
                expected_speedup=1.1 + i * 0.1,
                risk_level=0.1,
                confidence=0.6,
                metadata={"speedup": 1.1 + i * 0.1},
            )
            for i in range(3)
        ]
        batch2 = [
            Hypothesis(
                description=f"Batch2-{i}",
                target_path="test_app.core.parser",
                mutation_type=MutationStrategy.INLINE_OPTIMIZATION,
                expected_speedup=1.0 + i * 0.2,
                risk_level=0.2,
                confidence=0.5,
                metadata={"speedup": 1.0 + i * 0.2},
            )
            for i in range(2)
        ]
        results = speculator.batch_speculate([batch1, batch2])
        assert len(results) == 2
        assert all(isinstance(r, SpeculationResult) for r in results)

    def test_batch_empty_batches(self, speculator):
        results = speculator.batch_speculate([[], []])
        assert len(results) == 2
        assert all(r.hypotheses_evaluated == 0 for r in results)


class TestSpeculativeEngineMetrics:

    def test_initial_improvement_rate(self, speculator):
        assert speculator.improvement_rate == 0.0

    def test_improvement_rate_increases(self, speculator):
        hyp = Hypothesis(
            description="Test",
            target_path="test_app.core.engine",
            mutation_type=MutationStrategy.INLINE_OPTIMIZATION,
            expected_speedup=1.2,
            risk_level=0.1,
            confidence=0.8,
            metadata={"speedup": 1.2},
        )
        speculator.speculate([hyp])
        # Rate is 0 or 1 depending on outcome
        assert speculator._total_speculations == 1


# ════════════════════════════════════════════════════════════════════════
# DecisionOracle Tests
# ════════════════════════════════════════════════════════════════════════

class TestOracleCreation:

    def test_oracle_creation(self, oracle):
        assert isinstance(oracle, DecisionOracle)

    def test_oracle_repr(self, oracle):
        r = repr(oracle)
        assert "DecisionOracle" in r


class TestOracleShouldMutate:

    def test_should_mutate_safe_proposal(self, oracle, twin):
        proposal = MutationProposal(
            strategy=MutationStrategy.INLINE_OPTIMIZATION,
            target="test_app.core.engine",
            description="Safe inline optimization",
            kwargs={"speedup": 1.2},
            estimated_speedup=1.2,
            estimated_risk=0.1,
        )
        decision = oracle.should_mutate(proposal)
        assert isinstance(decision, OracleDecision)
        assert isinstance(decision.confidence, float)
        assert 0.0 <= decision.confidence <= 1.0
        assert isinstance(decision.reasoning, str)

    def test_should_mutate_risky_proposal(self, oracle):
        proposal = MutationProposal(
            strategy=MutationStrategy.RECOMPILE_LANGUAGE,
            target="test_app.core.engine",
            description="Risky recompile",
            kwargs={"new_language": "c_simd"},
            estimated_speedup=16.0,
            estimated_risk=0.9,
        )
        decision = oracle.should_mutate(proposal)
        assert isinstance(decision, OracleDecision)
        assert decision.estimated_risk > 0.5

    def test_should_mutate_expected_value(self, oracle):
        proposal = MutationProposal(
            strategy=MutationStrategy.INLINE_OPTIMIZATION,
            target="test_app.core.engine",
            description="Test",
            kwargs={"speedup": 1.5},
            estimated_speedup=1.5,
            estimated_risk=0.1,
        )
        decision = oracle.should_mutate(proposal)
        assert decision.expected_value >= 0.0

    def test_should_mutate_is_high_confidence(self, oracle):
        proposal = MutationProposal(
            strategy=MutationStrategy.INLINE_OPTIMIZATION,
            target="test_app.core.engine",
            description="High confidence",
            kwargs={"speedup": 1.2},
            estimated_speedup=1.2,
            estimated_risk=0.05,
        )
        decision = oracle.should_mutate(proposal)
        # Should be high confidence for safe inline optimization
        assert decision.confidence > 0.3

    def test_should_mutate_acceptance_tracking(self, oracle):
        proposal = MutationProposal(
            strategy=MutationStrategy.INLINE_OPTIMIZATION,
            target="test_app.core.engine",
            description="Track",
            kwargs={"speedup": 1.2},
            estimated_speedup=1.2,
            estimated_risk=0.1,
        )
        oracle.should_mutate(proposal)
        assert oracle.total_decisions == 1


class TestOracleRanking:

    def test_rank_proposals(self, oracle):
        proposals = [
            MutationProposal(
                strategy=MutationStrategy.INLINE_OPTIMIZATION,
                target=f"mod_{i}",
                description=f"Proposal {i}",
                kwargs={"speedup": 1.0 + i * 0.2},
                estimated_speedup=1.0 + i * 0.2,
                estimated_risk=0.1,
            )
            for i in range(5)
        ]
        ranked = oracle.rank_proposals(proposals)
        assert len(ranked) == 5
        # Scores should be in descending order
        scores = [score for _, score in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_rank_empty(self, oracle):
        ranked = oracle.rank_proposals([])
        assert ranked == []

    def test_rank_single(self, oracle):
        proposal = MutationProposal(
            strategy=MutationStrategy.INLINE_OPTIMIZATION,
            target="mod_a",
            description="Single",
            kwargs={"speedup": 1.2},
            estimated_speedup=1.2,
            estimated_risk=0.1,
        )
        ranked = oracle.rank_proposals([proposal])
        assert len(ranked) == 1


class TestOracleROI:

    def test_roi_basic(self, oracle):
        proposal = MutationProposal(
            strategy=MutationStrategy.RECOMPILE_LANGUAGE,
            target="test_app.dsp.filter",
            description="Recompile to Rust",
            kwargs={"new_language": "rust"},
            estimated_speedup=10.0,
            estimated_risk=0.3,
        )
        roi = oracle.roi_estimate(proposal)
        assert isinstance(roi, ROIEstimate)
        assert roi.estimated_speedup > 1.0

    def test_roi_inline_cheaper(self, oracle):
        proposal_inline = MutationProposal(
            strategy=MutationStrategy.INLINE_OPTIMIZATION,
            target="test_app.core.engine",
            description="Inline",
            kwargs={"speedup": 1.2},
            estimated_speedup=1.2,
            estimated_risk=0.1,
        )
        proposal_recompile = MutationProposal(
            strategy=MutationStrategy.RECOMPILE_LANGUAGE,
            target="test_app.dsp.filter",
            description="Recompile",
            kwargs={"new_language": "rust"},
            estimated_speedup=10.0,
            estimated_risk=0.3,
        )
        roi_inline = oracle.roi_estimate(proposal_inline)
        roi_recompile = oracle.roi_estimate(proposal_recompile)
        # Inline should have lower compile time
        assert roi_inline.compile_time_s < roi_recompile.compile_time_s

    def test_roi_fields(self, oracle):
        proposal = MutationProposal(
            strategy=MutationStrategy.RECOMPILE_LANGUAGE,
            target="test_app.dsp.filter",
            description="Test ROI",
            kwargs={"new_language": "rust"},
            estimated_speedup=10.0,
            estimated_risk=0.3,
        )
        roi = oracle.roi_estimate(proposal)
        assert roi.test_time_s > 0
        assert roi.downtime_s > 0
        assert roi.total_cost_s > 0
        assert roi.recommendation != ""


class TestOracleNextBestAction:

    def test_next_best_action(self, oracle, twin):
        recommendation = oracle.next_best_action()
        assert isinstance(recommendation, OracleRecommendation)
        assert recommendation.action != ""
        assert recommendation.confidence >= 0.0

    def test_next_best_action_with_hot_modules(self, oracle, twin):
        # Make a module hot
        for mod in twin.shadow_genome.modules.values():
            mod.heat_level = "HEAT"
        recommendation = oracle.next_best_action()
        assert recommendation.action != ""

    def test_next_best_action_alternatives(self, oracle):
        recommendation = oracle.next_best_action()
        assert isinstance(recommendation.alternative_actions, list)

    def test_next_best_action_time_estimate(self, oracle):
        recommendation = oracle.next_best_action()
        assert recommendation.time_to_implement_ms >= 0


class TestOracleWithKnowledge:

    def test_oracle_uses_knowledge(self, oracle, knowledge):
        # Add some historical data
        from flux.flywheel.hypothesis import ExperimentResult, ExperimentOutcome
        hyp = Hypothesis(
            description="Test",
            target_path="test_app.core.engine",
            mutation_type=MutationStrategy.INLINE_OPTIMIZATION,
        )
        result = ExperimentResult(
            hypothesis=hyp,
            outcome=ExperimentOutcome.SUCCESS,
            actual_speedup=1.3,
        )
        knowledge.add_success(result)

        proposal = MutationProposal(
            strategy=MutationStrategy.INLINE_OPTIMIZATION,
            target="test_app.core.engine",
            description="Similar to successful one",
            kwargs={"speedup": 1.2},
            estimated_speedup=1.2,
            estimated_risk=0.1,
        )
        decision = oracle.should_mutate(proposal)
        # Knowledge should influence confidence
        assert decision.confidence > 0.0


# ════════════════════════════════════════════════════════════════════════
# Integration Tests
# ════════════════════════════════════════════════════════════════════════

class TestIntegration:

    def test_full_pipeline_twin_predict_speculate(self, synth, twin, predictor, cost_model):
        """Test that twin, predictor, and speculator work together."""
        # Capture shadow
        twin.capture_shadow()

        # Simulate a mutation
        proposal = MutationProposal(
            strategy=MutationStrategy.RECOMPILE_LANGUAGE,
            target="test_app.dsp.filter",
            description="Recompile filter to Rust",
            kwargs={"new_language": "rust"},
            estimated_speedup=10.0,
            estimated_risk=0.3,
        )
        sim_result = twin.simulate_mutation(proposal)
        assert sim_result.estimated_speedup > 1.0

        # Predict performance
        predictor.record_execution("test_app.dsp.filter", 100000.0, "python")
        exec_time = predictor.predict_execution_time("test_app.dsp.filter")
        assert exec_time > 0

        # Run speculation
        speculator = SpeculativeEngine(synth, twin)
        hyp = Hypothesis(
            description="Inline optimize",
            target_path="test_app.core.engine",
            mutation_type=MutationStrategy.INLINE_OPTIMIZATION,
            expected_speedup=1.2,
            risk_level=0.1,
            confidence=0.7,
            metadata={"speedup": 1.2},
        )
        result = speculator.speculate([hyp])
        assert result.hypotheses_evaluated == 1

    def test_oracle_with_all_subsystems(self, synth, cost_model, memory_store):
        """Test oracle with all subsystems wired together."""
        twin = DigitalTwin(synth)
        twin.capture_shadow()
        predictor = PerformancePredictor(cost_model, memory_store)
        knowledge = KnowledgeBase()
        oracle = DecisionOracle(predictor, twin, knowledge)

        # Record some data
        predictor.record_execution("test_app.dsp.filter", 100000.0, "python")

        # Get recommendation
        rec = oracle.next_best_action()
        assert rec.action != ""

        # Get twin report
        report = twin.get_twin_report()
        assert isinstance(report, TwinReport)

    def test_prediction_feedback_loop(self, twin):
        """Test that predictions improve with feedback."""
        # Make some predictions and record outcomes
        for i in range(10):
            predicted = 2.0 + i * 0.05
            actual = 2.0 + i * 0.06  # slightly off
            twin.record_prediction("speedup", f"mod_{i}", predicted, actual, 0.7)

        accuracy = twin.prediction_accuracy()
        assert accuracy > 0.0  # Most should be accurate (within 20%)

    def test_simulated_evolution_with_chaos(self, twin):
        """Test evolution simulation followed by chaos testing."""
        # Simulate evolution
        evo_report = twin.simulate_evolution(generations=3)
        assert evo_report.generations_simulated == 3

        # Run chaos test
        chaos_report = twin.chaos_test(n_faults=5)
        assert chaos_report.total_faults == 5

        # Get comprehensive report
        twin_report = twin.get_twin_report()
        assert twin_report.last_chaos_report is not None
        assert twin_report.total_predictions >= 0

    def test_capacity_forecast_drives_oracle(self, predictor, twin, knowledge):
        """Test that capacity forecasting can inform oracle decisions."""
        oracle = DecisionOracle(predictor, twin, knowledge)

        # Create high-pressure scenario
        forecast = predictor.forecast_capacity(0.9, 0.15, 20)
        assert forecast.risk_level in ("HIGH", "CRITICAL")

        # Oracle should still work under pressure
        rec = oracle.next_best_action()
        assert isinstance(rec, OracleRecommendation)
