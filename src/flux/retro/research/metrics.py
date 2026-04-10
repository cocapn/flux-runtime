"""Metrics collection and analysis for reverse engineering research.

Provides standardized measurement of implementation quality across all
10 target games, enabling cross-target comparative analysis.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Generator


@dataclass
class MetricSnapshot:
    """A point-in-time measurement of implementation characteristics."""

    timestamp: str = ""
    bytecode_size: int = 0
    code_section_size: int = 0
    total_cycles: int = 0
    peak_memory_bytes: int = 0
    num_instructions: int = 0
    num_registers_used: int = 0
    num_basic_blocks: int = 0
    opcodes_used: list = field(default_factory=list)
    compile_time_ms: float = 0.0
    execution_time_ms: float = 0.0
    test_pass_rate: float = 0.0
    coverage_lines: float = 0.0
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


@dataclass
class Metrics:
    """Accumulated metrics across multiple snapshots for trend analysis."""

    target: str
    snapshots: list[MetricSnapshot] = field(default_factory=list)

    def add(self, snapshot: MetricSnapshot) -> None:
        self.snapshots.append(snapshot)

    def latest(self) -> MetricSnapshot | None:
        return self.snapshots[-1] if self.snapshots else None

    def trend(self, key: str) -> list[float]:
        """Extract a time series for a given metric key."""
        return [
            getattr(s, key, 0)
            for s in self.snapshots
            if isinstance(getattr(s, key, None), (int, float))
        ]

    def improvement(self, key: str) -> float:
        """Compute improvement ratio between first and latest snapshot."""
        vals = self.trend(key)
        if len(vals) < 2 or vals[0] == 0:
            return 0.0
        return (vals[0] - vals[-1]) / vals[0]

    def summary(self) -> str:
        """Format a readable summary."""
        latest = self.latest()
        if not latest:
            return f"No metrics recorded for {self.target}"
        lines = [
            f"Metrics: {self.target} ({len(self.snapshots)} snapshots)",
            f"  Bytecode:    {latest.bytecode_size} bytes",
            f"  Cycles:      {latest.total_cycles:,}",
            f"  Memory:      {latest.peak_memory_bytes:,} bytes",
            f"  Registers:   {latest.num_registers_used}",
            f"  Blocks:      {latest.num_basic_blocks}",
            f"  Opcodes:     {len(latest.opcodes_used)} unique",
            f"  Test rate:   {latest.test_pass_rate:.0%}",
            f"  Compile:     {latest.compile_time_ms:.1f}ms",
            f"  Execute:     {latest.execution_time_ms:.1f}ms",
        ]
        return "\n".join(lines)


class Timer:
    """Context manager for timing execution."""

    def __init__(self) -> None:
        self.elapsed_ms: float = 0.0
        self._start: float = 0.0

    def __enter__(self) -> Timer:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: object) -> None:
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000


@contextmanager
def measure_compile() -> Generator[Timer, None, None]:
    """Context manager that measures compile time."""
    t = Timer()
    with t:
        yield t


@contextmanager
def measure_execution() -> Generator[Timer, None, None]:
    """Context manager that measures execution time."""
    t = Timer()
    with t:
        yield t
