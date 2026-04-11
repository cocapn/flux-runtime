"""
FORMAT_A through FORMAT_G — Instruction Encoding Reference

This is the definitive reference for FLUX instruction encoding formats.
JetsonClaw1 ports this to C. All implementations must match exactly.

Format A: 1 byte  — [op]                    HALT, NOP
Format B: 2 bytes — [op][rd]                INC, DEC, PUSH, POP
Format C: 2 bytes — [op][imm8]              Small immediates
Format D: 3 bytes — [op][rd][imm8]          MOVI rd, 8-bit literal
Format E: 4 bytes — [op][rd][rs1][rs2]      3-register arithmetic
Format F: 4 bytes — [op][rd][imm16hi][imm16lo]  MOVI rd, 16-bit literal
Format G: 5 bytes — [op][rd][rs1][imm16hi][imm16lo] Load/store with offset

Confidence-aware variants (CONF_* opcodes) use same format as base but
opcode bit 6 is set (0x40 range). They write confidence to a parallel
register file indexed by rd.
"""

from enum import IntEnum
from dataclasses import dataclass
from typing import List, Tuple, Optional
import struct


class Format(IntEnum):
    A = 1   # 1 byte
    B = 2   # 2 bytes
    C = 3   # 2 bytes (same width as B, different semantics)
    D = 4   # 3 bytes
    E = 5   # 4 bytes
    F = 6   # 4 bytes (same width as E, different semantics)
    G = 7   # 5 bytes


class TypeField(IntEnum):
    SCALAR_INT = 0b00
    SCALAR_FLOAT = 0b01
    VECTOR_INT = 0b10
    VECTOR_FLOAT = 0b11


# Unified opcode space
class Opcode(IntEnum):
    # Format A (1 byte) — System
    HALT = 0x00
    NOP = 0x01
    RET = 0x02
    IRET = 0x03       # Interrupt return
    
    # Format B (2 bytes) — Single register
    INC = 0x08        # rd = rd + 1
    DEC = 0x09        # rd = rd - 1
    NOT = 0x0A        # rd = ~rd
    NEG = 0x0B        # rd = -rd
    PUSH = 0x0C       # push rd
    POP = 0x0D        # pop rd
    CONF_LOAD = 0x0E  # Load confidence from register
    CONF_STORE = 0x0F # Store confidence to register
    
    # Format C (2 bytes) — Immediate only
    SYS = 0x10        # System call with imm8 code
    STRIPCONF = 0x17  # Strip confidence from next N ops (JetsonClaw1's request)
    
    # Format D (3 bytes) — Register + 8-bit immediate
    MOVI = 0x18       # rd = imm8 (sign-extended)
    ADDI = 0x19       # rd = rd + imm8
    SUBI = 0x1A       # rd = rd - imm8
    ANDI = 0x1B       # rd = rd & imm8
    ORI = 0x1C        # rd = rd | imm8
    XORI = 0x1D       # rd = rd ^ imm8
    SHLI = 0x1E       # rd = rd << imm8
    SHRI = 0x1F       # rd = rd >> imm8
    
    # Format E (4 bytes) — 3-register arithmetic
    ADD = 0x20        # rd = rs1 + rs2
    SUB = 0x21        # rd = rs1 - rs2
    MUL = 0x22        # rd = rs1 * rs2
    DIV = 0x23        # rd = rs1 / rs2
    MOD = 0x24        # rd = rs1 % rs2
    AND = 0x25        # rd = rs1 & rs2
    OR = 0x26         # rd = rs1 | rs2
    XOR = 0x27        # rd = rs1 ^ rs2
    SHL = 0x28        # rd = rs1 << rs2
    SHR = 0x29        # rd = rs1 >> rs2
    MIN = 0x2A        # rd = min(rs1, rs2)
    MAX = 0x2B        # rd = max(rs1, rs2)
    CMP_EQ = 0x2C     # rd = (rs1 == rs2) ? 1 : 0
    CMP_LT = 0x2D     # rd = (rs1 < rs2) ? 1 : 0
    CMP_GT = 0x2E     # rd = (rs1 > rs2) ? 1 : 0
    CMP_NE = 0x2F     # rd = (rs1 != rs2) ? 1 : 0
    
    # Format E (4 bytes) — Float arithmetic
    FADD = 0x30       # rd = f(rs1) + f(rs2)
    FSUB = 0x31       # rd = f(rs1) - f(rs2)
    FMUL = 0x32       # rd = f(rs1) * f(rs2)
    FDIV = 0x33       # rd = f(rs1) / f(rs2)
    FMIN = 0x34       # rd = fmin(rs1, rs2)
    FMAX = 0x35       # rd = fmax(rs1, rs2)
    FTOI = 0x36       # rd = int(rs1)
    ITOF = 0x37       # rd = float(rs1)
    
    # Format E (4 bytes) — Memory
    LOAD = 0x38       # rd = mem[rs1 + rs2]
    STORE = 0x39      # mem[rs1 + rs2] = rd
    MOV = 0x3A        # rd = rs1 (rs2 ignored)
    SWP = 0x3B        # swap(rd, rs1)
    
    # Format E (4 bytes) — Control flow
    JZ = 0x3C         # if rd == 0: pc += rs1 (rs2 = offset high)
    JNZ = 0x3D        # if rd != 0: pc += rs1
    JLT = 0x3E        # if rd < 0: pc += rs1
    JGT = 0x3F        # if rd > 0: pc += rs1
    
    # Format F (4 bytes) — Register + 16-bit immediate
    MOVI16 = 0x40     # rd = imm16
    ADDI16 = 0x41     # rd = rd + imm16
    SUBI16 = 0x42     # rd = rd - imm16
    JMP = 0x43        # pc += imm16 (relative jump)
    JAL = 0x44        # rd = pc; pc += imm16 (jump and link)
    
    # Format G (5 bytes) — Register + register + 16-bit offset
    LOADOFF = 0x48    # rd = mem[rs1 + imm16]
    STOREOFF = 0x49   # mem[rs1 + imm16] = rd
    LOADI = 0x4A      # Load immediate from address
    
    # Confidence-aware variants (same formats, bit 6 set)
    CONF_ADD = 0x60   # Format E: rd, crd = rs1 + rs2, min(crs1, crs2)
    CONF_SUB = 0x61
    CONF_MUL = 0x62
    CONF_DIV = 0x63
    CONF_FADD = 0x64
    CONF_FSUB = 0x65
    CONF_FMUL = 0x66
    CONF_FDIV = 0x67
    CONF_MERGE = 0x68  # Format E: crd = merge strategy(crs1, crs2)
    CONF_THRESHOLD = 0x69  # Format D: if crd < imm8: skip next


# Opcode → Format mapping
OPCODE_FORMAT = {}
for name, val in Opcode.__members__.items():
    op = int(val)
    if op <= 0x03:
        OPCODE_FORMAT[op] = Format.A
    elif op <= 0x0F:
        OPCODE_FORMAT[op] = Format.B
    elif op <= 0x17:
        OPCODE_FORMAT[op] = Format.C
    elif op <= 0x1F:
        OPCODE_FORMAT[op] = Format.D
    elif op <= 0x3F:
        OPCODE_FORMAT[op] = Format.E
    elif op <= 0x47:
        OPCODE_FORMAT[op] = Format.F
    elif op <= 0x4F:
        OPCODE_FORMAT[op] = Format.G
    elif op <= 0x6F:
        OPCODE_FORMAT[op] = Format.E  # CONF_ variants use Format E
    else:
        OPCODE_FORMAT[op] = Format.A


def encode_format_a(opcode: int) -> bytes:
    """Encode Format A: [op] — 1 byte"""
    return bytes([opcode & 0xFF])


def encode_format_b(opcode: int, rd: int) -> bytes:
    """Encode Format B: [op][rd] — 2 bytes"""
    return bytes([opcode & 0xFF, rd & 0xFF])


def encode_format_c(opcode: int, imm8: int) -> bytes:
    """Encode Format C: [op][imm8] — 2 bytes"""
    return bytes([opcode & 0xFF, imm8 & 0xFF])


def encode_format_d(opcode: int, rd: int, imm8: int) -> bytes:
    """Encode Format D: [op][rd][imm8] — 3 bytes"""
    return bytes([opcode & 0xFF, rd & 0xFF, imm8 & 0xFF])


def encode_format_e(opcode: int, rd: int, rs1: int, rs2: int) -> bytes:
    """Encode Format E: [op][rd][rs1][rs2] — 4 bytes"""
    return bytes([opcode & 0xFF, rd & 0xFF, rs1 & 0xFF, rs2 & 0xFF])


def encode_format_f(opcode: int, rd: int, imm16: int) -> bytes:
    """Encode Format F: [op][rd][imm16hi][imm16lo] — 4 bytes"""
    imm16 = imm16 & 0xFFFF
    return bytes([opcode & 0xFF, rd & 0xFF, (imm16 >> 8) & 0xFF, imm16 & 0xFF])


def encode_format_g(opcode: int, rd: int, rs1: int, imm16: int) -> bytes:
    """Encode Format G: [op][rd][rs1][imm16hi][imm16lo] — 5 bytes"""
    imm16 = imm16 & 0xFFFF
    return bytes([opcode & 0xFF, rd & 0xFF, rs1 & 0xFF, (imm16 >> 8) & 0xFF, imm16 & 0xFF])


def decode_instruction(data: bytes) -> Tuple[int, dict]:
    """Decode an instruction from bytes. Returns (opcode, fields)."""
    if not data:
        raise ValueError("Empty data")
    
    opcode = data[0]
    
    # Dispatch by opcode range (not format enum, since B and C overlap)
    if opcode <= 0x03:  # Format A
        return opcode, {"format": "A", "size": 1}
    elif opcode <= 0x0F:  # Format B
        return opcode, {"format": "B", "size": 2, "rd": data[1] if len(data) > 1 else 0}
    elif opcode <= 0x17:  # Format C
        return opcode, {"format": "C", "size": 2, "imm8": data[1] if len(data) > 1 else 0}
    elif opcode <= 0x1F:  # Format D
        return opcode, {"format": "D", "size": 3, "rd": data[1] if len(data) > 1 else 0,
                        "imm8": data[2] if len(data) > 2 else 0}
    elif opcode <= 0x3F:  # Format E
        return opcode, {"format": "E", "size": 4, "rd": data[1] if len(data) > 1 else 0,
                        "rs1": data[2] if len(data) > 2 else 0, "rs2": data[3] if len(data) > 3 else 0}
    elif opcode <= 0x47:  # Format F
        imm16 = ((data[2] if len(data) > 2 else 0) << 8) | (data[3] if len(data) > 3 else 0)
        return opcode, {"format": "F", "size": 4, "rd": data[1] if len(data) > 1 else 0, "imm16": imm16}
    elif opcode <= 0x4F:  # Format G
        imm16 = ((data[3] if len(data) > 3 else 0) << 8) | (data[4] if len(data) > 4 else 0)
        return opcode, {"format": "G", "size": 5, "rd": data[1] if len(data) > 1 else 0,
                        "rs1": data[2] if len(data) > 2 else 0, "imm16": imm16}
    elif opcode <= 0x6F:  # CONF_ variants (Format E)
        return opcode, {"format": "E", "size": 4, "rd": data[1] if len(data) > 1 else 0,
                        "rs1": data[2] if len(data) > 2 else 0, "rs2": data[3] if len(data) > 3 else 0}
    else:
        return opcode, {"format": "unknown", "size": 1}


def opcode_table() -> List[dict]:
    """Generate the complete opcode reference table."""
    table = []
    for name, val in sorted(Opcode.__members__.items(), key=lambda x: int(x[1])):
        op = int(val)
        fmt = OPCODE_FORMAT.get(op, Format.A)
        is_conf = bool(op & 0x40) and op >= 0x60
        table.append({
            "hex": f"0x{op:02X}",
            "name": name,
            "format": fmt.name,
            "size": int(fmt),
            "confidence": is_conf,
        })
    return table
