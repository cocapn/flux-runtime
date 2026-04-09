"""Pattern Mining — discovers hot execution patterns that could become tiles.

Like a music producer finding the perfect sample, the PatternMiner watches
execution traces to find frequently-occurring subsequences of module calls,
then suggests them as reusable tiles with estimated cost savings.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Any

from flux.adaptive.profiler import AdaptiveProfiler, HeatLevel


# ── Trace Types ───────────────────────────────────────────────────────────────

@dataclass
class ExecutionTrace:
    """A single execution trace — a sequence of module calls."""
    module_calls: list[str] = field(default_factory=list)
    timestamp: float = 0.0
    total_duration_ns: int = 0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    @property
    def length(self) -> int:
        return len(self.module_calls)

    def __len__(self) -> int:
        return self.length


@dataclass
class DiscoveredPattern:
    """A pattern discovered by mining execution traces."""
    sequence: tuple[str, ...]  # ordered module call names
    frequency: int = 0          # how often this pattern appears
    total_occurrences: int = 0  # total times any subsequence occurs
    avg_duration_ns: float = 0.0
    estimated_speedup: float = 1.0
    confidence: float = 0.0     # 0.0 to 1.0 — confidence in the pattern
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    @property
    def length(self) -> int:
        return len(self.sequence)

    @property
    def name(self) -> str:
        """Generate a human-readable name for this pattern."""
        if not self.sequence:
            return "empty_pattern"
        if len(self.sequence) == 1:
            return self.sequence[0]
        return "_".join(self.sequence[:3]) + (f"_x{self.length}" if self.length > 3 else "")

    @property
    def benefit_score(self) -> float:
        """Overall benefit score: frequency × speedup × confidence."""
        return self.frequency * self.estimated_speedup * self.confidence

    def __repr__(self) -> str:
        return (
            f"DiscoveredPattern({self.name!r}, "
            f"freq={self.frequency}, speedup={self.estimated_speedup:.2f}, "
            f"benefit={self.benefit_score:.2f})"
        )


@dataclass
class TileSuggestion:
    """A suggestion to create a new tile from a discovered pattern."""
    pattern: DiscoveredPattern
    suggested_name: str
    tile_type: str  # "compute", "memory", "control", etc.
    estimated_cost: float
    cost_savings: float
    recommended_params: dict[str, Any] = field(default_factory=dict)
    input_ports: list[str] = field(default_factory=list)
    output_ports: list[str] = field(default_factory=list)
    fir_blueprint_hint: str = ""  # description of how to emit FIR

    def __repr__(self) -> str:
        return (
            f"TileSuggestion({self.suggested_name!r}, "
            f"type={self.tile_type}, savings={self.cost_savings:.2f})"
        )


# ── Pattern Miner ─────────────────────────────────────────────────────────────

class PatternMiner:
    """Mines execution traces to find hot patterns that could become tiles.

    Uses a modified Apriori algorithm:
    1. Find all individual module calls and their frequencies
    2. Extend to pairs, triples, etc.
    3. Prune below min_frequency
    4. Score each pattern by: frequency × estimated_speedup_if_fused

    Args:
        profiler: The AdaptiveProfiler providing execution data.
        max_trace_length: Maximum trace length to keep (prevents memory bloat).
    """

    def __init__(
        self,
        profiler: AdaptiveProfiler,
        max_trace_length: int = 10_000,
    ) -> None:
        self.profiler = profiler
        self._trace_log: list[ExecutionTrace] = []
        self._patterns: list[DiscoveredPattern] = []
        self._max_trace_length: int = max_trace_length
        self._subsequence_cache: dict[tuple[str, ...], int] = defaultdict(int)

    # ── Recording ───────────────────────────────────────────────────────

    def record_trace(self, trace: ExecutionTrace) -> None:
        """Record a single execution trace (sequence of module calls).

        Args:
            trace: The ExecutionTrace to record.
        """
        # Prevent memory bloat
        if len(self._trace_log) >= self._max_trace_length:
            self._trace_log.pop(0)
        self._trace_log.append(trace)

        # Update subsequence frequency cache
        calls = tuple(trace.module_calls)
        for length in range(1, min(len(calls) + 1, 6)):  # up to 5-grams
            for start in range(len(calls) - length + 1):
                subseq = calls[start:start + length]
                self._subsequence_cache[subseq] += 1

    def record_call_sequence(self, module_calls: list[str], duration_ns: int = 0) -> None:
        """Convenience: record a raw list of module calls as a trace.

        Args:
            module_calls: List of module path strings.
            duration_ns: Total duration of the trace.
        """
        trace = ExecutionTrace(
            module_calls=list(module_calls),
            total_duration_ns=duration_ns,
        )
        self.record_trace(trace)

    def clear_traces(self) -> None:
        """Clear all recorded traces and mined patterns."""
        self._trace_log.clear()
        self._patterns.clear()
        self._subsequence_cache.clear()

    # ── Mining ──────────────────────────────────────────────────────────

    def mine_patterns(
        self,
        min_frequency: int = 5,
        min_length: int = 2,
        max_length: int = 5,
    ) -> list[DiscoveredPattern]:
        """Find frequently-occurring subsequences in execution traces.

        Uses a modified Apriori algorithm:
        1. Find all individual module calls and their frequencies
        2. Extend to pairs, triples, etc.
        3. Prune below min_frequency
        4. Score each pattern by: frequency × estimated_speedup_if_fused

        Args:
            min_frequency: Minimum number of occurrences to be considered.
            min_length: Minimum sequence length for a pattern.
            max_length: Maximum sequence length for a pattern.

        Returns:
            List of DiscoveredPattern sorted by benefit_score descending.
        """
        self._patterns = []

        # Gather all subsequences above min_frequency
        candidates: list[tuple[tuple[str, ...], int]] = []
        for subseq, freq in self._subsequence_cache.items():
            if freq >= min_frequency and min_length <= len(subseq) <= max_length:
                candidates.append((subseq, freq))

        # Score and enrich each candidate
        heatmap = self.profiler.get_heatmap()
        for subseq, freq in candidates:
            # Estimate speedup if fused: more modules = more overhead to eliminate
            base_speedup = 1.0 + (len(subseq) - 1) * 0.3

            # Boost speedup if modules are hot
            heat_boost = 1.0
            for mod in subseq:
                heat = heatmap.get(mod, HeatLevel.FROZEN)
                if heat == HeatLevel.HEAT:
                    heat_boost *= 1.5
                elif heat == HeatLevel.HOT:
                    heat_boost *= 1.3
                elif heat == HeatLevel.WARM:
                    heat_boost *= 1.1

            estimated_speedup = base_speedup * heat_boost

            # Compute average duration from traces
            total_duration = 0.0
            duration_count = 0
            for trace in self._trace_log:
                trace_calls = tuple(trace.module_calls)
                if subseq in self._contiguous_subsequences(trace_calls, subseq):
                    total_duration += trace.total_duration_ns / max(len(trace_calls), 1)
                    duration_count += 1

            avg_duration = total_duration / duration_count if duration_count > 0 else 0.0

            # Confidence: based on frequency relative to total traces
            total_traces = len(self._trace_log)
            confidence = min(1.0, freq / max(total_traces, 1) * 2)

            pattern = DiscoveredPattern(
                sequence=subseq,
                frequency=freq,
                total_occurrences=freq,
                avg_duration_ns=avg_duration,
                estimated_speedup=estimated_speedup,
                confidence=confidence,
            )
            self._patterns.append(pattern)

        # Sort by benefit score descending
        self._patterns.sort(key=lambda p: p.benefit_score, reverse=True)
        return self._patterns

    @staticmethod
    def _contiguous_subsequences(trace: tuple[str, ...], pattern: tuple[str, ...]) -> list[int]:
        """Find all starting indices where pattern appears contiguously in trace."""
        if not pattern or not trace or len(pattern) > len(trace):
            return []
        indices = []
        for i in range(len(trace) - len(pattern) + 1):
            if trace[i:i + len(pattern)] == pattern:
                indices.append(i)
        return indices

    # ── Suggestions ─────────────────────────────────────────────────────

    def suggest_tile(self, pattern: DiscoveredPattern) -> TileSuggestion:
        """Generate a tile suggestion from a discovered pattern.

        Analyzes the pattern's module call sequence and produces:
        - A name for the suggested tile
        - Estimated FIR blueprint (how to emit the fused instructions)
        - Cost savings estimate
        - Recommended parameters

        Args:
            pattern: The DiscoveredPattern to suggest a tile for.

        Returns:
            TileSuggestion with all metadata.
        """
        heatmap = self.profiler.get_heatmap()

        # Determine tile type based on the pattern's module names
        tile_type = self._infer_tile_type(pattern.sequence, heatmap)

        # Generate name
        name = f"evolved_{pattern.name}"

        # Estimate current cost (sum of individual module costs)
        current_cost = len(pattern.sequence) * 1.0

        # Fused tile cost: removing call overhead between modules
        fused_cost = current_cost * 0.6
        cost_savings = current_cost - fused_cost

        # Generate port hints
        input_ports = [f"in_{i}" for i in range(1, min(pattern.length + 1, 4))]
        output_ports = ["out"]

        # Determine FIR blueprint hint
        fir_hint = self._generate_fir_hint(pattern.sequence, tile_type)

        # Recommended parameters
        params = {
            "source_modules": list(pattern.sequence),
            "fusion_level": pattern.length,
            "estimated_speedup": pattern.estimated_speedup,
        }

        return TileSuggestion(
            pattern=pattern,
            suggested_name=name,
            tile_type=tile_type,
            estimated_cost=fused_cost,
            cost_savings=cost_savings,
            recommended_params=params,
            input_ports=input_ports,
            output_ports=output_ports,
            fir_blueprint_hint=fir_hint,
        )

    @staticmethod
    def _infer_tile_type(
        sequence: tuple[str, ...],
        heatmap: dict[str, HeatLevel],
    ) -> str:
        """Infer the best tile type for a pattern based on its modules."""
        type_counts: dict[str, int] = defaultdict(int)

        for mod in sequence:
            heat = heatmap.get(mod, HeatLevel.FROZEN)
            if "compute" in mod.lower() or "calc" in mod.lower() or "math" in mod.lower():
                type_counts["compute"] += 2
            elif "mem" in mod.lower() or "load" in mod.lower() or "store" in mod.lower():
                type_counts["memory"] += 2
            elif "loop" in mod.lower() or "branch" in mod.lower() or "cond" in mod.lower():
                type_counts["control"] += 2
            elif "a2a" in mod.lower() or "tell" in mod.lower() or "ask" in mod.lower():
                type_counts["a2a"] += 2
            elif "log" in mod.lower() or "print" in mod.lower() or "io" in mod.lower():
                type_counts["effect"] += 2

            # Hot modules lean toward compute
            if heat in (HeatLevel.HEAT, HeatLevel.HOT):
                type_counts["compute"] += 1

        if not type_counts:
            return "compute"

        return max(type_counts, key=type_counts.get)  # type: ignore[arg-type]

    @staticmethod
    def _generate_fir_hint(sequence: tuple[str, ...], tile_type: str) -> str:
        """Generate a human-readable FIR blueprint hint."""
        if not sequence:
            return "empty"

        parts = []
        for i, mod in enumerate(sequence):
            if i == 0:
                parts.append(f"call {mod}")
            else:
                parts.append(f"  → chain {mod}")

        return "\n".join(parts)

    # ── Queries ─────────────────────────────────────────────────────────

    def get_hot_sequences(self, top_n: int = 10) -> list[list[str]]:
        """Get the most frequently-executed module call sequences.

        Args:
            top_n: Maximum number of sequences to return.

        Returns:
            List of module call lists sorted by frequency descending.
        """
        if not self._patterns:
            # Mine with low threshold if no patterns cached
            self.mine_patterns(min_frequency=2, min_length=1, max_length=3)

        return [list(p.sequence) for p in self._patterns[:top_n]]

    def get_patterns(self) -> list[DiscoveredPattern]:
        """Get all discovered patterns (or empty if not yet mined)."""
        return list(self._patterns)

    @property
    def trace_count(self) -> int:
        """Number of recorded traces."""
        return len(self._trace_log)

    @property
    def pattern_count(self) -> int:
        """Number of discovered patterns."""
        return len(self._patterns)

    @property
    def total_subsequences(self) -> int:
        """Total number of unique subsequences in cache."""
        return len(self._subsequence_cache)

    def __repr__(self) -> str:
        return (
            f"PatternMiner("
            f"traces={self.trace_count}, "
            f"patterns={self.pattern_count}, "
            f"subseqs={self.total_subsequences})"
        )
