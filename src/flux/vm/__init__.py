"""FLUX Micro-VM — bytecode interpreter for the FLUX runtime system.

This module implements the execution engine that runs compiled FLUX bytecode
directly on raw bytes. It provides:

- **RegisterFile**: 64-register file (R0-R15 general, F0-F15 float, V0-V15 vector)
- **MemoryManager**: Linear region-based memory with ownership semantics
- **Interpreter**: Fetch-decode-execute loop with cycle budget
- **VM Errors**: Typed exception hierarchy for debugging
"""

from .registers import RegisterFile
from .memory import MemoryRegion, MemoryManager
from .interpreter import (
    VMError,
    VMHaltError,
    VMStackOverflowError,
    VMInvalidOpcodeError,
    VMDivisionByZeroError,
    Interpreter,
)

__all__ = [
    # Registers
    "RegisterFile",
    # Memory
    "MemoryRegion",
    "MemoryManager",
    # Interpreter
    "Interpreter",
    # Errors
    "VMError",
    "VMHaltError",
    "VMStackOverflowError",
    "VMInvalidOpcodeError",
    "VMDivisionByZeroError",
]
