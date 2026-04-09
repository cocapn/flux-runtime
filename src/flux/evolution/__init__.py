"""FLUX Evolution Engine — the system that builds a better version of itself.

The evolution engine ties together:
- Genome (system DNA snapshots)
- Pattern Mining (hot pattern discovery from execution traces)
- System Mutator (proposing and applying improvements)
- Correctness Validator (ensuring mutations don't break things)
- Evolution Engine (the main loop orchestrating everything)
"""

from .genome import (
    Genome,
    GenomeDiff,
    ModuleSnapshot,
    TileSnapshot,
    ProfilerSnapshot,
    OptimizationRecord,
    MutationStrategy,
)
from .pattern_mining import (
    PatternMiner,
    ExecutionTrace,
    DiscoveredPattern,
    TileSuggestion,
)
from .mutator import (
    SystemMutator,
    MutationProposal,
    MutationResult,
    MutationRecord,
)
from .validator import (
    CorrectnessValidator,
    TestCase,
    TestResult,
    ValidationResult,
    RegressionReport,
)
from .evolution import (
    EvolutionEngine,
    EvolutionRecord,
    EvolutionReport,
    EvolutionStep,
)

__all__ = [
    # Genome
    "Genome",
    "GenomeDiff",
    "ModuleSnapshot",
    "TileSnapshot",
    "ProfilerSnapshot",
    "OptimizationRecord",
    "MutationStrategy",
    # Pattern Mining
    "PatternMiner",
    "ExecutionTrace",
    "DiscoveredPattern",
    "TileSuggestion",
    # Mutator
    "SystemMutator",
    "MutationProposal",
    "MutationResult",
    "MutationRecord",
    # Validator
    "CorrectnessValidator",
    "TestCase",
    "TestResult",
    "ValidationResult",
    "RegressionReport",
    # Engine
    "EvolutionEngine",
    "EvolutionRecord",
    "EvolutionReport",
    "EvolutionStep",
]
