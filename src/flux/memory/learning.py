"""Learning Rate Adaptation for the FLUX evolution engine.

Dynamically adjusts the exploration rate based on improvement signals:
- When improvements are being found → exploit more (lower exploration)
- When improvements plateau → explore more (higher exploration)
- When a big improvement is found → spike exploration (something changed)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


# ── Learning State ───────────────────────────────────────────────────────────

@dataclass
class LearningState:
    """Snapshot of the learning rate adapter's state."""
    base_rate: float
    current_rate: float
    improvement_history: list[float]
    generations_no_improvement: int
    total_updates: int
    plateau_detected: bool
    spike_detected: bool
    converged: bool

    def to_dict(self) -> dict:
        return {
            "base_rate": self.base_rate,
            "current_rate": round(self.current_rate, 4),
            "improvement_history": [round(x, 4) for x in self.improvement_history],
            "generations_no_improvement": self.generations_no_improvement,
            "total_updates": self.total_updates,
            "plateau_detected": self.plateau_detected,
            "spike_detected": self.spike_detected,
            "converged": self.converged,
        }


# ── Learning Rate Adapter ────────────────────────────────────────────────────

class LearningRateAdapter:
    """Adapts the evolution engine's exploration rate.

    When improvements are being found → exploit more (lower exploration)
    When improvements plateau → explore more (higher exploration)
    When a big improvement is found → spike exploration (something changed)

    The exploration rate controls how likely the evolution engine is to try
    novel mutations vs sticking with proven ones. A rate of 1.0 means pure
    exploration; 0.0 means pure exploitation.
    """

    # Rate bounds
    MIN_RATE: float = 0.05
    MAX_RATE: float = 0.95

    def __init__(
        self,
        base_rate: float = 0.3,
        plateau_threshold: float = 0.01,
        spike_threshold: float = 0.10,
        max_generations_no_improvement: int = 5,
    ):
        """Initialize the learning rate adapter.

        Args:
            base_rate: Starting exploration rate (0.0-1.0).
            plateau_threshold: Improvement below this fraction is a plateau (< 1%).
            spike_threshold: Improvement above this fraction triggers a spike (> 10%).
            max_generations_no_improvement: Generations without improvement
                before converging.
        """
        self.base_rate: float = max(self.MIN_RATE, min(self.MAX_RATE, base_rate))
        self.current_rate: float = self.base_rate
        self._improvement_history: list[float] = []
        self._plateau_threshold: float = plateau_threshold
        self._spike_threshold: float = spike_threshold
        self._max_generations_no_improvement: int = max_generations_no_improvement
        self._generations_no_improvement: int = 0
        self._total_updates: int = 0
        self._plateau_detected: bool = False
        self._spike_detected: bool = False
        self._converged: bool = False

    # ── Update ──────────────────────────────────────────────────────────

    def update(self, improvement: float) -> float:
        """Update exploration rate based on latest improvement.

        The adaptation rules:
        1. If improvement > spike_threshold → spike exploration
           (something fundamental changed, explore aggressively)
        2. If improvement < plateau_threshold → gradually increase exploration
           (current strategy isn't working, search wider)
        3. If improvement is steady and meaningful → decrease exploration
           (exploit what works)

        Args:
            improvement: Fractional improvement (0.0 = no change, 0.1 = 10% better).

        Returns:
            The new exploration rate.
        """
        self._total_updates += 1
        self._improvement_history.append(improvement)
        self._spike_detected = False
        self._plateau_detected = False

        if improvement >= self._spike_threshold:
            # SPIKE: Big improvement found — explore more
            self._spike_detected = True
            self._generations_no_improvement = 0
            # Spike the rate toward the upper bound
            spike_amount = min(0.3, improvement * 2.0)
            self.current_rate = min(
                self.MAX_RATE,
                self.current_rate + spike_amount,
            )
        elif improvement < self._plateau_threshold:
            # PLATEAU: Little or no improvement — explore more gradually
            self._plateau_detected = True
            self._generations_no_improvement += 1
            # Increase exploration slowly
            self.current_rate = min(
                self.MAX_RATE,
                self.current_rate + 0.05,
            )
        else:
            # STEADY: Meaningful improvement — exploit more
            self._generations_no_improvement = 0
            # Decay exploration toward base rate
            decay_factor = 0.8  # move 20% toward base
            self.current_rate = (
                self.base_rate + (self.current_rate - self.base_rate) * decay_factor
            )

        # Clamp to bounds
        self.current_rate = max(self.MIN_RATE, min(self.MAX_RATE, self.current_rate))

        return self.current_rate

    # ── Convergence Detection ───────────────────────────────────────────

    def should_stop(self, max_generations_no_improvement: Optional[int] = None) -> bool:
        """Has the system converged? No meaningful improvement in N generations.

        Args:
            max_generations_no_improvement: Override the threshold. If None,
                uses the value from __init__.

        Returns:
            True if the system should stop evolving.
        """
        threshold = (
            max_generations_no_improvement
            if max_generations_no_improvement is not None
            else self._max_generations_no_improvement
        )
        self._converged = self._generations_no_improvement >= threshold
        return self._converged

    # ── Analysis ────────────────────────────────────────────────────────

    def recent_improvement(self, n: int = 5) -> float:
        """Average improvement over the last N generations.

        Args:
            n: Number of recent generations to average.

        Returns:
            Average improvement, or 0.0 if no history.
        """
        recent = self._improvement_history[-n:]
        if not recent:
            return 0.0
        return sum(recent) / len(recent)

    def improvement_trend(self) -> str:
        """Determine if improvement is trending up, down, or flat.

        Compares the average improvement of the first half vs second half
        of the history.

        Returns:
            "improving", "declining", "flat", or "insufficient_data"
        """
        if len(self._improvement_history) < 4:
            return "insufficient_data"

        mid = len(self._improvement_history) // 2
        first_half = sum(self._improvement_history[:mid]) / mid
        second_half = sum(self._improvement_history[mid:]) / (len(self._improvement_history) - mid)

        if first_half < 0.5 * self._plateau_threshold and second_half < 0.5 * self._plateau_threshold:
            return "flat"

        if second_half > first_half * 1.2:
            return "improving"
        elif second_half < first_half * 0.8:
            return "declining"
        else:
            return "flat"

    # ── Reset ───────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset to initial state."""
        self.current_rate = self.base_rate
        self._improvement_history.clear()
        self._generations_no_improvement = 0
        self._total_updates = 0
        self._plateau_detected = False
        self._spike_detected = False
        self._converged = False

    # ── State Export ────────────────────────────────────────────────────

    def get_state(self) -> LearningState:
        """Get a snapshot of the current learning state."""
        return LearningState(
            base_rate=self.base_rate,
            current_rate=self.current_rate,
            improvement_history=list(self._improvement_history),
            generations_no_improvement=self._generations_no_improvement,
            total_updates=self._total_updates,
            plateau_detected=self._plateau_detected,
            spike_detected=self._spike_detected,
            converged=self._converged,
        )

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def plateau_detected(self) -> bool:
        """Whether a plateau was detected in the last update."""
        return self._plateau_detected

    @property
    def spike_detected(self) -> bool:
        """Whether a spike was detected in the last update."""
        return self._spike_detected

    @property
    def converged(self) -> bool:
        """Whether the system has converged."""
        return self._converged

    @property
    def generations_no_improvement(self) -> int:
        """Number of consecutive generations with no meaningful improvement."""
        return self._generations_no_improvement

    @property
    def total_updates(self) -> int:
        """Total number of update() calls."""
        return self._total_updates

    @property
    def history_len(self) -> int:
        """Length of the improvement history."""
        return len(self._improvement_history)

    def __repr__(self) -> str:
        return (
            f"LearningRateAdapter(rate={self.current_rate:.3f}, "
            f"base={self.base_rate:.3f}, "
            f"updates={self._total_updates}, "
            f"no_improve={self._generations_no_improvement})"
        )
