"""FLUX Retro: Tic-Tac-Toe AI — win detection in FLUX bytecode.

Board is 9 cells stored in memory (stack region at offset 1000):
  • Values: 0 = empty, 1 = X (player), 2 = O (AI)
  • Layout:  [0][1][2] / [3][4][5] / [6][7][8]

The VM bytecode checks all 8 winning lines:
  • Sets R0 = winner (0=none, 1=X, 2=O)

Python handles the AI (minimax) and game orchestration.
"""

from __future__ import annotations

from flux.bytecode.opcodes import Op
from flux.vm.interpreter import Interpreter
from ._builder import BytecodeBuilder

# Board memory layout
_MEM_BOARD = 1000  # 9 bytes at stack offset 1000

# 8 winning lines
_LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),  # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),  # columns
    (0, 4, 8), (2, 4, 6),             # diagonals
]

_EMPTY = 0
_X = 1
_O = 2


class TicTacToeAI:
    """Tic-Tac-Toe with FLUX bytecode for win detection."""

    def __init__(self):
        self.board = [_EMPTY] * 9

    # ── bytecode: win detection ─────────────────────────────────────────

    def build_bytecode(self) -> bytes:
        """Build bytecode that checks all 8 winning lines.

        Reads board from memory at _MEM_BOARD (9 bytes).
        Sets R0 = winner (0=none, 1=X, 2=O).
        """
        b = BytecodeBuilder()

        b.movi(0, 0)  # R0 = winner = 0

        # Check each winning line (load 3 cells from memory, compare)
        for idx, (a, c_, d) in enumerate(_LINES):
            tag = f"L{idx}"

            # Load board[a] into R1
            b.movi(1, _MEM_BOARD + a)
            b.load8(1, 1)
            # Load board[b] into R2
            b.movi(2, _MEM_BOARD + c_)
            b.load8(2, 2)
            # Load board[c] into R3
            b.movi(3, _MEM_BOARD + d)
            b.load8(3, 3)

            # Skip if any cell is empty
            b.movi(4, 0)
            b.cmp(1, 4)
            b.je(f"skip_{tag}")
            b.cmp(2, 4)
            b.je(f"skip_{tag}")
            b.cmp(3, 4)
            b.je(f"skip_{tag}")

            # Check all three equal
            b.cmp(1, 2)
            b.jne(f"skip_{tag}")
            b.cmp(2, 3)
            b.jne(f"skip_{tag}")

            # Winner found!
            b.mov(0, 1)

            b.label(f"skip_{tag}")

        b.halt()
        return b.build()

    # ── evaluation ──────────────────────────────────────────────────────

    def vm_check_winner(self) -> int:
        """Run VM to check for a winner. Returns 0, 1, or 2."""
        bc = self.build_bytecode()
        vm = Interpreter(bc, memory_size=65536)
        stack = vm.memory.get_region("stack")
        for i in range(9):
            stack.write(_MEM_BOARD + i, bytes([self.board[i]]))
        vm.execute()
        return vm.regs.read_gp(0)

    # ── game logic (Python) ────────────────────────────────────────────

    def _check_winner_py(self) -> int:
        """Python-side winner check."""
        for a, b_, c in _LINES:
            if self.board[a] == self.board[b_] == self.board[c] != _EMPTY:
                return self.board[a]
        return _EMPTY

    def _get_empty(self) -> list[int]:
        return [i for i in range(9) if self.board[i] == _EMPTY]

    def _ai_move(self) -> int:
        """AI selects best move using minimax."""
        best_score = -float("inf")
        best_move = -1
        for move in self._get_empty():
            self.board[move] = _O
            score = self._minimax(False, 0, -float("inf"), float("inf"))
            self.board[move] = _EMPTY
            if score > best_score:
                best_score = score
                best_move = move
        return best_move

    def _minimax(self, is_max: bool, depth: int, alpha: int, beta: int) -> int:
        winner = self._check_winner_py()
        if winner == _O:
            return 10 - depth
        if winner == _X:
            return depth - 10
        if not self._get_empty():
            return 0
        if is_max:
            best = -float("inf")
            for move in self._get_empty():
                self.board[move] = _O
                best = max(best, self._minimax(False, depth + 1, alpha, beta))
                self.board[move] = _EMPTY
                alpha = max(alpha, best)
                if beta <= alpha:
                    break
            return best
        else:
            best = float("inf")
            for move in self._get_empty():
                self.board[move] = _X
                best = min(best, self._minimax(True, depth + 1, alpha, beta))
                self.board[move] = _EMPTY
                beta = min(beta, best)
                if beta <= alpha:
                    break
            return best

    # ── full game run ───────────────────────────────────────────────────

    def run(self) -> dict:
        """Run a full game (simple AI vs minimax AI)."""
        self.board = [_EMPTY] * 9
        moves = []
        winner = _EMPTY
        total_cycles = 0

        for turn in range(9):
            if turn % 2 == 0:
                player = _X
                # X plays a corner or center
                empties = self._get_empty()
                move = self._x_strategy(empties, turn)
            else:
                player = _O
                move = self._ai_move()

            self.board[move] = player

            # Verify with VM
            bc = self.build_bytecode()
            vm = Interpreter(bc, memory_size=65536)
            stack = vm.memory.get_region("stack")
            for i in range(9):
                stack.write(_MEM_BOARD + i, bytes([self.board[i]]))
            cycles = vm.execute()
            total_cycles += cycles
            vm_winner = vm.regs.read_gp(0)

            moves.append({
                "turn": turn,
                "player": "X" if player == _X else "O",
                "move": move,
                "vm_winner": vm_winner,
            })

            winner = self._check_winner_py()
            if winner != _EMPTY:
                break

        return {
            "board": self.board[:],
            "moves": moves,
            "winner": "X" if winner == _X else ("O" if winner == _O else "Draw"),
            "total_cycles": total_cycles,
        }

    def _x_strategy(self, empties: list[int], turn: int) -> int:
        """Simple strategy for X player."""
        # First move: center
        if 4 in empties:
            return 4
        # Second move: corner
        corners = [c for c in [0, 2, 6, 8] if c in empties]
        if corners:
            return corners[0]
        # Otherwise: first available
        return empties[0]

    # ── rendering ───────────────────────────────────────────────────────

    @staticmethod
    def _render_board(board: list[int]) -> str:
        symbols = {_EMPTY: " ", _X: "X", _O: "O"}
        rows = []
        for r in range(3):
            cells = []
            for c in range(3):
                cells.append(f" {symbols[board[r * 3 + c]]} ")
            rows.append("|".join(cells))
            if r < 2:
                rows.append("---+---+---")
        return "\n".join(rows)

    # ── demonstration ───────────────────────────────────────────────────

    @staticmethod
    def demonstrate():
        print("=" * 60)
        print("  FLUX RETRO — TIC-TAC-TOE AI")
        print("  Win detection in FLUX bytecode, minimax AI")
        print("=" * 60)

        game = TicTacToeAI()
        result = game.run()

        print()
        for entry in result["moves"]:
            player = entry["player"]
            move = entry["move"]
            r, c = move // 3, move % 3
            vm_w = {0: "none", 1: "X", 2: "O"}.get(entry["vm_winner"], "?")
            print(f"  Turn {entry['turn']}: {player} plays ({r},{c})  "
                  f"[VM detects winner: {vm_w}]")
            # Show board at this point
            temp_board = [_EMPTY] * 9
            for prev in result["moves"]:
                if prev["turn"] <= entry["turn"]:
                    p = _X if prev["player"] == "X" else _O
                    temp_board[prev["move"]] = p
            print("  " + game._render_board(temp_board).replace("\n", "\n  "))
            print()

        print(f"  Result: {result['winner']}")
        print(f"  Total VM cycles: {result['total_cycles']}")
        print()
