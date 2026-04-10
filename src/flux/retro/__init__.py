"""FLUX Retro — Reverse-engineering 10 iconic games and software into FLUX bytecode.

This module provides the implementation framework and catalog for systematically
re-engineering classic software into FLUX's bytecode VM, with full scientific
tracking (seeds, metrics, reflections) for ML-driven iterative improvement.

The 10 targets span different computational paradigms to stress-test FLUX:

    #  Target                     Category         Key FLUX Features Exercised
    1  Conway's Game of Life      Cellular Automaton Grid ops, SIMD patterns, neighbor counting
    2  Pong                       Real-time Game    Ball physics, paddle input, collision
    3  Snake                      Grid Game         State machine, collision, growing
    4  Tetris                     Puzzle Game       Rotation matrices, line clearing
    5  Text Adventure (Zork)      Interactive       Parser, room graph, inventory, A2A
    6  Mandelbrot Set             Math/Rendering   Float ops, escape iteration, pixel output
    7  Mastermind                 Logic/Puzzle      Comparison ops, deduction feedback
    8  Lunar Lander               Physics Sim       Continuous simulation, fuel mgmt
    9  Tic-Tac-Toe AI             Search/AI         Minimax, recursive evaluation
   10  Markov Chain Text          NLP/Probabilistic Memory patterns, probability tables

Usage:
    from flux.retro import GameCatalog
    catalog = GameCatalog()
    for game in catalog.all():
        print(f"{game.rank}. {game.name} — {game.category}")
"""

from .catalog import GameCatalog, GameSpec

__all__ = ["GameCatalog", "GameSpec"]
