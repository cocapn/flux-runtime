"""FLUX Memory System — persistent memory, experience recording, and meta-learning.

This package provides:
- MemoryStore: Four-tier persistent memory (hot/warm/cold/frozen)
- ExperienceRecorder: Records and generalizes from evolution experiences
- MutationBandit: Multi-armed bandit for strategy selection (Thompson Sampling)
- LearningRateAdapter: Adapts exploration rate based on improvement signals
"""

from .store import (
    MemoryStore,
    MemoryEntry,
    MemoryStats,
    TIER_ORDER,
)
from .experience import (
    Experience,
    ExperienceRecorder,
    GeneralizedRule,
)
from .bandit import (
    MutationBandit,
    StrategyStats,
)
from .learning import (
    LearningRateAdapter,
    LearningState,
)

__all__ = [
    # Store
    "MemoryStore",
    "MemoryEntry",
    "MemoryStats",
    "TIER_ORDER",
    # Experience
    "Experience",
    "ExperienceRecorder",
    "GeneralizedRule",
    # Bandit
    "MutationBandit",
    "StrategyStats",
    # Learning
    "LearningRateAdapter",
    "LearningState",
]
