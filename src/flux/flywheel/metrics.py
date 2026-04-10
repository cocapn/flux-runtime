"""Flywheel Metrics — tracks metrics across flywheel revolutions.

The metrics module is the flywheel's dashboard. It tracks:
- Per-revolution timing, improvements, experiments, success rates
- Cumulative totals and running averages
- Velocity trend (accelerating, steady, decelerating)
- Acceleration factors over time

Like a speedometer that also tells you whether you're accelerating or braking.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Any


# ── Flywheel Metrics ───────────────────────────────────────────────────

class FlywheelMetrics:
    """Tracks metrics across flywheel revolutions.

    Each revolution contributes a data point. The metrics class computes
    trends, averages, and velocity changes to answer questions like:
    - Is the flywheel accelerating? (getting faster each revolution)
    - Is the success rate improving? (learning from failures)
    - What's the total cumulative speedup?
    """

    def __init__(self) -> None:
        # Per-revolution tracking
        self.revolution_times: list[float] = []         # wall-clock time per revolution (s)
        self.improvements_per_revolution: list[int] = []
        self.experiments_per_revolution: list[int] = []
        self.success_rate_per_revolution: list[float] = []
        self.acceleration_factors: list[float] = []     # acceleration factor at end of each rev

        # Cumulative tracking
        self.total_improvements: int = 0
        self.total_experiments: int = 0
        self.total_successes: int = 0
        self.total_failures: int = 0
        self.cumulative_speedup: float = 1.0
        self.start_time: float = time.time()
        self.last_revolution_time: float = 0.0

    def record_revolution(self, record: Any) -> None:
        """Record metrics from a completed revolution.

        Args:
            record: A FlywheelRecord instance.
        """
        import time as _time
        rev_time_s = record.revolution_time_ns / 1_000_000_000.0
        self.revolution_times.append(rev_time_s)
        self.improvements_per_revolution.append(record.successes)
        self.experiments_per_revolution.append(
            record.successes + record.failures + record.timeouts + record.inconclusive
        )
        self.success_rate_per_revolution.append(record.success_rate)
        self.acceleration_factors.append(record.acceleration_after)

        # Update cumulative totals
        self.total_improvements += record.successes
        self.total_experiments += (
            record.successes + record.failures + record.timeouts + record.inconclusive
        )
        self.total_successes += record.successes
        self.total_failures += record.failures + record.timeouts
        self.last_revolution_time = _time.time()

        # Update cumulative speedup
        if record.acceleration_after > 0:
            self.cumulative_speedup = record.acceleration_after

    def get_velocity_trend(self) -> str:
        """Determine if the flywheel is accelerating, steady, or decelerating.

        Uses the last 3 revolution times to compute a trend:
        - If times are decreasing → "accelerating" (each revolution is faster)
        - If times are roughly stable → "steady"
        - If times are increasing → "decelerating"

        Returns:
            One of: "accelerating", "steady", "decelerating", "insufficient_data"
        """
        if len(self.revolution_times) < 3:
            return "insufficient_data"

        recent = self.revolution_times[-3:]
        diffs = [recent[i + 1] - recent[i] for i in range(len(recent) - 1)]

        avg_diff = sum(diffs) / len(diffs)
        avg_time = sum(recent) / len(recent)

        if avg_time == 0:
            return "steady"

        relative_change = avg_diff / avg_time

        if relative_change < -0.05:  # Getting 5%+ faster
            return "accelerating"
        elif relative_change > 0.05:  # Getting 5%+ slower
            return "decelerating"
        else:
            return "steady"

    def get_success_trend(self) -> str:
        """Determine if success rate is improving, steady, or declining."""
        if len(self.success_rate_per_revolution) < 3:
            return "insufficient_data"

        recent = self.success_rate_per_revolution[-3:]
        diffs = [recent[i + 1] - recent[i] for i in range(len(recent) - 1)]

        avg_diff = sum(diffs) / len(diffs)

        if avg_diff > 0.05:
            return "improving"
        elif avg_diff < -0.05:
            return "declining"
        else:
            return "steady"

    def get_average_revolution_time(self) -> float:
        """Average time per revolution in seconds."""
        if not self.revolution_times:
            return 0.0
        return sum(self.revolution_times) / len(self.revolution_times)

    def get_average_success_rate(self) -> float:
        """Average success rate across all revolutions."""
        if not self.success_rate_per_revolution:
            return 0.0
        return sum(self.success_rate_per_revolution) / len(self.success_rate_per_revolution)

    def get_average_improvements_per_rev(self) -> float:
        """Average number of improvements per revolution."""
        if not self.improvements_per_revolution:
            return 0.0
        return sum(self.improvements_per_revolution) / len(self.improvements_per_revolution)

    @property
    def overall_success_rate(self) -> float:
        """Overall success rate across all experiments."""
        total = self.total_successes + self.total_failures
        if total == 0:
            return 0.0
        return self.total_successes / total

    @property
    def uptime_seconds(self) -> float:
        """Seconds since metrics were created."""
        return time.time() - self.start_time

    @property
    def revolutions_completed(self) -> int:
        """Number of completed revolutions."""
        return len(self.revolution_times)

    def to_dict(self) -> dict[str, Any]:
        """Serialize metrics to a JSON-compatible dict."""
        return {
            "per_revolution": {
                "times_s": self.revolution_times,
                "improvements": self.improvements_per_revolution,
                "experiments": self.experiments_per_revolution,
                "success_rates": self.success_rate_per_revolution,
                "acceleration_factors": self.acceleration_factors,
            },
            "cumulative": {
                "total_improvements": self.total_improvements,
                "total_experiments": self.total_experiments,
                "total_successes": self.total_successes,
                "total_failures": self.total_failures,
                "cumulative_speedup": self.cumulative_speedup,
                "overall_success_rate": self.overall_success_rate,
            },
            "trends": {
                "velocity": self.get_velocity_trend(),
                "success": self.get_success_trend(),
            },
            "averages": {
                "revolution_time_s": self.get_average_revolution_time(),
                "success_rate": self.get_average_success_rate(),
                "improvements_per_rev": self.get_average_improvements_per_rev(),
            },
            "uptime_s": self.uptime_seconds,
            "revolutions": self.revolutions_completed,
        }

    def reset(self) -> None:
        """Reset all metrics."""
        self.revolution_times.clear()
        self.improvements_per_revolution.clear()
        self.experiments_per_revolution.clear()
        self.success_rate_per_revolution.clear()
        self.acceleration_factors.clear()
        self.total_improvements = 0
        self.total_experiments = 0
        self.total_successes = 0
        self.total_failures = 0
        self.cumulative_speedup = 1.0
        self.start_time = time.time()
        self.last_revolution_time = 0.0

    def __repr__(self) -> str:
        return (
            f"FlywheelMetrics("
            f"revs={self.revolutions_completed}, "
            f"improvements={self.total_improvements}, "
            f"speedup={self.cumulative_speedup:.2f}x, "
            f"trend={self.get_velocity_trend()})"
        )
