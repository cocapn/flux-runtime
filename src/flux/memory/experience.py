"""Experience Recording & Generalization for the FLUX evolution system.

Records evolution experiences (context, action, outcome, metrics) and provides:
- Case-based reasoning (find similar past experiences)
- Rule generalization (extract patterns from accumulated experiences)
- Success rate tracking per mutation type and heat level
- Best mutation recommendation based on historical context
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


# ── Experience ───────────────────────────────────────────────────────────────

@dataclass
class Experience:
    """A single evolution experience record.

    Each experience captures:
    - Context: what was the system state?
    - Action: what mutation was attempted?
    - Outcome: success or failure?
    - Metrics: speedup, modularity change, time cost
    - Tags: classification for search
    """
    context: dict = field(default_factory=dict)
    action: dict = field(default_factory=dict)
    outcome: str = "pending"       # "success" / "failure" / "timeout"
    metrics: dict = field(default_factory=dict)
    tags: set[str] = field(default_factory=set)
    timestamp: float = 0.0
    generation: int = 0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()
        # Ensure tags is a set
        if isinstance(self.tags, (list, tuple)):
            self.tags = set(self.tags)

    def to_dict(self) -> dict:
        return {
            "context": self.context,
            "action": self.action,
            "outcome": self.outcome,
            "metrics": self.metrics,
            "tags": sorted(self.tags),
            "timestamp": self.timestamp,
            "generation": self.generation,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Experience:
        tags = data.get("tags", [])
        if isinstance(tags, list):
            tags = set(tags)
        return cls(
            context=data.get("context", {}),
            action=data.get("action", {}),
            outcome=data.get("outcome", "pending"),
            metrics=data.get("metrics", {}),
            tags=tags,
            timestamp=data.get("timestamp", 0.0),
            generation=data.get("generation", 0),
        )


# ── Generalized Rule ─────────────────────────────────────────────────────────

@dataclass
class GeneralizedRule:
    """A rule extracted from accumulated experiences.

    Captures: "When condition X holds, action Y yields outcome Z
    with confidence W based on N observations."
    """
    condition: dict = field(default_factory=dict)
    action: str = ""
    expected_outcome: dict = field(default_factory=dict)
    confidence: float = 0.0
    evidence_count: int = 0
    success_count: int = 0
    failure_count: int = 0

    @property
    def success_rate(self) -> float:
        """Empirical success rate from evidence."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.success_count / total

    def to_dict(self) -> dict:
        return {
            "condition": self.condition,
            "action": self.action,
            "expected_outcome": self.expected_outcome,
            "confidence": self.confidence,
            "evidence_count": self.evidence_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> GeneralizedRule:
        return cls(
            condition=data.get("condition", {}),
            action=data.get("action", ""),
            expected_outcome=data.get("expected_outcome", {}),
            confidence=data.get("confidence", 0.0),
            evidence_count=data.get("evidence_count", 0),
            success_count=data.get("success_count", 0),
            failure_count=data.get("failure_count", 0),
        )


# ── Experience Recorder ──────────────────────────────────────────────────────

class ExperienceRecorder:
    """Records and generalizes from evolution experiences.

    Each experience has:
    - Context: what was the system state?
    - Action: what mutation was attempted?
    - Outcome: success or failure?
    - Metrics: speedup, modularity change, time cost
    - Tags: classification for search
    """

    MIN_EXPERIENCES_FOR_GENERALIZATION = 3
    MIN_CONFIDENCE_FOR_RULE = 0.5

    def __init__(self, store: Any = None):
        """Initialize with optional MemoryStore for persistence.

        Args:
            store: A MemoryStore instance for persistent storage. If None,
                   experiences are kept in memory only.
        """
        self.store = store
        self._experiences: list[Experience] = []

    # ── Recording ───────────────────────────────────────────────────────

    def record(self, experience: Experience) -> None:
        """Record a new experience.

        Args:
            experience: The experience to record.
        """
        self._experiences.append(experience)

        # Persist to store if available
        if self.store is not None:
            key = f"experience:{experience.generation}:{id(experience)}"
            self.store.store(
                key,
                experience.to_dict(),
                tier="warm",
            )

    def record_experience(
        self,
        context: dict,
        action: dict,
        outcome: str,
        metrics: Optional[dict] = None,
        tags: Optional[set[str]] = None,
        generation: int = 0,
    ) -> Experience:
        """Convenience method to create and record an experience.

        Returns:
            The created Experience object.
        """
        exp = Experience(
            context=context,
            action=action,
            outcome=outcome,
            metrics=metrics or {},
            tags=tags or set(),
            generation=generation,
        )
        self.record(exp)
        return exp

    # ── Similarity Search (Case-Based Reasoning) ────────────────────────

    def find_similar(self, context: dict, n: int = 5) -> list[Experience]:
        """Find experiences with similar context (case-based reasoning).

        Similarity is computed based on shared keys and values in the
        context dict. Higher overlap → higher similarity.

        Args:
            context: The current system state to match against.
            n: Maximum number of similar experiences to return.

        Returns:
            List of up to n most similar experiences, sorted by similarity.
        """
        if not self._experiences:
            return []

        scored: list[tuple[float, Experience]] = []

        for exp in self._experiences:
            sim = self._context_similarity(context, exp.context)
            if sim > 0.0:
                scored.append((sim, exp))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [exp for _, exp in scored[:n]]

    @staticmethod
    def _context_similarity(a: dict, b: dict) -> float:
        """Compute similarity between two context dicts.

        Uses Jaccard similarity on key sets, with bonus for matching values.
        """
        if not a and not b:
            return 1.0
        if not a or not b:
            return 0.0

        keys_a = set(a.keys())
        keys_b = set(b.keys())

        # Jaccard similarity on keys
        key_intersection = keys_a & keys_b
        key_union = keys_a | keys_b
        key_sim = len(key_intersection) / len(key_union) if key_union else 0.0

        # Value match bonus for shared keys
        value_matches = 0
        for key in key_intersection:
            if a[key] == b[key]:
                value_matches += 1

        value_bonus = value_matches / len(key_intersection) if key_intersection else 0.0

        return 0.6 * key_sim + 0.4 * value_bonus

    # ── Generalization ──────────────────────────────────────────────────

    def generalize(self) -> list[GeneralizedRule]:
        """Extract rules from accumulated experiences.

        Groups experiences by (mutation_type, heat_level) and creates
        rules with success rates and confidence scores.

        Returns:
            List of GeneralizedRule objects, sorted by confidence descending.
        """
        if len(self._experiences) < self.MIN_EXPERIENCES_FOR_GENERALIZATION:
            return []

        # Group experiences by action type + context features
        groups: dict[str, list[Experience]] = {}
        for exp in self._experiences:
            if exp.outcome == "pending":
                continue

            # Build group key from action type and key context features
            action_type = exp.action.get("type", exp.action.get("mutation_type", "unknown"))
            heat_level = exp.context.get("heat_level", "unknown")
            group_key = f"{action_type}|{heat_level}"

            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(exp)

        rules: list[GeneralizedRule] = []
        for group_key, experiences in groups.items():
            if len(experiences) < self.MIN_EXPERIENCES_FOR_GENERALIZATION:
                continue

            action_type, heat_level = group_key.split("|", 1)

            successes = [e for e in experiences if e.outcome == "success"]
            failures = [e for e in experiences if e.outcome == "failure"]
            timeouts = [e for e in experiences if e.outcome == "timeout"]

            success_count = len(successes)
            failure_count = len(failures) + len(timeouts)
            total = len(experiences)
            success_rate = success_count / total if total > 0 else 0.0

            # Compute confidence using Laplace smoothing
            confidence = (success_count + 1) / (total + 2)

            if confidence < self.MIN_CONFIDENCE_FOR_RULE:
                continue

            # Compute expected outcome metrics from successful experiences
            avg_speedup = 1.0
            avg_modularity_delta = 0.0
            if successes:
                speedups = [
                    e.metrics.get("speedup", 1.0) for e in successes
                    if "speedup" in e.metrics
                ]
                avg_speedup = (
                    sum(speedups) / len(speedups) if speedups else 1.0
                )
                mod_deltas = [
                    e.metrics.get("modularity_delta", 0.0) for e in successes
                    if "modularity_delta" in e.metrics
                ]
                avg_modularity_delta = (
                    sum(mod_deltas) / len(mod_deltas) if mod_deltas else 0.0
                )

            # Build condition from shared context features
            condition: dict[str, Any] = {"heat_level": heat_level}
            # Add common context keys
            context_keys = set()
            for exp in experiences:
                context_keys.update(exp.context.keys())
            context_keys.discard("heat_level")
            for ck in sorted(context_keys)[:3]:  # Top 3 context features
                values = set(exp.context.get(ck) for exp in experiences)
                if len(values) == 1:
                    condition[ck] = values.pop()

            rule = GeneralizedRule(
                condition=condition,
                action=action_type,
                expected_outcome={
                    "avg_speedup": round(avg_speedup, 3),
                    "avg_modularity_delta": round(avg_modularity_delta, 3),
                    "success_rate": round(success_rate, 3),
                },
                confidence=round(confidence, 3),
                evidence_count=total,
                success_count=success_count,
                failure_count=failure_count,
            )
            rules.append(rule)

        rules.sort(key=lambda r: r.confidence, reverse=True)
        return rules

    # ── Success Rate ────────────────────────────────────────────────────

    def success_rate_for(self, mutation_type: str, heat_level: str) -> float:
        """Historical success rate for a mutation type at a heat level.

        Args:
            mutation_type: The mutation strategy type (e.g., "recompile_language").
            heat_level: The heat level of the target module (e.g., "HOT", "HEAT").

        Returns:
            Success rate between 0.0 and 1.0. Returns 0.0 if no data.
        """
        matching = [
            e for e in self._experiences
            if (e.action.get("type", e.action.get("mutation_type", "")) == mutation_type
                and e.context.get("heat_level") == heat_level
                and e.outcome in ("success", "failure", "timeout"))
        ]
        if not matching:
            return 0.0
        successes = sum(1 for e in matching if e.outcome == "success")
        return successes / len(matching)

    # ── Best Mutation ───────────────────────────────────────────────────

    def best_mutation_for(self, context: dict) -> Optional[str]:
        """Based on experience, what's the best mutation to try?

        Looks at the heat level in the context and returns the mutation
        type with the highest historical success rate for that heat level.

        Args:
            context: Current system state, should include "heat_level".

        Returns:
            Best mutation type string, or None if no data available.
        """
        heat_level = context.get("heat_level", "")
        if not heat_level:
            return None

        # Collect all mutation types seen at this heat level
        mutation_rates: dict[str, tuple[int, int]] = {}  # type → (successes, total)
        for exp in self._experiences:
            if exp.context.get("heat_level") != heat_level:
                continue
            if exp.outcome == "pending":
                continue
            mtype = exp.action.get("type", exp.action.get("mutation_type", ""))
            if not mtype:
                continue
            successes, total = mutation_rates.get(mtype, (0, 0))
            total += 1
            if exp.outcome == "success":
                successes += 1
            mutation_rates[mtype] = (successes, total)

        if not mutation_rates:
            return None

        # Find the mutation with the highest success rate
        best_type = None
        best_rate = -1.0
        for mtype, (successes, total) in mutation_rates.items():
            rate = successes / total if total > 0 else 0.0
            if rate > best_rate:
                best_rate = rate
                best_type = mtype

        return best_type

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def count(self) -> int:
        """Total number of recorded experiences."""
        return len(self._experiences)

    @property
    def experiences(self) -> list[Experience]:
        """Read-only access to all experiences."""
        return list(self._experiences)
