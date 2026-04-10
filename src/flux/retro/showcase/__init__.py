#!/usr/bin/env python3
"""FLUX Retro Showcase — Run all 10 reverse-engineered games with metrics.

Usage:
    python3 -m flux.retro.showcase              # Run all games
    python3 -m flux.retro.showcase --game pong   # Run specific game
    python3 -m flux.retro.showcase --research    # Run with full research tracking
    python3 -m flux.retro.showcase --bench       # Benchmark all games
"""

from __future__ import annotations

import sys
import time
import argparse
from pathlib import Path

# ── ANSI Helpers ──────────────────────────────────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
RED = "\033[91m"
RESET = "\033[0m"


def header(text: str, width: int = 72) -> None:
    print()
    print(f"{BOLD}{MAGENTA}{'═' * width}{RESET}")
    print(f"{BOLD}{MAGENTA}  {text}{RESET}")
    print(f"{BOLD}{MAGENTA}{'═' * width}{RESET}")
    print()


def sub(text: str) -> None:
    print(f"\n{BOLD}{CYAN}── {text} {'─' * (60 - len(text))}{RESET}\n")


# ── Game Registry ────────────────────────────────────────────────────────────

GAMES = {
    "game_of_life": ("Conway's Game of Life (1970)", "Cellular Automaton"),
    "pong": ("Pong (1972)", "Real-time Game"),
    "snake": ("Snake (1976)", "Grid Game"),
    "tetris": ("Tetris (1984)", "Puzzle Game"),
    "text_adventure": ("Text Adventure / Zork (1977)", "Interactive Fiction"),
    "mandelbrot": ("Mandelbrot Set (1980)", "Mathematical Visualization"),
    "mastermind": ("Mastermind (1970)", "Logic Puzzle"),
    "lunar_lander": ("Lunar Lander (1979)", "Physics Simulation"),
    "tic_tac_toe": ("Tic-Tac-Toe AI (1952)", "Search/AI"),
    "markov_text": ("Markov Chain Text (1913)", "Probabilistic Generation"),
}


def _import_game(slug: str):
    """Dynamically import a game implementation."""
    mod_map = {
        "game_of_life": "game_of_life",
        "pong": "pong",
        "snake": "snake",
        "tetris": "tetris",
        "text_adventure": "text_adventure",
        "mandelbrot": "mandelbrot",
        "mastermind": "mastermind",
        "lunar_lander": "lunar_lander",
        "tic_tac_toe": "tic_tac_toe",
        "markov_text": "markov_text",
    }
    mod_name = f"flux.retro.implementations.{mod_map[slug]}"
    __import__(mod_name)
    return sys.modules[mod_name]


def run_single(slug: str) -> dict:
    """Run a single game and return metrics."""
    mod = _import_game(slug)
    # Find the class
    cls = None
    for name in dir(mod):
        obj = getattr(mod, name)
        if isinstance(obj, type) and hasattr(obj, "demonstrate"):
            cls = obj
            break
    if cls is None:
        print(f"  {RED}No implementation found for {slug}{RESET}")
        return {"slug": slug, "error": "no implementation"}

    # Run the demo
    start = time.perf_counter()
    try:
        cls.demonstrate()
        elapsed = time.perf_counter() - start
        return {"slug": slug, "status": "ok", "elapsed_ms": round(elapsed * 1000, 1)}
    except Exception as e:
        elapsed = time.perf_counter() - start
        print(f"  {RED}Error: {e}{RESET}")
        return {"slug": slug, "status": "error", "error": str(e), "elapsed_ms": round(elapsed * 1000, 1)}


def run_all() -> list[dict]:
    """Run all games and collect metrics."""
    results = []
    order = list(GAMES.keys())
    for i, slug in enumerate(order):
        name, category = GAMES[slug]
        print(f"\n  [{i+1:2d}/10] {BOLD}{name}{RESET} {DIM}({category}){RESET}")
        print(f"  {'─' * 60}")
        result = run_single(slug)
        results.append(result)
    return results


def run_benchmark() -> list[dict]:
    """Run all games in benchmark mode (5 iterations each)."""
    results = []
    order = list(GAMES.keys())
    for slug in order:
        name, category = GAMES[slug]
        print(f"\n  Benchmarking: {BOLD}{name}{RESET}")
        times = []
        for _ in range(5):
            mod = _import_game(slug)
            cls = None
            for n in dir(mod):
                obj = getattr(mod, n)
                if isinstance(obj, type) and hasattr(obj, "demonstrate"):
                    cls = obj
                    break
            if cls:
                start = time.perf_counter()
                cls.demonstrate()
                times.append(time.perf_counter() - start)
        if times:
            avg = sum(times) / len(times) * 1000
            mn = min(times) * 1000
            mx = max(times) * 1000
            print(f"    avg={avg:.1f}ms  min={mn:.1f}ms  max={mx:.1f}ms  runs={len(times)}")
            results.append({"slug": slug, "avg_ms": round(avg, 1), "min_ms": round(mn, 1), "max_ms": round(mx, 1)})
    return results


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="flux.retro.showcase",
        description="FLUX Retro — Reverse-Engineered Classic Games Showcase",
    )
    parser.add_argument("--game", "-g", help="Run a specific game by slug")
    parser.add_argument("--research", "-r", action="store_true", help="Run with research tracking")
    parser.add_argument("--bench", "-b", action="store_true", help="Benchmark mode")
    parser.add_argument("--list", "-l", action="store_true", help="List all games")
    args = parser.parse_args()

    header("FLUX RETRO — 10 Iconic Games Reverse-Engineered in FLUX Bytecode")

    if args.list:
        print(f"  {'#':>2}  {'Name':<42}  {'Category':<24}")
        print(f"  {'─'*2}  {'─'*42}  {'─'*24}")
        for i, (slug, (name, cat)) in enumerate(GAMES.items()):
            print(f"  {i+1:>2}  {name:<42}  {cat:<24}")
        print()
        return

    if args.bench:
        sub("Benchmark Mode (5 iterations each)")
        bench_results = run_benchmark()
        print(f"\n  {'Game':<40}  {'Avg':>8}  {'Min':>8}  {'Max':>8}")
        print(f"  {'─'*40}  {'─'*8}  {'─'*8}  {'─'*8}")
        for r in bench_results:
            name = GAMES.get(r["slug"], ("?", "?"))[0]
            print(f"  {name:<40}  {r['avg_ms']:>7.1f}ms {r['min_ms']:>7.1f}ms {r['max_ms']:>7.1f}ms")
        return

    if args.research:
        from flux.retro.research.session import ResearchSession
        from flux.retro.research.reflection import Reflection  # type: ignore
        sub("Research Mode — Tracking with Seeds & Metrics")

    if args.game:
        slug = args.game.lower().replace(" ", "_")
        if slug not in GAMES:
            print(f"  {RED}Unknown game: {slug}{RESET}")
            print(f"  Available: {', '.join(GAMES.keys())}")
            return
        name, category = GAMES[slug]
        print(f"  Running: {BOLD}{name}{RESET} ({category})")
        run_single(slug)
        return

    # Default: run all
    sub("Running All 10 Games")
    results = run_all()

    # Summary
    print()
    header("SHOWCASE RESULTS")
    ok = [r for r in results if r.get("status") == "ok"]
    err = [r for r in results if r.get("status") == "error"]
    print(f"  {GREEN}✓ Passed: {len(ok)}/10{RESET}")
    if err:
        print(f"  {RED}✗ Failed: {len(err)}/10{RESET}")
        for e in err:
            print(f"    {e['slug']}: {e.get('error', 'unknown')[:60]}")
    total_ms = sum(r.get("elapsed_ms", 0) for r in results)
    print(f"\n  Total execution time: {total_ms:.0f}ms")
    print(f"  Average per game: {total_ms/10:.0f}ms")
    print()


if __name__ == "__main__":
    main()
