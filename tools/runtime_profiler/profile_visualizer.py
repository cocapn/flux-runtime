"""FLUX Profile Visualizer — Visual reports from profiling data.

Reads profile JSON files (produced by ``profiler.py``) and generates:

    - ASCII bar charts for opcode frequency and timing
    - Text-based flame graph representation
    - Top-N tables (most executed, most time-consuming, most memory)
    - Side-by-side comparison of two profiles
    - Trend analysis across multiple profile runs

Usage::

    from tools.runtime_profiler.profile_visualizer import ProfileVisualizer

    viz = ProfileVisualizer()
    viz.load("profile.json")
    viz.print_summary()
    viz.print_bar_chart("execution_count", top_n=15)
    viz.print_flame_graph()
    viz.print_top_n("total_time_ns", top_n=10)

    # Compare two profiles
    viz2 = ProfileVisualizer("profile_after.json")
    viz.print_comparison(viz2)

    # Trend analysis across runs
    viz_trend = ProfileVisualizer()
    viz_trend.load_multiple(["run1.json", "run2.json", "run3.json"])
    viz_trend.print_trend("total_time_ns")
"""

from __future__ import annotations

import json
import os
import sys
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Ensure project source is importable
_project_root = os.path.join(os.path.dirname(__file__), "..", "..", "src")
if _project_root not in sys.path:
    sys.path.insert(0, os.path.abspath(_project_root))


# ── Terminal Colors ───────────────────────────────────────────────────────────

class Colors:
    """ANSI terminal color codes (disabled when output is not a TTY)."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"

    @staticmethod
    def disable() -> None:
        """Reset all color codes to empty strings."""
        for attr in ["RESET", "BOLD", "DIM", "RED", "GREEN", "YELLOW", "BLUE",
                      "MAGENTA", "CYAN", "WHITE", "BG_RED", "BG_GREEN",
                      "BG_YELLOW", "BG_BLUE", "BG_MAGENTA", "BG_CYAN", "BG_WHITE"]:
            setattr(Colors, attr, "")

    @staticmethod
    def is_tty() -> bool:
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


if not Colors.is_tty():
    Colors.disable()


# ── Color Palette for Charts ─────────────────────────────────────────────────

CATEGORY_COLORS: Dict[str, str] = {
    "control_flow": Colors.BG_BLUE,
    "data_movement": Colors.BG_CYAN,
    "integer_arithmetic": Colors.BG_GREEN,
    "bitwise": Colors.BG_GREEN,
    "comparison": Colors.BG_YELLOW,
    "stack_frame": Colors.BG_MAGENTA,
    "float_arithmetic": Colors.BG_RED,
    "float_comparison": Colors.BG_RED,
    "simd": Colors.BG_WHITE,
    "memory_management": Colors.BG_MAGENTA,
    "type_operations": Colors.BG_YELLOW,
    "a2a_protocol": Colors.BG_RED,
    "trust_capability": Colors.BG_YELLOW,
    "synchronization": Colors.BG_BLUE,
    "evolution": Colors.BG_MAGENTA,
    "meta": Colors.BG_CYAN,
    "resource": Colors.BG_YELLOW,
    "unknown": Colors.DIM,
}


# ── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class OpcodeData:
    """Parsed opcode statistics from a profile JSON."""
    name: str
    opcode_hex: str
    format_letter: str
    category: str
    execution_count: int
    total_time_ns: int
    avg_time_ns: float
    min_time_ns: int
    max_time_ns: int
    self_time_ns: int
    total_memory_bytes: int
    memory_alloc_count: int
    memory_dealloc_count: int
    hot_pcs: List[Tuple[int, int]]

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "OpcodeData":
        return cls(
            name=d.get("name", ""),
            opcode_hex=d.get("opcode_hex", "0x00"),
            format_letter=d.get("format", "C"),
            category=d.get("category", "unknown"),
            execution_count=d.get("execution_count", 0),
            total_time_ns=d.get("total_time_ns", 0),
            avg_time_ns=d.get("avg_time_ns", 0.0),
            min_time_ns=d.get("min_time_ns", 0),
            max_time_ns=d.get("max_time_ns", 0),
            self_time_ns=d.get("self_time_ns", 0),
            total_memory_bytes=d.get("total_memory_bytes", 0),
            memory_alloc_count=d.get("memory_alloc_count", 0),
            memory_dealloc_count=d.get("memory_dealloc_count", 0),
            hot_pcs=[tuple(pc) for pc in d.get("hot_pcs", [])],
        )


@dataclass
class ProfileData:
    """Parsed complete profile from a JSON file."""
    metadata: Dict[str, Any] = field(default_factory=dict)
    opcode_stats: Dict[str, OpcodeData] = field(default_factory=dict)
    function_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    memory_snapshots: List[Dict[str, Any]] = field(default_factory=list)
    hot_path: List[Tuple[str, int]] = field(default_factory=list)

    @classmethod
    def from_json(cls, path: str) -> "ProfileData":
        """Load profile data from a JSON file."""
        with open(path) as f:
            raw = json.load(f)

        metadata = raw.get("metadata", {})
        opcode_stats = {}
        for name, stats in raw.get("opcode_stats", {}).items():
            opcode_stats[name] = OpcodeData.from_dict(stats)

        function_stats = raw.get("function_stats", {})
        memory_snapshots = raw.get("memory_snapshots", [])
        hot_path = [
            (item.get("opcode", ""), item.get("count", 0))
            for item in raw.get("hot_path", [])
        ]

        return cls(
            metadata=metadata,
            opcode_stats=opcode_stats,
            function_stats=function_stats,
            memory_snapshots=memory_snapshots,
            hot_path=hot_path,
        )

    @property
    def total_time_ns(self) -> int:
        return self.metadata.get("total_time_ns", 0)

    @property
    def total_instructions(self) -> int:
        return self.metadata.get("total_instructions", 0)

    @property
    def total_cycles(self) -> int:
        return self.metadata.get("total_cycles", 0)

    @property
    def program_name(self) -> str:
        return self.metadata.get("program_name", "unknown")

    @property
    def mode(self) -> str:
        return self.metadata.get("mode", "unknown")

    @property
    def peak_memory_bytes(self) -> int:
        return self.metadata.get("peak_memory_bytes", 0)


# ── Formatting Helpers ────────────────────────────────────────────────────────

def fmt_ns(ns: float) -> str:
    """Format nanoseconds to human-readable string."""
    if ns < 1000:
        return f"{ns:.1f} ns"
    elif ns < 1_000_000:
        return f"{ns / 1000:.1f} us"
    elif ns < 1_000_000_000:
        return f"{ns / 1_000_000:.2f} ms"
    else:
        return f"{ns / 1_000_000_000:.3f} s"


def fmt_bytes(n: int) -> str:
    """Format bytes to human-readable string."""
    if n < 0:
        return f"-{fmt_bytes(-n)}"
    if n < 1024:
        return f"{n} B"
    elif n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    elif n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    return f"{n / (1024 * 1024 * 1024):.2f} GB"


def fmt_number(n: int) -> str:
    """Format large integers with commas."""
    return f"{n:,}"


def bar_str(value: float, max_value: float, width: int = 40) -> str:
    """Generate an ASCII bar string of the given width."""
    if max_value <= 0:
        return " " * width
    filled = int((value / max_value) * width)
    filled = min(filled, width)
    return "\u2588" * filled + "\u2591" * (width - filled)


# ── Main Visualizer ───────────────────────────────────────────────────────────

class ProfileVisualizer:
    """Visualize FLUX profiling data with ASCII charts and tables.

    Parameters
    ----------
    profile_path :
        Path to a profile JSON file to load on construction.
    """

    def __init__(self, profile_path: Optional[str] = None) -> None:
        self.profiles: List[ProfileData] = []
        self._current: Optional[ProfileData] = None
        if profile_path:
            self.load(profile_path)

    def load(self, path: str) -> ProfileData:
        """Load a profile JSON file and set it as the current profile.

        Parameters
        ----------
        path :
            Path to the profile JSON file.

        Returns
        -------
        ProfileData
            The loaded profile data.
        """
        data = ProfileData.from_json(path)
        self._current = data
        self.profiles.append(data)
        return data

    def load_multiple(self, paths: List[str]) -> List[ProfileData]:
        """Load multiple profile JSON files for trend analysis.

        Parameters
        ----------
        paths :
            List of paths to profile JSON files.

        Returns
        -------
        List of loaded ProfileData objects.
        """
        for path in paths:
            self.load(path)
        return self.profiles

    @property
    def current(self) -> Optional[ProfileData]:
        """The currently active profile data."""
        return self._current

    # ── Summary ───────────────────────────────────────────────────────────

    def print_summary(self, data: Optional[ProfileData] = None) -> None:
        """Print a compact summary of the profile.

        Parameters
        ----------
        data :
            Profile data to visualize (defaults to current).
        """
        data = data or self._current
        if data is None:
            print("No profile data loaded. Use load() first.")
            return

        w = 55
        print()
        print(f"{Colors.BOLD}{'=' * w}{Colors.RESET}")
        print(f"{Colors.BOLD}  FLUX Profile: {data.program_name}{Colors.RESET}")
        print(f"{Colors.BOLD}{'=' * w}{Colors.RESET}")
        print(f"  Mode:              {data.mode}")
        print(f"  Total Cycles:      {fmt_number(data.total_cycles)}")
        print(f"  Total Instructions:{fmt_number(data.total_instructions)}")
        print(f"  Total Wall Time:   {fmt_ns(data.total_time_ns)}")
        print(f"  Bytecode Size:     {data.metadata.get('bytecode_size', 0):,} bytes")
        print(f"  Peak Memory:       {fmt_bytes(data.peak_memory_bytes)}")
        print(f"  Max Call Depth:    {data.metadata.get('call_depth_max', 0)}")
        print(f"  Avg Call Depth:    {data.metadata.get('call_depth_avg', 0):.1f}")

        if data.total_time_ns > 0 and data.total_instructions > 0:
            ns_per = data.total_time_ns / data.total_instructions
            ips = data.total_instructions / (data.total_time_ns / 1e9)
            print(f"  ns/Instruction:    {ns_per:.1f} ns")
            print(f"  Instructions/sec:  {fmt_number(int(ips))}")

        # Unique opcodes used
        unique_ops = len(data.opcode_stats)
        print(f"  Unique Opcodes:    {unique_ops}")

        halted = data.metadata.get("halted", False)
        error = data.metadata.get("error")
        status = f"{Colors.GREEN}HALTED{Colors.RESET}" if halted else f"{Colors.YELLOW}CYCLE LIMIT{Colors.RESET}"
        if error:
            status = f"{Colors.RED}ERROR{Colors.RESET}: {error}"
        print(f"  Status:            {status}")
        print(f"{Colors.BOLD}{'=' * w}{Colors.RESET}\n")

    # ── ASCII Bar Charts ──────────────────────────────────────────────────

    def print_bar_chart(
        self,
        metric: str = "execution_count",
        top_n: int = 15,
        data: Optional[ProfileData] = None,
        bar_width: int = 35,
        colored: bool = True,
    ) -> None:
        """Print an ASCII horizontal bar chart of opcode statistics.

        Parameters
        ----------
        metric :
            Which metric to chart. One of: ``execution_count``,
            ``total_time_ns``, ``avg_time_ns``, ``total_memory_bytes``,
            ``memory_alloc_count``, ``memory_dealloc_count``.
        top_n :
            Number of items to display.
        data :
            Profile data to visualize.
        bar_width :
            Width of the bar in characters.
        colored :
            Whether to use terminal colors for category highlighting.
        """
        data = data or self._current
        if data is None or not data.opcode_stats:
            print("No opcode data available.")
            return

        # Sort by metric
        sorted_ops = sorted(
            data.opcode_stats.values(),
            key=lambda s: getattr(s, metric),
            reverse=True,
        )[:top_n]

        if not sorted_ops:
            print(f"No data for metric '{metric}'.")
            return

        max_val = getattr(sorted_ops[0], metric)
        if max_val <= 0:
            print(f"All values are 0 for metric '{metric}'.")
            return

        metric_label = metric.replace("_", " ").title()

        # Determine column widths
        name_width = max(len(op.name) for op in sorted_ops)
        name_width = max(name_width, 8)  # minimum "Opcode"
        value_width = max(len(fmt_number(int(getattr(op, metric)))) for op in sorted_ops)
        value_width = max(value_width, len("Value"))

        header = f"  {'Opcode':<{name_width}}  {'Value':>{value_width}}  {'Bar'}"
        separator = f"  {'-' * name_width}  {'-' * value_width}  {'-' * (bar_width + 4)}"

        print(f"\n{Colors.BOLD}{metric_label} (Top {top_n}){Colors.RESET}")
        print(f"{Colors.DIM}{header}{Colors.RESET}")
        print(f"{Colors.DIM}{separator}{Colors.RESET}")

        for op in sorted_ops:
            value = getattr(op, metric)
            bar = bar_str(value, max_val, bar_width)

            # Color the bar based on opcode category
            if colored:
                cat_color = CATEGORY_COLORS.get(op.category, "")
                colored_bar = f"{cat_color}{bar}{Colors.RESET}"
            else:
                colored_bar = bar

            # Format value based on metric
            if "time" in metric:
                val_str = fmt_ns(value)
            elif "bytes" in metric or "memory" in metric:
                val_str = fmt_bytes(value)
            else:
                val_str = fmt_number(int(value))

            line = f"  {op.name:<{name_width}}  {val_str:>{value_width}}  {colored_bar}"
            print(line)

        # Print total
        total = sum(getattr(op, metric) for op in data.opcode_stats.values())
        if "time" in metric:
            total_str = fmt_ns(total)
        elif "bytes" in metric or "memory" in metric:
            total_str = fmt_bytes(total)
        else:
            total_str = fmt_number(int(total))
        print(f"{Colors.DIM}{separator}{Colors.RESET}")
        print(f"  {'TOTAL':<{name_width}}  {total_str:>{value_width}}\n")

    def print_category_chart(
        self,
        data: Optional[ProfileData] = None,
    ) -> None:
        """Print a category-level breakdown bar chart.

        Parameters
        ----------
        data :
            Profile data to visualize.
        """
        data = data or self._current
        if data is None:
            print("No profile data loaded.")
            return

        # Aggregate by category
        cat_data: Dict[str, Dict[str, float]] = defaultdict(lambda: {
            "count": 0, "time": 0, "memory": 0,
        })
        for op in data.opcode_stats.values():
            cat = op.category
            cat_data[cat]["count"] += op.execution_count
            cat_data[cat]["time"] += op.total_time_ns
            cat_data[cat]["memory"] += op.total_memory_bytes

        sorted_cats = sorted(cat_data.items(), key=lambda x: x[1]["count"], reverse=True)
        if not sorted_cats:
            print("No category data available.")
            return

        max_count = sorted_cats[0][1]["count"]

        print(f"\n{Colors.BOLD}Category Breakdown{Colors.RESET}")
        print(f"  {'Category':<22s} {'Instructions':>12s}  {'%':>6s}  {'Bar'}")
        print(f"  {'-' * 22} {'-' * 12}  {'-' * 6}  {'-' * 37}")

        total_count = sum(c["count"] for _, c in sorted_cats)
        for cat_name, c in sorted_cats:
            pct = (c["count"] / total_count * 100) if total_count > 0 else 0
            bar = bar_str(c["count"], max_count, 35)
            cat_color = CATEGORY_COLORS.get(cat_name, "")
            colored_bar = f"{cat_color}{bar}{Colors.RESET}" if cat_color else bar
            print(
                f"  {cat_name:<22s} {fmt_number(int(c['count'])):>12s} "
                f"{pct:>5.1f}%  {colored_bar}"
            )
        print()

    # ── Flame Graph ───────────────────────────────────────────────────────

    def print_flame_graph(
        self,
        data: Optional[ProfileData] = None,
        max_width: int = 80,
        top_n: int = 20,
    ) -> None:
        """Print a text-based flame graph representation.

        Displays opcodes as colored blocks, with width proportional to
        execution time. Opcodes in the same category share the same color.

        Parameters
        ----------
        data :
            Profile data to visualize.
        max_width :
            Maximum width of the flame graph in characters.
        top_n :
            Number of opcodes to include in the flame graph.
        """
        data = data or self._current
        if data is None or not data.opcode_stats:
            print("No opcode data available for flame graph.")
            return

        # Sort by total time
        sorted_ops = sorted(
            data.opcode_stats.values(),
            key=lambda s: s.total_time_ns,
            reverse=True,
        )[:top_n]

        total_time = sum(op.total_time_ns for op in sorted_ops)
        if total_time <= 0:
            print("No timing data available for flame graph.")
            return

        print(f"\n{Colors.BOLD}Flame Graph (proportional to execution time){Colors.RESET}")
        print(f"{Colors.DIM}  Legend: Each row = time attribution per opcode{Colors.RESET}\n")

        # Generate flame layers (bottom = widest, top = narrowest)
        # Layer 0: all opcodes (full width)
        # Layer 1+: sub-grouped by category
        layers: List[List[Tuple[str, float, str]]] = []

        # Layer 0: individual opcodes
        layer0 = []
        for op in sorted_ops:
            pct = (op.total_time_ns / total_time) * 100
            layer0.append((op.name, pct, op.category))
        layers.append(layer0)

        # Layer 1: grouped by category
        cat_groups: Dict[str, float] = defaultdict(float)
        for op in sorted_ops:
            cat_groups[op.category] += (op.total_time_ns / total_time) * 100

        layer1 = []
        for cat_name, pct in sorted(cat_groups.items(), key=lambda x: x[1], reverse=True):
            label = cat_name.replace("_", " ").title()
            layer1.append((label, pct, cat_name))
        layers.append(layer1)

        # Layer 2: hot path
        if data.hot_path:
            hot_total = sum(count for _, count in data.hot_path)
            layer2 = []
            for op_name, count in data.hot_path[:10]:
                pct = (count / hot_total) * 100
                layer2.append((f"hot:{op_name}", pct, "hot"))
            layers.append(layer2)

        # Print layers bottom to top
        for layer_idx, layer in enumerate(reversed(layers)):
            y_label = f"{Colors.DIM}{'base' if layer_idx == len(layers) - 1 else f'L{len(layers) - 1 - layer_idx}':>4s} |{Colors.RESET}"

            for name, pct, cat in layer:
                # Calculate block width
                block_width = max(2, int((pct / 100) * max_width))
                block_width = min(block_width, max_width)

                # Truncate name to fit
                max_name_len = block_width - 2  # leave margin
                if max_name_len < 1:
                    display_name = ""
                elif len(name) <= max_name_len:
                    display_name = name
                else:
                    display_name = name[:max_name_len - 1] + "~"

                # Color based on category
                if cat == "hot":
                    bg = Colors.BG_RED
                else:
                    bg = CATEGORY_COLORS.get(cat, "")

                if bg:
                    block = f"{bg} {display_name:<{block_width - 1}}{Colors.RESET}"
                else:
                    block = f" {display_name:<{block_width - 1}}"

                print(f"{y_label}{block}")

        # Print scale
        print(f"{'':>5s}", end="")
        for i in range(0, max_width, 10):
            pct_mark = f"{i * 100 // max_width}%"
            print(f"{pct_mark:>10s}", end="")
        print(f"\n")

    # ── Top-N Tables ──────────────────────────────────────────────────────

    def print_top_n(
        self,
        metric: str = "execution_count",
        top_n: int = 10,
        data: Optional[ProfileData] = None,
    ) -> None:
        """Print a formatted Top-N table.

        Parameters
        ----------
        metric :
            Which metric to sort by.
        top_n :
            Number of items to show.
        data :
            Profile data.
        """
        data = data or self._current
        if data is None or not data.opcode_stats:
            print("No opcode data available.")
            return

        sorted_ops = sorted(
            data.opcode_stats.values(),
            key=lambda s: getattr(s, metric),
            reverse=True,
        )[:top_n]

        metric_label = metric.replace("_", " ").title()

        print(f"\n{Colors.BOLD}Top {top_n} Opcodes by {metric_label}{Colors.RESET}")
        print(f"  {'#':>3s}  {'Opcode':<10s} {'Category':<22s} {'Value':>14s}  {'%':>6s}")
        print(f"  {'---':>3s}  {'----------':<10s} {'----------------------':<22s} {'--------------':>14s}  {'------':>6s}")

        total = sum(getattr(op, metric) for op in data.opcode_stats.values())
        for i, op in enumerate(sorted_ops, 1):
            value = getattr(op, metric)
            if "time" in metric:
                val_str = fmt_ns(value)
            elif "bytes" in metric or "memory" in metric:
                val_str = fmt_bytes(value)
            else:
                val_str = fmt_number(int(value))

            pct = (value / total * 100) if total > 0 else 0

            # Highlight top 3
            if i <= 3:
                name_str = f"{Colors.RED}{op.name}{Colors.RESET}"
            else:
                name_str = op.name

            print(
                f"  {i:>3d}  {name_str:<10s} {op.category:<22s} "
                f"{val_str:>14s}  {pct:>5.1f}%"
            )
        print()

    def print_memory_top_n(
        self,
        top_n: int = 10,
        data: Optional[ProfileData] = None,
    ) -> None:
        """Print top memory-allocating and memory-deallocating opcodes.

        Parameters
        ----------
        top_n :
            Number of items.
        data :
            Profile data.
        """
        data = data or self._current
        if data is None:
            print("No profile data available.")
            return

        # Filter to opcodes with non-zero memory activity
        mem_ops = [
            op for op in data.opcode_stats.values()
            if op.total_memory_bytes != 0 or op.memory_alloc_count > 0
        ]
        mem_ops.sort(key=lambda op: abs(op.total_memory_bytes), reverse=True)[:top_n]

        if not mem_ops:
            print("\nNo memory activity detected.\n")
            return

        print(f"\n{Colors.BOLD}Top {top_n} Memory-Active Opcodes{Colors.RESET}")
        print(f"  {'Opcode':<10s} {'Allocs':>10s} {'Deallocs':>10s} {'Net Bytes':>14s}")
        print(f"  {'----------':<10s} {'----------':>10s} {'----------':>10s} {'--------------':>14s}")

        for op in mem_ops:
            net = op.total_memory_bytes
            sign = "+" if net > 0 else ""
            print(
                f"  {op.name:<10s} {op.memory_alloc_count:>10,} "
                f"{op.memory_dealloc_count:>10,} {sign}{fmt_bytes(abs(net)):>14s}"
            )
        print()

    # ── Comparison Mode ───────────────────────────────────────────────────

    def print_comparison(
        self,
        other: "ProfileVisualizer",
        top_n: int = 15,
    ) -> None:
        """Print a side-by-side comparison of two profiles.

        Parameters
        ----------
        other :
            Another ProfileVisualizer with a loaded profile.
        top_n :
            Number of opcodes to compare.
        """
        if self._current is None or other._current is None:
            print("Both visualizers must have loaded profile data.")
            return

        a = self._current
        b = other._current

        print(f"\n{Colors.BOLD}{'=' * 80}{Colors.RESET}")
        print(f"{Colors.BOLD}  Profile Comparison: {a.program_name}  vs  {b.program_name}{Colors.RESET}")
        print(f"{Colors.BOLD}{'=' * 80}{Colors.RESET}\n")

        # Summary comparison
        metrics = [
            ("Total Time", "total_time_ns", fmt_ns),
            ("Instructions", "total_instructions", fmt_number),
            ("Cycles", "total_cycles", fmt_number),
            ("Peak Memory", "peak_memory_bytes", fmt_bytes),
        ]

        print(f"  {'Metric':<20s} {'Before':>18s} {'After':>18s} {'Delta':>14s} {'Change':>8s}")
        print(f"  {'-' * 20} {'-' * 18} {'-' * 18} {'-' * 14} {'-' * 8}")

        for label, key, fmt_fn in metrics:
            val_a = a.metadata.get(key, 0)
            val_b = b.metadata.get(key, 0)
            delta = val_b - val_a
            if val_a > 0:
                change_pct = (delta / val_a) * 100
                sign = "+" if change_pct > 0 else ""
                change_str = f"{sign}{change_pct:.1f}%"
            else:
                change_str = "N/A"

            # Color code: green = improvement (less time), red = regression
            if "time" in key.lower() or "memory" in key.lower():
                color = Colors.GREEN if delta < 0 else (Colors.RED if delta > 0 else "")
            else:
                color = ""

            delta_str = fmt_fn(abs(delta))
            if delta < 0:
                delta_str = f"-{delta_str}"

            print(
                f"  {label:<20s} {fmt_fn(val_a):>18s} {fmt_fn(val_b):>18s} "
                f"{delta_str:>14s} {color}{change_str}{Colors.RESET:>8s}"
            )
        print()

        # Per-opcode comparison
        all_opcodes = set(a.opcode_stats.keys()) | set(b.opcode_stats.keys())

        opcode_comparison = []
        for op_name in all_opcodes:
            op_a = a.opcode_stats.get(op_name)
            op_b = b.opcode_stats.get(op_name)

            count_a = op_a.execution_count if op_a else 0
            count_b = op_b.execution_count if op_b else 0
            time_a = op_a.total_time_ns if op_a else 0
            time_b = op_b.total_time_ns if op_b else 0

            if count_a > 0 or count_b > 0:
                opcode_comparison.append((op_name, count_a, count_b, time_a, time_b))

        # Sort by absolute time change
        opcode_comparison.sort(key=lambda x: abs(x[4] - x[3]), reverse=True)

        if opcode_comparison:
            print(f"{Colors.BOLD}Per-Opcode Comparison (Top {top_n} by time change){Colors.RESET}")
            col1 = 10
            print(
                f"  {'Opcode':<{col1}s} "
                f"{'Before Count':>12s} {'After Count':>12s} {'Delta':>8s}  "
                f"{'Before Time':>12s} {'After Time':>12s} {'Delta':>10s}"
            )
            print(
                f"  {'-' * col1} "
                f"{'-' * 12} {'-' * 12} {'-' * 8}  "
                f"{'-' * 12} {'-' * 12} {'-' * 10}"
            )

            for op_name, ca, cb, ta, tb in opcode_comparison[:top_n]:
                delta_c = cb - ca
                delta_t = tb - ta
                sign_c = "+" if delta_c >= 0 else ""
                sign_t = "+" if delta_t >= 0 else ""

                color = Colors.GREEN if delta_t < 0 else (Colors.RED if delta_t > 0 else "")

                print(
                    f"  {op_name:<{col1}s} "
                    f"{fmt_number(ca):>12s} {fmt_number(cb):>12s} {sign_c}{fmt_number(delta_c):>7s}  "
                    f"{fmt_ns(ta):>12s} {fmt_ns(tb):>12s} {color}{sign_t}{fmt_ns(delta_t):>9s}{Colors.RESET}"
                )
            print()

    # ── Trend Analysis ────────────────────────────────────────────────────

    def print_trend(
        self,
        metric: str = "total_time_ns",
        top_n_opcodes: int = 10,
    ) -> None:
        """Print trend analysis across multiple loaded profiles.

        Parameters
        ----------
        metric :
            Metadata metric to track over time (e.g., ``total_time_ns``).
        top_n_opcodes :
            Number of opcodes to include in per-opcode trends.
        """
        if len(self.profiles) < 2:
            print("Need at least 2 profiles for trend analysis. Use load_multiple().")
            return

        print(f"\n{Colors.BOLD}Trend Analysis Across {len(self.profiles)} Profiles{Colors.RESET}")
        print(f"{Colors.DIM}Tracking: {metric.replace('_', ' ').title()}{Colors.RESET}\n")

        # Overall trend
        print(f"  {'#':>3s}  {'Program':<30s} {'Value':>14s} {'Delta':>14s}")
        print(f"  {'---':>3s}  {'------------------------------':<30s} {'--------------':>14s} {'--------------':>14s}")

        prev_val = None
        for i, profile in enumerate(self.profiles, 1):
            val = profile.metadata.get(metric, 0)
            if "time" in metric:
                val_str = fmt_ns(val)
            elif "memory" in metric:
                val_str = fmt_bytes(val)
            else:
                val_str = fmt_number(int(val))

            if prev_val is not None:
                delta = val - prev_val
                if "time" in metric:
                    delta_str = fmt_ns(abs(delta))
                elif "memory" in metric:
                    delta_str = fmt_bytes(abs(delta))
                else:
                    delta_str = fmt_number(int(abs(delta)))
                if delta < 0:
                    delta_str = f"{Colors.GREEN}-{delta_str}{Colors.RESET}"
                elif delta > 0:
                    delta_str = f"{Colors.RED}+{delta_str}{Colors.RESET}"
                else:
                    delta_str = "  0"
            else:
                delta_str = "  -"

            print(f"  {i:>3d}  {profile.program_name:<30s} {val_str:>14s} {delta_str:>14s}")
            prev_val = val

        # Per-opcode trends
        print(f"\n{Colors.BOLD}Per-Opcode Trends (Top {top_n_opcodes} by first profile count){Colors.RESET}")

        # Get union of all opcodes
        all_opcodes: Dict[str, List[int]] = {}
        for profile in self.profiles:
            for op_name, op_data in profile.opcode_stats.items():
                if op_name not in all_opcodes:
                    all_opcodes[op_name] = []
                all_opcodes[op_name].append(op_data.execution_count)

        # Find opcodes with the most activity
        top_opcodes = sorted(
            all_opcodes.items(),
            key=lambda x: max(x[1]) if x[1] else 0,
            reverse=True,
        )[:top_n_opcodes]

        if not top_opcodes:
            print("  No opcode data available.\n")
            return

        # Header
        header = f"  {'Opcode':<10s}"
        for i in range(len(self.profiles)):
            header += f" {'Run ' + str(i + 1):>12s}"
        header += f"  {'Trend':>8s}"
        print(header)
        sep = f"  {'-' * 10}"
        for i in range(len(self.profiles)):
            sep += f" {'-' * 12}"
        sep += f"  {'-' * 8}"
        print(f"{Colors.DIM}{sep}{Colors.RESET}")

        for op_name, counts in top_opcodes:
            row = f"  {op_name:<10s}"
            for count in counts:
                row += f" {fmt_number(count):>12s}"

            # Determine trend
            if len(counts) >= 2:
                first, last = counts[0], counts[-1]
                if first > 0:
                    change = ((last - first) / first) * 100
                    if change < -5:
                        trend = f"{Colors.GREEN}\u2193{Colors.RESET}"
                    elif change > 5:
                        trend = f"{Colors.RED}\u2191{Colors.RESET}"
                    else:
                        trend = "\u2192"
                else:
                    trend = "NEW"
            else:
                trend = "-"
            row += f"  {trend:>6s}"
            print(row)
        print()

    # ── Full Report ───────────────────────────────────────────────────────

    def print_full_report(
        self,
        data: Optional[ProfileData] = None,
        top_n: int = 15,
    ) -> None:
        """Print a comprehensive visual report.

        Includes summary, bar charts, flame graph, top-N tables, and
        category breakdown.

        Parameters
        ----------
        data :
            Profile data to report on.
        top_n :
            Number of items in top-N tables.
        """
        data = data or self._current
        if data is None:
            print("No profile data loaded. Use load() first.")
            return

        self.print_summary(data)
        self.print_bar_chart("execution_count", top_n=top_n, data=data)
        self.print_bar_chart("total_time_ns", top_n=top_n, data=data)
        self.print_category_chart(data)
        self.print_flame_graph(data, top_n=min(top_n, 15))
        self.print_top_n("execution_count", top_n=min(top_n, 10), data=data)
        self.print_top_n("total_time_ns", top_n=min(top_n, 10), data=data)
        self.print_memory_top_n(top_n=min(top_n, 10), data=data)

        # Hot path summary
        if data.hot_path:
            print(f"{Colors.BOLD}Hot Path Summary{Colors.RESET}")
            print(f"  {'#':>3s}  {'Opcode':<12s} {'Weight':>10s}")
            print(f"  {'---':>3s}  {'------------':<12s} {'----------':>10s}")
            total_weight = sum(count for _, count in data.hot_path)
            for i, (op_name, count) in enumerate(data.hot_path[:15], 1):
                pct = (count / total_weight * 100) if total_weight > 0 else 0
                print(f"  {i:>3d}  {op_name:<12s} {count:>10,} ({pct:.1f}%)")
            print()


# ── CLI Entry Point ───────────────────────────────────────────────────────────

def main() -> None:
    """CLI entry point for the profile visualizer."""
    import argparse

    parser = argparse.ArgumentParser(
        description="FLUX Profile Visualizer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # View command
    view_parser = subparsers.add_parser("view", help="View a profile report")
    view_parser.add_argument("profile", help="Path to profile JSON file")
    view_parser.add_argument("--top-n", type=int, default=15, help="Top N items")
    view_parser.add_argument("--no-color", action="store_true", help="Disable colors")

    # Compare command
    compare_parser = subparsers.add_parser("compare", help="Compare two profiles")
    compare_parser.add_argument("profile_before", help="Path to 'before' profile JSON")
    compare_parser.add_argument("profile_after", help="Path to 'after' profile JSON")
    compare_parser.add_argument("--top-n", type=int, default=15, help="Top N items")

    # Trend command
    trend_parser = subparsers.add_parser("trend", help="Trend analysis across profiles")
    trend_parser.add_argument("profiles", nargs="+", help="Paths to profile JSON files")
    trend_parser.add_argument("--metric", default="total_time_ns",
                              help="Metric to track (default: total_time_ns)")

    args = parser.parse_args()

    if args.no_color:
        Colors.disable()

    if args.command == "view":
        viz = ProfileVisualizer(args.profile)
        viz.print_full_report(top_n=args.top_n)

    elif args.command == "compare":
        viz_a = ProfileVisualizer(args.profile_before)
        viz_b = ProfileVisualizer(args.profile_after)
        viz_a.print_comparison(viz_b, top_n=args.top_n)

    elif args.command == "trend":
        viz = ProfileVisualizer()
        viz.load_multiple(args.profiles)
        viz.print_trend(metric=args.metric)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
