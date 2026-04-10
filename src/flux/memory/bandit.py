"""Meta-Learning via Multi-Armed Bandit for mutation strategy selection.

Uses Thompson Sampling to balance exploration vs exploitation across
mutation strategies. Each strategy is an "arm" with a Beta-distributed
success probability that is updated after each trial.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional


# ── Bandit Strategy ──────────────────────────────────────────────────────────

@dataclass
class StrategyStats:
    """Statistics for a single bandit arm (mutation strategy)."""
    name: str
    successes: int = 1      # Laplace prior (pseudo-count of 1)
    failures: int = 1       # Laplace prior (pseudo-count of 1)

    @property
    def total(self) -> int:
        return self.successes + self.failures

    @property
    def empirical_rate(self) -> float:
        """Empirical success rate (with Laplace smoothing)."""
        return self.successes / self.total

    @property
    def mean(self) -> float:
        """Mean of the Beta(successes, failures) distribution."""
        return self.successes / self.total

    @property
    def variance(self) -> float:
        """Variance of the Beta(successes, failures) distribution."""
        a, b = self.successes, self.failures
        return (a * b) / ((a + b) ** 2 * (a + b + 1))

    @property
    def std(self) -> float:
        """Standard deviation of the Beta distribution."""
        return math.sqrt(self.variance)

    def sample(self) -> float:
        """Draw a sample from Beta(successes, failures)."""
        return random.betavariate(self.successes, self.failures)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "successes": self.successes,
            "failures": self.failures,
            "empirical_rate": round(self.empirical_rate, 4),
            "mean": round(self.mean, 4),
            "std": round(self.std, 4),
        }


# ── Mutation Bandit ──────────────────────────────────────────────────────────

class MutationBandit:
    """Multi-armed bandit for selecting mutation strategies.

    Arms (mutation strategies):
    - RECOMPILE_LANGUAGE: change module language
    - FUSE_PATTERN: merge frequent pattern into tile
    - REPLACE_TILE: swap expensive tile for cheaper alternative
    - MERGE_TILES: combine co-occurring tiles
    - INLINE_OPTIMIZATION: inline small functions

    Uses Thompson Sampling to balance exploration vs exploitation:
    - Track success/failure for each strategy
    - Sample from Beta(success+1, failure+1) distribution
    - Pick strategy with highest sample
    - Update based on actual outcome
    """

    STRATEGIES = [
        "recompile_language",
        "fuse_pattern",
        "replace_tile",
        "merge_tiles",
        "inline_optimization",
    ]

    def __init__(self, strategies: Optional[list[str]] = None, seed: Optional[int] = None):
        """Initialize the bandit with strategy arms.

        Args:
            strategies: List of strategy names. Defaults to STRATEGIES.
            seed: Random seed for reproducibility.
        """
        if seed is not None:
            random.seed(seed)

        self._strategies = strategies or list(self.STRATEGIES)
        self._stats: dict[str, StrategyStats] = {}
        for s in self._strategies:
            self._stats[s] = StrategyStats(name=s)

    # ── Selection ───────────────────────────────────────────────────────

    def select(self) -> str:
        """Select a mutation strategy using Thompson Sampling.

        For each strategy, draw a sample from Beta(successes, failures).
        Return the strategy with the highest sample value.

        Returns:
            Name of the selected strategy.
        """
        best_strategy = self._strategies[0]
        best_sample = -1.0

        for name, stats in self._stats.items():
            sample = stats.sample()
            if sample > best_sample:
                best_sample = sample
                best_strategy = name

        return best_strategy

    def select_exploit(self) -> str:
        """Select the strategy with the highest empirical success rate.

        Unlike select(), this is deterministic (greedy exploitation).

        Returns:
            Name of the best-performing strategy.
        """
        return self.best_strategy()

    # ── Update ──────────────────────────────────────────────────────────

    def update(self, strategy: str, success: bool) -> None:
        """Update bandit statistics based on mutation outcome.

        Args:
            strategy: The strategy that was tried.
            success: Whether the mutation was successful.
        """
        if strategy not in self._stats:
            self._stats[strategy] = StrategyStats(name=strategy)

        if success:
            self._stats[strategy].successes += 1
        else:
            self._stats[strategy].failures += 1

    def reset(self) -> None:
        """Reset all statistics to Laplace priors."""
        for stats in self._stats.values():
            stats.successes = 1
            stats.failures = 1

    # ── Analysis ────────────────────────────────────────────────────────

    def get_distribution(self) -> dict[str, tuple[float, float]]:
        """Return (mean, std) of each strategy's success distribution.

        Returns:
            Dict mapping strategy name to (mean, std) tuple.
        """
        return {
            name: (stats.mean, stats.std)
            for name, stats in self._stats.items()
        }

    def best_strategy(self) -> str:
        """Strategy with the highest empirical success rate.

        Returns:
            Name of the best strategy.
        """
        return max(self._stats, key=lambda s: self._stats[s].empirical_rate)

    def worst_strategy(self) -> str:
        """Strategy with the lowest empirical success rate.

        Returns:
            Name of the worst strategy.
        """
        return min(self._stats, key=lambda s: self._stats[s].empirical_rate)

    def exploration_rate(self) -> float:
        """How much exploration is happening? (entropy of selection distribution).

        Computes the normalized entropy of the empirical success rate
        distribution. Higher values indicate more exploration.

        Returns:
            Entropy between 0.0 (pure exploitation) and 1.0 (uniform exploration).
        """
        n = len(self._stats)
        if n <= 1:
            return 0.0

        rates = [stats.empirical_rate for stats in self._stats.values()]
        total = sum(rates)

        if total == 0:
            return 1.0

        # Compute Shannon entropy
        entropy = 0.0
        for r in rates:
            if r > 0:
                p = r / total
                entropy -= p * math.log2(p)

        # Normalize by max entropy (uniform distribution)
        max_entropy = math.log2(n)
        if max_entropy == 0:
            return 0.0

        return entropy / max_entropy

    def regret(self) -> float:
        """Cumulative regret compared to always choosing the best strategy.

        Regret = sum of (best_rate - chosen_rate) over all trials.
        Approximated from the current statistics.

        Returns:
            Estimated regret (lower is better).
        """
        best_rate = max(stats.empirical_rate for stats in self._stats.values())
        total_trials = sum(stats.total - 2 for stats in self._stats.values())  # -2 for Laplace prior
        if total_trials <= 0:
            return 0.0

        # Approximate regret: for each strategy, (best_rate - rate) * trials
        regret = 0.0
        for stats in self._stats.values():
            trials = stats.total - 2  # subtract Laplace prior
            if trials > 0:
                regret += (best_rate - stats.empirical_rate) * trials

        return max(0.0, regret)

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def strategy_count(self) -> int:
        """Number of registered strategies."""
        return len(self._stats)

    @property
    def total_trials(self) -> int:
        """Total number of trials across all strategies (excluding priors)."""
        return sum(stats.total - 2 for stats in self._stats.values())

    def get_stats(self, strategy: str) -> Optional[StrategyStats]:
        """Get statistics for a specific strategy."""
        return self._stats.get(strategy)

    def all_stats(self) -> dict[str, StrategyStats]:
        """Get statistics for all strategies."""
        return dict(self._stats)

    def __repr__(self) -> str:
        best = self.best_strategy()
        best_rate = self._stats[best].empirical_rate
        return (
            f"MutationBandit(strategies={self.strategy_count}, "
            f"trials={self.total_trials}, "
            f"best={best!r}@{best_rate:.2%}, "
            f"exploration={self.exploration_rate():.2f})"
        )
