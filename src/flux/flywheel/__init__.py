"""FLUX Flywheel — the self-reinforcing improvement loop.

The flywheel makes the system increasingly capable with each revolution.
Each revolution runs 6 phases: OBSERVE → LEARN → HYPOTHESIZE → EXPERIMENT
→ INTEGRATE → ACCELERATE.

The key insight: improvements in phase 5 make phases 1-4 faster in the
next cycle. Like a flywheel, momentum builds — each revolution is faster
and more effective than the last.

Usage:
    from flux.flywheel import FlywheelEngine, FlywheelPhase

    engine = FlywheelEngine(synthesizer)
    report = engine.spin(rounds=5)
    print(f"Speedup: {report.total_speedup:.2f}x")
"""

from .engine import (
    FlywheelEngine,
    FlywheelPhase,
)
from .hypothesis import (
    Hypothesis,
    ExperimentResult,
    ExperimentOutcome,
    ObservationData,
    LearnedInsights,
    FlywheelRecord,
    FlywheelReport,
    IntegrationReport,
)
from .knowledge import (
    KnowledgeBase,
    GeneralizedRule,
)
from .metrics import (
    FlywheelMetrics,
)

__all__ = [
    # Engine
    "FlywheelEngine",
    "FlywheelPhase",
    # Hypothesis & Results
    "Hypothesis",
    "ExperimentResult",
    "ExperimentOutcome",
    "ObservationData",
    "LearnedInsights",
    "FlywheelRecord",
    "FlywheelReport",
    "IntegrationReport",
    # Knowledge
    "KnowledgeBase",
    "GeneralizedRule",
    # Metrics
    "FlywheelMetrics",
]
