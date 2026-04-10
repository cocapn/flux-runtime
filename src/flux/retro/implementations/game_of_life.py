"""FLUX Retro: Game of Life — cellular automaton in FLUX bytecode.

An 8×8 grid with Conway's rules, implemented with padded borders (10×10 buffer).
The VM bytecode computes one full generation:
  • Reads 64 cells from source buffer
  • Counts 8 neighbors per cell
  • Applies birth/survival rules
  • Writes next state to destination buffer

Memory layout (stack region):
  • 1000–1099: Source buffer (10×10 padded grid, 100 bytes)
  • 1200–1299: Destination buffer (10×10 padded grid, 100 bytes)

Python orchestrates multiple generations, swaps buffers, and renders.
"""

from __future__ import annotations

from flux.bytecode.opcodes import Op
from flux.vm.interpreter import Interpreter
from ._builder import BytecodeBuilder

_GRID = 8
_PAD = 1
_PADDED = _GRID + 2 * _PAD  # 10
_BUF_SIZE = _PADDED * _PADDED  # 100
_SRC_BASE = 1000
_DST_BASE = 1200

# Neighbor offsets in padded grid (row_delta * 10 + col_delta)
_NBR_OFFSETS = [-11, -10, -9, -1, 1, 9, 10, 11]


class GameOfLife:
    """Conway's Game of Life on an 8×8 grid with FLUX bytecode generation logic."""

    def __init__(self, pattern: str = "glider"):
        self.grid = [[0] * _GRID for _ in range(_GRID)]
        self._init_pattern(pattern)

    def _init_pattern(self, pattern: str):
        """Set up initial pattern on the grid."""
        if pattern == "glider":
            # Classic glider
            cells = [(0, 1), (1, 2), (2, 0), (2, 1), (2, 2)]
            for r, c in cells:
                self.grid[r][c] = 1
        elif pattern == "blinker":
            # Blinker oscillator (period 2)
            self.grid[3][2] = 1
            self.grid[3][3] = 1
            self.grid[3][4] = 1
        elif pattern == "block":
            # Still life: 2×2 block
            self.grid[2][2] = 1
            self.grid[2][3] = 1
            self.grid[3][2] = 1
            self.grid[3][3] = 1
        elif pattern == "beacon":
            # Beacon oscillator
            for r, c in [(1, 1), (1, 2), (2, 1), (3, 4), (4, 3), (4, 4)]:
                self.grid[r][c] = 1
        elif pattern == "glider_gun_seed":
            # Small active seed pattern
            cells = [(1, 2), (1, 3), (2, 1), (2, 2), (3, 2), (3, 3), (4, 1)]
            for r, c in cells:
                if r < _GRID and c < _GRID:
                    self.grid[r][c] = 1
        else:
            # Random
            import random
            for r in range(_GRID):
                for c in range(_GRID):
                    self.grid[r][c] = random.randint(0, 1)

    # ── grid ↔ padded buffer conversion ─────────────────────────────────

    def _grid_to_padded(self) -> bytearray:
        """Convert 8×8 grid to 10×10 padded buffer."""
        buf = bytearray(_BUF_SIZE)  # all zeros (border = dead)
        for r in range(_GRID):
            for c in range(_GRID):
                buf[(r + _PAD) * _PADDED + (c + _PAD)] = self.grid[r][c]
        return buf

    def _padded_to_grid(self, buf: bytearray) -> list[list[int]]:
        """Convert 10×10 padded buffer back to 8×8 grid."""
        grid = [[0] * _GRID for _ in range(_GRID)]
        for r in range(_GRID):
            for c in range(_GRID):
                grid[r][c] = buf[(r + _PAD) * _PADDED + (c + _PAD)]
        return grid

    # ── bytecode generation ─────────────────────────────────────────────

    def build_generation_bytecode(self) -> bytes:
        """Build bytecode that computes one full generation.

        Reads from _SRC_BASE, writes to _DST_BASE.
        Uses registers:
            R1 = neighbor count accumulator
            R3 = temp address
            R4 = temp value
            R5 = current cell value
        """
        b = BytecodeBuilder()

        for r in range(_GRID):
            for c in range(_GRID):
                src_addr = _SRC_BASE + (r + _PAD) * _PADDED + (c + _PAD)
                dst_addr = _DST_BASE + (r + _PAD) * _PADDED + (c + _PAD)
                self._emit_cell(b, src_addr, dst_addr, r, c)

        b.halt()
        return b.build()

    def build_bytecode(self) -> bytes:
        """Alias — builds one generation of bytecode."""
        return self.build_generation_bytecode()

    def _emit_cell(self, b: BytecodeBuilder, src_addr: int, dst_addr: int,
                   row: int, col: int):
        """Emit bytecode to process one cell: count neighbors, apply rules, write."""
        tag = f"c{row}_{col}"

        # ── Count 8 neighbors ──────────────────────────────────────────
        b.movi(1, 0)  # R1 = neighbor_count = 0

        for offset in _NBR_OFFSETS:
            nbr_addr = src_addr + offset
            b.movi(3, nbr_addr)    # R3 = neighbor address
            b.load8(4, 3)          # R4 = neighbor value
            b.iadd(1, 1, 4)       # count += neighbor

        # ── Read current cell ──────────────────────────────────────────
        b.movi(3, src_addr)
        b.load8(5, 3)             # R5 = current cell value

        # ── Apply rules ────────────────────────────────────────────────
        # If alive (R5 != 0):
        #   survive if count == 2 or count == 3
        # If dead (R5 == 0):
        #   birth if count == 3
        # Else: dead

        # Check if alive
        b.movi(4, 0)
        b.cmp(5, 4)
        b.je(f"dead_{tag}")       # if current == 0, jump to dead case

        # ── Alive: check survival ──────────────────────────────────────
        b.movi(4, 2)
        b.cmp(1, 4)
        b.je(f"survive_{tag}")    # count == 2 → survive

        b.movi(4, 3)
        b.cmp(1, 4)
        b.je(f"survive_{tag}")    # count == 3 → survive

        # Die (under/over-population)
        b.movi(4, 0)
        b.jmp(f"write_{tag}")

        # ── Dead: check birth ──────────────────────────────────────────
        b.label(f"dead_{tag}")
        b.movi(4, 3)
        b.cmp(1, 4)
        b.je(f"survive_{tag}")    # count == 3 → birth

        b.movi(4, 0)              # stay dead
        b.jmp(f"write_{tag}")

        # ── Survive / Birth ────────────────────────────────────────────
        b.label(f"survive_{tag}")
        b.movi(4, 1)

        # ── Write result ───────────────────────────────────────────────
        b.label(f"write_{tag}")
        b.movi(3, dst_addr)
        b.store8(4, 3)            # write result to dest buffer

    # ── simulation ──────────────────────────────────────────────────────

    def run(self, generations: int = 8) -> dict:
        """Run the simulation for N generations."""
        frames = [self._grid_to_padded()]

        # Pre-build bytecode (it's the same for every generation)
        bc = self.build_generation_bytecode()

        for gen in range(generations):
            # Create VM with source buffer pre-loaded
            vm = Interpreter(bc, memory_size=65536)
            stack = vm.memory.get_region("stack")

            # Write source buffer
            src_buf = frames[-1]
            stack.write(_SRC_BASE, bytes(src_buf))

            # Clear destination buffer
            stack.write(_DST_BASE, bytes(_BUF_SIZE))

            vm.execute()

            # Read destination buffer
            dst_data = stack.read(_DST_BASE, _BUF_SIZE)
            frames.append(bytearray(dst_data))

        return {
            "generations": generations,
            "frames": frames,
            "bytecode_size": len(bc),
            "cycles": generations,  # will be updated below
        }

    def run_with_metrics(self, generations: int = 8) -> dict:
        """Run with per-generation metrics."""
        frames = [self._grid_to_padded()]
        bc = self.build_generation_bytecode()
        gen_metrics = []

        for gen in range(generations):
            vm = Interpreter(bc, memory_size=65536)
            stack = vm.memory.get_region("stack")
            stack.write(_SRC_BASE, bytes(frames[-1]))
            stack.write(_DST_BASE, bytes(_BUF_SIZE))
            cycles = vm.execute()
            dst_data = stack.read(_DST_BASE, _BUF_SIZE)
            frames.append(bytearray(dst_data))
            gen_metrics.append({"gen": gen, "cycles": cycles})

        total_cycles = sum(m["cycles"] for m in gen_metrics)
        return {
            "generations": generations,
            "frames": frames,
            "bytecode_size": len(bc),
            "gen_metrics": gen_metrics,
            "total_cycles": total_cycles,
        }

    # ── rendering ───────────────────────────────────────────────────────

    @staticmethod
    def _render_padded(buf: bytearray) -> str:
        """Render the 8×8 grid from a padded buffer."""
        lines = []
        for r in range(_GRID):
            row = ""
            for c in range(_GRID):
                val = buf[(r + _PAD) * _PADDED + (c + _PAD)]
                row += "██" if val else "··"
            lines.append(row)
        return "\n".join(lines)

    # ── demonstration ───────────────────────────────────────────────────

    @staticmethod
    def demonstrate():
        print("=" * 60)
        print("  FLUX RETRO — GAME OF LIFE")
        print("  Conway's cellular automaton in FLUX bytecode")
        print("=" * 60)

        for pattern in ["blinker", "glider"]:
            print(f"\n  ── Pattern: {pattern.upper()} ──\n")
            game = GameOfLife(pattern=pattern)
            result = game.run_with_metrics(generations=8)

            for i, frame in enumerate(result["frames"]):
                grid = GameOfLife._render_padded(frame)
                alive = sum(frame[(r + _PAD) * _PADDED + (c + _PAD)]
                            for r in range(_GRID) for c in range(_GRID))
                gen_label = f"Gen {i}"
                if i < len(result["gen_metrics"]):
                    gen_label += f" ({result['gen_metrics'][i]['cycles']} cycles)"
                print(f"  {gen_label}  [{alive} alive]")
                print("  " + grid.replace("\n", "\n  "))
                print()

        print(f"  Total bytecode size: {result['bytecode_size']} bytes")
        print(f"  Total VM cycles: {result['total_cycles']}")
        print()
