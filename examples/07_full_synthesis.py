#!/usr/bin/env python3
"""FLUX Full Synthesis — The Grand Tour.

Wires everything together:
  - Load modules, profile, classify heat
  - Select optimal languages
  - Run evolution
  - Show the full system report
  - Hot-reload a module mid-execution
  - This is the "wow" demo

Run:
    PYTHONPATH=src python3 examples/07_full_synthesis.py
"""

from __future__ import annotations

import random
import time

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
    width = 66
    print()
    print(f"{BOLD}{MAGENTA}{'═' * width}{RESET}")
    print(f"{BOLD}{MAGENTA}  {text}{RESET}")
    print(f"{BOLD}{MAGENTA}{'═' * width}{RESET}")


def info(text: str) -> None:
    print(f"  {GREEN}✓{RESET} {text}")


def warn(text: str) -> None:
    print(f"  {YELLOW}⚠{RESET} {text}")


def detail(text: str) -> None:
    print(f"    {DIM}{text}{RESET}")


def section(text: str) -> None:
    print()
    print(f"{BOLD}{CYAN}── {text} {'─' * (58 - len(text))}{RESET}")


def big_box(lines: list[str]) -> None:
    """Print a box of text."""
    max_len = max(len(line) for line in lines) if lines else 0
    inner = max_len + 4
    print(f"    ╔{'═' * (inner - 2)}╗")
    for line in lines:
        print(f"    ║ {line:<{inner - 4}} ║")
    print(f"    ╚{'═' * (inner - 2)}╝")


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print()
    print(f"{BOLD}{YELLOW}{'╔' + '═' * 64 + '╗'}{RESET}")
    print(f"{BOLD}{YELLOW}{'║'}                                                                {'║'}{RESET}")
    print(f"{BOLD}{YELLOW}{'║'}  {BOLD}FLUX Full Synthesis — The Grand Tour{RESET}{'':>32s}{'║'}{RESET}")
    print(f"{BOLD}{YELLOW}{'║'}  The self-assembling, self-improving runtime                {'║'}{RESET}")
    print(f"{BOLD}{YELLOW}{'║'}                                                                {'║'}{RESET}")
    print(f"{BOLD}{YELLOW}{'╚' + '═' * 64 + '╝'}{RESET}")

    # ══════════════════════════════════════════════════════════════════
    # Phase 1: Create the Synthesizer
    # ══════════════════════════════════════════════════════════════════

    header("Phase 1: Boot the FLUX Synthesizer")

    from flux.synthesis.synthesizer import FluxSynthesizer

    synth = FluxSynthesizer("signal_processor")
    info(f"Created: {synth}")

    # ══════════════════════════════════════════════════════════════════
    # Phase 2: Load Modules
    # ══════════════════════════════════════════════════════════════════

    header("Phase 2: Load Modules (Fractal Hierarchy)")

    modules = {
        "audio/dsp/fft_core":     ("def fft(signal):\n    return signal", "python"),
        "audio/dsp/filter_iir":   ("def iir_filter(signal):\n    return signal", "python"),
        "audio/dsp/resampler":    ("def resample(signal, rate):\n    return signal", "python"),
        "audio/effects/reverb":   ("def reverb(signal):\n    return signal", "python"),
        "audio/effects/delay":    ("def delay(signal, ms):\n    return signal", "python"),
        "audio/effects/chorus":   ("def chorus(signal):\n    return signal", "python"),
        "audio/mixer/sum":        ("def sum(signals):\n    return 0", "python"),
        "audio/mixer/pan":        ("def pan(signal, pos):\n    return signal", "python"),
        "audio/codec/decode":     ("def decode(data):\n    return data", "python"),
        "audio/codec/encode":     ("def encode(signal):\n    return b''", "python"),
        "ui/visualizer":          ("def visualize(data):\n    pass", "python"),
        "ui/controls":            ("def handle_input(event):\n    pass", "python"),
    }

    for path, (source, lang) in modules.items():
        card = synth.load_module(path, source, language=lang)
        info(f"Loaded: {path} ({lang})")

    info(f"\nModule tree:")
    tree = synth.get_module_tree()
    for line in tree.split("\n"):
        detail(line)

    # ══════════════════════════════════════════════════════════════════
    # Phase 3: Profile a Workload
    # ══════════════════════════════════════════════════════════════════

    header("Phase 3: Run & Profile Workload")

    def workload():
        """Simulate an audio processing workload."""
        pass  # Profiling is recorded manually below

    # Record calls with varying frequencies
    call_freq = {
        "signal_processor.audio.dsp.fft_core":   (500, 8000),
        "signal_processor.audio.dsp.filter_iir": (400, 6000),
        "signal_processor.audio.effects.reverb":  (200, 12000),
        "signal_processor.audio.mixer.sum":       (300, 3000),
        "signal_processor.audio.mixer.pan":       (150, 2000),
        "signal_processor.audio.codec.decode":    (100, 15000),
        "signal_processor.audio.codec.encode":    (50,  18000),
        "signal_processor.audio.dsp.resampler":   (80,  5000),
        "signal_processor.audio.effects.delay":   (120, 4000),
        "signal_processor.audio.effects.chorus":  (60,  7000),
        "signal_processor.ui.visualizer":         (20,  1000),
        "signal_processor.ui.controls":           (10,  500),
    }

    start = time.time()
    for mod_path, (count, avg_ns) in call_freq.items():
        for _ in range(count):
            synth.profiler.record_call(mod_path, duration_ns=random.randint(avg_ns // 2, avg_ns * 2))

    elapsed_ms = (time.time() - start) * 1000

    result = synth.run_workload(workload)
    info(f"Workload completed: {result.elapsed_ms:.1f}ms")
    info(f"  Samples recorded: {synth.profiler.sample_count}")
    info(f"  Modules profiled: {synth.profiler.module_count}")

    # ══════════════════════════════════════════════════════════════════
    # Phase 4: Heat Classification
    # ══════════════════════════════════════════════════════════════════

    header("Phase 4: Heat Classification")

    heatmap = synth.get_heatmap()
    heat_order = {"HEAT": 0, "HOT": 1, "WARM": 2, "COOL": 3}

    HEAT_COLORS = {
        "FROZEN": "\033[97m", "COOL": "\033[96m",
        "WARM": "\033[93m", "HOT": "\033[38;5;208m", "HEAT": "\033[91m",
    }

    sorted_modules = sorted(heatmap.items(), key=lambda x: heat_order.get(x[1], 99))

    print()
    for mod_path, heat in sorted_modules:
        color = HEAT_COLORS.get(heat, RESET)
        stats = synth.profiler.get_module_stats(mod_path)
        calls = stats["call_count"] if stats else 0
        avg_us = stats["avg_time_ns"] / 1000 if stats else 0
        bar_w = min(calls // 20, 20)
        bar = "█" * bar_w + "░" * (20 - bar_w)
        short_path = mod_path.replace("signal_processor.", "")
        print(f"    {color}{heat:<6s}{RESET} {short_path:<36s} "
              f"calls={calls:>4d}  {CYAN}{bar}{RESET}")

    # ══════════════════════════════════════════════════════════════════
    # Phase 5: Language Recommendations
    # ══════════════════════════════════════════════════════════════════

    header("Phase 5: Language Recommendations")

    recs = synth.get_recommendations()
    rec_sorted = sorted(recs.items(), key=lambda x: heat_order.get(x[1].heat_level.name, 99))

    print()
    print(f"    {'Module':<34s} {'Current':>10s} {'→':>2s} {'Recommended':>12s} {'Speedup':>8s}")
    print(f"    {'─' * 34} {'─' * 10}   {'─' * 12} {'─' * 8}")

    for mod_path, rec in rec_sorted:
        short = mod_path.replace("signal_processor.", "")
        change = f"{GREEN}→{RESET}" if rec.should_change else f"{DIM}·{RESET}"
        speedup = f"{rec.estimated_speedup:.0f}x" if rec.should_change else "1x"
        print(f"    {short:<34s} {rec.current_language:>10s} {change:>2s} "
              f"{rec.recommended_language:>12s} {speedup:>7s}")

    # ══════════════════════════════════════════════════════════════════
    # Phase 6: Hot-Reload a Module
    # ══════════════════════════════════════════════════════════════════

    header("Phase 6: Hot-Reload a Module")

    info("Before reload:")
    card = synth.get_module("audio/dsp/fft_core")
    if card:
        detail(f"  fft_core version: {card.version}")

    new_source = "def fft(signal):\n    # Optimized: use Cooley-Tukey\n    return signal"
    reload_result = synth.hot_swap("audio/dsp/fft_core", new_source)

    if reload_result.success:
        info(f"Hot-swap successful!")
        detail(f"  Path: {reload_result.path}")
        detail(f"  Old checksum: {reload_result.old_checksum}")
        detail(f"  New checksum: {reload_result.new_checksum}")
    else:
        warn(f"Hot-swap failed: {reload_result.error}")

    # ══════════════════════════════════════════════════════════════════
    # Phase 7: Run Evolution
    # ══════════════════════════════════════════════════════════════════

    header("Phase 7: Self-Evolution (3 generations)")

    info("Running evolution loop: capture → mine → propose → validate → commit")

    def validation_fn(genome):
        """Simple validation — always passes for demo."""
        return True

    report = synth.evolve(generations=3, validation_fn=validation_fn)

    info(f"Evolution complete!")
    info(f"  Generations:    {report.generations}")
    info(f"  Initial fitness: {report.initial_fitness:.4f}")
    info(f"  Final fitness:   {report.final_fitness:.4f}")
    info(f"  Improvement:     {report.fitness_improvement_pct:.1f}%")
    info(f"  Mutations:       {report.mutations_succeeded} succeeded, "
         f"{report.mutations_failed} failed")
    info(f"  Patterns found:  {report.patterns_discovered}")

    if report.records:
        print()
        print(f"    {'Gen':<5s} {'Fitness':>10s} {'Δ':>8s} {'Mutations':>12s} {'Status':>10s}")
        print(f"    {'─' * 5} {'─' * 10} {'─' * 8} {'─' * 12} {'─' * 10}")
        for rec in report.records:
            arrow = f"{GREEN}↑{RESET}" if rec.is_improvement else f"{DIM}→{RESET}"
            delta = f"{rec.fitness_delta:+.4f}"
            muts = f"{rec.mutations_committed}/{rec.mutations_proposed}"
            print(f"    {rec.generation:<5d} {rec.fitness_after:>9.4f} {arrow} {delta:>7s} "
                  f"{muts:>12s} {'OK' if rec.is_improvement else '...':>10s}")

    # ══════════════════════════════════════════════════════════════════
    # Phase 8: Bottleneck Report
    # ══════════════════════════════════════════════════════════════════

    header("Phase 8: Bottleneck Analysis")

    bottleneck = synth.get_bottleneck_report(top_n=5)

    print()
    print(f"    {'#':<3s} {'Module':<34s} {'Calls':>6s} {'Avg(μs)':>8s} {'Heat':>6s}")
    print(f"    {'─' * 3} {'─' * 34} {'─' * 6} {'─' * 8} {'─' * 6}")

    for i, entry in enumerate(bottleneck.entries, 1):
        short = entry.module_path.replace("signal_processor.", "")
        avg_us = entry.avg_time_ns / 1000
        color = HEAT_COLORS.get(str(entry.heat_level), RESET)
        print(f"    {i:<3d} {short:<34s} {entry.call_count:>6d} "
              f"{avg_us:>7.1f} {color}{str(entry.heat_level):<6s}{RESET}")

    # ══════════════════════════════════════════════════════════════════
    # Phase 9: Full System Report
    # ══════════════════════════════════════════════════════════════════

    header("Phase 9: System Report")

    stats = synth.stats()

    big_box([
        f"FLUX Synthesizer: {stats['name']}",
        f"",
        f"  Modules loaded:    {stats['modules']}",
        f"  Containers:        {stats['containers']}",
        f"  Tiles available:   {stats['tiles']}",
        f"  Evolution gen:     {stats['generation']}",
        f"  Current fitness:   {stats['fitness']:.4f}",
        f"  Profiled modules:  {stats['profiled_modules']}",
        f"  Profiling samples: {stats['samples']}",
        f"  Evolution runs:    {stats['evolution_runs']}",
        f"  Reload history:    {stats['reload_history']}",
        f"  Uptime:            {stats['uptime_s']:.1f}s",
    ])

    # ══════════════════════════════════════════════════════════════════
    # Finale
    # ══════════════════════════════════════════════════════════════════

    header("The Grand Tour — Complete")

    big_box([
        "  What you just saw:",
        "",
        "  1. Created a synthesizer with 12 modules",
        "  2. Profiled an audio processing workload",
        "  3. Classified modules by heat (FROZEN→HEAT)",
        "  4. Got language recommendations per module",
        "  5. Hot-reloaded a module (zero downtime)",
        "  6. Ran 3 generations of self-evolution",
        "  7. Identified top bottlenecks",
        "  8. Got a full system report",
        "",
        "  The system is now smarter than when it started.",
    ])

    print()
    print(f"{BOLD}{GREEN}  ═══ FLUX: Self-Assembling, Self-Improving Runtime ═══{RESET}")
    print()
