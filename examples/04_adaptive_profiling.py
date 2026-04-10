#!/usr/bin/env python3
"""FLUX Adaptive Profiling — Heat Classification & Language Recommendations.

Demonstrates the adaptive subsystem:
  - Create a profiler and record module execution calls
  - Show heat classification (FROZEN → COOL → WARM → HOT → HEAT)
  - Show language recommendations (Python → C + SIMD)
  - Display as a beautiful heatmap table

Run:
    PYTHONPATH=src python3 examples/04_adaptive_profiling.py
"""

from __future__ import annotations

import random

# ── ANSI helpers ──────────────────────────────────────────────────────────

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def header(text: str) -> None:
    width = 64
    print()
    print(f"{BOLD}{MAGENTA}{'═' * width}{RESET}")
    print(f"{BOLD}{MAGENTA}  {text}{RESET}")
    print(f"{BOLD}{MAGENTA}{'═' * width}{RESET}")


def info(text: str) -> None:
    print(f"  {GREEN}✓{RESET} {text}")


def detail(text: str) -> None:
    print(f"    {DIM}{text}{RESET}")


def section(text: str) -> None:
    print()
    print(f"{BOLD}{CYAN}── {text} {'─' * (56 - len(text))}{RESET}")


# ══════════════════════════════════════════════════════════════════════════
# Heat Level Color Mapping
# ══════════════════════════════════════════════════════════════════════════

HEAT_COLORS = {
    "FROZEN": "\033[97m",   # white
    "COOL":   "\033[96m",   # cyan
    "WARM":   "\033[93m",   # yellow
    "HOT":    "\033[38;5;208m",  # orange
    "HEAT":   "\033[91m",   # red
}

HEAT_BAR_CHARS = {
    "FROZEN": "░",
    "COOL":   "▒",
    "WARM":   "▓",
    "HOT":    "▓",
    "HEAT":   "█",
}


def heat_color(heat_name: str) -> str:
    return HEAT_COLORS.get(heat_name, RESET)


def heat_bar(heat_name: str, width: int = 30) -> str:
    """Generate a colored bar representing heat level."""
    levels = {"FROZEN": 0, "COOL": 1, "WARM": 2, "HOT": 3, "HEAT": 4}
    level = levels.get(heat_name, 0)
    filled = int((level + 1) / 5 * width)
    char = HEAT_BAR_CHARS.get(heat_name, "░")
    color = heat_color(heat_name)
    bar = char * filled + "░" * (width - filled)
    return f"{color}{bar}{RESET}"


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print()
    print(f"{BOLD}{YELLOW}{'╔' + '═' * 62 + '╗'}{RESET}")
    print(f"{BOLD}{YELLOW}{'║'}  FLUX Adaptive Profiling — Heat & Language Selection  {'║'}{RESET}")
    print(f"{BOLD}{YELLOW}{'║'}  Like a DJ choosing instruments based on the vibe     {'║'}{RESET}")
    print(f"{BOLD}{YELLOW}{'╚' + '═' * 62 + '╝'}{RESET}")

    from flux.adaptive.profiler import AdaptiveProfiler, HeatLevel
    from flux.adaptive.selector import AdaptiveSelector, LanguageRecommendation

    # ── Create profiler and selector ──────────────────────────────────
    section("Step 1: Initialize Adaptive Subsystem")

    profiler = AdaptiveProfiler(hot_threshold=0.8, warm_threshold=0.5)
    selector = AdaptiveSelector(profiler)

    info(f"Profiler: {profiler}")
    info(f"Selector: {selector}")
    detail("  hot_threshold=0.8 → top 20% classified as HEAT")
    detail("  warm_threshold=0.5 → top 50% classified as HOT or above")

    # ── Simulate module execution ─────────────────────────────────────
    section("Step 2: Simulate Module Execution Calls")

    # Simulate a realistic workload with varying call frequencies
    modules = {
        "audio.dsp.fft_core":     1000,  # HEAT — critical DSP path
        "audio.dsp.filter_iir":   800,   # HEAT — hot filter
        "audio.mixer.sum_channels": 500, # HOT — frequent mixing
        "audio.effects.reverb":   300,   # HOT — reverb effect
        "audio.effects.delay":    200,   # WARM — delay line
        "audio.codec.decode_mp3": 150,   # WARM — codec work
        "audio.codec.encode_aac": 80,    # COOL — occasional encode
        "audio.io.read_stream":   50,    # COOL — I/O bound
        "audio.io.write_stream":  30,    # COOL — I/O bound
        "ui.render.visualizer":   10,    # COOL — UI rendering
        "ui.handle.input":        5,     # COOL — user input
        "config.load.settings":   2,     # COOL — rarely called
    }

    info("Recording module calls (realistic audio pipeline workload):")
    for mod_path, count in modules.items():
        for _ in range(count):
            duration_ns = random.randint(100, 5000)
            profiler.record_call(mod_path, duration_ns=duration_ns)

    info(f"Total samples recorded: {profiler.sample_count}")
    info(f"Unique modules profiled: {profiler.module_count}")

    # ── Heat classification ──────────────────────────────────────────
    section("Step 3: Heat Classification")

    heatmap = profiler.get_heatmap()

    # Sort by heat level (descending)
    heat_order = {HeatLevel.HEAT: 0, HeatLevel.HOT: 1, HeatLevel.WARM: 2, HeatLevel.COOL: 3}
    sorted_modules = sorted(heatmap.items(), key=lambda x: heat_order.get(x[1], 99))

    print()
    print(f"    {'Module':<32s} {'Calls':>6s} {'Avg(ns)':>10s}  {'Heat':<8s}  Bar")
    print(f"    {'─' * 32} {'─' * 6} {'─' * 10}  {'─' * 8}  {'─' * 30}")

    for mod_path, heat in sorted_modules:
        stats = profiler.get_module_stats(mod_path)
        if stats is None:
            continue
        heat_name = heat.name
        color = heat_color(heat_name)
        bar = heat_bar(heat_name)
        print(f"    {mod_path:<32s} {stats['call_count']:>6d} "
              f"{stats['avg_time_ns']:>10.0f}  {color}{heat_name:<8s}{RESET}  {bar}")

    # ── Heat distribution ────────────────────────────────────────────
    section("Step 4: Heat Distribution")

    from collections import Counter
    heat_counts = Counter(h.name for h in heatmap.values())

    print()
    total = sum(heat_counts.values())
    print(f"    {'Level':<10s} {'Count':>5s} {'Pct':>6s}  Visualization")
    print(f"    {'─' * 10} {'─' * 5} {'─' * 6}  {'─' * 40}")
    for level in ["HEAT", "HOT", "WARM", "COOL"]:
        count = heat_counts.get(level, 0)
        pct = count / total * 100 if total > 0 else 0
        color = heat_color(level)
        bar_len = int(pct / 100 * 40)
        bar = "█" * bar_len
        print(f"    {color}{level:<10s}{RESET} {count:>5d} {pct:>5.1f}%  {color}{bar}{RESET}")

    # ── Language recommendations ──────────────────────────────────────
    section("Step 5: Language Recommendations")

    # Register current languages
    for mod_path in modules:
        selector._current_languages[mod_path] = "python"

    recommendations = selector.select_all()

    # Sort by priority (HEAT first)
    rec_sorted = sorted(recommendations.items(),
                        key=lambda x: heat_order.get(x[1].heat_level, 99))

    print()
    print(f"    {'Module':<30s} {'Current':>10s} {'→':>3s} {'Recommended':>12s}  {'Speedup':>8s}")
    print(f"    {'─' * 30} {'─' * 10}   {'─' * 12}  {'─' * 8}")

    for mod_path, rec in rec_sorted:
        arrow_color = GREEN if rec.should_change else DIM
        change_marker = f"{arrow_color}→{RESET}"
        speedup = f"{rec.estimated_speedup:>7.1f}x" if rec.should_change else f"{'1.0x':>7s}"
        print(f"    {mod_path:<30s} {rec.current_language:>10s} {change_marker:>3s} "
              f"{rec.recommended_language:>12s}  {speedup}")

    # ── Bottleneck analysis ──────────────────────────────────────────
    section("Step 6: Top Bottlenecks")

    report = profiler.get_bottleneck_report(top_n=5)

    print()
    print(f"    {'#':<3s} {'Module':<30s} {'Calls':>6s} {'Total(μs)':>10s}  {'Rec'}")
    print(f"    {'─' * 3} {'─' * 30} {'─' * 6} {'─' * 10}  {'─' * 40}")

    for i, entry in enumerate(report.entries, 1):
        total_us = entry.total_time_ns / 1000
        heat_c = heat_color(entry.heat_level.name)
        rec_short = entry.recommendation.split(".")[0]
        print(f"    {i:<3d} {entry.module_path:<30s} {entry.call_count:>6d} "
              f"{total_us:>10.1f}  {heat_c}{rec_short}{RESET}")

    # ── Speedup estimates ─────────────────────────────────────────────
    section("Step 7: Speedup Estimates")

    info("Estimated speedup if critical modules were recompiled:")
    hot_modules = [(m, h) for m, h in heatmap.items() if h in (HeatLevel.HEAT, HeatLevel.HOT)]
    for mod_path, heat in hot_modules[:3]:
        for lang, expected in [("typescript", "~2x"), ("rust", "~10x"), ("c_simd", "~16x")]:
            speedup = profiler.estimate_speedup(mod_path, lang)
            detail(f"  {mod_path}: Python → {lang:<12s} = {speedup:.1f}x speedup {expected}")

    # ── Modularity score ─────────────────────────────────────────────
    section("Step 8: System Metrics")

    modularity = selector.get_modularity_score()
    bandwidth = selector.get_bandwidth_allocation()

    info(f"System modularity score: {modularity:.2f} / 1.00")
    info(f"  (higher = more Python-like = easier to modify)")
    info(f"Bandwidth allocation (top 3 consumers):")
    top_bw = sorted(bandwidth.items(), key=lambda x: x[1], reverse=True)[:3]
    for mod_path, frac in top_bw:
        detail(f"  {mod_path}: {frac:.1%} of total execution time")

    print()
    print(f"{BOLD}{GREEN}── Done! ──{RESET}")
    print()
