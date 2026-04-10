"""FLUX Retro: Snake — movement and collision in FLUX bytecode.

The snake moves on an 8×8 grid stored in memory:
  • 0 = empty,  1 = snake body,  2 = food,  3 = snake head
  • Grid stored at stack memory offset 1000 (64 bytes)

The VM handles:
  • Computing new head position from direction
  • Collision detection (walls, self)
  • Food consumption
  • Score tracking in registers

Python orchestrates the game loop and renders the display.
"""

from __future__ import annotations

import random
from flux.bytecode.opcodes import Op
from flux.vm.interpreter import Interpreter
from ._builder import BytecodeBuilder

_GRID = 8
_GRID_SIZE = _GRID * _GRID  # 64
_MEM_GRID = 1000
_STEPS = 20

# Direction deltas: 0=right, 1=down, 2=left, 3=up
_DIR_DR = [0, 1, 0, -1]
_DIR_DC = [1, 0, -1, 0]


class Snake:
    """Snake game with FLUX bytecode for movement and collision logic."""

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    # ── bytecode: one step of snake movement ────────────────────────────

    def build_step_bytecode(self) -> bytes:
        """Build bytecode for one movement step.

        Input registers:
            R0 = head row  (0-7)
            R1 = head col  (0-7)
            R2 = direction (0-3)
            R3 = food row  (0-7)
            R4 = food col  (0-7)
            R5 = score
            R6 = grid base address
            R7 = grid width (8)

        Output registers:
            R0 = new head row
            R1 = new head col
            R5 = updated score
            R8 = collision flag (0=ok, 1=collision)
            R9 = ate food flag (0=no, 1=yes)
        """
        b = BytecodeBuilder()

        # Initialise collision and ate flags
        b.movi(8, 0)    # collision = 0
        b.movi(9, 0)    # ate_food = 0

        # ── Compute new head position ──────────────────────────────────
        # direction deltas stored as i32 in memory at offset 600 / 620
        # delta_row: [+0, +1, +0, -1] at 600, 604, 608, 612
        # delta_col: [+1, +0, -1, +0] at 620, 624, 628, 632

        # new_row = head_row + delta_row[direction]
        b.movi(10, 600)          # R10 = base of delta_row
        b.movi(11, 4)            # R11 = 4
        b.imul(11, 2, 11)       # R11 = direction * 4
        b.iadd(10, 10, 11)      # R10 += direction * 4
        b.load(11, 10)          # R11 = delta_row[dir] (i32)
        b.iadd(0, 0, 11)         # R0 = head_row + delta_row

        # new_col = head_col + delta_col[direction]
        b.movi(10, 620)          # R10 = base of delta_col
        b.movi(11, 4)            # R11 = 4
        b.imul(11, 2, 11)       # R11 = direction * 4
        b.iadd(10, 10, 11)      # R10 += direction * 4
        b.load(11, 10)          # R11 = delta_col[dir] (i32)
        b.iadd(1, 1, 11)         # R1 = head_col + delta_col

        # ── Wall collision check ───────────────────────────────────────
        # if new_row < 0 or new_row >= 8 or new_col < 0 or new_col >= 8
        b.movi(10, 0)
        b.cmp(0, 10)
        b.jl("collision")         # new_row < 0

        b.movi(10, _GRID)
        b.cmp(0, 10)
        b.jge("collision")        # new_row >= 8

        b.movi(10, 0)
        b.cmp(1, 10)
        b.jl("collision")         # new_col < 0

        b.movi(10, _GRID)
        b.cmp(1, 10)
        b.jge("collision")        # new_col >= 8

        # ── Self-collision check ───────────────────────────────────────
        # Compute address of new head: grid_base + new_row * 8 + new_col
        b.mov(10, 6)              # R10 = grid base
        b.imul(11, 0, 7)          # R11 = new_row * 8  (R7 = width)
        b.iadd(10, 10, 11)        # R10 += new_row * 8
        b.iadd(10, 10, 1)         # R10 += new_col
        b.load8(11, 10)           # R11 = grid[new_head]

        # If grid cell == 1 (snake body) → collision
        b.movi(12, 1)
        b.cmp(11, 12)
        b.je("collision")

        # ── Food check ─────────────────────────────────────────────────
        # If new_head == food position
        b.cmp(0, 3)              # new_row == food_row?
        b.jne("no_food")
        b.cmp(1, 4)              # new_col == food_col?
        b.jne("no_food")

        # Ate food!
        b.movi(9, 1)             # ate_food = 1
        b.inc(5)                 # score++
        b.jmp("step_done")

        b.label("no_food")

        # ── Write new head to grid (mark as head=3) ────────────────────
        # R10 still has the grid address of new head
        b.movi(12, 3)
        b.store8(12, 10)         # grid[new_head] = 3 (head)

        b.jmp("step_done")

        b.label("collision")
        b.movi(8, 1)             # collision = 1

        b.label("step_done")
        b.halt()
        return b.build()

    def build_bytecode(self) -> bytes:
        """Alias for build_step_bytecode (one step at a time)."""
        return self.build_step_bytecode()

    # ── game loop ───────────────────────────────────────────────────────

    def run(self) -> dict:
        """Run the full snake game."""
        grid = bytearray(_GRID_SIZE)  # all empty

        # Place initial snake (3 cells) going right
        snake = [(3, 0), (3, 1), (3, 2)]
        for r, c in snake:
            grid[r * _GRID + c] = 1  # body
        grid[3 * _GRID + 2] = 3     # head

        # Place food
        food = self._place_food(grid)
        grid[food[0] * _GRID + food[1]] = 2

        head = snake[-1]
        direction = 0  # right

        bc = self.build_bytecode()
        log = []
        alive = True
        score = 0

        for step in range(_STEPS):
            vm = Interpreter(bc, memory_size=65536)
            stack = vm.memory.get_region("stack")

            # Write grid to memory
            stack.write(_MEM_GRID, bytes(grid))

            # Write direction deltas to memory (i32, 4 bytes each)
            import struct as _struct
            for i in range(4):
                stack.write_i32(600 + i * 4, _DIR_DR[i])
                stack.write_i32(620 + i * 4, _DIR_DC[i])

            # Set input registers
            vm.regs.write_gp(0, head[0])       # head row
            vm.regs.write_gp(1, head[1])       # head col
            vm.regs.write_gp(2, direction)     # direction
            vm.regs.write_gp(3, food[0])       # food row
            vm.regs.write_gp(4, food[1])       # food col
            vm.regs.write_gp(5, score)         # score
            vm.regs.write_gp(6, _MEM_GRID)     # grid base
            vm.regs.write_gp(7, _GRID)         # grid width

            vm.execute()

            new_row = vm.regs.read_gp(0)
            new_col = vm.regs.read_gp(1)
            score = vm.regs.read_gp(5)
            collision = vm.regs.read_gp(8)
            ate = vm.regs.read_gp(9)

            # Read updated grid
            grid_data = stack.read(_MEM_GRID, _GRID_SIZE)
            grid = bytearray(grid_data)

            log.append({
                "step": step,
                "head": (new_row, new_col),
                "direction": direction,
                "food": food,
                "score": score,
                "collision": collision,
                "ate_food": ate,
                "grid": [grid[i] for i in range(_GRID_SIZE)],
            })

            if collision:
                alive = False
                break

            # Update game state
            # Mark old head as body
            grid[head[0] * _GRID + head[1]] = 1

            if ate:
                food = self._place_food(grid)
                grid[food[0] * _GRID + food[1]] = 2
            else:
                # Remove tail
                tail = snake[0]
                grid[tail[0] * _GRID + tail[1]] = 0
                snake.pop(0)

            head = (new_row, new_col)
            snake.append(head)

            # Simple AI: change direction to move toward food
            direction = self._choose_direction(head, food, direction, grid)

        return {
            "log": log,
            "score": score,
            "alive": alive,
            "steps": len(log),
            "snake_length": len(snake) if alive else len(snake),
        }

    def _place_food(self, grid: bytearray) -> tuple[int, int]:
        empty = [(r, c) for r in range(_GRID) for c in range(_GRID)
                 if grid[r * _GRID + c] == 0]
        return self.rng.choice(empty) if empty else (0, 0)

    def _choose_direction(self, head: tuple, food: tuple,
                          current_dir: int, grid: bytearray) -> int:
        """Simple greedy AI: move toward food, avoid collisions."""
        hr, hc = head
        fr, fc = food

        # Preferred directions based on food position
        preferred = []
        if fr > hr: preferred.append(1)  # down
        if fr < hr: preferred.append(3)  # up
        if fc > hc: preferred.append(0)  # right
        if fc < hc: preferred.append(2)  # left

        for d in preferred:
            nr, nc = hr + _DIR_DR[d], hc + _DIR_DC[d]
            if 0 <= nr < _GRID and 0 <= nc < _GRID:
                if grid[nr * _GRID + nc] not in (1, 3):
                    return d

        # Try current direction
        nr, nc = hr + _DIR_DR[current_dir], hc + _DIR_DC[current_dir]
        if 0 <= nr < _GRID and 0 <= nc < _GRID:
            if grid[nr * _GRID + nc] not in (1, 3):
                return current_dir

        # Try any valid direction
        for d in range(4):
            nr, nc = hr + _DIR_DR[d], hc + _DIR_DC[d]
            if 0 <= nr < _GRID and 0 <= nc < _GRID:
                if grid[nr * _GRID + nc] not in (1, 3):
                    return d

        return current_dir  # no valid move

    # ── grid rendering ──────────────────────────────────────────────────

    @staticmethod
    def _render_grid(grid: list[int]) -> str:
        symbols = {0: "·", 1: "■", 2: "★", 3: "◉"}
        lines = []
        for r in range(8):
            row = ""
            for c in range(8):
                row += f" {symbols.get(grid[r * 8 + c], '?')}"
            lines.append(row)
        return "\n".join(lines)

    # ── demonstration ───────────────────────────────────────────────────

    @staticmethod
    def demonstrate():
        print("=" * 60)
        print("  FLUX RETRO — SNAKE")
        print("  Movement & collision computed in FLUX bytecode")
        print("=" * 60)

        game = Snake(seed=42)
        result = game.run()

        print(f"\n  Snake game: {result['steps']} steps, "
              f"score: {result['score']}")
        print(f"  Result: {'🎉 Survived!' if result['alive'] else '💀 Crashed!'}")
        print()

        # Show key frames
        log = result["log"]
        frames = [0] + list(range(4, len(log), 5)) + [len(log) - 1]
        frames = sorted(set(f for f in frames if f < len(log)))

        dir_names = {0: "→", 1: "↓", 2: "←", 3: "↑"}
        for fi in frames:
            entry = log[fi]
            step = entry["step"]
            head = entry["head"]
            direction = entry["direction"]
            score = entry["score"]
            collision = entry["collision"]
            ate = entry["ate_food"]

            status = ""
            if collision:
                status = "💥 COLLISION"
            elif ate:
                status = "🍎 ATE FOOD"
            else:
                status = ""

            print(f"  ── Step {step}  dir={dir_names.get(direction, '?')}  "
                  f"head=({head[0]},{head[1]})  score={score}  {status}")
            print("  " + Snake._render_grid(entry["grid"]))
            print()

        print(f"  Final score: {result['score']}")
        print()
