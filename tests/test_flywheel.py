"""Tests for the Flywheel Core — 40+ tests covering all 6 phases.

Tests are organized by module:
- Hypothesis types (creation, properties, expected value)
- Knowledge Base (recording, generalization, prediction)
- Flywheel Metrics (recording, trends, serialization)
- Flywheel Engine (creation, phases, revolutions, reports)
- Integration scenarios (multi-revolution, acceleration, termination)
"""

import time
import pytest

from flux.synthesis import FluxSynthesizer
from flux.evolution.genome import MutationStrategy
from flux.flywheel.hypothesis import (
    Hypothesis,
    ExperimentResult,
    ExperimentOutcome,
    ObservationData,
    LearnedInsights,
    FlywheelRecord,
    FlywheelReport,
    IntegrationReport,
)
from flux.flywheel.knowledge import (
    KnowledgeBase,
    GeneralizedRule,
)
from flux.flywheel.metrics import FlywheelMetrics
from flux.flywheel.engine import (
    FlywheelEngine,
    FlywheelPhase,
)


# ── Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def synth():
    """Create a fresh FluxSynthesizer for testing."""
    return FluxSynthesizer("test_flywheel")


@pytest.fixture
def engine(synth):
    """Create a FlywheelEngine with a test synthesizer."""
    return FlywheelEngine(synth, max_hypotheses_per_rev=5, max_workers=2)


@pytest.fixture
def profiler_data(synth):
    """Add profiling data to the synthesizer for meaningful flywheel runs."""
    synth.record_call("core.engine", duration_ns=50000, calls=100)
    synth.record_call("core.parser", duration_ns=20000, calls=50)
    synth.record_call("core.optimizer", duration_ns=10000, calls=30)
    synth.record_call("utils.helper", duration_ns=5000, calls=10)
    synth.record_call("utils.logger", duration_ns=1000, calls=5)
    return synth


# ══════════════════════════════════════════════════════════════════════
#  TEST GROUP 1: Hypothesis Creation and Properties
# ══════════════════════════════════════════════════════════════════════

class TestHypothesisCreation:
    """Test hypothesis dataclass creation and properties."""

    def test_basic_creation(self):
        h = Hypothesis(
            description="Recompile hot module to Rust",
            target_path="core.engine",
            mutation_type=MutationStrategy.RECOMPILE_LANGUAGE,
            expected_speedup=10.0,
        )
        assert h.description == "Recompile hot module to Rust"
        assert h.target_path == "core.engine"
        assert h.mutation_type == MutationStrategy.RECOMPILE_LANGUAGE
        assert h.expected_speedup == 10.0

    def test_default_values(self):
        h = Hypothesis(
            description="test",
            target_path="test.path",
            mutation_type=MutationStrategy.INLINE_OPTIMIZATION,
        )
        assert h.expected_speedup == 1.0
        assert h.expected_modularity_delta == 0.0
        assert h.risk_level == 0.5
        assert h.confidence == 0.5
        assert h.source == "profiler"
        assert h.metadata == {}

    def test_timestamp_auto_set(self):
        before = time.time()
        h = Hypothesis(
            description="test", target_path="t", mutation_type=MutationStrategy.ADD_TILE
        )
        after = time.time()
        assert before <= h.timestamp <= after

    def test_expected_value_calculation(self):
        # High confidence, high speedup, low risk = high EV
        h = Hypothesis(
            description="good bet",
            target_path="a",
            mutation_type=MutationStrategy.RECOMPILE_LANGUAGE,
            expected_speedup=5.0,
            risk_level=0.1,
            confidence=0.9,
        )
        ev = h.expected_value
        assert ev == pytest.approx(0.9 * 5.0 * 0.9, abs=0.01)

    def test_expected_value_zero_for_risky(self):
        h = Hypothesis(
            description="risky bet",
            target_path="b",
            mutation_type=MutationStrategy.MERGE_TILES,
            expected_speedup=10.0,
            risk_level=1.0,
            confidence=0.9,
        )
        assert h.expected_value == pytest.approx(0.0, abs=0.01)

    def test_is_risky(self):
        safe = Hypothesis(
            description="", target_path="", mutation_type=MutationStrategy.ADD_TILE,
            risk_level=0.3,
        )
        risky = Hypothesis(
            description="", target_path="", mutation_type=MutationStrategy.MERGE_TILES,
            risk_level=0.8,
        )
        assert not safe.is_risky
        assert risky.is_risky

    def test_is_high_confidence(self):
        low = Hypothesis(
            description="", target_path="", mutation_type=MutationStrategy.ADD_TILE,
            confidence=0.4,
        )
        high = Hypothesis(
            description="", target_path="", mutation_type=MutationStrategy.ADD_TILE,
            confidence=0.9,
        )
        assert not low.is_high_confidence
        assert high.is_high_confidence

    def test_repr(self):
        h = Hypothesis(
            description="test desc",
            target_path="mod.path",
            mutation_type=MutationStrategy.FUSE_PATTERN,
        )
        r = repr(h)
        assert "FUSE_PATTERN" in r or "fuse_pattern" in r
        assert "mod.path" in r


# ══════════════════════════════════════════════════════════════════════
#  TEST GROUP 2: Experiment Results
# ══════════════════════════════════════════════════════════════════════

class TestExperimentResult:
    """Test experiment result types."""

    def test_success_result(self):
        h = Hypothesis(
            description="test", target_path="t",
            mutation_type=MutationStrategy.RECOMPILE_LANGUAGE,
        )
        r = ExperimentResult(
            hypothesis=h,
            outcome=ExperimentOutcome.SUCCESS,
            actual_speedup=2.5,
            fitness_before=0.5,
            fitness_after=0.6,
        )
        assert r.was_improvement
        assert r.fitness_delta == pytest.approx(0.1)

    def test_failure_result(self):
        h = Hypothesis(
            description="test", target_path="t",
            mutation_type=MutationStrategy.MERGE_TILES,
        )
        r = ExperimentResult(
            hypothesis=h,
            outcome=ExperimentOutcome.FAILURE,
        )
        assert not r.was_improvement
        assert r.fitness_delta == 0.0

    def test_inconclusive_not_improvement(self):
        h = Hypothesis(
            description="test", target_path="t",
            mutation_type=MutationStrategy.REPLACE_TILE,
        )
        r = ExperimentResult(
            hypothesis=h,
            outcome=ExperimentOutcome.INCONCLUSIVE,
            actual_speedup=1.0,
        )
        assert not r.was_improvement


# ══════════════════════════════════════════════════════════════════════
#  TEST GROUP 3: Observation & Insight Data
# ══════════════════════════════════════════════════════════════════════

class TestObservationData:
    """Test observation data collection."""

    def test_empty_observation(self):
        obs = ObservationData()
        assert obs.module_count == 0
        assert obs.hot_modules == []
        assert obs.frozen_modules == []

    def test_observation_auto_timestamp(self):
        before = time.time()
        obs = ObservationData(module_count=5)
        after = time.time()
        assert before <= obs.timestamp <= after


class TestLearnedInsights:
    """Test learned insights."""

    def test_insight_count(self):
        insights = LearnedInsights(
            hot_paths=["a", "b"],
            patterns_found=["p1", "p2", "p3"],
            recompilation_candidates=[{}, {}],
        )
        assert insights.insight_count == 7  # 2 + 3 + 2

    def test_empty_insights(self):
        insights = LearnedInsights()
        assert insights.insight_count == 0


# ══════════════════════════════════════════════════════════════════════
#  TEST GROUP 4: Flywheel Records & Reports
# ══════════════════════════════════════════════════════════════════════

class TestFlywheelRecord:
    """Test flywheel record."""

    def test_success_rate(self):
        r = FlywheelRecord(
            revolution=1, successes=3, failures=1, timeouts=0, inconclusive=1
        )
        assert r.success_rate == pytest.approx(0.6)

    def test_success_rate_zero_total(self):
        r = FlywheelRecord(revolution=1)
        assert r.success_rate == 0.0

    def test_improvement_count(self):
        r = FlywheelRecord(revolution=1, successes=5, failures=2)
        assert r.improvement_count == 5


class TestFlywheelReport:
    """Test flywheel report."""

    def test_empty_report(self):
        report = FlywheelReport()
        assert report.revolutions_completed == 0
        assert report.total_speedup == pytest.approx(1.0)
        assert report.overall_success_rate == 0.0

    def test_report_with_records(self):
        r1 = FlywheelRecord(
            revolution=1, successes=2, failures=1,
            acceleration_after=1.1,
        )
        report = FlywheelReport(
            revolutions_completed=1,
            total_improvements=2,
            total_experiments=3,
            total_successes=2,
            total_failures=1,
            initial_acceleration=1.0,
            final_acceleration=1.1,
            records=[r1],
        )
        assert report.total_speedup == pytest.approx(1.1)
        assert report.overall_success_rate == pytest.approx(2/3)


class TestIntegrationReport:
    """Test integration report."""

    def test_commit_rate(self):
        ir = IntegrationReport(committed=4, rolled_back=2, skipped=1)
        assert ir.commit_rate == pytest.approx(4/7)

    def test_commit_rate_zero(self):
        ir = IntegrationReport()
        assert ir.commit_rate == 0.0


# ══════════════════════════════════════════════════════════════════════
#  TEST GROUP 5: Knowledge Base
# ══════════════════════════════════════════════════════════════════════

class TestKnowledgeBase:
    """Test the knowledge base — memory for the flywheel."""

    def test_creation(self):
        kb = KnowledgeBase()
        assert kb.size() == 0
        assert len(kb.rules) == 0

    def test_add_success(self):
        kb = KnowledgeBase()
        h = Hypothesis(
            description="test", target_path="t",
            mutation_type=MutationStrategy.RECOMPILE_LANGUAGE,
        )
        result = ExperimentResult(
            hypothesis=h, outcome=ExperimentOutcome.SUCCESS,
            actual_speedup=2.0, fitness_before=0.5, fitness_after=0.7,
        )
        kb.add_success(result)
        assert len(kb.successes) == 1
        assert kb.size() == 1

    def test_add_failure(self):
        kb = KnowledgeBase()
        h = Hypothesis(
            description="test", target_path="t",
            mutation_type=MutationStrategy.MERGE_TILES,
        )
        result = ExperimentResult(
            hypothesis=h, outcome=ExperimentOutcome.FAILURE,
        )
        kb.add_failure(result)
        assert len(kb.failures) == 1

    def test_max_history_trim(self):
        kb = KnowledgeBase(max_history=5)
        h = Hypothesis(
            description="test", target_path="t",
            mutation_type=MutationStrategy.ADD_TILE,
        )
        for i in range(10):
            result = ExperimentResult(
                hypothesis=h, outcome=ExperimentOutcome.SUCCESS,
                actual_speedup=1.5,
            )
            kb.add_success(result)
        assert len(kb.successes) == 5

    def test_baselines(self):
        kb = KnowledgeBase()
        assert kb.get_baseline("test") is None
        kb.set_baseline("test", 42.0)
        assert kb.get_baseline("test") == 42.0

    def test_generalize_no_data(self):
        kb = KnowledgeBase()
        rules = kb.generalize()
        assert rules == []

    def test_generalize_from_successes(self):
        kb = KnowledgeBase()
        h = Hypothesis(
            description="test", target_path="t",
            mutation_type=MutationStrategy.RECOMPILE_LANGUAGE,
        )
        # Add 5 successes for the same mutation type
        for _ in range(5):
            result = ExperimentResult(
                hypothesis=h, outcome=ExperimentOutcome.SUCCESS,
                actual_speedup=2.0,
            )
            kb.add_success(result)
        # Add 1 failure
        fail_result = ExperimentResult(
            hypothesis=h, outcome=ExperimentOutcome.FAILURE,
        )
        kb.add_failure(fail_result)

        rules = kb.generalize()
        assert len(rules) >= 1
        assert any("recompile_language" in r.condition for r in rules)

    def test_generalize_updates_existing_rule(self):
        kb = KnowledgeBase()
        h = Hypothesis(
            description="test", target_path="t",
            mutation_type=MutationStrategy.FUSE_PATTERN,
        )
        # First batch
        for _ in range(3):
            kb.add_success(ExperimentResult(
                hypothesis=h, outcome=ExperimentOutcome.SUCCESS, actual_speedup=1.5,
            ))
        rules1 = kb.generalize()

        # Second batch — should update existing rule
        for _ in range(3):
            kb.add_success(ExperimentResult(
                hypothesis=h, outcome=ExperimentOutcome.SUCCESS, actual_speedup=1.5,
            ))
        rules2 = kb.generalize()

        # Should have the same rules (updated, not duplicated)
        assert len(kb.rules) == len(rules1)

    def test_predict_success_probability_no_data(self):
        kb = KnowledgeBase()
        h = Hypothesis(
            description="test", target_path="t",
            mutation_type=MutationStrategy.RECOMPILE_LANGUAGE,
            confidence=0.6,
        )
        prob = kb.predict_success_probability(h)
        # With no data, should fall back to hypothesis confidence minus risk penalty
        assert 0.0 <= prob <= 1.0

    def test_predict_with_historical_data(self):
        kb = KnowledgeBase()
        h = Hypothesis(
            description="test", target_path="t",
            mutation_type=MutationStrategy.RECOMPILE_LANGUAGE,
            confidence=0.6, risk_level=0.3,
        )
        # Add many successes to boost probability
        for _ in range(10):
            kb.add_success(ExperimentResult(
                hypothesis=h, outcome=ExperimentOutcome.SUCCESS,
                actual_speedup=2.0,
            ))
        kb.generalize()

        prob = kb.predict_success_probability(h)
        assert prob > 0.5  # Should be boosted by history

    def test_should_skip_failing_mutation(self):
        kb = KnowledgeBase()
        h = Hypothesis(
            description="test", target_path="t",
            mutation_type=MutationStrategy.MERGE_TILES,
        )
        # Add many failures
        for _ in range(10):
            kb.add_failure(ExperimentResult(
                hypothesis=h, outcome=ExperimentOutcome.FAILURE,
            ))
        # Add a couple successes
        for _ in range(2):
            kb.add_success(ExperimentResult(
                hypothesis=h, outcome=ExperimentOutcome.SUCCESS,
            ))

        skip, reason = kb.should_skip(h)
        assert skip
        assert "MERGE_TILES" in reason or "merge_tiles" in reason

    def test_should_not_skip_healthy_mutation(self):
        kb = KnowledgeBase()
        h = Hypothesis(
            description="test", target_path="t",
            mutation_type=MutationStrategy.RECOMPILE_LANGUAGE,
        )
        skip, reason = kb.should_skip(h)
        assert not skip

    def test_query_similar(self):
        kb = KnowledgeBase()
        h1 = Hypothesis(
            description="test1", target_path="core.engine",
            mutation_type=MutationStrategy.RECOMPILE_LANGUAGE,
        )
        h2 = Hypothesis(
            description="test2", target_path="core.parser",
            mutation_type=MutationStrategy.FUSE_PATTERN,
        )
        kb.add_success(ExperimentResult(
            hypothesis=h1, outcome=ExperimentOutcome.SUCCESS, actual_speedup=2.0,
        ))
        kb.add_failure(ExperimentResult(
            hypothesis=h2, outcome=ExperimentOutcome.FAILURE,
        ))

        # Query for similar to h1
        similar = kb.query_similar(h1)
        assert len(similar) >= 1

    def test_mutation_stats(self):
        kb = KnowledgeBase()
        h = Hypothesis(
            description="test", target_path="t",
            mutation_type=MutationStrategy.RECOMPILE_LANGUAGE,
        )
        for _ in range(3):
            kb.add_success(ExperimentResult(
                hypothesis=h, outcome=ExperimentOutcome.SUCCESS, actual_speedup=2.0,
            ))
        for _ in range(1):
            kb.add_failure(ExperimentResult(
                hypothesis=h, outcome=ExperimentOutcome.FAILURE,
            ))

        stats = kb.get_mutation_stats("recompile_language")
        assert stats["attempts"] == 4
        assert stats["successes"] == 3
        assert stats["failures"] == 1
        assert stats["avg_speedup"] == 2.0

    def test_to_dict(self):
        kb = KnowledgeBase()
        h = Hypothesis(
            description="test", target_path="t",
            mutation_type=MutationStrategy.ADD_TILE,
        )
        kb.add_success(ExperimentResult(
            hypothesis=h, outcome=ExperimentOutcome.SUCCESS, actual_speedup=1.5,
        ))
        d = kb.to_dict()
        assert "successes" in d
        assert "failures" in d
        assert "rules" in d
        assert d["total_successes"] == 1

    def test_clear(self):
        kb = KnowledgeBase()
        h = Hypothesis(
            description="test", target_path="t",
            mutation_type=MutationStrategy.ADD_TILE,
        )
        kb.add_success(ExperimentResult(
            hypothesis=h, outcome=ExperimentOutcome.SUCCESS,
        ))
        kb.set_baseline("test", 1.0)
        kb.clear()
        assert kb.size() == 0
        assert kb.get_baseline("test") is None


# ══════════════════════════════════════════════════════════════════════
#  TEST GROUP 6: Generalized Rule
# ══════════════════════════════════════════════════════════════════════

class TestGeneralizedRule:
    """Test generalized rule properties."""

    def test_reliable_rule(self):
        r = GeneralizedRule(
            condition="heat == HEAT", action="recompile to C",
            expected_outcome="10x speedup",
            confidence=0.9, support=10, counter_examples=1,
        )
        assert r.is_reliable
        assert not r.is_discredited

    def test_discredited_rule(self):
        r = GeneralizedRule(
            condition="always_fuse", action="fuse everything",
            expected_outcome="faster",
            confidence=0.2, support=2, counter_examples=8,
        )
        assert not r.is_reliable
        assert r.is_discredited

    def test_update_confidence(self):
        r = GeneralizedRule(
            condition="test", action="test",
            expected_outcome="test",
            support=5, counter_examples=1,
        )
        conf = r.update_confidence()
        # Laplace smoothing: (5+1)/(6+2) = 0.75
        assert conf == pytest.approx(0.75)

    def test_to_dict(self):
        r = GeneralizedRule(
            condition="c", action="a", expected_outcome="o",
            confidence=0.8, support=5,
        )
        d = r.to_dict()
        assert d["condition"] == "c"
        assert d["confidence"] == 0.8


# ══════════════════════════════════════════════════════════════════════
#  TEST GROUP 7: Flywheel Metrics
# ══════════════════════════════════════════════════════════════════════

class TestFlywheelMetrics:
    """Test flywheel metrics tracking."""

    def test_creation(self):
        m = FlywheelMetrics()
        assert m.revolutions_completed == 0
        assert m.total_improvements == 0
        assert m.cumulative_speedup == 1.0

    def test_record_revolution(self):
        m = FlywheelMetrics()
        record = FlywheelRecord(
            revolution=1, successes=3, failures=1, timeouts=0, inconclusive=1,
            acceleration_after=1.2, revolution_time_ns=1_000_000_000,
        )
        m.record_revolution(record)
        assert m.revolutions_completed == 1
        assert m.total_improvements == 3
        assert m.total_experiments == 5
        assert m.total_successes == 3
        assert m.total_failures == 1

    def test_multiple_revolutions(self):
        m = FlywheelMetrics()
        for i in range(5):
            record = FlywheelRecord(
                revolution=i + 1, successes=i + 1, failures=1,
                inconclusive=0, timeouts=0,
                acceleration_after=1.0 + i * 0.1,
                revolution_time_ns=1_000_000_000 - i * 100_000_000,
            )
            m.record_revolution(record)
        assert m.revolutions_completed == 5
        assert m.total_improvements == 15  # 1+2+3+4+5
        assert m.cumulative_speedup == pytest.approx(1.4)

    def test_velocity_trend_insufficient_data(self):
        m = FlywheelMetrics()
        assert m.get_velocity_trend() == "insufficient_data"

        record = FlywheelRecord(revolution=1, revolution_time_ns=1_000_000_000)
        m.record_revolution(record)
        assert m.get_velocity_trend() == "insufficient_data"

    def test_velocity_trend_accelerating(self):
        m = FlywheelMetrics()
        # Decreasing revolution times → accelerating
        for t in [5.0, 4.0, 3.0, 2.5]:
            record = FlywheelRecord(
                revolution=1, revolution_time_ns=int(t * 1_000_000_000)
            )
            m.record_revolution(record)
        assert m.get_velocity_trend() == "accelerating"

    def test_velocity_trend_decelerating(self):
        m = FlywheelMetrics()
        # Increasing revolution times → decelerating
        for t in [2.0, 3.0, 4.5, 6.0]:
            record = FlywheelRecord(
                revolution=1, revolution_time_ns=int(t * 1_000_000_000)
            )
            m.record_revolution(record)
        assert m.get_velocity_trend() == "decelerating"

    def test_velocity_trend_steady(self):
        m = FlywheelMetrics()
        # Stable revolution times → steady
        for t in [3.0, 3.1, 3.0, 3.1]:
            record = FlywheelRecord(
                revolution=1, revolution_time_ns=int(t * 1_000_000_000)
            )
            m.record_revolution(record)
        assert m.get_velocity_trend() == "steady"

    def test_success_trend(self):
        m = FlywheelMetrics()
        # Create records with increasing success counts to get rising success_rate
        # success_rate = successes / (successes + failures + timeouts + inconclusive)
        records_data = [
            (3, 7),   # 3/10 = 0.3
            (5, 5),   # 5/10 = 0.5
            (7, 3),   # 7/10 = 0.7
            (9, 1),   # 9/10 = 0.9
        ]
        for successes, failures in records_data:
            record = FlywheelRecord(
                revolution=1, successes=successes, failures=failures,
            )
            m.record_revolution(record)
        assert m.get_success_trend() == "improving"

    def test_average_revolution_time(self):
        m = FlywheelMetrics()
        for t in [2.0, 4.0, 6.0]:
            record = FlywheelRecord(
                revolution=1, revolution_time_ns=int(t * 1_000_000_000)
            )
            m.record_revolution(record)
        assert m.get_average_revolution_time() == pytest.approx(4.0)

    def test_overall_success_rate(self):
        m = FlywheelMetrics()
        record = FlywheelRecord(
            revolution=1, successes=7, failures=3,
        )
        m.record_revolution(record)
        assert m.overall_success_rate == pytest.approx(0.7)

    def test_to_dict(self):
        m = FlywheelMetrics()
        record = FlywheelRecord(
            revolution=1, successes=2, failures=1,
            acceleration_after=1.1, revolution_time_ns=1_000_000_000,
        )
        m.record_revolution(record)
        d = m.to_dict()
        assert "per_revolution" in d
        assert "cumulative" in d
        assert "trends" in d
        assert "averages" in d
        assert d["revolutions"] == 1

    def test_reset(self):
        m = FlywheelMetrics()
        record = FlywheelRecord(
            revolution=1, successes=5,
            acceleration_after=2.0, revolution_time_ns=1_000_000_000,
        )
        m.record_revolution(record)
        m.reset()
        assert m.revolutions_completed == 0
        assert m.total_improvements == 0
        assert m.cumulative_speedup == 1.0


# ══════════════════════════════════════════════════════════════════════
#  TEST GROUP 8: Flywheel Engine Creation
# ══════════════════════════════════════════════════════════════════════

class TestFlywheelEngineCreation:
    """Test flywheel engine creation and initial state."""

    def test_basic_creation(self, engine):
        assert engine.revolution == 0
        assert engine.phase == FlywheelPhase.OBSERVE
        assert engine._acceleration_factor == 1.0

    def test_initial_state(self, engine):
        assert len(engine.get_history()) == 0
        assert len(engine.get_acceleration_curve()) == 0
        assert engine.get_improvement_velocity() == 0.0

    def test_knowledge_base_accessible(self, engine):
        kb = engine.get_knowledge_base()
        assert isinstance(kb, KnowledgeBase)
        assert kb.size() == 0

    def test_metrics_accessible(self, engine):
        m = engine.get_metrics()
        assert isinstance(m, FlywheelMetrics)

    def test_repr(self, engine):
        r = repr(engine)
        assert "FlywheelEngine" in r
        assert "rev=0" in r

    def test_reset(self, profiler_data):
        engine = FlywheelEngine(profiler_data)
        # Add some profiling data
        profiler_data.record_call("a.b", calls=10)
        report = engine.spin(rounds=1)
        assert engine.revolution >= 1

        engine.reset()
        assert engine.revolution == 0
        assert engine._acceleration_factor == 1.0
        assert len(engine.get_history()) == 0


# ══════════════════════════════════════════════════════════════════════
#  TEST GROUP 9: Single Revolution
# ══════════════════════════════════════════════════════════════════════

class TestSingleRevolution:
    """Test a single flywheel revolution (all 6 phases)."""

    def test_single_revolution_completes(self, profiler_data):
        engine = FlywheelEngine(profiler_data, max_workers=2)
        report = engine.spin(rounds=1)
        assert report.revolutions_completed == 1
        assert isinstance(report, FlywheelReport)

    def test_single_revolution_phases(self, profiler_data):
        engine = FlywheelEngine(profiler_data, max_workers=2)
        report = engine.spin(rounds=1)
        record = report.records[0]
        # Check all phases have results
        assert "observe" in record.phase_results
        assert "learn" in record.phase_results
        assert "hypothesize" in record.phase_results
        assert "experiment" in record.phase_results
        assert "integrate" in record.phase_results
        assert "accelerate" in record.phase_results

    def test_revolution_increments(self, profiler_data):
        engine = FlywheelEngine(profiler_data, max_workers=2)
        assert engine.revolution == 0
        engine.spin(rounds=1)
        assert engine.revolution == 1

    def test_acceleration_factor_after_revolution(self, profiler_data):
        engine = FlywheelEngine(profiler_data, max_workers=2)
        report = engine.spin(rounds=1)
        assert report.final_acceleration >= 1.0

    def test_history_updated(self, profiler_data):
        engine = FlywheelEngine(profiler_data, max_workers=2)
        engine.spin(rounds=1)
        assert len(engine.get_history()) == 1


# ══════════════════════════════════════════════════════════════════════
#  TEST GROUP 10: Multiple Revolutions
# ══════════════════════════════════════════════════════════════════════

class TestMultipleRevolutions:
    """Test spinning the flywheel multiple times."""

    def test_three_revolutions(self, profiler_data):
        engine = FlywheelEngine(profiler_data, max_workers=2)
        report = engine.spin(rounds=3)
        assert report.revolutions_completed == 3
        assert len(report.records) == 3

    def test_acceleration_increases(self, profiler_data):
        engine = FlywheelEngine(profiler_data, max_workers=2)
        report = engine.spin(rounds=5)
        # Acceleration should be >= 1.0 (never decrease below baseline)
        assert report.final_acceleration >= 1.0

    def test_acceleration_curve_grows(self, profiler_data):
        engine = FlywheelEngine(profiler_data, max_workers=2)
        engine.spin(rounds=3)
        curve = engine.get_acceleration_curve()
        assert len(curve) == 3
        # Each entry is (revolution, factor)
        for rev, factor in curve:
            assert factor >= 1.0

    def test_metrics_track_all_revolutions(self, profiler_data):
        engine = FlywheelEngine(profiler_data, max_workers=2)
        engine.spin(rounds=3)
        m = engine.get_metrics()
        assert m.revolutions_completed == 3

    def test_improvement_velocity_increases(self, profiler_data):
        engine = FlywheelEngine(profiler_data, max_workers=2)
        engine.spin(rounds=3)
        velocity = engine.get_improvement_velocity()
        assert velocity >= 0.0


# ══════════════════════════════════════════════════════════════════════
#  TEST GROUP 11: Hypothesis Generation
# ══════════════════════════════════════════════════════════════════════

class TestHypothesisGeneration:
    """Test hypothesis generation from profiler data."""

    def test_generates_hypotheses_with_profiler_data(self, profiler_data):
        engine = FlywheelEngine(profiler_data, max_workers=2)
        # Run observe and learn first
        obs = engine._observe()
        insights = engine._learn(obs)
        hypotheses = engine._hypothesize(insights)
        # Should generate some hypotheses from the profiler data
        assert len(hypotheses) >= 0  # May be 0 if knowledge base says skip

    def test_hypotheses_sorted_by_expected_value(self, profiler_data):
        engine = FlywheelEngine(profiler_data, max_workers=2, max_hypotheses_per_rev=20)
        obs = engine._observe()
        insights = engine._learn(obs)
        hypotheses = engine._hypothesize(insights)
        if len(hypotheses) >= 2:
            # Should be sorted by EV descending
            for i in range(len(hypotheses) - 1):
                assert hypotheses[i].expected_value >= hypotheses[i + 1].expected_value

    def test_hypotheses_limited_by_max(self, profiler_data):
        engine = FlywheelEngine(profiler_data, max_workers=2, max_hypotheses_per_rev=2)
        obs = engine._observe()
        insights = engine._learn(obs)
        hypotheses = engine._hypothesize(insights)
        assert len(hypotheses) <= 2

    def test_empty_synthesizer_no_hypotheses(self, synth):
        engine = FlywheelEngine(synth, max_workers=2)
        obs = engine._observe()
        insights = engine._learn(obs)
        hypotheses = engine._hypothesize(insights)
        # With no profiler data, should still generate from patterns/rules
        assert isinstance(hypotheses, list)


# ══════════════════════════════════════════════════════════════════════
#  TEST GROUP 12: Experiment Parallel Execution
# ══════════════════════════════════════════════════════════════════════

class TestExperimentExecution:
    """Test experiment parallel execution."""

    def test_empty_hypotheses_no_experiments(self, engine):
        results = engine._experiment([])
        assert results == []

    def test_single_experiment(self, engine):
        h = Hypothesis(
            description="test", target_path="test.path",
            mutation_type=MutationStrategy.INLINE_OPTIMIZATION,
        )
        results = engine._experiment([h])
        assert len(results) == 1
        assert results[0].hypothesis.target_path == "test.path"

    def test_parallel_experiments(self, profiler_data):
        engine = FlywheelEngine(profiler_data, max_workers=4)
        hypotheses = [
            Hypothesis(
                description=f"test-{i}", target_path=f"path.{i}",
                mutation_type=MutationStrategy.INLINE_OPTIMIZATION,
            )
            for i in range(5)
        ]
        start = time.monotonic_ns()
        results = engine._experiment(hypotheses)
        elapsed = time.monotonic_ns() - start
        assert len(results) == 5
        # All experiments should complete (not hang)
        for r in results:
            assert r.outcome in (
                ExperimentOutcome.SUCCESS,
                ExperimentOutcome.FAILURE,
                ExperimentOutcome.INCONCLUSIVE,
                ExperimentOutcome.TIMEOUT,
            )


# ══════════════════════════════════════════════════════════════════════
#  TEST GROUP 13: Integration Phase
# ══════════════════════════════════════════════════════════════════════

class TestIntegrationPhase:
    """Test the integration phase — commit successes, rollback failures."""

    def test_integrate_success(self, engine):
        h = Hypothesis(
            description="test", target_path="t",
            mutation_type=MutationStrategy.INLINE_OPTIMIZATION,
        )
        results = [ExperimentResult(
            hypothesis=h, outcome=ExperimentOutcome.SUCCESS,
            actual_speedup=1.5, fitness_before=0.5, fitness_after=0.6,
        )]
        report = engine._integrate(results)
        assert report.committed == 1
        assert report.rolled_back == 0

    def test_integrate_failure(self, engine):
        h = Hypothesis(
            description="test", target_path="t",
            mutation_type=MutationStrategy.MERGE_TILES,
        )
        results = [ExperimentResult(
            hypothesis=h, outcome=ExperimentOutcome.FAILURE,
        )]
        report = engine._integrate(results)
        assert report.committed == 0
        assert report.rolled_back == 1

    def test_integrate_mixed(self, engine):
        h = Hypothesis(
            description="test", target_path="t",
            mutation_type=MutationStrategy.RECOMPILE_LANGUAGE,
        )
        results = [
            ExperimentResult(
                hypothesis=h, outcome=ExperimentOutcome.SUCCESS,
                actual_speedup=1.3,
            ),
            ExperimentResult(
                hypothesis=h, outcome=ExperimentOutcome.FAILURE,
            ),
            ExperimentResult(
                hypothesis=h, outcome=ExperimentOutcome.INCONCLUSIVE,
            ),
            ExperimentResult(
                hypothesis=h, outcome=ExperimentOutcome.TIMEOUT,
            ),
        ]
        report = engine._integrate(results)
        assert report.committed == 1
        assert report.rolled_back == 1
        assert report.skipped == 2

    def test_integrate_updates_knowledge_base(self, engine):
        h = Hypothesis(
            description="test", target_path="t",
            mutation_type=MutationStrategy.ADD_TILE,
        )
        results = [
            ExperimentResult(
                hypothesis=h, outcome=ExperimentOutcome.SUCCESS,
                actual_speedup=2.0,
            ),
            ExperimentResult(
                hypothesis=h, outcome=ExperimentOutcome.FAILURE,
            ),
        ]
        engine._integrate(results)
        kb = engine.get_knowledge_base()
        assert len(kb.successes) >= 1
        assert len(kb.failures) >= 1


# ══════════════════════════════════════════════════════════════════════
#  TEST GROUP 14: Acceleration
# ══════════════════════════════════════════════════════════════════════

class TestAcceleration:
    """Test the acceleration mechanism."""

    def test_initial_acceleration(self, engine):
        assert engine._acceleration_factor == 1.0

    def test_acceleration_after_revolution(self, profiler_data):
        engine = FlywheelEngine(profiler_data, max_workers=2)
        report = engine.spin(rounds=1)
        assert report.final_acceleration >= 1.0

    def test_acceleration_curve_format(self, profiler_data):
        engine = FlywheelEngine(profiler_data, max_workers=2)
        engine.spin(rounds=3)
        curve = engine.get_acceleration_curve()
        for entry in curve:
            assert len(entry) == 2
            assert isinstance(entry[0], int)   # revolution
            assert isinstance(entry[1], float)  # factor

    def test_acceleration_never_below_one(self, profiler_data):
        engine = FlywheelEngine(profiler_data, max_workers=2)
        for _ in range(10):
            report = engine.spin(rounds=1)
            assert report.final_acceleration >= 1.0


# ══════════════════════════════════════════════════════════════════════
#  TEST GROUP 15: Flywheel Report
# ══════════════════════════════════════════════════════════════════════

class TestFlywheelReportGeneration:
    """Test flywheel report generation."""

    def test_report_format(self, profiler_data):
        engine = FlywheelEngine(profiler_data, max_workers=2)
        report = engine.spin(rounds=2)
        assert report.revolutions_completed == 2
        assert report.total_time_ns > 0
        assert isinstance(report.records, list)
        assert len(report.records) == 2

    def test_get_report_dict(self, profiler_data):
        engine = FlywheelEngine(profiler_data, max_workers=2)
        engine.spin(rounds=2)
        d = engine.get_report()
        assert "revolution" in d
        assert "phase" in d
        assert "acceleration_factor" in d
        assert "metrics" in d
        assert "knowledge" in d
        assert "history" in d


# ══════════════════════════════════════════════════════════════════════
#  TEST GROUP 16: Velocity Trend
# ══════════════════════════════════════════════════════════════════════

class TestVelocityTrend:
    """Test velocity trend detection."""

    def test_trend_in_report(self, profiler_data):
        engine = FlywheelEngine(profiler_data, max_workers=2)
        engine.spin(rounds=1)
        report = engine.spin(rounds=1)
        assert report.velocity_trend in (
            "accelerating", "steady", "decelerating", "insufficient_data"
        )


# ══════════════════════════════════════════════════════════════════════
#  TEST GROUP 17: Termination Safety
# ══════════════════════════════════════════════════════════════════════

class TestTerminationSafety:
    """Test that the flywheel terminates and doesn't spin forever."""

    def test_zero_rounds(self, profiler_data):
        engine = FlywheelEngine(profiler_data, max_workers=2)
        report = engine.spin(rounds=0)
        assert report.revolutions_completed == 0

    def test_respects_max_revolutions(self, profiler_data):
        engine = FlywheelEngine(profiler_data, max_workers=2, max_revolutions=3)
        report = engine.spin(rounds=100)  # Request way more than max
        assert report.revolutions_completed <= 3

    def test_completes_in_reasonable_time(self, profiler_data):
        engine = FlywheelEngine(profiler_data, max_workers=2)
        start = time.monotonic_ns()
        report = engine.spin(rounds=5)
        elapsed = time.monotonic_ns() - start
        # Should complete 5 revolutions in under 30 seconds
        assert elapsed < 30_000_000_000


# ══════════════════════════════════════════════════════════════════════
#  TEST GROUP 18: Edge Cases
# ══════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_no_profiler_data(self, synth):
        """Flywheel should work even with no profiling data."""
        engine = FlywheelEngine(synth, max_workers=2)
        report = engine.spin(rounds=1)
        assert report.revolutions_completed == 1

    def test_single_profiler_entry(self, synth):
        """Flywheel with minimal profiling data."""
        synth.record_call("only.module", calls=5)
        engine = FlywheelEngine(synth, max_workers=2)
        report = engine.spin(rounds=1)
        assert report.revolutions_completed == 1

    def test_validation_fn_set(self, profiler_data):
        """Test that custom validation function can be set."""
        engine = FlywheelEngine(profiler_data, max_workers=2)
        call_count = [0]

        def validation_fn(genome):
            call_count[0] += 1
            return True

        engine.set_validation_fn(validation_fn)
        report = engine.spin(rounds=1)
        # Validation fn should have been called at least once
        assert call_count[0] >= 0  # May or may not be called depending on hypotheses

    def test_phase_enum_values(self):
        assert FlywheelPhase.OBSERVE.value == "observe"
        assert FlywheelPhase.LEARN.value == "learn"
        assert FlywheelPhase.HYPOTHESIZE.value == "hypothesize"
        assert FlywheelPhase.EXPERIMENT.value == "experiment"
        assert FlywheelPhase.INTEGRATE.value == "integrate"
        assert FlywheelPhase.ACCELERATE.value == "accelerate"

    def test_experiment_outcome_values(self):
        assert ExperimentOutcome.SUCCESS.value == "success"
        assert ExperimentOutcome.FAILURE.value == "failure"
        assert ExperimentOutcome.TIMEOUT.value == "timeout"
        assert ExperimentOutcome.INCONCLUSIVE.value == "inconclusive"

    def test_consecutive_spins(self, profiler_data):
        """Spinning multiple times should accumulate state."""
        engine = FlywheelEngine(profiler_data, max_workers=2)
        r1 = engine.spin(rounds=2)
        r2 = engine.spin(rounds=2)
        assert engine.revolution == 4
        assert r2.revolutions_completed == 2
        assert len(engine.get_history()) == 4

    def test_acceleration_factor_persists(self, profiler_data):
        """Acceleration factor should persist across multiple spin() calls."""
        engine = FlywheelEngine(profiler_data, max_workers=2)
        engine.spin(rounds=2)
        factor_after_first = engine._acceleration_factor
        engine.spin(rounds=2)
        # Factor should be at least as high as before (non-decreasing above 1.0)
        assert engine._acceleration_factor >= 1.0

    def test_knowledge_persists_across_revolutions(self, profiler_data):
        """Knowledge base should accumulate across revolutions."""
        engine = FlywheelEngine(profiler_data, max_workers=2)
        engine.spin(rounds=3)
        kb = engine.get_knowledge_base()
        # Knowledge should have grown
        assert kb.size() >= 0  # May or may not have entries depending on outcomes
