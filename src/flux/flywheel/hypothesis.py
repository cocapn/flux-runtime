"""Flywheel Hypothesis — proposed improvements and experiment results.

Each hypothesis is a bet: "If I change X, the system will be Y% faster."
Each experiment result is the payoff: did the bet pay off?

The flywheel generates hypotheses from profiler data, pattern mining,
tile registry analysis, and accumulated knowledge. Experiments test
these hypotheses speculatively, and the knowledge base learns from
the outcomes to make better hypotheses next time.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any

from flux.evolution.genome import MutationStrategy


# ── Experiment Outcome ──────────────────────────────────────────────────

class ExperimentOutcome(Enum):
    """Outcome of testing a hypothesis."""
    SUCCESS = "success"          # Hypothesis confirmed, improvement measured
    FAILURE = "failure"          # Hypothesis rejected, caused regression
    TIMEOUT = "timeout"          # Experiment took too long
    INCONCLUSIVE = "inconclusive"  # Not enough data to decide


# ── Hypothesis ──────────────────────────────────────────────────────────

@dataclass
class Hypothesis:
    """A proposed improvement to the system.

    Each hypothesis encodes:
    - What to change (target_path, mutation_type)
    - How much we expect to gain (expected_speedup, expected_modularity_delta)
    - How risky it is (risk_level)
    - How confident we are (confidence)
    - Where the idea came from (source)
    """
    description: str
    target_path: str                           # module/tile path to modify
    mutation_type: MutationStrategy
    expected_speedup: float = 1.0              # estimated speedup factor
    expected_modularity_delta: float = 0.0     # positive = more modular
    risk_level: float = 0.5                    # 0.0 = safe, 1.0 = risky
    confidence: float = 0.5                    # how confident in the estimate
    source: str = "profiler"                   # profiler/pattern_miner/tile_registry/research
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    @property
    def expected_value(self) -> float:
        """Risk-adjusted expected value of this hypothesis.

        EV = confidence * expected_speedup * (1 - risk_level)
        A high-confidence, high-speedup, low-risk hypothesis has the highest EV.
        """
        return self.confidence * self.expected_speedup * (1.0 - self.risk_level)

    @property
    def is_risky(self) -> bool:
        """Is this hypothesis considered risky (risk > 0.7)?"""
        return self.risk_level > 0.7

    @property
    def is_high_confidence(self) -> bool:
        """Do we have high confidence (confidence > 0.8)?"""
        return self.confidence > 0.8

    def __repr__(self) -> str:
        return (
            f"Hypothesis({self.mutation_type.value}, "
            f"target={self.target_path!r}, "
            f"speedup={self.expected_speedup:.2f}, "
            f"risk={self.risk_level:.2f}, "
            f"conf={self.confidence:.2f}, "
            f"src={self.source!r})"
        )


# ── Experiment Result ──────────────────────────────────────────────────

@dataclass
class ExperimentResult:
    """Result of testing a hypothesis.

    The flywheel runs experiments in parallel, then integrates results:
    - SUCCESS → commit the improvement
    - FAILURE → rollback, add to knowledge base as a failure
    - TIMEOUT → discard, mark as risky
    - INCONCLUSIVE → re-queue for next revolution with lower priority
    """
    hypothesis: Hypothesis
    outcome: ExperimentOutcome = ExperimentOutcome.INCONCLUSIVE
    actual_speedup: float = 1.0
    actual_modularity_delta: float = 0.0
    time_to_validate_ns: int = 0
    details: str = ""
    fitness_before: float = 0.0
    fitness_after: float = 0.0
    elapsed_ns: int = 0

    def __post_init__(self):
        if self.elapsed_ns == 0 and self.time_to_validate_ns > 0:
            self.elapsed_ns = self.time_to_validate_ns

    @property
    def was_improvement(self) -> bool:
        """Did the experiment actually improve anything?"""
        return (
            self.outcome == ExperimentOutcome.SUCCESS
            and self.actual_speedup > 1.0
        )

    @property
    def fitness_delta(self) -> float:
        """Change in fitness from this experiment."""
        return self.fitness_after - self.fitness_before

    def __repr__(self) -> str:
        return (
            f"ExperimentResult({self.outcome.value}, "
            f"speedup={self.actual_speedup:.2f}, "
            f"target={self.hypothesis.target_path!r})"
        )


# ── Observation & Insight Data ─────────────────────────────────────────

@dataclass
class ObservationData:
    """Data collected during the OBSERVE phase.

    Aggregates profiler metrics, heatmap classification,
    tile costs, and module statistics into a single snapshot.
    """
    heatmap: dict[str, str] = field(default_factory=dict)            # path → heat level name
    call_counts: dict[str, int] = field(default_factory=dict)
    total_times_ns: dict[str, int] = field(default_factory=dict)
    module_count: int = 0
    sample_count: int = 0
    tile_count: int = 0
    bottleneck_modules: list[str] = field(default_factory=list)
    hot_modules: list[str] = field(default_factory=list)
    frozen_modules: list[str] = field(default_factory=list)
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class LearnedInsights:
    """Insights extracted during the LEARN phase.

    Generalizes from observation data and past experience
    into actionable patterns.
    """
    hot_paths: list[str] = field(default_factory=list)
    cold_paths: list[str] = field(default_factory=list)
    patterns_found: list[str] = field(default_factory=list)
    tile_replacements: list[dict[str, Any]] = field(default_factory=list)
    recompilation_candidates: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.5
    insight_count: int = 0
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()
        self.insight_count = (
            len(self.hot_paths)
            + len(self.patterns_found)
            + len(self.tile_replacements)
            + len(self.recompilation_candidates)
        )


# ── Flywheel Records & Reports ─────────────────────────────────────────

@dataclass
class FlywheelRecord:
    """Record of one complete flywheel revolution."""
    revolution: int
    phase_results: dict[str, Any] = field(default_factory=dict)
    hypotheses_generated: int = 0
    experiments_run: int = 0
    successes: int = 0
    failures: int = 0
    timeouts: int = 0
    inconclusive: int = 0
    acceleration_before: float = 1.0
    acceleration_after: float = 1.0
    revolution_time_ns: int = 0
    fitness_before: float = 0.0
    fitness_after: float = 0.0
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    @property
    def success_rate(self) -> float:
        total = self.successes + self.failures + self.timeouts + self.inconclusive
        if total == 0:
            return 0.0
        return self.successes / total

    @property
    def improvement_count(self) -> int:
        return self.successes


@dataclass
class FlywheelReport:
    """Summary report after spinning the flywheel."""
    revolutions_completed: int = 0
    total_improvements: int = 0
    total_experiments: int = 0
    total_successes: int = 0
    total_failures: int = 0
    total_time_ns: int = 0
    initial_acceleration: float = 1.0
    final_acceleration: float = 1.0
    initial_fitness: float = 0.0
    final_fitness: float = 0.0
    records: list[FlywheelRecord] = field(default_factory=list)
    velocity_trend: str = "steady"

    @property
    def total_speedup(self) -> float:
        return self.final_acceleration / max(self.initial_acceleration, 0.001)

    @property
    def overall_success_rate(self) -> float:
        total = self.total_successes + self.total_failures
        if total == 0:
            return 0.0
        return self.total_successes / total

    @property
    def elapsed_ms(self) -> float:
        return self.total_time_ns / 1_000_000.0

    def __repr__(self) -> str:
        return (
            f"FlywheelReport("
            f"revs={self.revolutions_completed}, "
            f"improvements={self.total_improvements}, "
            f"speedup={self.total_speedup:.2f}x, "
            f"accel={self.final_acceleration:.2f})"
        )


@dataclass
class IntegrationReport:
    """Result of the INTEGRATE phase."""
    committed: int = 0
    rolled_back: int = 0
    skipped: int = 0
    fitness_delta: float = 0.0
    details: list[str] = field(default_factory=list)

    @property
    def commit_rate(self) -> float:
        total = self.committed + self.rolled_back + self.skipped
        if total == 0:
            return 0.0
        return self.committed / total
