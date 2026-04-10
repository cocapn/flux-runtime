"""FLUX Retro Research Framework — Scientific Reverse Engineering.

Every iteration is tracked with:
  - Seed (deterministic RNG state for reproducibility)
  - Hypothesis (what we're testing)
  - Metrics (cycles, memory, bytecode size, coverage)
  - Reflection (what worked, what didn't, what to try next)
  - Artifacts (bytecode dumps, IR snapshots, performance traces)

The full log is saved to research_log.jsonl for ML reflection.
"""

from .session import ResearchSession, Iteration, Reflection
from .metrics import Metrics, MetricSnapshot

__all__ = [
    "ResearchSession",
    "Iteration",
    "Reflection",
    "Metrics",
    "MetricSnapshot",
]
