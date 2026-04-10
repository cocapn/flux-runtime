"""FLUX Retro: Mastermind — code-breaking comparison in FLUX bytecode.

The VM computes black/white pegs for a given guess vs. secret:
  • R0–R3 = secret code (digits 1-6)
  • R4–R7 = guess code   (digits 1-6)
  • R8     = black pegs (correct digit, correct position)
  • R9     = white pegs (correct digit, wrong position)

Bytecode algorithm:
  1. Compare each position for exact match → black pegs
  2. For non-matched positions, count frequency → white pegs
"""

from __future__ import annotations

import random
from flux.bytecode.opcodes import Op
from flux.vm.interpreter import Interpreter
from ._builder import BytecodeBuilder

_CODE_LEN = 4
_DIGITS = 6


class Mastermind:
    """Mastermind code-breaking game using FLUX bytecode for comparison."""

    def __init__(self, secret: list[int] | None = None):
        self.secret = secret or [random.randint(1, _DIGITS) for _ in range(_CODE_LEN)]

    # ── bytecode: peg computation ───────────────────────────────────────

    def build_bytecode(self) -> bytes:
        """Build bytecode that reads secret (R0-R3), guess (R4-R7),
        computes black pegs (R8) and white pegs (R9)."""
        b = BytecodeBuilder()

        # ── initialise ──────────────────────────────────────────────────
        b.movi(8, 0)     # R8 = black pegs = 0
        b.movi(9, 0)     # R9 = white pegs = 0
        b.movi(10, 0)    # R10 = index = 0

        # ── Phase 1: count black pegs (exact matches) ───────────────────
        # For each position i (0..3): if secret[i] == guess[i], R8++
        # Also mark matched positions: secret[i] = 0, guess[i] = -1

        b.label("black_loop")

        # Check if index >= 4 → done with black phase
        b.movi(11, _CODE_LEN)
        b.cmp(10, 11)
        b.jge("black_done")

        # Load secret[i] and guess[i] based on index
        # Since we can't do indexed register access, we use a switch:
        # i=0: compare R0, R4; i=1: compare R1, R5; etc.

        # Check i == 0
        b.movi(11, 0)
        b.cmp(10, 11)
        b.jne("chk_i1")
        b.cmp(0, 4)
        b.jne("no_black_0")
        b.inc(8)
        b.movi(0, 0)      # mark secret[0] as used
        b.movi(4, -1)     # mark guess[0] as used
        b.label("no_black_0")
        b.jmp("black_next")

        # Check i == 1
        b.label("chk_i1")
        b.movi(11, 1)
        b.cmp(10, 11)
        b.jne("chk_i2")
        b.cmp(1, 5)
        b.jne("no_black_1")
        b.inc(8)
        b.movi(1, 0)
        b.movi(5, -1)
        b.label("no_black_1")
        b.jmp("black_next")

        # Check i == 2
        b.label("chk_i2")
        b.movi(11, 2)
        b.cmp(10, 11)
        b.jne("chk_i3")
        b.cmp(2, 6)
        b.jne("no_black_2")
        b.inc(8)
        b.movi(2, 0)
        b.movi(6, -1)
        b.label("no_black_2")
        b.jmp("black_next")

        # Check i == 3
        b.label("chk_i3")
        b.cmp(3, 7)
        b.jne("no_black_3")
        b.inc(8)
        b.movi(3, 0)
        b.movi(7, -1)
        b.label("no_black_3")

        b.label("black_next")
        b.inc(10)
        b.jmp("black_loop")

        b.label("black_done")

        # ── Phase 2: count white pegs ───────────────────────────────────
        # For each guess position j (R4-R7), if guess[j] > 0,
        # search through remaining secret positions (R0-R3) for match.
        # We unroll this: check each guess digit against each secret digit.

        # guess[0] (R4) vs secret[0..3]
        b.movi(11, -1)
        b.cmp(4, 11)       # if guess[0] was already matched (-1)
        b.jle("w_g1_start")
        b.cmp(0, 4)
        b.jne("w_g0_s1")
        b.inc(9); b.movi(0, 0); b.movi(4, -1); b.jmp("w_g1_start")
        b.label("w_g0_s1")
        b.cmp(1, 4)
        b.jne("w_g0_s2")
        b.inc(9); b.movi(1, 0); b.movi(4, -1); b.jmp("w_g1_start")
        b.label("w_g0_s2")
        b.cmp(2, 4)
        b.jne("w_g0_s3")
        b.inc(9); b.movi(2, 0); b.movi(4, -1); b.jmp("w_g1_start")
        b.label("w_g0_s3")
        b.cmp(3, 4)
        b.jne("w_g1_start")
        b.inc(9); b.movi(3, 0); b.movi(4, -1)

        # guess[1] (R5) vs secret[0..3]
        b.label("w_g1_start")
        b.movi(11, -1)
        b.cmp(5, 11)
        b.jle("w_g2_start")
        b.cmp(0, 5)
        b.jne("w_g1_s1")
        b.inc(9); b.movi(0, 0); b.movi(5, -1); b.jmp("w_g2_start")
        b.label("w_g1_s1")
        b.cmp(1, 5)
        b.jne("w_g1_s2")
        b.inc(9); b.movi(1, 0); b.movi(5, -1); b.jmp("w_g2_start")
        b.label("w_g1_s2")
        b.cmp(2, 5)
        b.jne("w_g1_s3")
        b.inc(9); b.movi(2, 0); b.movi(5, -1); b.jmp("w_g2_start")
        b.label("w_g1_s3")
        b.cmp(3, 5)
        b.jne("w_g2_start")
        b.inc(9); b.movi(3, 0); b.movi(5, -1)

        # guess[2] (R6) vs secret[0..3]
        b.label("w_g2_start")
        b.movi(11, -1)
        b.cmp(6, 11)
        b.jle("w_g3_start")
        b.cmp(0, 6)
        b.jne("w_g2_s1")
        b.inc(9); b.movi(0, 0); b.movi(6, -1); b.jmp("w_g3_start")
        b.label("w_g2_s1")
        b.cmp(1, 6)
        b.jne("w_g2_s2")
        b.inc(9); b.movi(1, 0); b.movi(6, -1); b.jmp("w_g3_start")
        b.label("w_g2_s2")
        b.cmp(2, 6)
        b.jne("w_g2_s3")
        b.inc(9); b.movi(2, 0); b.movi(6, -1); b.jmp("w_g3_start")
        b.label("w_g2_s3")
        b.cmp(3, 6)
        b.jne("w_g3_start")
        b.inc(9); b.movi(3, 0); b.movi(6, -1)

        # guess[3] (R7) vs secret[0..3]
        b.label("w_g3_start")
        b.movi(11, -1)
        b.cmp(7, 11)
        b.jle("done")
        b.cmp(0, 7)
        b.jne("w_g3_s1")
        b.inc(9); b.movi(0, 0); b.movi(7, -1); b.jmp("done")
        b.label("w_g3_s1")
        b.cmp(1, 7)
        b.jne("w_g3_s2")
        b.inc(9); b.movi(1, 0); b.movi(7, -1); b.jmp("done")
        b.label("w_g3_s2")
        b.cmp(2, 7)
        b.jne("w_g3_s3")
        b.inc(9); b.movi(2, 0); b.movi(7, -1); b.jmp("done")
        b.label("w_g3_s3")
        b.cmp(3, 7)
        b.jne("done")
        b.inc(9); b.movi(3, 0); b.movi(7, -1)

        b.label("done")
        b.halt()
        return b.build()

    # ── single evaluation ───────────────────────────────────────────────

    def evaluate(self, guess: list[int]) -> dict:
        """Run the VM with secret and guess, return pegs."""
        bc = self.build_bytecode()
        vm = Interpreter(bc)
        # Load secret into R0-R3, guess into R4-R7
        for i in range(_CODE_LEN):
            vm.regs.write_gp(i, self.secret[i])
            vm.regs.write_gp(i + 4, guess[i])
        vm.execute()
        return {
            "black": vm.regs.read_gp(8),
            "white": vm.regs.read_gp(9),
            "cycles": vm.cycle_count,
        }

    # ── full game run ───────────────────────────────────────────────────

    def run(self) -> dict:
        """Run a full game with a simple solver, return results."""
        return self._auto_solve()

    def _auto_solve(self, max_guesses: int = 10) -> dict:
        guesses = []
        results = []
        solved = False

        # Simple strategy: try all combos systematically from [1,1,1,1]
        # For demo purposes, use a smarter approach
        candidates = []
        for a in range(1, _DIGITS + 1):
            for b_ in range(1, _DIGITS + 1):
                for c in range(1, _DIGITS + 1):
                    for d in range(1, _DIGITS + 1):
                        candidates.append([a, b_, c, d])

        random.shuffle(candidates)

        for _ in range(max_guesses):
            if not candidates:
                break
            guess = candidates.pop(0)
            pegs = self.evaluate(guess)
            guesses.append(guess)
            results.append(pegs)

            if pegs["black"] == _CODE_LEN:
                solved = True
                break

            # Filter candidates
            new_candidates = []
            for cand in candidates:
                # Use Python to quickly filter (VM eval is for scoring only)
                test_pegs = self._python_pegs(cand)
                if (test_pegs["black"] == pegs["black"] and
                        test_pegs["white"] == pegs["white"]):
                    new_candidates.append(cand)
            candidates = new_candidates

        return {
            "secret": self.secret,
            "guesses": guesses,
            "results": results,
            "solved": solved,
            "total_guesses": len(guesses),
        }

    def _python_pegs(self, guess: list[int]) -> dict:
        """Quick Python peg computation for candidate filtering."""
        black = sum(s == g for s, g in zip(self.secret, guess))
        secret_rem = []
        guess_rem = []
        for s, g in zip(self.secret, guess):
            if s != g:
                secret_rem.append(s)
                guess_rem.append(g)
        white = 0
        for g in guess_rem:
            if g in secret_rem:
                white += 1
                secret_rem.remove(g)
        return {"black": black, "white": white}

    # ── demonstration ───────────────────────────────────────────────────

    @staticmethod
    def demonstrate():
        print("=" * 60)
        print("  FLUX RETRO — MASTERMIND")
        print("  Code-breaking with FLUX bytecode comparison engine")
        print("=" * 60)

        game = Mastermind()
        result = game.run()

        print(f"\n  Secret code: {''.join(str(d) for d in result['secret'])}")
        print(f"  {'':>4}  {'GUESS':>10}  {'BLACK':>6}  {'WHITE':>6}")
        print("  " + "-" * 34)

        for i, (guess, pegs) in enumerate(zip(result["guesses"], result["results"])):
            g_str = "".join(str(d) for d in guess)
            b_str = "●" * pegs["black"] if pegs["black"] else " ·"
            w_str = "○" * pegs["white"] if pegs["white"] else " ·"
            print(f"  {i + 1:>3}  {g_str:>10}  {b_str:>6}  {w_str:>6}")

        print()
        if result["solved"]:
            print(f"  Solved in {result['total_guesses']} guesses!")
        else:
            print(f"  Not solved after {result['total_guesses']} guesses.")

        total_cycles = sum(r["cycles"] for r in result["results"])
        print(f"  Total VM cycles: {total_cycles}")
        print()
