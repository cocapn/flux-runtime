"""Tetris — simplified FLUX bytecode implementation.

Manages a 10-wide grid stored in a heap memory region.  An I-piece (4
horizontal blocks) is dropped one row at a time.  When it can no longer
move down it locks into the grid, completed lines are cleared, and a new
piece spawns at the top.

The grid is 10×20 = 200 cells, each stored as an i32 (4 bytes).
Total memory: 800 bytes.  Addressed as  grid_base + (row*10 + col)*4.
Row 0 is the **top** of the board (where pieces spawn), row 19 is the
bottom.

Register layout
---------------
    R0  piece_row      R1  piece_col
    R2  drop_steps     R3  grid_base
    R4  temp           R5  temp2
    R6  line_count     R7  total_lines_cleared
    R8  inner_col      R9  inner_row
    R10 frame_counter
"""

from __future__ import annotations

from flux.bytecode.opcodes import Op
from flux.vm.interpreter import Interpreter
from ._asm import Assembler


class Tetris:
    """Simplified Tetris with I-piece dropping in FLUX bytecode."""

    # Register assignments
    P_ROW = 0
    P_COL = 1
    DROP_STEPS = 2
    GRID_BASE = 3
    T = 4
    T2 = 5
    LINE_COUNT = 6
    TOTAL_LINES = 7
    INNER_COL = 8
    INNER_ROW = 9
    FRAME = 10

    WIDTH = 10
    HEIGHT = 20
    DROP_TOTAL = 40
    GRID_SIZE = WIDTH * HEIGHT
    CELL_BYTES = 4

    @classmethod
    def _emit_cell_addr(cls, a: Assembler, row_reg: int, col_reg: int,
                        dst: int) -> None:
        """Emit bytecode to compute dst = GRID_BASE + (row*10 + col)*4.

        Uses T and T2 as scratch (clobbers them).
        """
        # dst = row * 10
        a.movi(cls.T2, 10)
        a.imul(dst, row_reg, cls.T2)
        # dst += col
        a.iadd(dst, dst, col_reg)
        # dst *= 4  (each cell is 4 bytes)
        a.movi(cls.T2, 4)
        a.imul(dst, dst, cls.T2)
        # dst += GRID_BASE
        a.iadd(dst, dst, cls.GRID_BASE)

    @classmethod
    def build_bytecode(cls) -> bytes:
        """Assemble Tetris drop simulation."""
        a = Assembler()

        # ── Initialise ──────────────────────────────────────────────────
        a.movi(cls.GRID_BASE, 0x4000)
        a.movi(cls.P_ROW, 0)
        a.movi(cls.P_COL, 3)
        a.movi(cls.DROP_STEPS, cls.DROP_TOTAL)
        a.movi(cls.TOTAL_LINES, 0)

        # ── Main drop loop ──────────────────────────────────────────────
        a.label("drop_loop")

        # ── Check if piece_row + 1 >= HEIGHT → lock ────────────────────
        a.movi(cls.T, cls.HEIGHT - 1)
        a.cmp(cls.P_ROW, cls.T)
        a.jge("lock_piece")

        # ── Collision check: for each col, read grid[row+1][col] ───────
        a.movi(cls.INNER_COL, 0)
        a.label("check_col_loop")

        # Compute T = (P_ROW+1) * 10
        a.movi(cls.T, 1)
        a.iadd(cls.T, cls.P_ROW, cls.T)
        a.movi(cls.T2, 10)
        a.imul(cls.T, cls.T, cls.T2)

        # T += P_COL + INNER_COL
        a.iadd(cls.T, cls.T, cls.P_COL)
        a.iadd(cls.T, cls.T, cls.INNER_COL)

        # T *= 4
        a.movi(cls.T2, 4)
        a.imul(cls.T, cls.T, cls.T2)

        # T += GRID_BASE → T = absolute address
        a.iadd(cls.T, cls.T, cls.GRID_BASE)

        a.movi(cls.T2, 0)
        a.load(cls.T2, cls.T)

        a.movi(cls.T, 0)
        a.cmp(cls.T2, cls.T)
        a.jne("lock_piece")

        a.inc(cls.INNER_COL)
        a.movi(cls.T, 4)
        a.cmp(cls.INNER_COL, cls.T)
        a.jl("check_col_loop")

        # No collision → move piece down
        a.inc(cls.P_ROW)
        a.jmp("end_drop_step")

        # ── Lock piece into grid ────────────────────────────────────────
        a.label("lock_piece")

        a.movi(cls.INNER_COL, 0)
        a.label("lock_col_loop")

        # Compute address of grid[P_ROW][P_COL + INNER_COL]
        a.mov(cls.T, cls.P_ROW)
        a.movi(cls.T2, 10)
        a.imul(cls.T, cls.T, cls.T2)
        a.iadd(cls.T, cls.T, cls.P_COL)
        a.iadd(cls.T, cls.T, cls.INNER_COL)
        a.movi(cls.T2, 4)
        a.imul(cls.T, cls.T, cls.T2)
        a.iadd(cls.T, cls.T, cls.GRID_BASE)

        a.movi(cls.T2, 1)
        a.store(cls.T2, cls.T)

        a.inc(cls.INNER_COL)
        a.movi(cls.T, 4)
        a.cmp(cls.INNER_COL, cls.T)
        a.jl("lock_col_loop")

        # ── Check and clear completed lines ─────────────────────────────
        a.movi(cls.INNER_ROW, cls.HEIGHT - 1)
        a.movi(cls.LINE_COUNT, 0)

        a.label("scan_row_loop")
        a.movi(cls.T, 0)
        a.cmp(cls.INNER_ROW, cls.T)
        a.jl("scan_done")

        a.movi(cls.INNER_COL, 0)
        a.label("check_row_col_loop")

        # addr = GRID_BASE + (INNER_ROW*10 + INNER_COL)*4
        a.mov(cls.T, cls.INNER_ROW)
        a.movi(cls.T2, 10)
        a.imul(cls.T, cls.T, cls.T2)
        a.iadd(cls.T, cls.T, cls.INNER_COL)
        a.movi(cls.T2, 4)
        a.imul(cls.T, cls.T, cls.T2)
        a.iadd(cls.T, cls.T, cls.GRID_BASE)

        a.movi(cls.T2, 0)
        a.load(cls.T2, cls.T)
        a.movi(cls.T, 0)
        a.cmp(cls.T2, cls.T)
        a.je("row_not_full")

        a.inc(cls.INNER_COL)
        a.movi(cls.T, 10)
        a.cmp(cls.INNER_COL, cls.T)
        a.jl("check_row_col_loop")

        # Row full → clear
        a.movi(cls.INNER_COL, 0)
        a.label("clear_row_col_loop")

        a.mov(cls.T, cls.INNER_ROW)
        a.movi(cls.T2, 10)
        a.imul(cls.T, cls.T, cls.T2)
        a.iadd(cls.T, cls.T, cls.INNER_COL)
        a.movi(cls.T2, 4)
        a.imul(cls.T, cls.T, cls.T2)
        a.iadd(cls.T, cls.T, cls.GRID_BASE)
        a.movi(cls.T2, 0)
        a.store(cls.T2, cls.T)

        a.inc(cls.INNER_COL)
        a.movi(cls.T, 10)
        a.cmp(cls.INNER_COL, cls.T)
        a.jl("clear_row_col_loop")

        a.inc(cls.LINE_COUNT)
        a.jmp("scan_row_loop")

        a.label("row_not_full")
        a.dec(cls.INNER_ROW)
        a.jmp("scan_row_loop")

        a.label("scan_done")
        a.iadd(cls.TOTAL_LINES, cls.TOTAL_LINES, cls.LINE_COUNT)

        # ── Spawn new piece ─────────────────────────────────────────────
        a.movi(cls.P_ROW, 0)
        a.movi(cls.P_COL, 3)

        a.label("end_drop_step")
        a.dec(cls.DROP_STEPS)
        a.jnz(cls.DROP_STEPS, "drop_loop")

        a.halt()
        return a.to_bytes()

    # ── Grid I/O ────────────────────────────────────────────────────────

    @classmethod
    def _read_grid(cls, vm: Interpreter) -> list[list[int]]:
        """Read the grid from VM stack memory."""
        stack = vm.memory.get_region("stack")
        grid = []
        for row in range(cls.HEIGHT):
            row_data = []
            for col in range(cls.WIDTH):
                addr = 0x4000 + (row * cls.WIDTH + col) * 4
                row_data.append(stack.read_i32(addr))
            grid.append(row_data)
        return grid

    @classmethod
    def _place_piece_visual(
        cls, grid: list[list[int]], prow: int, pcol: int
    ) -> list[list[int]]:
        """Return a copy of grid with the piece overlaid for display."""
        display = [r[:] for r in grid]
        for dc in range(4):
            c = pcol + dc
            if 0 <= prow < cls.HEIGHT and 0 <= c < cls.WIDTH:
                display[prow][c] = 2
        return display

    @staticmethod
    def render_grid(grid: list[list[int]]) -> str:
        """ASCII render of a 20×10 Tetris grid."""
        lines = ["  +----------+"]
        for row in grid:
            line = "  |"
            for cell in row:
                if cell == 2:
                    line += "O"  # active piece
                elif cell:
                    line += "#"  # locked
                else:
                    line += "."
            line += "|"
            lines.append(line)
        lines.append("  +----------+")
        return "\n".join(lines)

    # ── Demonstrate ─────────────────────────────────────────────────────

    @classmethod
    def demonstrate(cls) -> None:
        """Build, execute, and display Tetris simulation results."""
        bytecode = cls.build_bytecode()
        vm = Interpreter(bytecode, memory_size=65536)

        print("=" * 64)
        print("  FLUX BYTECODE TETRIS  —  I-piece drop simulation")
        print("=" * 64)
        print(f"  Bytecode size: {len(bytecode)} bytes")
        print(f"  Grid: {cls.WIDTH}x{cls.HEIGHT}, Drop steps: {cls.DROP_TOTAL}")

        vm.execute()
        cycles = vm.cycle_count

        grid = cls._read_grid(vm)
        prow = vm.regs.read_gp(cls.P_ROW)
        pcol = vm.regs.read_gp(cls.P_COL)
        total = vm.regs.read_gp(cls.TOTAL_LINES)

        print(f"\n  Executed in {cycles} cycles")
        print(f"  Total lines cleared: {total}")
        print(f"  Current piece: row={prow}, col={pcol}..{pcol+3}")

        display = cls._place_piece_visual(grid, prow, pcol)
        print(f"\n{cls.render_grid(display)}")

        occupied = sum(1 for r in grid for c in r if c == 1)
        print(f"\n  Cells locked: {occupied}/{cls.WIDTH * cls.HEIGHT}")

        gp = vm.regs.snapshot()["gp"]
        print(f"  Registers: {' '.join(f'R{i}={gp[i]}' for i in range(11))}")
        print(f"  VM halted: {vm.halted}")
        print()


if __name__ == "__main__":
    Tetris.demonstrate()
