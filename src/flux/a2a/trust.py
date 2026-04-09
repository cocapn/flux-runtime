"""INCREMENTS+2 Trust Engine — Multi-dimensional trust computation for A2A agents.

Trust is computed as a weighted composite of six dimensions:

    T = α·T_history + β·T_capability + γ·T_latency
        + δ·T_consistency + ε·T_determinism + ζ·T_audit

Dimension weights:
    history      α = 0.30
    capability   β = 0.25
    latency      γ = 0.20
    consistency  δ = 0.15
    determinism  ε = 0.05
    audit        ζ = 0.05

Decay
-----
Trust decays over time based on the most recent interaction:
    composite *= (1 − λ · elapsed / max_age)

where λ is the decay rate per second and max_age is the time horizon.

Profiles are stored as ``dict[(agent_a, agent_b)] → AgentProfile``, where
each profile holds a bounded deque of ``InteractionRecord`` entries.
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Optional, Tuple


# ── Interaction Record ────────────────────────────────────────────────────


@dataclass
class InteractionRecord:
    """Single interaction outcome for trust computation.

    Attributes
    ----------
    timestamp : float
        Unix timestamp (``time.time()``) when the interaction occurred.
    success : bool
        Whether the interaction achieved its goal.
    latency_ms : float
        Round-trip latency in milliseconds.
    capability_match : float
        How well the capability matched expectations (0.0–1.0).
    behavior_signature : float
        Metric of behavioral consistency / fingerprint.
    """

    timestamp: float
    success: bool
    latency_ms: float
    capability_match: float = 1.0
    behavior_signature: float = 0.0


# ── Agent Profile ─────────────────────────────────────────────────────────


@dataclass
class AgentProfile:
    """Trust profile for a pairwise relationship (evaluator → target).

    Attributes
    ----------
    agent_id : str
        Identifier of the agent being evaluated.
    history : deque[InteractionRecord]
        Bounded ring buffer of recent interactions (maxlen=1000).
    w_history, w_capability, … : float
        Dimension weights (must sum to 1.0).
    decay_rate : float
        Decay per second (λ).
    max_age_seconds : float
        Time horizon for decay computation.
    """

    agent_id: str
    history: Deque[InteractionRecord] = field(
        default_factory=lambda: deque(maxlen=1000)
    )

    # Weights (sum to 1.0)
    w_history: float = 0.30
    w_capability: float = 0.25
    w_latency: float = 0.20
    w_consistency: float = 0.15
    w_determinism: float = 0.05
    w_audit: float = 0.05

    # Decay parameters
    decay_rate: float = 0.01  # per second (λ)
    max_age_seconds: float = 3600.0  # 1 hour horizon


# ── Trust Engine ──────────────────────────────────────────────────────────


class TrustEngine:
    """INCREMENTS+2 trust engine.

    Computes a composite trust score in [0.0, 1.0] from six weighted
    dimensions, with time-based decay applied to the final result.

    When no interaction history exists, returns a neutral trust of 0.5.

    Stores profiles keyed by ``(agent_a, agent_b)`` tuples where each
    profile holds a deque of :class:`InteractionRecord` entries.
    """

    NEUTRAL_TRUST: float = 0.5

    def __init__(self) -> None:
        self._profiles: Dict[Tuple[str, str], AgentProfile] = {}

    # ── Public API ────────────────────────────────────────────────────────

    def record_interaction(
        self,
        agent_a: str,
        agent_b: str,
        success: bool,
        latency_ms: float,
        capability_match: float = 1.0,
        behavior_signature: float = 0.0,
    ) -> None:
        """Record an interaction between *agent_a* (evaluator) and *agent_b* (target).

        Parameters
        ----------
        agent_a : str
            The evaluating agent.
        agent_b : str
            The agent being evaluated.
        success : bool
            Whether the interaction succeeded.
        latency_ms : float
            Round-trip latency in milliseconds.
        capability_match : float
            How well the capability matched expectations (0.0–1.0).
        behavior_signature : float
            Metric of behavioral consistency.
        """
        profile = self._get_profile(agent_a, agent_b)
        record = InteractionRecord(
            timestamp=time.time(),
            success=success,
            latency_ms=latency_ms,
            capability_match=max(0.0, min(1.0, capability_match)),
            behavior_signature=behavior_signature,
        )
        profile.history.append(record)

    def compute_trust(self, agent_a: str, agent_b: str) -> float:
        """Compute composite trust score in [0.0, 1.0].

        Returns 0.5 (neutral) when no interaction history exists.
        """
        profile = self._get_profile(agent_a, agent_b)

        if len(profile.history) == 0:
            return self.NEUTRAL_TRUST

        # Six sub-scores
        t_history = self._compute_history(profile)
        t_capability = self._compute_capability(profile)
        t_latency = self._compute_latency(profile)
        t_consistency = self._compute_consistency(profile)
        t_determinism = self._compute_determinism(profile)
        t_audit = self._compute_audit(profile)

        # Weighted composite
        composite = (
            profile.w_history * t_history
            + profile.w_capability * t_capability
            + profile.w_latency * t_latency
            + profile.w_consistency * t_consistency
            + profile.w_determinism * t_determinism
            + profile.w_audit * t_audit
        )

        # Apply time decay: composite *= (1 - decay_rate * elapsed / max_age)
        decay = self._compute_decay(profile)

        return max(0.0, min(1.0, composite * decay))

    def check_trust(self, agent_a: str, agent_b: str, threshold: float) -> bool:
        """Check if trust from *agent_a* to *agent_b* meets *threshold*."""
        return self.compute_trust(agent_a, agent_b) >= threshold

    def revoke_trust(self, agent_a: str, agent_b: str) -> None:
        """Set trust to neutral by clearing all interaction history.

        The profile itself remains (just empty), so future interactions
        can rebuild trust from scratch.
        """
        key = self._make_key(agent_a, agent_b)
        if key in self._profiles:
            self._profiles[key].history.clear()

    # ── Profile access ────────────────────────────────────────────────────

    def get_profile(self, agent_a: str, agent_b: str) -> Optional[AgentProfile]:
        """Return the profile, or ``None`` if it doesn't exist."""
        return self._profiles.get(self._make_key(agent_a, agent_b))

    def _get_profile(self, a: str, b: str) -> AgentProfile:
        """Return the profile, creating it if needed."""
        key = self._make_key(a, b)
        if key not in self._profiles:
            self._profiles[key] = AgentProfile(agent_id=b)
        return self._profiles[key]

    @staticmethod
    def _make_key(a: str, b: str) -> Tuple[str, str]:
        return (a, b)

    # ── Dimension computations ────────────────────────────────────────────

    def _compute_history(self, profile: AgentProfile) -> float:
        """T_history: exponential moving average of binary outcomes.

        Uses EMA with α=0.1 seeded at NEUTRAL_TRUST.
        Success → 1.0, Failure → 0.0.
        """
        alpha = 0.1
        ema = self.NEUTRAL_TRUST
        for record in profile.history:
            value = 1.0 if record.success else 0.0
            ema = alpha * value + (1.0 - alpha) * ema
        return ema

    def _compute_capability(self, profile: AgentProfile) -> float:
        """T_capability: average capability match of recent 50 interactions."""
        recent = list(profile.history)[-50:]
        if not recent:
            return self.NEUTRAL_TRUST
        return sum(r.capability_match for r in recent) / len(recent)

    def _compute_latency(self, profile: AgentProfile) -> float:
        """T_latency: inverse linear interpolation.

        Target latency = 10 ms → score 1.0
        Max latency = 1000 ms → score 0.0
        Latencies below target still score 1.0; above max score 0.0.
        """
        recent = list(profile.history)[-50:]
        if not recent:
            return self.NEUTRAL_TRUST

        avg_latency = sum(r.latency_ms for r in recent) / len(recent)
        target_ms = 10.0
        max_ms = 1000.0

        if avg_latency <= target_ms:
            return 1.0
        if avg_latency >= max_ms:
            return 0.0
        return 1.0 - (avg_latency - target_ms) / (max_ms - target_ms)

    def _compute_consistency(self, profile: AgentProfile) -> float:
        """T_consistency: 1 − coefficient_of_variation of latencies.

        Measures how stable the latency pattern is.  A consistently
        fast agent scores high; an erratic one scores low.
        Requires at least 2 data points.
        """
        recent = list(profile.history)[-20:]
        if len(recent) < 2:
            return self.NEUTRAL_TRUST

        latencies = [r.latency_ms for r in recent]
        mean_lat = sum(latencies) / len(latencies)
        if mean_lat == 0.0:
            return 1.0

        variance = sum((l - mean_lat) ** 2 for l in latencies) / len(latencies)
        stdev = math.sqrt(variance)
        cv = stdev / mean_lat  # coefficient of variation

        return max(0.0, 1.0 - cv)

    def _compute_determinism(self, profile: AgentProfile) -> float:
        """T_determinism: how consistent behavior signatures are.

        Computed as 1 − (stdev / mean) of behavior_signature values.
        If all signatures are identical, this returns 1.0.
        Requires at least 2 data points.
        """
        recent = list(profile.history)[-20:]
        if len(recent) < 2:
            return self.NEUTRAL_TRUST

        sigs = [r.behavior_signature for r in recent]
        mean_sig = sum(sigs) / len(sigs)
        if mean_sig == 0.0:
            return 1.0

        variance = sum((s - mean_sig) ** 2 for s in sigs) / len(sigs)
        stdev = math.sqrt(variance)
        cv = stdev / abs(mean_sig)

        return max(0.0, 1.0 - cv)

    def _compute_audit(self, profile: AgentProfile) -> float:
        """T_audit: 1.0 if records exist, 0.0 if no audit trail."""
        return 1.0 if len(profile.history) > 0 else 0.0

    def _compute_decay(self, profile: AgentProfile) -> float:
        """Time-based decay factor.

        decay = max(0.0, 1 − λ · elapsed / max_age)

        where elapsed is the time since the most recent interaction.
        """
        if len(profile.history) == 0:
            return 1.0

        most_recent = profile.history[-1].timestamp
        elapsed = time.time() - most_recent

        if elapsed <= 0:
            return 1.0

        factor = 1.0 - (profile.decay_rate * elapsed / profile.max_age_seconds)
        return max(0.0, min(1.0, factor))
