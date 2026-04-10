"""Performance Predictor — predicts system performance without running workloads.

Uses cost model for static analysis, historical data for regression,
and trend extrapolation for forecasting.
"""

from __future__ import annotations

import time
import math
from dataclasses import dataclass, field
from typing import Optional, Any

from flux.cost.model import CostModel, CostEstimate
from flux.adaptive.profiler import AdaptiveProfiler, HeatLevel


# ── Memory Store (dict-based fallback) ─────────────────────────────────

class MemoryStore:
    """Simple dict-based memory store for historical performance data.

    Acts as a lightweight database for the predictor's historical data.
    For production use, this could be backed by SQLite, Redis, etc.
    """

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}
        self._history: list[dict[str, Any]] = []

    def put(self, key: str, value: Any) -> None:
        """Store a value."""
        self._store[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value, or return default."""
        return self._store.get(key, default)

    def has(self, key: str) -> bool:
        """Check if a key exists."""
        return key in self._store

    def delete(self, key: str) -> bool:
        """Delete a key. Returns True if it existed."""
        if key in self._store:
            del self._store[key]
            return True
        return False

    def append_history(self, entry: dict[str, Any]) -> None:
        """Append an entry to the history log."""
        entry.setdefault("timestamp", time.time())
        self._history.append(entry)

    def get_history(self, key: Optional[str] = None) -> list[dict[str, Any]]:
        """Get history entries, optionally filtered by a key presence."""
        if key is None:
            return list(self._history)
        return [e for e in self._history if key in e]

    def get_recent(self, n: int = 10) -> list[dict[str, Any]]:
        """Get the most recent N history entries."""
        return list(self._history[-n:])

    def clear(self) -> None:
        """Clear all stored data."""
        self._store.clear()
        self._history.clear()

    @property
    def size(self) -> int:
        """Total number of stored keys."""
        return len(self._store)

    @property
    def history_size(self) -> int:
        """Total number of history entries."""
        return len(self._history)


# ── Data Types ──────────────────────────────────────────────────────────

@dataclass
class CapacityForecast:
    """Forecast of when the system will hit capacity limits."""
    current_load: float              # 0.0-1.0 utilization
    growth_rate: float               # growth per time unit
    time_horizon: int                # number of time units to forecast
    projected_loads: list[float] = field(default_factory=list)
    time_to_capacity: float = float('inf')  # time units until full
    risk_level: str = "LOW"          # LOW / MEDIUM / HIGH / CRITICAL
    recommendation: str = ""


# ── Performance Predictor ───────────────────────────────────────────────

class PerformancePredictor:
    """Predicts system performance without running workloads.

    Uses:
    - Cost model for static analysis
    - Historical data for regression
    - Trend extrapolation for forecasting
    """

    # Speed factors for different languages
    SPEED_FACTORS: dict[str, float] = {
        "python": 1.0,
        "typescript": 2.0,
        "csharp": 4.0,
        "c": 8.0,
        "c_simd": 16.0,
        "rust": 10.0,
    }

    # Base execution times per language (nanoseconds for typical function call)
    BASE_TIMES_NS: dict[str, float] = {
        "python": 10000.0,
        "typescript": 5000.0,
        "csharp": 2500.0,
        "c": 1250.0,
        "c_simd": 625.0,
        "rust": 1000.0,
    }

    def __init__(self, cost_model: CostModel, memory_store: Optional[MemoryStore] = None) -> None:
        self.cost_model = cost_model
        self.store = memory_store or MemoryStore()

    # ── Execution Time Prediction ───────────────────────────────────────

    def predict_execution_time(self, module_path: str) -> float:
        """Predict execution time for a module (in nanoseconds).

        Uses historical data if available, otherwise falls back to
        language-based estimation.

        Args:
            module_path: Dot-separated module identifier.

        Returns:
            Predicted execution time in nanoseconds.
        """
        # Check for stored historical average
        history = self.store.get_history("module_path")
        relevant = [e for e in history if e.get("module_path") == module_path]

        if relevant:
            # Use exponential moving average of historical data
            avg = sum(e.get("execution_time_ns", 0) for e in relevant) / len(relevant)
            recent_weight = 0.6
            old_weight = 0.4

            if len(relevant) > 1:
                recent = relevant[-1].get("execution_time_ns", avg)
                old_avg = sum(e.get("execution_time_ns", avg) for e in relevant[:-1]) / (len(relevant) - 1)
                return recent_weight * recent + old_weight * old_avg
            return avg

        # Fall back to language-based estimation
        lang = self.store.get(f"lang:{module_path}", "python")
        base = self.BASE_TIMES_NS.get(lang, 10000.0)
        return base

    # ── Heat Level Prediction ───────────────────────────────────────────

    def predict_heat_level(self, module_path: str) -> str:
        """Predict if a module will be FROZEN/COOL/WARM/HOT/HEAT.

        Uses historical call frequency and cost model analysis.

        Args:
            module_path: Dot-separated module identifier.

        Returns:
            Heat level string: FROZEN, COOL, WARM, HOT, or HEAT.
        """
        # Check for stored call frequency data
        call_count = self.store.get(f"calls:{module_path}", 0)
        total_calls = sum(
            self.store.get(f"calls:{k}", 0)
            for k in self.store._store
            if k.startswith("calls:")
        )

        if total_calls == 0 or call_count == 0:
            return "FROZEN"

        # Estimate percentile
        all_counts = [
            self.store.get(k, 0)
            for k in self.store._store
            if k.startswith("calls:")
        ]
        all_counts.sort(reverse=True)
        n = len(all_counts)

        if n == 0:
            return "FROZEN"

        # Find rank of this module
        rank = 0
        for i, c in enumerate(all_counts):
            if c <= call_count:
                rank = i
                break
        else:
            rank = n - 1

        fraction = rank / max(n - 1, 1)

        if fraction < 0.2:
            return "HEAT"
        elif fraction < 0.5:
            return "HOT"
        elif fraction > 0.8:
            return "COOL"
        elif call_count <= 1:
            return "COOL"
        else:
            return "WARM"

    # ── Speedup Prediction ──────────────────────────────────────────────

    def predict_speedup(self, module_path: str, target_lang: str) -> float:
        """Predict speedup from recompilation.

        Args:
            module_path: Dot-separated module identifier.
            target_lang: Target language to recompile to.

        Returns:
            Predicted speedup factor (1.0 = no change).
        """
        current_lang = self.store.get(f"lang:{module_path}", "python")
        current_speed = self.SPEED_FACTORS.get(current_lang, 1.0)
        target_speed = self.SPEED_FACTORS.get(target_lang, 1.0)

        if current_speed == 0:
            return 1.0

        return target_speed / current_speed

    # ── Bottleneck Prediction ───────────────────────────────────────────

    def predict_bottleneck(self, module_paths: list[str]) -> str:
        """Predict which module will be the bottleneck.

        The bottleneck is the module with the highest predicted
        execution time × call frequency.

        Args:
            module_paths: List of module paths to evaluate.

        Returns:
            Path of the predicted bottleneck module.
            Empty string if no modules provided.
        """
        if not module_paths:
            return ""

        worst_path = ""
        worst_cost = 0.0

        for path in module_paths:
            exec_time = self.predict_execution_time(path)
            call_count = self.store.get(f"calls:{path}", 1)
            total_cost = exec_time * call_count

            if total_cost > worst_cost:
                worst_cost = total_cost
                worst_path = path

        return worst_path

    # ── Capacity Forecasting ────────────────────────────────────────────

    def forecast_capacity(
        self,
        current_load: float,
        growth_rate: float,
        time_horizon: int,
    ) -> CapacityForecast:
        """Forecast when the system will hit capacity limits.

        Args:
            current_load: Current utilization (0.0-1.0).
            growth_rate: Growth per time unit (e.g. 0.05 = 5% per unit).
            time_horizon: Number of time units to forecast.

        Returns:
            CapacityForecast with projected loads and recommendations.
        """
        projected: list[float] = []
        time_to_full = float('inf')

        for t in range(time_horizon + 1):
            # Exponential growth model
            load = current_load * ((1.0 + growth_rate) ** t)
            projected.append(min(load, 2.0))  # cap at 200%

            if load >= 1.0 and time_to_full == float('inf'):
                time_to_full = float(t)

        # Determine risk level
        if current_load < 0.5:
            risk = "LOW"
            recommendation = "System has plenty of headroom."
        elif current_load < 0.75:
            risk = "MEDIUM"
            recommendation = "Monitor growth. Consider optimization within 2-3 time units."
        elif current_load < 0.9:
            risk = "HIGH"
            recommendation = "Urgent: start optimizing hot paths."
        else:
            risk = "CRITICAL"
            recommendation = "Capacity exceeded! Immediate action required."

        if time_to_full < 5:
            recommendation += f" Capacity expected in ~{time_to_full:.0f} time units."

        return CapacityForecast(
            current_load=current_load,
            growth_rate=growth_rate,
            time_horizon=time_horizon,
            projected_loads=projected,
            time_to_capacity=time_to_full,
            risk_level=risk,
            recommendation=recommendation,
        )

    # ── Mutation Recommendation ─────────────────────────────────────────

    def recommend_mutation(self, module_path: str) -> str:
        """Based on prediction, what's the best mutation?

        Args:
            module_path: Dot-separated module identifier.

        Returns:
            Mutation type string, e.g. "recompile:rust", "replace_tile", "inline".
        """
        heat = self.predict_heat_level(module_path)
        current_lang = self.store.get(f"lang:{module_path}", "python")

        if heat == "FROZEN":
            return "none"  # Don't optimize unused modules

        if heat in ("HEAT", "HOT"):
            if current_lang == "python":
                return "recompile:rust"
            elif current_lang == "typescript":
                return "recompile:c"
            elif current_lang in ("c", "csharp"):
                return "recompile:c_simd"
            else:
                return "inline"  # Already in fast language

        if heat == "WARM":
            if current_lang == "python":
                return "recompile:typescript"
            return "none"

        # COOL — don't optimize
        return "none"

    # ── Helpers ─────────────────────────────────────────────────────────

    def record_execution(
        self,
        module_path: str,
        execution_time_ns: float,
        language: str = "python",
    ) -> None:
        """Record a module execution for future predictions.

        Args:
            module_path: Module identifier.
            execution_time_ns: Measured execution time.
            language: Language of the module.
        """
        self.store.append_history({
            "module_path": module_path,
            "execution_time_ns": execution_time_ns,
            "language": language,
        })

        # Update call count
        current_calls = self.store.get(f"calls:{module_path}", 0)
        self.store.put(f"calls:{module_path}", current_calls + 1)

        # Update language mapping
        if not self.store.has(f"lang:{module_path}"):
            self.store.put(f"lang:{module_path}", language)

    def __repr__(self) -> str:
        return (
            f"PerformancePredictor("
            f"history={self.store.history_size}, "
            f"keys={self.store.size})"
        )
