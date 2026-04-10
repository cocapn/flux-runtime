"""Flywheel Knowledge Base — accumulated wisdom that makes each revolution smarter.

The knowledge base is the flywheel's memory. It stores:
- Successful mutations (what worked → try again in similar situations)
- Failed mutations (what failed → avoid)
- Generalized rules (patterns that always help)
- Performance baselines (to measure improvement against)

Like a DJ's muscle memory: after hundreds of sets, you don't think about
which track goes next — you just know. The knowledge base encodes that
intuition into rules that make hypothesis generation smarter every revolution.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Any


# ── Generalized Rule ───────────────────────────────────────────────────

@dataclass
class GeneralizedRule:
    """A generalized rule extracted from experiment history.

    Examples:
    - "When a module is HEAT and in Python, recompiling to C always helps"
    - "Fusing map+filter into flatmap always improves by 15-25%"
    - "Merging tiles that share 3+ ports is risky (60% failure rate)"
    """
    condition: str                    # What must be true
    action: str                       # What to do
    expected_outcome: str             # What should happen
    confidence: float = 0.5           # How sure we are (0-1)
    support: int = 1                  # How many experiments support this
    counter_examples: int = 0         # How many times it didn't work
    source: str = ""                  # Where this rule came from
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    @property
    def net_support(self) -> int:
        """Support minus counter-examples."""
        return self.support - self.counter_examples

    @property
    def is_reliable(self) -> bool:
        """Is this rule reliable (confidence > 0.7 and support > 2)?"""
        return self.confidence > 0.7 and self.support > 2

    @property
    def is_discredited(self) -> bool:
        """Has this rule been discredited (more counter-examples than support)?"""
        return self.counter_examples > self.support

    def update_confidence(self) -> float:
        """Recalculate confidence based on support/counter-examples.

        Uses Laplace smoothing: confidence = (support + 1) / (total + 2)
        """
        total = self.support + self.counter_examples
        if total == 0:
            self.confidence = 0.5
        else:
            self.confidence = (self.support + 1) / (total + 2)
        return self.confidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition": self.condition,
            "action": self.action,
            "expected_outcome": self.expected_outcome,
            "confidence": self.confidence,
            "support": self.support,
            "counter_examples": self.counter_examples,
            "source": self.source,
        }

    def __repr__(self) -> str:
        return (
            f"Rule({self.condition!r} → {self.action!r}, "
            f"conf={self.confidence:.2f}, support={self.support})"
        )


# ── Knowledge Base ─────────────────────────────────────────────────────

class KnowledgeBase:
    """Accumulated knowledge that makes each flywheel revolution smarter.

    The knowledge base persists across flywheel revolutions. Each successful
    experiment adds to the success pool; each failure adds to the failure pool.
    Periodically, generalize() extracts patterns from the pool into rules.

    The flywheel queries the knowledge base during hypothesis generation to:
    - Boost confidence for hypothesis types that have worked before
    - Reduce confidence for hypothesis types that have failed
    - Skip hypotheses that match discredited rules
    - Prioritize hypotheses that match highly reliable rules
    """

    def __init__(self, max_history: int = 1000) -> None:
        self.successes: list[dict[str, Any]] = []
        self.failures: list[dict[str, Any]] = []
        self.rules: list[GeneralizedRule] = []
        self.baselines: dict[str, float] = {}     # metric → baseline value
        self._max_history: int = max_history
        self._rule_index: dict[str, list[int]] = defaultdict(list)  # condition → rule indices
        self._mutation_stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"attempts": 0, "successes": 0, "failures": 0,
                      "total_speedup": 0.0, "avg_speedup": 0.0}
        )

    # ── Recording ───────────────────────────────────────────────────────

    def add_success(self, result: Any) -> None:
        """Record a successful experiment result.

        Args:
            result: An ExperimentResult instance.
        """
        entry = self._result_to_entry(result, success=True)
        self.successes.append(entry)

        # Trim if over max
        if len(self.successes) > self._max_history:
            self.successes = self.successes[-self._max_history:]

        # Update mutation stats
        self._update_mutation_stats(entry, success=True)

        # Update baselines
        if hasattr(result, "actual_speedup") and result.actual_speedup > 1.0:
            key = f"speedup:{result.hypothesis.mutation_type.value}"
            current = self.baselines.get(key, 1.0)
            # Exponential moving average
            self.baselines[key] = current * 0.7 + result.actual_speedup * 0.3

    def add_failure(self, result: Any) -> None:
        """Record a failed experiment result.

        Args:
            result: An ExperimentResult instance.
        """
        entry = self._result_to_entry(result, success=False)
        self.failures.append(entry)

        if len(self.failures) > self._max_history:
            self.failures = self.failures[-self._max_history:]

        self._update_mutation_stats(entry, success=False)

    def set_baseline(self, metric: str, value: float) -> None:
        """Set a performance baseline for a metric.

        Args:
            metric: Name of the metric (e.g. "revolution_time_ms").
            value: Baseline value.
        """
        self.baselines[metric] = value

    def get_baseline(self, metric: str) -> Optional[float]:
        """Get the baseline for a metric, or None if not set."""
        return self.baselines.get(metric)

    # ── Generalization ──────────────────────────────────────────────────

    def generalize(self) -> list[GeneralizedRule]:
        """Extract generalized rules from successes and failures.

        Looks for patterns like:
        - "Hypotheses with mutation_type RECOMPILE_LANGUAGE on HEAT modules
           succeed 80% of the time"
        - "Tile merges with risk > 0.6 fail 70% of the time"
        - "Fusing patterns with expected_speedup > 2.0 always succeeds"

        Returns:
            List of newly extracted GeneralizedRule instances.
        """
        new_rules: list[GeneralizedRule] = []

        # Extract rules from mutation stats
        for mut_type, stats in self._mutation_stats.items():
            if stats["attempts"] < 2:
                continue

            total = stats["successes"] + stats["failures"]
            success_rate = stats["successes"] / total if total > 0 else 0

            # Check if this matches an existing rule
            condition = f"mutation_type == {mut_type}"
            existing = self._find_rule_by_condition(condition)

            if existing is not None:
                # Update existing rule
                existing.support = stats["successes"]
                existing.counter_examples = stats["failures"]
                existing.update_confidence()
            elif total >= 3:
                # Create new rule
                if success_rate > 0.7:
                    rule = GeneralizedRule(
                        condition=condition,
                        action=f"apply {mut_type} mutation",
                        expected_outcome=f"success with ~{success_rate:.0%} probability",
                        confidence=success_rate,
                        support=stats["successes"],
                        counter_examples=stats["failures"],
                        source="generalization",
                    )
                    self.rules.append(rule)
                    self._rule_index[condition].append(len(self.rules) - 1)
                    new_rules.append(rule)
                elif success_rate < 0.3:
                    rule = GeneralizedRule(
                        condition=condition,
                        action=f"avoid {mut_type} mutation",
                        expected_outcome=f"likely failure (~{(1-success_rate):.0%} probability)",
                        confidence=1.0 - success_rate,
                        support=stats["failures"],
                        counter_examples=stats["successes"],
                        source="generalization",
                    )
                    self.rules.append(rule)
                    self._rule_index[condition].append(len(self.rules) - 1)
                    new_rules.append(rule)

        return new_rules

    # ── Querying ────────────────────────────────────────────────────────

    def query_similar(self, hypothesis: Any) -> list[dict[str, Any]]:
        """Find similar past experiments to a hypothesis.

        Matches based on mutation_type and target_path similarity.

        Args:
            hypothesis: A Hypothesis instance.

        Returns:
            List of past experiment entries (success or failure dicts).
        """
        similar: list[dict[str, Any]] = []

        mut_type = hypothesis.mutation_type.value
        target = hypothesis.target_path

        for entry in self.successes + self.failures:
            if entry.get("mutation_type") == mut_type:
                # Exact match on mutation type
                similar.append(entry)
            elif target and entry.get("target_path") == target:
                # Match on target path
                similar.append(entry)

        # Sort by recency (newest first)
        similar.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return similar[:20]  # limit results

    def predict_success_probability(self, hypothesis: Any) -> float:
        """Based on historical data, how likely is this to succeed?

        Uses Bayesian-inspired combination of:
        1. Historical success rate for this mutation type
        2. Prior from hypothesis confidence
        3. Rule-based adjustments

        Args:
            hypothesis: A Hypothesis instance.

        Returns:
            Probability between 0.0 and 1.0.
        """
        mut_type = hypothesis.mutation_type.value
        stats = self._mutation_stats[mut_type]

        # Historical success rate
        if stats["attempts"] > 0:
            historical_rate = stats["successes"] / stats["attempts"]
            # Weight by number of data points (more data = more weight)
            data_weight = min(stats["attempts"] / 10.0, 0.9)  # max 0.9
            prior_weight = 1.0 - data_weight
            base_prob = prior_weight * hypothesis.confidence + data_weight * historical_rate
        else:
            base_prob = hypothesis.confidence

        # Rule-based adjustments
        condition = f"mutation_type == {mut_type}"
        rule = self._find_rule_by_condition(condition)
        if rule is not None:
            if rule.is_reliable:
                # Boost toward rule's confidence
                base_prob = 0.3 * base_prob + 0.7 * rule.confidence
            elif rule.is_discredited:
                # Suppress based on discredited rule
                base_prob *= 0.3

        # Risk adjustment
        risk_penalty = hypothesis.risk_level * 0.2
        adjusted = base_prob - risk_penalty

        return max(0.0, min(1.0, adjusted))

    def should_skip(self, hypothesis: Any) -> tuple[bool, str]:
        """Check if a hypothesis should be skipped based on knowledge.

        Skips hypotheses that:
        - Match discredited rules
        - Have been tried and failed > 3 times with same params

        Args:
            hypothesis: A Hypothesis instance.

        Returns:
            (should_skip, reason) tuple.
        """
        mut_type = hypothesis.mutation_type.value
        stats = self._mutation_stats[mut_type]

        # Check if this mutation type has been failing consistently
        if stats["attempts"] >= 3 and stats["failures"] > stats["successes"] * 2:
            return True, (
                f"Mutation type {mut_type} has failed "
                f"{stats['failures']}/{stats['attempts']} times — skipping"
            )

        # Check discredited rules
        condition = f"mutation_type == {mut_type}"
        rule = self._find_rule_by_condition(condition)
        if rule is not None and rule.is_discredited:
            return True, f"Rule discredited: {rule.condition} → {rule.action}"

        return False, ""

    def get_mutation_stats(self, mutation_type: str) -> dict[str, Any]:
        """Get statistics for a specific mutation type.

        Args:
            mutation_type: The mutation type name.

        Returns:
            Dict with attempts, successes, failures, total_speedup, avg_speedup.
        """
        return dict(self._mutation_stats.get(mutation_type, {
            "attempts": 0, "successes": 0, "failures": 0,
            "total_speedup": 0.0, "avg_speedup": 0.0,
        }))

    # ── Serialization ───────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serialize knowledge base to JSON-compatible dict."""
        return {
            "successes": self.successes[-50:],  # Keep last 50 for serialization
            "failures": self.failures[-50:],
            "rules": [r.to_dict() for r in self.rules],
            "baselines": dict(self.baselines),
            "mutation_stats": dict(self._mutation_stats),
            "total_successes": len(self.successes),
            "total_failures": len(self.failures),
            "total_rules": len(self.rules),
        }

    def size(self) -> int:
        """Total number of stored entries."""
        return len(self.successes) + len(self.failures) + len(self.rules)

    def clear(self) -> None:
        """Clear all accumulated knowledge."""
        self.successes.clear()
        self.failures.clear()
        self.rules.clear()
        self.baselines.clear()
        self._rule_index.clear()
        self._mutation_stats.clear()

    # ── Internal ────────────────────────────────────────────────────────

    @staticmethod
    def _result_to_entry(result: Any, success: bool) -> dict[str, Any]:
        """Convert an ExperimentResult to a knowledge entry dict."""
        entry: dict[str, Any] = {
            "success": success,
            "timestamp": time.time(),
        }
        if hasattr(result, "hypothesis"):
            h = result.hypothesis
            entry["mutation_type"] = h.mutation_type.value
            entry["target_path"] = h.target_path
            entry["expected_speedup"] = h.expected_speedup
            entry["risk_level"] = h.risk_level
            entry["confidence"] = h.confidence
            entry["source"] = h.source
        if hasattr(result, "actual_speedup"):
            entry["actual_speedup"] = result.actual_speedup
        if hasattr(result, "outcome"):
            entry["outcome"] = result.outcome.value
        if hasattr(result, "details"):
            entry["details"] = result.details
        return entry

    def _update_mutation_stats(self, entry: dict[str, Any], success: bool) -> None:
        """Update per-mutation-type statistics."""
        mut_type = entry.get("mutation_type", "unknown")
        stats = self._mutation_stats[mut_type]
        stats["attempts"] += 1
        if success:
            stats["successes"] += 1
            speedup = entry.get("actual_speedup", 1.0)
            stats["total_speedup"] += speedup
            stats["avg_speedup"] = stats["total_speedup"] / stats["successes"]
        else:
            stats["failures"] += 1

    def _find_rule_by_condition(self, condition: str) -> Optional[GeneralizedRule]:
        """Find a rule matching a condition string."""
        indices = self._rule_index.get(condition, [])
        for idx in indices:
            if idx < len(self.rules):
                return self.rules[idx]
        return None

    def __repr__(self) -> str:
        return (
            f"KnowledgeBase("
            f"successes={len(self.successes)}, "
            f"failures={len(self.failures)}, "
            f"rules={len(self.rules)}, "
            f"baselines={len(self.baselines)})"
        )
