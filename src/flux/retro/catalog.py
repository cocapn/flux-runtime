"""Game Catalog — specifications for all 10 reverse-engineering targets."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GameSpec:
    """Specification for a single reverse-engineering target."""

    rank: int
    name: str
    year: int
    original_platform: str
    original_language: str
    category: str
    complexity: str  # "simple", "medium", "complex"
    description: str
    core_mechanics: list[str]
    flux_features: list[str]  # FLUX subsystems this exercises
    approximate_bytecode_budget: int  # rough estimate in bytes
    approximate_cycle_budget: int  # rough estimate in cycles per frame/tick
    original_lines_of_code: int  # approximate original implementation size
    key_algorithms: list[str]
    open_challenges: list[str]  # research questions to explore

    @property
    def slug(self) -> str:
        return self.name.lower().replace(" ", "_").replace("(", "").replace(")", "")


GAMES: list[GameSpec] = [
    GameSpec(
        rank=1,
        name="Game of Life",
        year=1970,
        original_platform="Mathematics",
        original_language="Mathematical notation",
        category="Cellular Automaton",
        complexity="simple",
        description=(
            "John Conway's cellular automaton: a grid of cells where each cell "
            "lives or dies based on the number of living neighbors. Demonstrates "
            "emergent complexity from simple rules — perfect for testing FLUX's "
            "grid computation patterns and SIMD-like parallel operations."
        ),
        core_mechanics=[
            "Grid state (NxN boolean array)",
            "Neighbor counting (8-connectivity)",
            "Birth rule: dead cell with exactly 3 neighbors becomes alive",
            "Survival rule: live cell with 2-3 neighbors stays alive",
            "All other cells die or stay dead",
            "Generation stepping",
        ],
        flux_features=["memory regions", "arithmetic ops", "comparison ops", "loop patterns"],
        approximate_bytecode_budget=512,
        approximate_cycle_budget=10000,
        original_lines_of_code=20,
        key_algorithms=["Moore neighborhood", "Double buffering", "Boundary conditions"],
        open_challenges=[
            "Can we represent the grid as a FLUX memory region for zero-copy access?",
            "How to efficiently count 8 neighbors with only 16 GP registers?",
            "What's the minimum cycle count per generation for a 32x32 grid?",
            "Can the tile system compose reusable 'cell update' tiles?",
        ],
    ),
    GameSpec(
        rank=2,
        name="Pong",
        year=1972,
        original_platform="Arcade",
        original_language="Assembly",
        category="Real-time Game",
        complexity="medium",
        description=(
            "Atari's Pong: two paddles, one ball, simple physics. The original "
            "arcade hit that launched the video game industry. Perfect for testing "
            "FLUX's ability to handle real-time input, physics simulation, and "
            "collision detection in bytecode."
        ),
        core_mechanics=[
            "Ball position (x, y) and velocity (vx, vy)",
            "Paddle positions (left, right)",
            "Ball-wall collision (top/bottom bounce)",
            "Ball-paddle collision (angle reflection based on hit position)",
            "Score tracking",
            "Game state machine (serving, playing, scoring)",
        ],
        flux_features=["float ops", "comparison ops", "control flow", "memory regions", "IO"],
        approximate_bytecode_budget=1024,
        approximate_cycle_budget=5000,
        original_lines_of_code=200,
        key_algorithms=[
            "Ball reflection physics",
            "Collision detection (AABB)",
            "Frame timing",
            "Angle calculation from hit position",
        ],
        open_challenges=[
            "FLUX uses integer registers — how to simulate floating-point ball physics?",
            "Fixed-point arithmetic: what precision is optimal for Pong?",
            "Can we use memory regions as a framebuffer for ball rendering?",
            "What's the minimum cycles per frame for playable responsiveness?",
        ],
    ),
    GameSpec(
        rank=3,
        name="Snake",
        year=1976,
        original_platform="Arcade / Nokia",
        original_language="C",
        category="Grid Game",
        complexity="simple",
        description=(
            "The classic snake game: a growing snake moves on a grid, eating food "
            "to grow longer while avoiding walls and itself. Tests FLUX's state "
            "management, queue operations, and collision detection."
        ),
        core_mechanics=[
            "Snake body as a queue of grid positions",
            "Direction input (up/down/left/right)",
            "Food spawning at random empty positions",
            "Collision detection (wall, self)",
            "Growth on eating food",
            "Score = food eaten",
        ],
        flux_features=["memory regions", "arithmetic", "comparison", "control flow", "stack ops"],
        approximate_bytecode_budget=768,
        approximate_cycle_budget=3000,
        original_lines_of_code=150,
        key_algorithms=[
            "Queue management (circular buffer)",
            "Random food placement",
            "Grid collision detection",
            "Direction buffering (prevent 180° turns)",
        ],
        open_challenges=[
            "How to implement a queue in FLUX bytecode with only stack operations?",
            "Circular buffer in a memory region — what addressing mode works best?",
            "Can we use ENTER/LEAVE for snake segment allocation?",
            "What's the optimal grid size for FLUX's memory constraints?",
        ],
    ),
    GameSpec(
        rank=4,
        name="Tetris",
        year=1984,
        original_platform="Electronika 60 / NES",
        original_language="Assembly / C",
        category="Puzzle Game",
        complexity="complex",
        description=(
            "Alexey Pajitnov's Tetris: seven tetromino shapes fall, player rotates "
            "and places them to complete lines. Tests FLUX's ability to handle "
            "rotation matrices, complex state machines, and real-time rendering."
        ),
        core_mechanics=[
            "7 tetromino shapes (I, O, T, S, Z, J, L)",
            "Piece rotation (90° clockwise/counterclockwise)",
            "Line clearing (1-4 lines at once)",
            "Scoring (more lines = more points)",
            "Level progression (increasing speed)",
            "Next piece preview",
            "Wall kicks on rotation",
            "Game over detection",
        ],
        flux_features=["arithmetic", "comparison", "memory regions", "control flow", "bitwise"],
        approximate_bytecode_budget=2048,
        approximate_cycle_budget=15000,
        original_lines_of_code=500,
        key_algorithms=[
            "Rotation matrices",
            "Collision detection for all 7 piece orientations",
            "Line clearing with row compaction",
            "Random bag generator (7-bag randomizer)",
        ],
        open_challenges=[
            "Rotation matrices with integer arithmetic — can ISHL/ISHR approximate rotation?",
            "How to represent the 10x20 playfield efficiently in memory regions?",
            "Can the tile system compose 'piece rotation' tiles with 'collision check' tiles?",
            "What's the minimum bytecode for all 7 piece shapes plus rotations?",
        ],
    ),
    GameSpec(
        rank=5,
        name="Text Adventure",
        year=1977,
        original_platform="PDP-10 / Home computers",
        original_language="MDL / Fortran",
        category="Interactive Fiction",
        complexity="medium",
        description=(
            "Will Crowther & Don Woods' Colossal Cave Adventure: a text-based "
            "dungeon exploration game with rooms, objects, and a parser. Perfect "
            "for testing FLUX's A2A protocol — rooms as agents, objects as "
            "messages, and the parser as an A2A dispatcher."
        ),
        core_mechanics=[
            "Room graph (connections between locations)",
            "Player inventory",
            "Object placement (in rooms or inventory)",
            "Text parser (verb + noun)",
            "Game state (locked doors, puzzles solved)",
            "Win/lose conditions",
        ],
        flux_features=["A2A protocol", "memory regions", "comparison", "control flow", "string ops"],
        approximate_bytecode_budget=2048,
        approximate_cycle_budget=2000,
        original_lines_of_code=800,
        key_algorithms=[
            "Graph traversal (room connections)",
            "Pattern matching (text parser)",
            "State machine (game progression)",
            "Object ownership tracking",
        ],
        open_challenges=[
            "Can rooms be modeled as A2A agents that TELL each other about player movement?",
            "How to implement string matching in FLUX bytecode without native string ops?",
            "Can the parser use IO_WRITE for output and IO_READ for input?",
            "What's the minimum memory region layout for 20+ rooms with connections?",
        ],
    ),
    GameSpec(
        rank=6,
        name="Mandelbrot Set",
        year=1980,
        original_platform="Mathematics / Research",
        original_language="Fortran / C",
        category="Mathematical Visualization",
        complexity="medium",
        description=(
            "Benoit Mandelbrot's fractal: iterate z = z² + c for each point in "
            "the complex plane and color based on escape iteration. Tests FLUX's "
            "floating-point capabilities and iterative computation patterns."
        ),
        core_mechanics=[
            "Complex plane coordinates (real, imaginary)",
            "Iteration: z_new = z_real² - z_imag² + c_real, 2*z_real*z_imag + c_imag",
            "Escape detection (|z| > 2)",
            "Color mapping (iteration count → grayscale/color)",
            "Viewport transformation (screen coords → complex plane)",
            "Zoom levels",
        ],
        flux_features=["float ops", "comparison", "arithmetic", "memory regions"],
        approximate_bytecode_budget=1024,
        approximate_cycle_budget=500000,
        original_lines_of_code=50,
        key_algorithms=[
            "Escape time algorithm",
            "Complex multiplication",
            "Viewport mapping",
            "Color palette generation",
        ],
        open_challenges=[
            "FLUX has FP registers but limited FP opcodes — how to implement z² + c efficiently?",
            "Can we use fixed-point (int*256) as a faster alternative to FP?",
            "What's the minimum resolution for a recognizable Mandelbrot rendering?",
            "Can memory regions serve as a pixel buffer for output?",
        ],
    ),
    GameSpec(
        rank=7,
        name="Mastermind",
        year=1970,
        original_platform="Board game / Electronic",
        original_language="Logic",
        category="Logic Puzzle",
        complexity="simple",
        description=(
            "Mordecai Meirowitz's Mastermind: guess a 4-color code with feedback "
            "on correct position (black pegs) and correct color wrong position "
            "(white pegs). Tests FLUX's comparison and bitwise operations."
        ),
        core_mechanics=[
            "Secret code (4 positions, 6 colors)",
            "Guess input (4 positions)",
            "Black pegs: correct color AND position",
            "White pegs: correct color, wrong position",
            "Max 10 guesses",
            "Win detection (4 black pegs)",
            "AI codebreaker (optional: minimax algorithm)",
        ],
        flux_features=["comparison", "bitwise", "arithmetic", "control flow"],
        approximate_bytecode_budget=512,
        approximate_cycle_budget=1000,
        original_lines_of_code=100,
        key_algorithms=[
            "Multiset intersection for black pegs",
            "Set difference for white pegs",
            "Minimax for optimal AI guesses",
            "Knuth's five-guess algorithm",
        ],
        open_challenges=[
            "Can bitwise AND/XOR patterns efficiently compute black/white pegs?",
            "How to represent 6 colors × 4 positions as a compact FLUX register value?",
            "Can we use SIMD registers for parallel comparison of all positions?",
            "What's the optimal AI strategy expressible in FLUX bytecode?",
        ],
    ),
    GameSpec(
        rank=8,
        name="Lunar Lander",
        year=1979,
        original_platform="Arcade / Text",
        original_language="Assembly / Fortran",
        category="Physics Simulation",
        complexity="medium",
        description=(
            "Atari's Lunar Lander: pilot a lander to the moon's surface, "
            "managing thrust and fuel to achieve a soft landing. Tests FLUX's "
            "ability to simulate continuous physics with discrete bytecode."
        ),
        core_mechanics=[
            "Altitude, velocity, fuel, thrust",
            "Gravity (constant downward acceleration)",
            "Thrust (burns fuel, applies upward force)",
            "Safe landing criteria (velocity < threshold)",
            "Crash detection (velocity too high at touchdown)",
            "Fuel management (empty = no thrust)",
        ],
        flux_features=["arithmetic", "comparison", "control flow", "memory regions"],
        approximate_bytecode_budget=768,
        approximate_cycle_budget=50000,
        original_lines_of_code=200,
        key_algorithms=[
            "Euler integration (position += velocity * dt)",
            "Velocity clamping",
            "Landing score calculation",
            "Fuel burn rate simulation",
        ],
        open_challenges=[
            "How to implement Euler integration with fixed-point arithmetic in FLUX?",
            "Can ENTER/LEAVE frame management help with physics state stacking?",
            "What frame rate (cycles per tick) gives smooth enough physics?",
            "Can we use the adaptive profiler to detect 'landing approach' hot paths?",
        ],
    ),
    GameSpec(
        rank=9,
        name="Tic-Tac-Toe AI",
        year=1952,
        original_platform="EDSAC / Paper",
        original_language="Assembly / Mathematical",
        category="Search/AI",
        complexity="simple",
        description=(
            "Oxo (1952) / Tic-tac-toe with perfect AI: the minimax algorithm "
            "plays perfectly. Tests FLUX's recursive call/return mechanism, "
            "stack depth management, and evaluation functions."
        ),
        core_mechanics=[
            "3x3 board (9 cells, each X/O/empty)",
            "Win detection (rows, columns, diagonals)",
            "Draw detection (board full, no winner)",
            "Minimax algorithm (recursive, depth-first)",
            "Alpha-beta pruning (optimization)",
            "Move ordering (center > corners > edges)",
        ],
        flux_features=["control flow", "CALL/RET", "comparison", "memory regions", "stack"],
        approximate_bytecode_budget=1024,
        approximate_cycle_budget=10000,
        original_lines_of_code=150,
        key_algorithms=[
            "Minimax with alpha-beta pruning",
            "Board evaluation heuristic",
            "Win detection (8 lines)",
            "Move generation",
        ],
        open_challenges=[
            "FLUX has a 4096-byte stack — can minimax recurse deep enough for 9-ply search?",
            "How many cycles does a full game tree evaluation take?",
            "Can CALL/RET + stack operations implement recursive minimax efficiently?",
            "What's the optimal board encoding for FLUX registers (bitboard vs array)?",
        ],
    ),
    GameSpec(
        rank=10,
        name="Markov Chain Text",
        year=1913,
        original_platform="Mathematics",
        original_language="Mathematical notation",
        category="Probabilistic Generation",
        complexity="medium",
        description=(
            "Andrey Markov's chain: generate text by probabilistically choosing "
            "the next word based on the current state (previous N words). Tests "
            "FLUX's memory management, probability tables, and state machine design."
        ),
        core_mechanics=[
            "N-gram model (bigrams or trigrams)",
            "Training: count word transitions from source text",
            "Generation: pick next word probabilistically based on current state",
            "Probability tables (stored in memory regions)",
            "Start/end tokens for sentence boundaries",
            "Seed selection for reproducibility",
        ],
        flux_features=["memory regions", "arithmetic", "comparison", "control flow", "random"],
        approximate_bytecode_budget=1536,
        approximate_cycle_budget=50000,
        original_lines_of_code=200,
        key_algorithms=[
            "N-gram frequency counting",
            "Cumulative distribution for sampling",
            "Linear search for probability bin",
            "Pseudo-random number generation",
        ],
        open_challenges=[
            "Can memory regions store a usable probability table for bigrams?",
            "How to implement pseudo-random number generation in FLUX bytecode?",
            "What's the minimum vocabulary size for coherent generated text?",
            "Can IO_READ/IO_WRITE handle word-by-word generation interactively?",
        ],
    ),
]


class GameCatalog:
    """Catalog of all 10 reverse-engineering targets with lookup methods."""

    def __init__(self) -> None:
        self._games = {g.slug: g for g in GAMES}

    def all(self) -> list[GameSpec]:
        return list(GAMES)

    def get(self, slug: str) -> GameSpec | None:
        return self._games.get(slug.lower().replace(" ", "_"))

    def by_complexity(self, complexity: str) -> list[GameSpec]:
        return [g for g in GAMES if g.complexity == complexity]

    def by_category(self, category: str) -> list[GameSpec]:
        return [g for g in GAMES if g.category == category]

    def __len__(self) -> int:
        return len(GAMES)

    def summary_table(self) -> str:
        """Format a readable summary table."""
        lines = [
            f"{'#':>2}  {'Name':<24}  {'Year':>4}  {'Complexity':<10}  {'Bytecode Est':>12}  {'Cycles Est':>10}",
            f"{'─'*2}  {'─'*24}  {'─'*4}  {'─'*10}  {'─'*12}  {'─'*10}",
        ]
        for g in GAMES:
            lines.append(
                f"{g.rank:>2}  {g.name:<24}  {g.year:>4}  {g.complexity:<10}  "
                f"{g.approximate_bytecode_budget:>10}B  {g.approximate_cycle_budget:>10,}"
            )
        return "\n".join(lines)
