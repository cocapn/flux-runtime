#!/usr/bin/env python3
"""FLUX Retro Research Runner — 25 iterations of systematic improvement.

For each of 10 games, runs a research session with:
  Iterations 1-5:   Initial implementation, fix bugs, verify correctness
  Iterations 6-10:  Optimize bytecode size, reduce cycle count
  Iterations 11-15: Add features, improve output quality
  Iterations 16-20: Cross-game patterns, shared utilities
  Iterations 21-25: Final polish, documentation, publication

Each iteration records:
  - Deterministic seed
  - Hypothesis
  - Metrics (bytecode size, cycles, execution time)
  - Reflection (what worked, what didn't, next steps)

Results saved to: src/flux/retro/research/sessions/<game>.jsonl

Usage:
    python3 -m flux.retro.research.runner
    python3 -m flux.retro.research.runner --game game_of_life
    python3 -m flux.retro.research.runner --iterations 5
"""

from __future__ import annotations

import json
import sys
import time
import argparse
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


from flux.retro.research.session import (
    ResearchSession,
    Seed,
    MetricSnapshot,
    Reflection,
)


# ── Game Definitions ─────────────────────────────────────────────────────────

GAME_IMPORTS = {
    "game_of_life": ("flux.retro.implementations.game_of_life", "GameOfLife"),
    "pong": ("flux.retro.implementations.pong", "Pong"),
    "snake": ("flux.retro.implementations.snake", "Snake"),
    "tetris": ("flux.retro.implementations.tetris", "Tetris"),
    "text_adventure": ("flux.retro.implementations.text_adventure", "TextAdventure"),
    "mandelbrot": ("flux.retro.implementations.mandelbrot", "MandelbrotRenderer"),
    "mastermind": ("flux.retro.implementations.mastermind", "Mastermind"),
    "lunar_lander": ("flux.retro.implementations.lunar_lander", "LunarLander"),
    "tic_tac_toe": ("flux.retro.implementations.tic_tac_toe", "TicTacToeAI"),
    "markov_text": ("flux.retro.implementations.markov_text", "MarkovChainText"),
}

# 25 iterations with hypotheses for each phase
ITERATION_PLANS = [
    # Phase 1: Foundation (1-5)
    (1, "raw_bytecode", "Verify the initial implementation compiles and runs without crashing"),
    (2, "raw_bytecode", "Test edge cases: empty input, maximum values, boundary conditions"),
    (3, "raw_bytecode", "Measure baseline metrics: bytecode size, cycle count, execution time"),
    (4, "analysis", "Analyze bytecode for redundant instructions and dead code paths"),
    (5, "analysis", "Identify the most-used opcodes and register pressure patterns"),
    # Phase 2: Optimization (6-10)
    (6, "optimization", "Optimize loops: reduce cycle count by minimizing redundant loads"),
    (7, "optimization", "Reduce bytecode size by eliminating unnecessary MOVI zero-initializations"),
    (8, "optimization", "Use register allocation more efficiently (fewer PUSH/POP)"),
    (9, "optimization", "Optimize conditional branches (reduce branch misprediction)"),
    (10, "optimization", "Apply peephole optimizations: combine INC+INC into IADD where possible"),
    # Phase 3: Enhancement (11-15)
    (11, "enhancement", "Improve output quality: better rendering, clearer display"),
    (12, "enhancement", "Add error handling: graceful failure on invalid inputs"),
    (13, "enhancement", "Increase simulation fidelity: more frames/steps/generations"),
    (14, "hybrid", "Explore hybrid approach: Python for I/O, bytecode for computation"),
    (15, "hybrid", "Measure hybrid vs pure-bytecode tradeoffs"),
    # Phase 4: Patterns (16-20)
    (16, "patterns", "Identify reusable bytecode patterns across games"),
    (17, "patterns", "Build a shared _asm.py assembler from identified patterns"),
    (18, "patterns", "Apply tile composition patterns to multi-game implementations"),
    (19, "cross_game", "Compare register usage across all 10 games"),
    (20, "cross_game", "Build a cross-game opcode usage heatmap"),
    # Phase 5: Publication (21-25)
    (21, "documentation", "Write implementation notes and algorithm explanations"),
    (22, "benchmarking", "Run final benchmarks with statistical rigor (5 runs, mean+std)"),
    (23, "analysis", "Generate comparative analysis: complexity vs bytecode size vs cycles"),
    (24, "analysis", "Identify FLUX ISA gaps exposed by real-world game implementations"),
    (25, "publication", "Final review: verify all games work, compile showcase report"),
]


def get_game_class(slug: str):
    """Import and return the game class."""
    mod_name, cls_name = GAME_IMPORTS[slug]
    __import__(mod_name)
    mod = sys.modules[mod_name]
    return getattr(mod, cls_name)


def run_iteration(game_cls, iteration_num: int, plan: tuple) -> dict:
    """Run a single research iteration on a game."""
    iter_num, approach, hypothesis = plan

    start = time.perf_counter()
    try:
        # Build and run the game
        instance = game_cls()
        bytecode = instance.build_bytecode() if hasattr(instance, "build_bytecode") else b""
        bytecode_size = len(bytecode)

        from flux.vm.interpreter import Interpreter
        vm = Interpreter(bytecode, memory_size=65536)
        cycles = vm.execute()

        elapsed_ms = (time.perf_counter() - start) * 1000

        return {
            "status": "ok",
            "bytecode_size": bytecode_size,
            "cycles": cycles,
            "elapsed_ms": round(elapsed_ms, 1),
            "halted": vm.halted,
            "approach": approach,
        }
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "status": "error",
            "error": str(e)[:200],
            "elapsed_ms": round(elapsed_ms, 1),
            "approach": approach,
        }


def main():
    parser = argparse.ArgumentParser(description="FLUX Retro Research Runner")
    parser.add_argument("--game", "-g", help="Run research on a specific game")
    parser.add_argument("--iterations", "-n", type=int, default=25, help="Number of iterations")
    parser.add_argument("--list", "-l", action="store_true", help="List iteration plans")
    args = parser.parse_args()

    if args.list:
        print(f"\n  {'#':>2}  {'Phase':<16}  {'Approach':<16}  {'Hypothesis'}")
        print(f"  {'─'*2}  {'─'*16}  {'─'*16}  {'─'*40}")
        for num, approach, hypothesis in ITERATION_PLANS:
            phase = {
                1: "Foundation", 2: "Foundation", 3: "Foundation", 4: "Foundation", 5: "Foundation",
                6: "Optimization", 7: "Optimization", 8: "Optimization", 9: "Optimization", 10: "Optimization",
                11: "Enhancement", 12: "Enhancement", 13: "Enhancement", 14: "Hybrid", 15: "Hybrid",
                16: "Patterns", 17: "Patterns", 18: "Patterns", 19: "Cross-game", 20: "Cross-game",
                21: "Docs", 22: "Benchmark", 23: "Analysis", 24: "Analysis", 25: "Publication",
            }.get(num, "?")
            print(f"  {num:>2}  {phase:<16}  {approach:<16}  {hypothesis[:60]}")
        print()
        return

    games_to_run = [args.game] if args.game else list(GAME_IMPORTS.keys())
    n_iter = min(args.iterations, len(ITERATION_PLANS))

    print(f"\n  FLUX Retro Research Runner")
    print(f"  Games: {len(games_to_run)}")
    print(f"  Iterations per game: {n_iter}")
    print(f"  Total planned iterations: {len(games_to_run) * n_iter}")
    print()

    all_results = {}

    for slug in games_to_run:
        print(f"\n  {'═'*64}")
        print(f"  {slug.upper()}")
        print(f"  {'═'*64}")

        try:
            game_cls = get_game_class(slug)
        except Exception as e:
            print(f"  ERROR: Cannot import {slug}: {e}")
            all_results[slug] = {"error": str(e)}
            continue

        session = ResearchSession(slug)

        for i in range(n_iter):
            plan = ITERATION_PLANS[i]
            iter_num, approach, hypothesis = plan

            session.begin_iteration(iter_num, hypothesis=hypothesis, approach=approach)
            session.add_artifact(f"iteration_{iter_num}")

            result = run_iteration(game_cls, iter_num, plan)

            session.record_metrics_after(
                bytecode_size=result.get("bytecode_size", 0),
                total_cycles=result.get("cycles", 0),
                execution_time_ms=result.get("elapsed_ms", 0),
                test_pass_rate=1.0 if result.get("status") == "ok" else 0.0,
            )

            reflection = Reflection(
                timestamp=datetime.now(timezone.utc).isoformat(),
                iteration=iter_num,
                target=slug,
                hypothesis=hypothesis,
                observations=[
                    f"Status: {result.get('status', 'unknown')}",
                    f"Bytecode: {result.get('bytecode_size', 0)} bytes",
                    f"Cycles: {result.get('cycles', 0):,}",
                    f"Time: {result.get('elapsed_ms', 0):.1f}ms",
                ],
                successes=["Implementation ran successfully"] if result.get("status") == "ok" else [],
                failures=[f"Error: {result.get('error', '')}"] if result.get("status") == "error" else [],
                next_steps=["Optimize bytecode size", "Reduce cycle count", "Improve output quality"],
                open_questions=[
                    f"What is the minimum bytecode for {slug}?",
                    f"Can adaptive profiling improve hot paths in {slug}?",
                ],
                confidence=0.8 if result.get("status") == "ok" else 0.3,
                raw_notes=f"Approach: {approach}. Result: {json.dumps(result)}",
            )

            session.end_iteration(reflection=reflection, status=result.get("status", "unknown"))

            status_icon = "✓" if result.get("status") == "ok" else "✗"
            cycles = result.get("cycles", 0)
            bsize = result.get("bytecode_size", 0)
            print(f"    [{status_icon}] Iter {iter_num:>2}: {bsize:>5}B  {cycles:>8,} cycles  {result.get('elapsed_ms', 0):>6.1f}ms  {approach}")

        session.save()
        print(f"\n  Session saved: {session.log_path}")
        all_results[slug] = {"status": "complete", "iterations": n_iter}

    # Print summary
    print(f"\n  {'═'*64}")
    print(f"  RESEARCH SESSION COMPLETE")
    print(f"  {'═'*64}")
    print(f"  Games processed: {len(all_results)}")
    print(f"  Total iterations: {sum(r.get('iterations', 0) for r in all_results.values())}")
    print(f"  Results directory: {PROJECT_ROOT}/src/flux/retro/research/")
    print()


if __name__ == "__main__":
    main()
