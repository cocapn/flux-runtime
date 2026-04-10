"""FLUX Retro Implementations — Working bytecode for iconic games.

Each game is implemented as a self-contained Python module that:
1. Generates FLUX bytecode
2. Runs it on the VM
3. Provides an interactive/steppable execution mode
4. Records metrics to the research framework
"""

# Lazy imports — only import games that exist
_HAS = {}

try:
    from .game_of_life import GameOfLife
    _HAS["GameOfLife"] = True
except ImportError:
    pass

try:
    from .snake import Snake
    _HAS["Snake"] = True
except ImportError:
    pass

try:
    from .mastermind import Mastermind
    _HAS["Mastermind"] = True
except ImportError:
    pass

try:
    from .tic_tac_toe import TicTacToeAI
    _HAS["TicTacToeAI"] = True
except ImportError:
    pass

try:
    from .lunar_lander import LunarLander
    _HAS["LunarLander"] = True
except ImportError:
    pass

__all__ = [name for name, present in _HAS.items() if present]
