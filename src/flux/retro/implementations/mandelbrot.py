"""Mandelbrot set renderer — hybrid FLUX bytecode approach.

Computes a 16×16 pixel Mandelbrot set using **Python for the outer loops**
and **FLUX bytecode for the inner hot loop** (z = z² + c iteration).

Each pixel is computed by running a small bytecode program that:
  1. Takes cr, ci as register inputs (8.8 fixed-point)
  2. Iterates z = z² + c up to 50 times
  3. Counts iterations until |z|² > threshold or max reached
  4. Stores iteration count in a memory region

Fixed-point format: values × 256  (8 bits integer, 8 bits fraction)
  e.g. -2.0 → -512,  1.0 → 256,  0.5 → 128

Register layout (inner loop bytecode)
------------------------------------
    R0  zr            R1  zi
    R2  cr            R3  ci
    R4  iter_count    R5  max_iter (50)
    R6  temp1         R7  temp2
    R8  temp3         R9  addr (store target)
    R10 scale (256, for fixed-point division)
"""

from __future__ import annotations

from flux.bytecode.opcodes import Op
from flux.vm.interpreter import Interpreter
from ._asm import Assembler


class MandelbrotRenderer:
    """Hybrid Mandelbrot renderer: Python outer loops + bytecode inner loop."""

    # Registers
    ZR = 0
    ZI = 1
    CR = 2
    CI = 3
    ITER = 4
    MAX_ITER = 5
    T1 = 6
    T2 = 7
    T3 = 8
    ADDR = 9
    SCALE = 10

    GRID = 16
    MAX_ITERATIONS = 50
    # Mandelbrot view: real in [-2.0, 1.0], imag in [-1.5, 1.5]
    REAL_MIN = -2.0
    REAL_MAX = 1.0
    IMAG_MIN = -1.5
    IMAG_MAX = 1.5

    # Memory base for storing iteration counts
    MEM_BASE = 0x6000

    @classmethod
    def build_pixel_bytecode(cls) -> bytes:
        """Build the inner Mandelbrot iteration loop.

        Expects: R0=0 (zr), R1=0 (zi), R2=cr, R3=ci, R4=0, R5=50,
                 R9=addr, R10=256
        On halt: iteration count stored at memory[R9] as i32.
        """
        a = Assembler()

        a.movi(cls.SCALE, 256)
        a.movi(cls.ITER, 0)
        a.movi(cls.ZR, 0)
        a.movi(cls.ZI, 0)

        # ── Iteration loop ──────────────────────────────────────────────
        a.label("iter_loop")

        # Check iter >= max_iter → done
        a.cmp(cls.ITER, cls.MAX_ITER)
        a.jge("done")

        # ── Check |z|² > threshold ──────────────────────────────────────
        # |z|² = zr²/256 + zi²/256  (in fixed-point)
        # Threshold: 4.0 → 4*256 = 1024 in fixed-point

        # T1 = zr² / 256
        a.imul(cls.T1, cls.ZR, cls.ZR)
        a.idiv(cls.T1, cls.T1, cls.SCALE)

        # T2 = zi² / 256
        a.imul(cls.T2, cls.ZI, cls.ZI)
        a.idiv(cls.T2, cls.T2, cls.SCALE)

        # T3 = |z|² = T1 + T2
        a.iadd(cls.T3, cls.T1, cls.T2)

        # Compare with threshold 1024
        a.movi(cls.T1, 1024)
        a.cmp(cls.T3, cls.T1)
        a.jg("done")

        # ── Compute z = z² + c ─────────────────────────────────────────
        # zr_new = (zr² - zi²) / 256 + cr
        # zi_new = (2 * zr * zi) / 256 + ci

        # Recompute squares (T1/T2 were clobbered above)
        # T1 = zr * zr
        a.imul(cls.T1, cls.ZR, cls.ZR)
        # T2 = zi * zi
        a.imul(cls.T2, cls.ZI, cls.ZI)
        # T3 = zr * zi
        a.imul(cls.T3, cls.ZR, cls.ZI)

        # zr_new = (T1 - T2) / 256 + cr
        a.isub(cls.T1, cls.T1, cls.T2)      # T1 = zr² - zi²
        a.idiv(cls.T1, cls.T1, cls.SCALE)   # T1 = (zr² - zi²) / 256
        a.iadd(cls.T1, cls.T1, cls.CR)      # T1 = zr_new

        # zi_new = (2 * T3) / 256 + ci
        # We need 2 * zr * zi / 256.  Use T2 = 2.
        a.movi(cls.T2, 2)
        a.imul(cls.T2, cls.T3, cls.T2)      # T2 = 2 * zr * zi
        a.idiv(cls.T2, cls.T2, cls.SCALE)   # T2 = (2*zr*zi) / 256
        a.iadd(cls.T2, cls.T2, cls.CI)      # T2 = zi_new

        # Store new z values
        a.mov(cls.ZR, cls.T1)
        a.mov(cls.ZI, cls.T2)

        # Increment iteration counter and loop
        a.inc(cls.ITER)
        a.jmp("iter_loop")

        # ── Done: store iteration count ─────────────────────────────────
        a.label("done")
        a.store(cls.ITER, cls.ADDR)
        a.halt()

        return a.to_bytes()

    @classmethod
    def _compute_pixel(cls, vm: Interpreter, cr: float, ci: float,
                       addr: int) -> int:
        """Set up registers and run the inner-loop bytecode for one pixel."""
        # Reset VM execution state (keep memory)
        vm.pc = 0
        vm.halted = False
        vm.running = False
        vm._flag_zero = False
        vm._flag_sign = False
        vm._flag_carry = False
        vm._flag_overflow = False

        # Set fixed-point inputs
        vm.regs.write_gp(cls.ZR, 0)                  # z starts at 0
        vm.regs.write_gp(cls.ZI, 0)
        vm.regs.write_gp(cls.CR, int(cr * 256))      # c real in 8.8
        vm.regs.write_gp(cls.CI, int(ci * 256))      # c imag in 8.8
        vm.regs.write_gp(cls.ITER, 0)
        vm.regs.write_gp(cls.MAX_ITER, cls.MAX_ITERATIONS)
        vm.regs.write_gp(cls.ADDR, addr)

        vm.execute()

        # Read result from memory
        stack = vm.memory.get_region("stack")
        return stack.read_i32(addr)

    @staticmethod
    def render_ascii(iterations: list[list[int]]) -> str:
        """Render iteration counts as ASCII art."""
        chars = " .:-=+*#%@"
        lines = []
        for row in iterations:
            line = ""
            for it in row:
                idx = min(it * len(chars) // (50 + 1), len(chars) - 1)
                line += chars[idx]
            lines.append(line)
        return "\n".join(lines)

    @classmethod
    def demonstrate(cls) -> None:
        """Compute and render a 16×16 Mandelbrot set."""
        bytecode = cls.build_pixel_bytecode()
        vm = Interpreter(bytecode, memory_size=65536)

        print("=" * 64)
        print("  FLUX BYTECODE MANDELBROT  —  16×16 hybrid renderer")
        print("=" * 64)
        print(f"  Inner-loop bytecode: {len(bytecode)} bytes")
        print(f"  Grid: {cls.GRID}×{cls.GRID}, max iterations: {cls.MAX_ITERATIONS}")

        # Compute all pixels
        iterations = []
        total_cycles = 0

        for y in range(cls.GRID):
            row = []
            for x in range(cls.GRID):
                # Map pixel to complex plane
                cr = cls.REAL_MIN + (x / (cls.GRID - 1)) * (cls.REAL_MAX - cls.REAL_MIN)
                ci = cls.IMAG_MIN + (y / (cls.GRID - 1)) * (cls.IMAG_MAX - cls.IMAG_MIN)

                addr = cls.MEM_BASE + y * cls.GRID * 4 + x * 4
                it = cls._compute_pixel(vm, cr, ci, addr)
                row.append(it)
                total_cycles += vm.cycle_count
            iterations.append(row)

        # Render
        art = cls.render_ascii(iterations)
        print(f"\n  Total cycles: {total_cycles}")
        print(f"  Avg cycles/pixel: {total_cycles // (cls.GRID * cls.GRID)}")
        print(f"\n  {art}")

        # Statistics
        all_iters = [it for row in iterations for it in row]
        in_set = sum(1 for it in all_iters if it >= cls.MAX_ITERATIONS)
        print(f"\n  Pixels in set: {in_set}/{cls.GRID * cls.GRID}")
        print(f"  VM halted: {vm.halted}")
        print()


if __name__ == "__main__":
    MandelbrotRenderer.demonstrate()
