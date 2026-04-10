"""Pong game — FLUX bytecode implementation.

Simulates 200 frames of Pong with ball physics, paddle AI, wall bouncing,
and scoring.  All physics run in pure FLUX bytecode; Python handles setup
and ASCII rendering of snapshots.

Register layout
---------------
    R0  ball_x        R1  ball_y
    R2  ball_vx       R3  ball_vy
    R4  left_paddle   R5  right_paddle
    R6  left_score    R7  right_score
    R8  frame_count   R9  temp
    R10 temp2
"""

from __future__ import annotations

from flux.bytecode.opcodes import Op
from flux.vm.interpreter import Interpreter
from ._asm import Assembler


class Pong:
    """Pong implemented in FLUX bytecode."""

    # Register assignments
    BALL_X = 0
    BALL_Y = 1
    BALL_VX = 2
    BALL_VY = 3
    L_PAD = 4
    R_PAD = 5
    L_SCORE = 6
    R_SCORE = 7
    FRAME = 8
    T = 9
    T2 = 10

    WIDTH = 32
    HEIGHT = 16
    PADDLE_H = 3
    NUM_FRAMES = 200

    @classmethod
    def build_bytecode(cls) -> bytes:
        """Assemble the full Pong simulation loop."""
        a = Assembler()

        # ── Initialise ──────────────────────────────────────────────────
        a.movi(cls.BALL_X, 15)
        a.movi(cls.BALL_Y, 7)
        a.movi(cls.BALL_VX, 1)
        a.movi(cls.BALL_VY, 1)
        a.movi(cls.L_PAD, 5)
        a.movi(cls.R_PAD, 5)
        a.movi(cls.L_SCORE, 0)
        a.movi(cls.R_SCORE, 0)
        a.movi(cls.FRAME, cls.NUM_FRAMES)

        # ── Main loop ───────────────────────────────────────────────────
        a.label("loop")

        # Move ball: ball_x += ball_vx, ball_y += ball_vy
        a.iadd(cls.BALL_X, cls.BALL_X, cls.BALL_VX)
        a.iadd(cls.BALL_Y, cls.BALL_Y, cls.BALL_VY)

        # ── Top wall (ball_y < 0) ──────────────────────────────────────
        a.movi(cls.T, 0)
        a.cmp(cls.BALL_Y, cls.T)
        a.jge("skip_top")
        a.ineg(cls.BALL_VY, cls.BALL_VY)
        a.label("skip_top")

        # ── Bottom wall (ball_y > 15) ──────────────────────────────────
        a.movi(cls.T, 15)
        a.cmp(cls.BALL_Y, cls.T)
        a.jle("skip_bot")
        a.ineg(cls.BALL_VY, cls.BALL_VY)
        a.label("skip_bot")

        # ── Left paddle AI (track ball_y) ──────────────────────────────
        a.cmp(cls.BALL_Y, cls.L_PAD)
        a.jge("lp_ok")
        a.dec(cls.L_PAD)                        # move up
        a.label("lp_ok")
        # paddle bottom = L_PAD + PADDLE_H
        a.movi(cls.T, cls.PADDLE_H)
        a.iadd(cls.T, cls.L_PAD, cls.T)
        a.cmp(cls.BALL_Y, cls.T)
        a.jle("lp_done")
        a.inc(cls.L_PAD)                        # move down
        a.label("lp_done")

        # ── Right paddle AI (tracks ball_y with lag) ───────────────────
        a.cmp(cls.BALL_Y, cls.R_PAD)
        a.jge("rp_ok")
        a.dec(cls.R_PAD)
        a.label("rp_ok")
        a.movi(cls.T, cls.PADDLE_H)
        a.iadd(cls.T, cls.R_PAD, cls.T)
        a.cmp(cls.BALL_Y, cls.T)
        a.jle("rp_done")
        a.inc(cls.R_PAD)
        a.label("rp_done")

        # ── Left paddle collision (ball_x <= 1) ───────────────────────
        a.movi(cls.T, 1)
        a.cmp(cls.BALL_X, cls.T)
        a.jg("skip_lp_score")                    # ball_x > 1 → skip left paddle

        # ball_y in [L_PAD, L_PAD+PADDLE_H]?
        a.cmp(cls.BALL_Y, cls.L_PAD)
        a.jl("lp_miss")                         # ball above paddle
        a.movi(cls.T, cls.PADDLE_H)
        a.iadd(cls.T, cls.L_PAD, cls.T)
        a.cmp(cls.BALL_Y, cls.T)
        a.jg("lp_miss")                         # ball below paddle

        # HIT → negate vx, push ball right
        a.movi(cls.T, 1)
        a.mov(cls.BALL_VX, cls.T)               # ensure vx = 1 (right)
        a.jmp("skip_lp_score")

        a.label("lp_miss")
        # ball_x < 0 → right scores, reset ball
        a.movi(cls.T, 0)
        a.cmp(cls.BALL_X, cls.T)
        a.jge("skip_lp_score")
        a.inc(cls.R_SCORE)
        a.movi(cls.BALL_X, 15)
        a.movi(cls.BALL_Y, 7)
        a.movi(cls.BALL_VX, 1)
        a.label("skip_lp_score")

        # ── Right paddle collision (ball_x >= 30) ─────────────────────
        a.movi(cls.T, 30)
        a.cmp(cls.BALL_X, cls.T)
        a.jl("skip_rp_score")

        a.cmp(cls.BALL_Y, cls.R_PAD)
        a.jl("rp_miss")
        a.movi(cls.T, cls.PADDLE_H)
        a.iadd(cls.T, cls.R_PAD, cls.T)
        a.cmp(cls.BALL_Y, cls.T)
        a.jg("rp_miss")

        a.movi(cls.T, -1)
        a.mov(cls.BALL_VX, cls.T)               # ensure vx = -1 (left)
        a.jmp("skip_rp_score")

        a.label("rp_miss")
        a.movi(cls.T, 31)
        a.cmp(cls.BALL_X, cls.T)
        a.jle("skip_rp_score")
        a.inc(cls.L_SCORE)
        a.movi(cls.BALL_X, 15)
        a.movi(cls.BALL_Y, 7)
        a.movi(cls.BALL_VX, -1)
        a.label("skip_rp_score")

        # ── Decrement frame counter, loop ──────────────────────────────
        a.dec(cls.FRAME)
        a.jnz(cls.FRAME, "loop")

        a.halt()
        return a.to_bytes()

    # ── Rendering ───────────────────────────────────────────────────────

    @staticmethod
    def render_field(bx: int, by: int, lp: int, rp: int) -> str:
        """Return a 16-line ASCII rendering of the Pong field."""
        lines = []
        for y in range(16):
            row = ""
            for x in range(32):
                if x == bx and y == by:
                    row += "o"
                elif x == 0 and lp <= y < lp + 3:
                    row += "|"
                elif x == 31 and rp <= y < rp + 3:
                    row += "|"
                elif x == 15:
                    row += "."
                elif y == 0 or y == 15:
                    row += "-"
                else:
                    row += " "
            lines.append(row)
        return "\n".join(lines)

    # ── Demonstrate ─────────────────────────────────────────────────────

    @classmethod
    def demonstrate(cls) -> None:
        """Build, execute, and display Pong simulation results."""
        bytecode = cls.build_bytecode()
        vm = Interpreter(bytecode, memory_size=65536)

        print("=" * 64)
        print("  FLUX BYTECODE PONG  —  200-frame simulation")
        print("=" * 64)
        print(f"  Bytecode size: {len(bytecode)} bytes")

        # Show initial state
        print(f"\n  Initial state:")
        print(cls.render_field(15, 7, 5, 5))

        vm.execute()
        cycles = vm.cycle_count

        bx = vm.regs.read_gp(cls.BALL_X)
        by = vm.regs.read_gp(cls.BALL_Y)
        vx = vm.regs.read_gp(cls.BALL_VX)
        vy = vm.regs.read_gp(cls.BALL_VY)
        lp = vm.regs.read_gp(cls.L_PAD)
        rp = vm.regs.read_gp(cls.R_PAD)
        ls = vm.regs.read_gp(cls.L_SCORE)
        rs = vm.regs.read_gp(cls.R_SCORE)
        fc = vm.regs.read_gp(cls.FRAME)

        print(f"\n  Final state (after {cycles} cycles, frame={fc}):")
        print(f"  Ball: pos=({bx},{by}) vel=({vx},{vy})")
        print(f"  Paddles: left_y={lp} right_y={rp}")
        print(f"  Score: {ls} - {rs}")
        print()
        print(cls.render_field(bx, by, lp, rp))
        print()

        # Show VM state
        gp = vm.regs.snapshot()["gp"]
        print(f"  Registers: {' '.join(f'R{i}={gp[i]}' for i in range(11))}")
        print(f"  VM halted: {vm.halted}")
        print()


if __name__ == "__main__":
    Pong.demonstrate()
