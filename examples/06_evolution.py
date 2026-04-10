#!/usr/bin/env python3
"""FLUX Self-Evolution — The System That Improves Itself.

Demonstrates the evolution engine:
  - Create a genome from a system snapshot
  - Run pattern mining to find hot sequences
  - Propose mutations (language recompilation, tile fusion)
  - Validate correctness
  - Show fitness improving over generations
  - Beautiful generational progress output

Run:
    PYTHONPATH=src python3 examples/06_evolution.py
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


def fitness_bar(fitness: float, max_fitness: float = 1.0, width: int = 30) -> str:
    """Generate a colored fitness bar."""
    filled = int(fitness / max_fitness * width)
    if fitness >= 0.7:
        color = GREEN
    elif fitness >= 0.4:
        color = YELLOW
    else:
        color = RED
    bar = "█" * filled + "░" * (width - filled)
    return f"{color}{bar}{RESET}"


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print()
    print(f"{BOLD}{YELLOW}{'╔' + '═' * 62 + '╗'}{RESET}")
    print(f"{BOLD}{YELLOW}{'║'}  FLUX Self-Evolution — The System Improves Itself    {'║'}{RESET}")
    print(f"{BOLD}{YELLOW}{'║'}  Capture → Profile → Mine → Propose → Validate → Commit {'║'}{RESET}")
    print(f"{BOLD}{YELLOW}{'╚' + '═' * 62 + '╝'}{RESET}")

    from flux.adaptive.profiler import AdaptiveProfiler, HeatLevel
    from flux.adaptive.selector import AdaptiveSelector
    from flux.evolution.genome import Genome, MutationStrategy
    from flux.evolution.pattern_mining import PatternMiner, ExecutionTrace
    from flux.evolution.mutator import SystemMutator, MutationProposal
    from flux.evolution.validator import CorrectnessValidator
    from flux.evolution.evolution import EvolutionEngine, EvolutionReport
    from flux.modules.container import ModuleContainer, ReloadResult
    from flux.modules.granularity import Granularity
    from flux.tiles.registry import TileRegistry, default_registry

    # ── Step 1: Set up a mock FLUX system ───────────────────────────
    section("Step 1: Set Up Mock FLUX System")

    # Create module hierarchy
    root = ModuleContainer("audio_app", Granularity.TRAIN)
    dsp_container = root.add_child("dsp", Granularity.CARRIAGE)
    effects_container = root.add_child("effects", Granularity.CARRIAGE)
    io_container = root.add_child("io", Granularity.LUGGAGE)

    # Load module cards
    dsp_container.load_card("fft_core", "def fft(x): ...", language="python")
    dsp_container.load_card("filter_iir", "def filter_iir(x): ...", language="python")
    effects_container.load_card("reverb", "def reverb(x): ...", language="python")
    effects_container.load_card("delay", "def delay(x): ...", language="python")
    io_container.load_card("read_stream", "def read(): ...", language="python")
    io_container.load_card("write_stream", "def write(x): ...", language="python")

    info(f"Module hierarchy created: {root.path}")
    for child in root.children.values():
        detail(f"  {child.path} [{child.granularity.name}] ({len(child.cards)} cards)")
        for cname, card in child.cards.items():
            detail(f"    └── {cname} ({card.language})")
    detail(f"  Containers: {root.path} → dsp, effects, io")
    detail(f"  Cards: fft_core, filter_iir, reverb, delay, read_stream, write_stream")

    # ── Step 2: Profile the system ───────────────────────────────────
    section("Step 2: Profile Module Execution")

    profiler = AdaptiveProfiler()
    selector = AdaptiveSelector(profiler)

    # Simulate realistic call patterns
    module_calls = {
        "audio_app.dsp.fft_core":     1000,
        "audio_app.dsp.filter_iir":   800,
        "audio_app.effects.reverb":   400,
        "audio_app.effects.delay":    200,
        "audio_app.io.read_stream":   100,
        "audio_app.io.write_stream":  100,
    }

    for mod_path, count in module_calls.items():
        selector._current_languages[mod_path] = "python"
        for _ in range(count):
            profiler.record_call(mod_path, duration_ns=random.randint(1000, 10000))

    # Record execution traces for pattern mining
    miner = PatternMiner(profiler)
    for _ in range(20):
        trace_calls = random.choices(
            list(module_calls.keys()),
            weights=list(module_calls.values()),
            k=random.randint(3, 6),
        )
        miner.record_call_sequence(trace_calls, duration_ns=50000)

    info(f"Profiled {profiler.module_count} modules")
    info(f"Recorded {profiler.sample_count} samples")
    info(f"Captured {miner.trace_count} execution traces")

    # ── Step 3: Show heat classification ────────────────────────────
    section("Step 3: Heat Classification")

    heatmap = profiler.get_heatmap()
    heat_order = {HeatLevel.HEAT: 0, HeatLevel.HOT: 1, HeatLevel.WARM: 2, HeatLevel.COOL: 3}
    sorted_heat = sorted(heatmap.items(), key=lambda x: heat_order.get(x[1], 99))

    for mod_path, heat in sorted_heat:
        color = {"HEAT": RED, "HOT": YELLOW, "WARM": CYAN, "COOL": DIM}.get(heat.name, RESET)
        stats = profiler.get_module_stats(mod_path)
        calls = stats["call_count"] if stats else 0
        print(f"    {color}{heat.name:<6s}{RESET} {mod_path:<36s} ({calls} calls)")

    # ── Step 4: Pattern mining ───────────────────────────────────────
    section("Step 4: Pattern Mining — Finding Hot Sequences")

    patterns = miner.mine_patterns(min_frequency=2, min_length=2, max_length=4)

    info(f"Discovered {len(patterns)} patterns:")
    for i, pat in enumerate(patterns[:8], 1):
        seq_str = " → ".join(str(p) for p in pat.sequence)
        bar_len = int(min(pat.benefit_score / 10, 30))
        bar = "█" * bar_len
        detail(f"  {i}. [{pat.frequency:>3d}x] {seq_str}")
        detail(f"     speedup={pat.estimated_speedup:.2f}x  benefit={pat.benefit_score:.1f}  {CYAN}{bar}{RESET}")

    # ── Step 5: Mutation proposals ───────────────────────────────────
    section("Step 5: Mutation Proposals")

    # Create a genome snapshot
    genome = Genome()
    genome.capture(root, default_registry, profiler, selector)
    genome.evaluate_fitness()

    info(f"Initial genome: {genome}")
    info(f"  Modules: {len(genome.modules)}")
    info(f"  Tiles:   {len(genome.tiles)}")
    info(f"  Fitness: {genome.fitness_score:.4f}")

    mutator = SystemMutator(max_mutations_per_step=5)
    proposals = mutator.propose_mutations(genome, patterns)

    info(f"Proposed {len(proposals)} mutations:")
    print()
    print(f"    {'#':<3s} {'Strategy':<22s} {'Target':<30s} {'Speedup':>8s} {'Risk':>5s}")
    print(f"    {'─' * 3} {'─' * 22} {'─' * 30} {'─' * 8} {'─' * 5}")

    for i, prop in enumerate(proposals, 1):
        detail_str = prop.target[:28] if len(prop.target) > 28 else prop.target
        speedup_color = GREEN if prop.estimated_speedup > 5 else YELLOW
        risk_color = GREEN if prop.estimated_risk < 0.3 else YELLOW if prop.estimated_risk < 0.6 else RED
        print(f"    {i:<3d} {prop.strategy.value:<22s} {detail_str:<30s} "
              f"{speedup_color}{prop.estimated_speedup:>7.1f}x{RESET} "
              f"{risk_color}{prop.estimated_risk:>4.2f}{RESET}")

    # ── Step 6: Apply mutations ──────────────────────────────────────
    section("Step 6: Apply & Validate Mutations")

    validator = CorrectnessValidator()
    # Register a simple test that always passes
    validator.register_test("basic_add", lambda: 2 + 2, 4)

    fitness_history = [(0, genome.fitness_score)]

    for i, proposal in enumerate(proposals[:5], 1):
        result = mutator.apply_mutation(proposal, genome, validator.validate_genome)

        if result.success:
            mutator.commit_mutation(proposal, result)
            # Update genome
            genome = genome.mutate(
                strategy=proposal.strategy,
                target=proposal.target,
                **proposal.kwargs,
            )
            genome.evaluate_fitness()
            status = f"{GREEN}COMMITTED{RESET}"
        else:
            mutator.rollback_mutation(proposal, result)
            status = f"{RED}ROLLED BACK{RESET}"

        fitness_history.append((i, genome.fitness_score))
        delta = f"{result.fitness_delta:+.4f}" if result.fitness_delta != 0 else "  0.000"
        info(f"  Gen {i}: {proposal.strategy.value:<22s} → {status}  Δ={delta}")

    # ── Step 7: Fitness progress ─────────────────────────────────────
    section("Step 7: Fitness Progress Over Generations")

    print()
    max_fitness = max(f for _, f in fitness_history) if fitness_history else 1.0
    max_fitness = max(max_fitness, 0.5)

    print(f"    {'Gen':<5s} {'Fitness':>10s}  Progress Bar")
    print(f"    {'─' * 5} {'─' * 10}  {'─' * 30}")

    prev_fitness = fitness_history[0][1] if fitness_history else 0
    for gen, fitness in fitness_history:
        bar = fitness_bar(fitness, max_fitness)
        delta = fitness - prev_fitness
        arrow = f"{GREEN}↑{RESET}" if delta > 0.0001 else f"{DIM}→{RESET}"
        print(f"    {gen:<5d} {fitness:>9.4f}  {bar} {arrow}")
        prev_fitness = fitness

    # ── Step 8: Evolution engine summary ─────────────────────────────
    section("Step 8: Evolution Summary")

    info(f"Mutator: {mutator}")
    info(f"  Success rate: {mutator.get_success_rate():.0%}")
    info(f"  Total speedup: {mutator.get_total_speedup():.2f}x")
    info(f"  Committed: {mutator.success_count}")
    info(f"  Failed: {mutator.failure_count}")

    info(f"Final genome fitness: {genome.fitness_score:.4f}")
    info(f"  Optimizations: {len(genome.optimization_history)}")

    if genome.optimization_history:
        detail("  Optimization log:")
        for rec in genome.optimization_history:
            speedup = f"{rec.speedup:.1f}x" if rec.speedup != 1.0 else ""
            detail(f"    Gen {rec.generation}: {rec.description} {speedup}")

    # ── Step 9: Genome diff ─────────────────────────────────────────
    section("Step 9: Genome Changes")

    original = Genome()
    original.capture(root, default_registry, profiler, selector)

    diff = original.diff(genome)
    if diff.language_changes:
        info("Language changes:")
        for path, (old_lang, new_lang) in diff.language_changes.items():
            detail(f"  {path}: {old_lang} → {new_lang}")
    else:
        info("No language changes detected (mutations were at tile level)")

    print()
    print(f"{BOLD}{GREEN}── Evolution Complete! ──{RESET}")
    print()
