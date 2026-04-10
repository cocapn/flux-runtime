"""Code Visualization — visual representations of tile graphs and execution traces.

Provides:
- TileGraphVisualizer: ASCII and colored text views of tile graphs
- ExecutionVisualizer: Timeline and flame graph views of execution traces
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flux.tiles.graph import TileGraph
    from flux.creative.sonification import ExecutionEvent


# ── Heat color helpers ──────────────────────────────────────────────────────

HEAT_COLORS = {
    "HEAT": "\033[91m",     # red
    "HOT": "\033[38;5;208m", # orange
    "WARM": "\033[93m",     # yellow
    "COOL": "\033[92m",     # green
    "FROZEN": "\033[94m",   # blue
    "RESET": "\033[0m",
}

HEAT_CHARS = {
    "HEAT": "#",
    "HOT": "@",
    "WARM": "=",
    "COOL": "~",
    "FROZEN": ".",
}


# ── TileGraphVisualizer ────────────────────────────────────────────────────

class TileGraphVisualizer:
    """Generates visual representations of tile graphs."""

    @staticmethod
    def to_ascii(tile_graph: TileGraph) -> str:
        """ASCII art representation of the tile graph.

        Shows nodes as boxes with their type and connections as arrows.
        """
        nodes = tile_graph.nodes
        edges = tile_graph.edges

        if not nodes:
            return "(empty tile graph)"

        lines = []
        lines.append("╔══════════════════════════════════╗")
        lines.append("║       TILE GRAPH                 ║")
        lines.append("╚══════════════════════════════════╝")
        lines.append("")

        # Draw nodes
        for name, instance in nodes.items():
            type_label = instance.tile_type.value.upper()
            tag_str = ",".join(sorted(instance.tile.tags)) if instance.tile.tags else ""
            lines.append(f"  ┌─ {name} ─────────────────┐")
            lines.append(f"  │ type: {type_label:<18s} │")
            if tag_str:
                lines.append(f"  │ tags: {tag_str[:18]:<18s} │")
            cost = f"{instance.tile.cost_estimate:.1f}"
            lines.append(f"  │ cost: {cost:<18s} │")
            lines.append(f"  └──────────────────────────┘")
            lines.append("")

        # Draw edges
        if edges:
            lines.append("  Connections:")
            for edge in edges:
                lines.append(f"    {edge.from_tile}.{edge.from_port} → {edge.to_tile}.{edge.to_port}")
            lines.append("")

        lines.append(f"  Total: {len(nodes)} tiles, {len(edges)} connections")
        return "\n".join(lines)

    @staticmethod
    def to_colored_text(
        tile_graph: TileGraph,
        heat_data: dict[str, str],
    ) -> str:
        """Colored text representation with heat indicators.

        Args:
            tile_graph: The tile graph to visualize
            heat_data: Mapping from tile name to heat level string
                       (e.g., {"audio": "HOT", "math": "COOL"})

        Colors: HEAT=red, HOT=orange, WARM=yellow, COOL=green, FROZEN=blue
        """
        nodes = tile_graph.nodes
        edges = tile_graph.edges

        if not nodes:
            return "(empty tile graph)"

        lines = []
        lines.append(f"{HEAT_COLORS.get('WARM', '')}═══ TILE GRAPH (HEAT MAP) ═══{HEAT_COLORS['RESET']}")

        for name, instance in nodes.items():
            heat = heat_data.get(name, "COOL")
            color = HEAT_COLORS.get(heat, HEAT_COLORS["COOL"])
            char = HEAT_CHARS.get(heat, "~")
            reset = HEAT_COLORS["RESET"]

            type_label = instance.tile_type.value.upper()
            lines.append(
                f"  {color}{char}{char}{char}{reset} {name} [{type_label}] ({heat})"
            )

        if edges:
            lines.append("")
            lines.append("  Connections:")
            for edge in edges:
                lines.append(f"    {edge.from_tile}.{edge.from_port} → {edge.to_tile}.{edge.to_port}")

        lines.append("")
        # Legend
        lines.append("  Legend:")
        for level, ch in HEAT_CHARS.items():
            c = HEAT_COLORS.get(level, "")
            lines.append(f"    {c}{ch * 3}{HEAT_COLORS['RESET']} {level}")

        return "\n".join(lines)

    @staticmethod
    def heatmap_bar(
        value: float,
        max_value: float,
        width: int = 40,
    ) -> str:
        """Generate a visual heatmap bar.

        Example: [████████░░░░░░░░] 53%

        Args:
            value: Current value
            max_value: Maximum value for 100%
            width: Width of the bar in characters

        Returns:
            Formatted bar string with percentage
        """
        if max_value <= 0:
            pct = 0.0
        else:
            pct = min(1.0, max(0.0, value / max_value))

        filled = int(pct * width)
        empty = width - filled

        # Use block characters for the bar
        bar = "█" * filled + "░" * empty
        pct_str = f"{pct * 100:.0f}%"

        return f"[{bar}] {pct_str}"


# ── ExecutionVisualizer ─────────────────────────────────────────────────────

class ExecutionVisualizer:
    """Visualizes execution traces."""

    @staticmethod
    def trace_to_ascii(trace: list[ExecutionEvent]) -> str:
        """ASCII timeline of execution events.

        Each event is shown as a row with time, opcode, and velocity.
        """
        if not trace:
            return "(empty trace)"

        lines = []
        lines.append("╔═══════════════════════════════════════════════╗")
        lines.append("║          EXECUTION TRACE TIMELINE            ║")
        lines.append("╚═══════════════════════════════════════════════╝")
        lines.append("")
        lines.append(f"  {'Time':>8s}  {'Opcode':>6s}  {'RegVal':>6s}  {'Heat':>8s}  {'Predicted':>10s}")
        lines.append(f"  {'─' * 8}  {'─' * 6}  {'─' * 6}  {'─' * 8}  {'─' * 10}")

        for event in trace:
            time_str = f"{event.time:.4f}"
            op_str = f"0x{event.opcode:02X}"
            reg_str = str(event.register_value)
            heat_str = event.heat_level
            pred_str = "✓" if event.is_branch_predicted else "✗"

            lines.append(
                f"  {time_str:>8s}  {op_str:>6s}  {reg_str:>6s}  {heat_str:>8s}  {pred_str:>10s}"
            )

        lines.append("")
        lines.append(f"  Total events: {len(trace)}")

        return "\n".join(lines)

    @staticmethod
    def trace_to_flame_graph(trace: list[ExecutionEvent]) -> str:
        """Flame graph style visualization of execution trace.

        Groups events by opcode category and shows proportional width.
        """
        if not trace:
            return "(empty trace)"

        # Categorize opcodes
        categories: dict[str, int] = {}
        for event in trace:
            op = event.opcode
            if op <= 0x07:
                cat = "CONTROL"
            elif op <= 0x0F:
                cat = "INT_ARITH"
            elif op <= 0x17:
                cat = "BITWISE"
            elif op <= 0x1F:
                cat = "COMPARE"
            elif op <= 0x27:
                cat = "STACK"
            elif op <= 0x2F:
                cat = "FUNCTION"
            elif op <= 0x37:
                cat = "MEMORY"
            elif op <= 0x3F:
                cat = "TYPE"
            elif op <= 0x4F:
                cat = "FLOAT"
            elif op <= 0x5F:
                cat = "SIMD"
            elif op <= 0x7F:
                cat = "A2A"
            else:
                cat = "SYSTEM"

            categories[cat] = categories.get(cat, 0) + 1

        total = len(trace)
        lines = []
        lines.append("╔═══════════════════════════════════════════════╗")
        lines.append("║              FLAME GRAPH                     ║")
        lines.append("╚═══════════════════════════════════════════════╝")
        lines.append("")

        # Sort by count descending
        sorted_cats = sorted(categories.items(), key=lambda x: x[1], reverse=True)

        # Draw stacked bar
        bar_width = 60
        bar_parts = []
        color_idx = 0
        block_chars = "█▓▓░░"

        for cat, count in sorted_cats:
            block_w = max(1, int(count / total * bar_width))
            ch = block_chars[color_idx % len(block_chars)]
            bar_parts.append(f"{ch * block_w}")
            color_idx += 1

        full_bar = "".join(bar_parts)[:bar_width]
        lines.append(f"  {full_bar}")
        lines.append("")

        # Legend with counts
        for cat, count in sorted_cats:
            pct = count / total * 100
            bar_len = max(1, int(pct / 100 * 30))
            bar = "█" * bar_len + "░" * (30 - bar_len)
            lines.append(f"  {cat:<12s} {bar} {count:>4d} ({pct:5.1f}%)")

        lines.append("")
        lines.append(f"  Total: {total} events")

        return "\n".join(lines)
