"""Execution tracer for JIT optimization decisions.

Profiles execution to identify hot paths (frequently executed blocks
and functions) that are candidates for JIT compilation. The tracer
accumulates execution counts and exposes thresholds for determining
when a function or block is "hot enough" to justify JIT compilation.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BlockProfile:
    """Execution profile for a single basic block."""
    label: str
    execution_count: int = 0
    function_name: str = ""


@dataclass
class FunctionProfile:
    """Execution profile for a single function."""
    name: str
    call_count: int = 0
    total_cycles: int = 0
    block_profiles: dict[str, BlockProfile] = field(default_factory=dict)
    is_compiled: bool = False


class ExecutionTracer:
    """Profiles execution to identify hot paths for JIT optimization.

    The tracer records execution counts for blocks and functions.
    When a function exceeds the hot threshold, it becomes a candidate
    for JIT compilation. Similarly, frequently-executed blocks within
    a function can guide optimization decisions.

    Args:
        hot_threshold: Number of calls before a function is considered hot.
        block_hot_threshold: Number of executions before a block is hot.
    """

    def __init__(
        self,
        hot_threshold: int = 100,
        block_hot_threshold: int = 1000,
    ) -> None:
        self._hot_threshold = hot_threshold
        self._block_hot_threshold = block_hot_threshold
        self._function_profiles: dict[str, FunctionProfile] = {}
        self._block_counts: dict[str, int] = defaultdict(int)
        self._call_counts: dict[str, int] = defaultdict(int)
        self._edge_counts: dict[tuple[str, str], int] = defaultdict(int)
        self._total_executions: int = 0

    # ── Recording ───────────────────────────────────────────────────────

    def record_block_execution(
        self,
        block_label: str,
        count: int = 1,
        function_name: str = "",
    ) -> None:
        """Record that a basic block was executed.

        Args:
            block_label: Label of the executed block.
            count: Number of times the block was executed.
            function_name: Name of the containing function.
        """
        self._block_counts[block_label] += count
        self._total_executions += count

        # Update function profile
        if function_name:
            profile = self._get_or_create_function_profile(function_name)
            if block_label not in profile.block_profiles:
                profile.block_profiles[block_label] = BlockProfile(
                    label=block_label,
                    function_name=function_name,
                )
            profile.block_profiles[block_label].execution_count += count

    def record_call(self, func_name: str, count: int = 1) -> None:
        """Record a function call.

        Args:
            func_name: Name of the called function.
            count: Number of times the function was called.
        """
        self._call_counts[func_name] += count
        profile = self._get_or_create_function_profile(func_name)
        profile.call_count += count

    def record_edge(
        self,
        from_block: str,
        to_block: str,
        count: int = 1,
    ) -> None:
        """Record a control flow edge between blocks.

        Args:
            from_block: Source block label.
            to_block: Target block label.
            count: Number of times this edge was taken.
        """
        self._edge_counts[(from_block, to_block)] += count

    def record_cycles(self, func_name: str, cycles: int) -> None:
        """Record CPU cycles spent in a function.

        Args:
            func_name: Name of the function.
            cycles: Number of CPU cycles consumed.
        """
        profile = self._get_or_create_function_profile(func_name)
        profile.total_cycles += cycles

    def mark_compiled(self, func_name: str) -> None:
        """Mark a function as having been JIT-compiled.

        Args:
            func_name: Name of the function.
        """
        profile = self._get_or_create_function_profile(func_name)
        profile.is_compiled = True

    # ── Queries ─────────────────────────────────────────────────────────

    def is_hot(self, block_label: str) -> bool:
        """Check if a block has been executed enough to be considered hot.

        Args:
            block_label: Label of the block.

        Returns:
            True if the block exceeds the hot threshold.
        """
        return self._block_counts.get(block_label, 0) >= self._block_hot_threshold

    def should_jit_compile(self, func_name: str) -> bool:
        """Check if a function should be JIT-compiled.

        Returns True if the function's call count exceeds the hot threshold
        and it hasn't been compiled yet.

        Args:
            func_name: Name of the function.

        Returns:
            True if JIT compilation is recommended.
        """
        profile = self._function_profiles.get(func_name)
        if profile is None:
            return False
        return (
            profile.call_count >= self._hot_threshold
            and not profile.is_compiled
        )

    def get_hot_paths(self) -> list[list[str]]:
        """Identify hot execution paths through functions.

        Returns a list of paths, where each path is a list of block labels
        ordered by execution frequency.

        Returns:
            List of hot paths.
        """
        paths = []
        for func_name, profile in self._function_profiles.items():
            if not profile.block_profiles:
                continue

            # Sort blocks by execution count (descending)
            sorted_blocks = sorted(
                profile.block_profiles.values(),
                key=lambda bp: bp.execution_count,
                reverse=True,
            )

            # Only include blocks that are hot
            hot_blocks = [
                bp.label
                for bp in sorted_blocks
                if bp.execution_count >= self._block_hot_threshold
            ]

            if len(hot_blocks) >= 1:
                paths.append(hot_blocks)

        return paths

    def get_hot_functions(self) -> list[str]:
        """Get functions that should be JIT-compiled.

        Returns:
            List of function names sorted by call count (descending).
        """
        candidates = [
            (name, profile.call_count)
            for name, profile in self._function_profiles.items()
            if self.should_jit_compile(name)
        ]
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in candidates]

    def get_block_frequency(self, block_label: str) -> int:
        """Get the execution count for a specific block.

        Args:
            block_label: Label of the block.

        Returns:
            Execution count, or 0 if never executed.
        """
        return self._block_counts.get(block_label, 0)

    def get_call_frequency(self, func_name: str) -> int:
        """Get the call count for a specific function.

        Args:
            func_name: Name of the function.

        Returns:
            Call count, or 0 if never called.
        """
        return self._call_counts.get(func_name, 0)

    def get_edge_frequency(
        self, from_block: str, to_block: str
    ) -> int:
        """Get the frequency of a control flow edge.

        Args:
            from_block: Source block label.
            to_block: Target block label.

        Returns:
            Edge frequency, or 0 if never taken.
        """
        return self._edge_counts.get((from_block, to_block), 0)

    def get_function_profile(
        self, func_name: str
    ) -> Optional[FunctionProfile]:
        """Get the profile for a specific function.

        Returns:
            FunctionProfile or None if not tracked.
        """
        return self._function_profiles.get(func_name)

    # ── Management ──────────────────────────────────────────────────────

    def reset(self) -> None:
        """Clear all tracing data."""
        self._function_profiles.clear()
        self._block_counts.clear()
        self._call_counts.clear()
        self._edge_counts.clear()
        self._total_executions = 0

    def reset_function(self, func_name: str) -> None:
        """Clear tracing data for a specific function."""
        if func_name in self._function_profiles:
            del self._function_profiles[func_name]
        # Clear related block counts
        profile = self._function_profiles.get(func_name)
        if profile:
            for bp in profile.block_profiles.values():
                self._block_counts.pop(bp.label, None)

    @property
    def hot_threshold(self) -> int:
        """Current function hot threshold."""
        return self._hot_threshold

    @hot_threshold.setter
    def hot_threshold(self, value: int) -> None:
        """Set the function hot threshold."""
        self._hot_threshold = value

    @property
    def block_hot_threshold(self) -> int:
        """Current block hot threshold."""
        return self._block_hot_threshold

    @block_hot_threshold.setter
    def block_hot_threshold(self, value: int) -> None:
        """Set the block hot threshold."""
        self._block_hot_threshold = value

    @property
    def total_executions(self) -> int:
        """Total number of block executions recorded."""
        return self._total_executions

    @property
    def tracked_functions(self) -> int:
        """Number of functions being tracked."""
        return len(self._function_profiles)

    @property
    def stats(self) -> dict[str, int]:
        """Tracer statistics."""
        return {
            "total_executions": self._total_executions,
            "tracked_functions": self.tracked_functions,
            "hot_functions": len(self.get_hot_functions()),
            "hot_blocks": sum(
                1 for c in self._block_counts.values()
                if c >= self._block_hot_threshold
            ),
        }

    # ── Internal ────────────────────────────────────────────────────────

    def _get_or_create_function_profile(self, name: str) -> FunctionProfile:
        """Get or create a function profile."""
        if name not in self._function_profiles:
            self._function_profiles[name] = FunctionProfile(name=name)
        return self._function_profiles[name]

    def __repr__(self) -> str:
        return (
            f"ExecutionTracer("
            f"functions={self.tracked_functions}, "
            f"executions={self._total_executions}, "
            f"hot_threshold={self._hot_threshold})"
        )
