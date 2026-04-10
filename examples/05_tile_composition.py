#!/usr/bin/env python3
"""FLUX Tile Composition — Building with the Tile System.

Demonstrates the tile system:
  - Load built-in tiles from the library
  - Create a custom tile (audio_filter)
  - Compose tiles: chain, parallel, nest
  - Show the tile graph
  - Search the registry

Run:
    PYTHONPATH=src python3 examples/05_tile_composition.py
"""

from __future__ import annotations

from typing import Any

# ── ANSI helpers ──────────────────────────────────────────────────────────

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
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
# Custom Tile Blueprint (FIR Emitter)
# ══════════════════════════════════════════════════════════════════════════

def _audio_filter_blueprint(
    builder: Any,
    inputs: dict[str, Any],
    params: dict[str, Any],
) -> dict[str, Any]:
    """FIR blueprint for a custom audio_filter tile.

    Applies a configurable low-pass filter: output = input * (1 - alpha) + prev * alpha
    """
    from flux.fir.types import TypeContext, IntType
    from flux.fir.values import Value

    data = inputs.get("data")
    if data is None:
        return {}

    alpha = params.get("alpha", 128)  # fixed-point alpha

    # Simulate: output = call("_audio_filter_fn", [data], i32)
    result = builder.call("_audio_filter_fn", [data], IntType(32, True))
    if result is not None:
        return {"result": result}
    return {}


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print()
    print(f"{BOLD}{YELLOW}{'╔' + '═' * 62 + '╗'}{RESET}")
    print(f"{BOLD}{YELLOW}{'║'}  FLUX Tile Composition — Building with Tiles           {'║'}{RESET}")
    print(f"{BOLD}{YELLOW}{'║'}  Like a DJ layering samples from a vinyl library        {'║'}{RESET}")
    print(f"{BOLD}{YELLOW}{'╚' + '═' * 62 + '╝'}{RESET}")

    from flux.tiles.registry import TileRegistry, default_registry
    from flux.tiles.tile import Tile, TileType, CompositeTile, ParallelTile
    from flux.tiles.library import ALL_BUILTIN_TILES
    from flux.tiles.ports import TilePort, PortDirection
    from flux.fir.types import TypeContext, IntType

    _ctx = TypeContext()
    _i32 = _ctx.get_int(32)

    # ── Step 1: Explore the built-in tile library ───────────────────
    section("Step 1: Built-In Tile Library")

    info(f"Registry: {default_registry}")
    info(f"Total tiles available: {default_registry.count}")

    # Group by type
    by_type: dict[str, list] = {}
    for tile in default_registry.all_tiles:
        t = tile.tile_type.value
        by_type.setdefault(t, []).append(tile)

    print()
    for ttype, tiles in sorted(by_type.items()):
        names = ", ".join(t.name for t in sorted(tiles, key=lambda x: x.name))
        detail(f"  {ttype:<10s} ({len(tiles):>2d}): {names}")

    # ── Step 2: Search the registry ──────────────────────────────────
    section("Step 2: Tile Search & Discovery")

    queries = ["map", "memory", "loop", "tell", "print"]
    for query in queries:
        results = default_registry.search(query)
        names = [t.name for t in results[:5]]
        info(f"Search '{query}' → {len(results)} results: {', '.join(names)}")

    # ── Step 3: Inspect a tile in detail ─────────────────────────────
    section("Step 3: Tile Anatomy — Inspect 'map' Tile")

    map_tile = default_registry.get("map")
    if map_tile:
        info(f"Name:            {map_tile.name}")
        info(f"Type:            {map_tile.tile_type.value}")
        info(f"Cost estimate:   {map_tile.cost_estimate}")
        info(f"Abstraction:     {map_tile.abstraction_level} (1=low-level, 10=high)")
        info(f"Language pref:   {map_tile.language_preference}")
        info(f"Has FIR blueprint: {map_tile.fir_blueprint is not None}")
        info(f"Parameters:      {map_tile.params}")
        info(f"Tags:            {', '.join(sorted(map_tile.tags))}")

        detail(f"Inputs:")
        for port in map_tile.inputs:
            detail(f"  {port.name} ({port.direction.value})")
        detail(f"Outputs:")
        for port in map_tile.outputs:
            detail(f"  {port.name} ({port.direction.value})")

    # ── Step 4: Create a custom tile ────────────────────────────────
    section("Step 4: Create Custom Tile — 'audio_filter'")

    audio_filter = Tile(
        name="audio_filter",
        tile_type=TileType.COMPUTE,
        inputs=[
            TilePort("data", PortDirection.INPUT, _i32),
        ],
        outputs=[
            TilePort("result", PortDirection.OUTPUT, _i32),
        ],
        params={"alpha": 128, "cutoff_hz": 8000},
        fir_blueprint=_audio_filter_blueprint,
        cost_estimate=2.5,
        abstraction_level=5,
        language_preference="fir",
        tags={"audio", "dsp", "filter", "low-pass", "custom"},
    )

    info(f"Created tile: {audio_filter}")
    info(f"  Type: {audio_filter.tile_type.value}")
    info(f"  Cost: {audio_filter.cost_estimate}")
    info(f"  Tags: {', '.join(sorted(audio_filter.tags))}")

    # Register it
    default_registry.register(audio_filter)
    info(f"Registered in default_registry (now {default_registry.count} tiles)")

    # ── Step 5: Tile composition — Chaining ─────────────────────────
    section("Step 5: Tile Composition — Chain")

    map_t = default_registry.get("map")
    filter_t = default_registry.get("audio_filter")

    if map_t and filter_t:
        # Chain: map → audio_filter
        composed = map_t.compose(filter_t, mapping={"result": "data"})
        info(f"Composed tile: {composed.name}")
        info(f"  Inputs:  {[p.name for p in composed.inputs]}")
        info(f"  Outputs: {[p.name for p in composed.outputs]}")
        info(f"  Total cost: {composed.cost_estimate}")
        detail(f"  Data flows: map.result → audio_filter.data")

    # ── Step 6: Tile composition — Parallel ─────────────────────────
    section("Step 6: Tile Composition — Parallel")

    loop_t = default_registry.get("loop")
    if loop_t:
        parallel = loop_t.parallel(4)
        info(f"Parallel tile: {parallel.name}")
        info(f"  Replications: {parallel.count}")
        info(f"  Total cost: {parallel.cost_estimate} (was {loop_t.cost_estimate})")
        detail(f"  4 parallel loop instances")

    # ── Step 7: Three-way chain ─────────────────────────────────────
    section("Step 7: Three-Way Chain — map → filter → reduce")

    reduce_t = default_registry.get("reduce")
    if map_t and filter_t and reduce_t:
        chain = map_t.compose(filter_t, mapping={"result": "data"})
        chain2 = chain.compose(reduce_t, mapping={"result": "data"})
        info(f"Chain: {chain2.name}")
        info(f"  Inputs:  {[p.name for p in chain2.inputs]}")
        info(f"  Outputs: {[p.name for p in chain2.outputs]}")
        info(f"  Total cost: {chain2.cost_estimate}")
        detail(f"  Data flow: map.result → filter.data → reduce.data")

    # ── Step 8: Find alternatives ────────────────────────────────────
    section("Step 8: Find Tile Alternatives")

    if map_t:
        alternatives = default_registry.find_alternatives(map_t)
        if alternatives:
            info(f"Alternatives to 'map' (same port signature):")
            for alt in alternatives:
                detail(f"  {alt.name:<16s} cost={alt.cost_estimate:.1f}  "
                      f"type={alt.tile_type.value}")
        else:
            info("No alternatives found for 'map' (unique port signature)")

    # ── Step 9: Most/least expensive tiles ───────────────────────────
    section("Step 9: Cost Analysis")

    expensive = default_registry.most_expensive(5)
    cheap = default_registry.least_expensive(5)

    info("Most expensive tiles:")
    for t in expensive:
        detail(f"  {t.name:<18s} cost={t.cost_estimate:.1f}  "
              f"type={t.tile_type.value:<10s}  abstract={t.abstraction_level}")

    info("Least expensive tiles:")
    for t in cheap:
        detail(f"  {t.name:<18s} cost={t.cost_estimate:.1f}  "
              f"type={t.tile_type.value:<10s}  abstract={t.abstraction_level}")

    # ── Step 10: Tile graph visualization ────────────────────────────
    section("Step 10: Tile Type Distribution")

    type_counts = {}
    for tile in default_registry.all_tiles:
        tt = tile.tile_type.value
        type_counts[tt] = type_counts.get(tt, 0) + 1

    total = sum(type_counts.values())
    max_count = max(type_counts.values()) if type_counts else 1

    for tt in sorted(type_counts.keys()):
        count = type_counts[tt]
        bar_len = int(count / max_count * 30)
        bar = "█" * bar_len + "░" * (30 - bar_len)
        pct = count / total * 100
        print(f"    {tt:<12s} {count:>2d} ({pct:>5.1f}%)  {CYAN}{bar}{RESET}")

    # ── Step 11: Tile instantiation ─────────────────────────────────
    section("Step 11: Tile Instantiation (Parameter Binding)")

    if map_t:
        instance = map_t.instantiate(fn="my_custom_map_fn")
        info(f"Instance of 'map': {instance}")
        info(f"  Bound params: {instance.params}")
        detail(f"  fn parameter overridden: 'my_custom_map_fn'")

    print()
    print(f"{BOLD}{GREEN}── Done! ──{RESET}")
    print()
