"""FLUX Bytecode — encoder, decoder, validator, and opcode definitions.

Provides:
- Op: bytecode opcode enum (IntEnum)
- BytecodeEncoder: encodes FIRModule → binary bytecode
- BytecodeDecoder: decodes binary bytecode → structured representation
- BytecodeValidator: validates bytecode structural integrity
"""

from .opcodes import Op, get_format, instruction_size
from .encoder import BytecodeEncoder
from .decoder import (
    BytecodeDecoder,
    DecodedInstruction,
    DecodedFunction,
    DecodedModule,
    DecodedType,
)
from .validator import BytecodeValidator

__all__ = [
    # Opcodes
    "Op",
    "get_format",
    "instruction_size",
    # Encoder
    "BytecodeEncoder",
    # Decoder
    "BytecodeDecoder",
    "DecodedInstruction",
    "DecodedFunction",
    "DecodedModule",
    "DecodedType",
    # Validator
    "BytecodeValidator",
]
