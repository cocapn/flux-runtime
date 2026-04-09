"""Bytecode Encoder — encodes FIRModule into FLUX binary bytecode format.

Binary layout:
  [Header 16B][Type Table][Name Pool][Function Table][Code Section]

Header (16 bytes):
  magic:    b'FLUX'         (4 bytes)
  version:  uint16 LE        (2 bytes)  — always 1
  flags:    uint16 LE        (2 bytes)  — reserved, 0
  n_funcs:  uint16 LE        (2 bytes)  — number of functions
  type_off: uint32 LE        (4 bytes)  — byte offset to type table
  code_off: uint32 LE        (4 bytes)  — byte offset to code section

Instruction encoding (variable length, little-endian):
  Format A (1B):  [opcode]
  Format B (2B):  [opcode][rd:u8]
  Format C (3B):  [opcode][rd:u8][rs1:u8]
  Format D (4B):  [opcode][rs1:u8][imm16:i16]
  Format E (5B):  [opcode][rd:u8][rs1:u8][rs2:u8]
  Format G (var): [opcode][len:u16][data:len bytes]
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

from .opcodes import Op

if TYPE_CHECKING:
    from ..fir.blocks import FIRModule, FIRFunction
    from ..fir.instructions import Instruction
    from ..fir.types import TypeContext, FIRType

# ── Constants ────────────────────────────────────────────────────────────────

MAGIC = b"FLUX"
VERSION = 1
HEADER_SIZE = 18  # 4s(4) + H(2) + H(2) + H(2) + I(4) + I(4) = 18

# Type kind tags for the type table
TK_INT = 0x01
TK_FLOAT = 0x02
TK_BOOL = 0x03
TK_UNIT = 0x04
TK_STRING = 0x05
TK_REF = 0x06
TK_ARRAY = 0x07
TK_VECTOR = 0x08
TK_FUNC = 0x09
TK_STRUCT = 0x0A
TK_ENUM = 0x0B
TK_REGION = 0x0C
TK_CAPABILITY = 0x0D
TK_AGENT = 0x0E
TK_TRUST = 0x0F

# FIR opcode → bytecode Op mappings

# Binary arithmetic (Format C: [op][rs1:u8][rs2:u8])
_BIN_ARITH = {
    "iadd": Op.IADD, "isub": Op.ISUB, "imul": Op.IMUL,
    "idiv": Op.IDIV, "imod": Op.IMOD,
    "iand": Op.IAND, "ior": Op.IOR, "ixor": Op.IXOR,
    "ishl": Op.ISHL, "ishr": Op.ISHR,
    "fadd": Op.FADD, "fsub": Op.FSUB, "fmul": Op.FMUL, "fdiv": Op.FDIV,
}

# Comparison (Format C: [op][rs1:u8][rs2:u8])
_BIN_CMP = {
    "ieq": Op.IEQ, "ilt": Op.ILT, "igt": Op.IGT, "ile": Op.ILE, "ige": Op.IGE,
    "feq": Op.FEQ, "flt": Op.FLT, "fgt": Op.FGT, "fle": Op.FLE, "fge": Op.FGE,
}

# Unary ops that are Format A by spec but we extend to Format B: [op][src:u8]
_UNARY = {"ineg": Op.INEG, "fneg": Op.FNEG, "inot": Op.INOT}

# Conversion ops → CAST
_CONV = {"itrunc": Op.CAST, "zext": Op.CAST, "sext": Op.CAST,
         "ftrunc": Op.CAST, "fext": Op.CAST, "bitcast": Op.CAST}


# ── Encoder ──────────────────────────────────────────────────────────────────

class BytecodeEncoder:
    """Encodes a FIRModule into FLUX bytecode bytes."""

    def encode(self, module: "FIRModule") -> bytes:
        """Encode a FIRModule to FLUX bytecode bytes."""
        # ── 1. Build name pool (null-terminated UTF-8 strings) ────────────
        name_pool = bytearray()
        name_offsets: dict[str, int] = {}
        for func_name in module.functions:
            name_offsets[func_name] = len(name_pool)
            name_pool.extend(func_name.encode("utf-8"))
            name_pool.append(0x00)

        # ── 2. Encode type table ─────────────────────────────────────────
        type_table = self._encode_type_table(module.type_ctx)

        # ── 3. Encode all function code ──────────────────────────────────
        func_entries: list[tuple[str, int, int]] = []  # (name, entry_off, code_size)
        code_section = bytearray()

        for func_name, func in module.functions.items():
            entry_off = len(code_section)
            func_code = self._encode_function(func)
            code_section.extend(func_code)
            func_entries.append((func_name, entry_off, len(func_code)))

        # ── 4. Compute section offsets ───────────────────────────────────
        type_off = HEADER_SIZE
        func_table_off = type_off + len(type_table) + len(name_pool)
        code_off = func_table_off + len(func_entries) * 12  # 3 × u32

        # ── 5. Assemble header (18 bytes) ───────────────────────────────
        header = struct.pack(
            "<4sHHHII",
            MAGIC, VERSION, 0, len(func_entries),
            type_off, code_off,
        )

        # ── 6. Assemble function table ───────────────────────────────────
        func_table = bytearray()
        for name, entry_off, code_size in func_entries:
            func_table.extend(struct.pack("<III", name_offsets[name], entry_off, code_size))

        return header + type_table + bytes(name_pool) + bytes(func_table) + bytes(code_section)

    # ── Type table ───────────────────────────────────────────────────────

    def _encode_type_table(self, type_ctx: "TypeContext") -> bytes:
        """Serialize all interned types for validation."""
        buf = bytearray()
        types_list = list(type_ctx._types.values())
        buf.extend(struct.pack("<H", len(types_list)))
        for t in types_list:
            buf.extend(self._encode_type(t))
        return bytes(buf)

    def _encode_type(self, t: "FIRType") -> bytes:
        """Encode a single FIRType to bytes."""
        from ..fir.types import (
            IntType, FloatType, BoolType, UnitType, StringType,
            RefType, ArrayType, VectorType, FuncType, StructType, EnumType,
            RegionType, CapabilityType, AgentType, TrustType,
        )
        buf = bytearray()

        if isinstance(t, IntType):
            buf.append(TK_INT)
            buf.extend(struct.pack("<BB", t.bits, 1 if t.signed else 0))
        elif isinstance(t, FloatType):
            buf.append(TK_FLOAT)
            buf.extend(struct.pack("<B", t.bits))
        elif isinstance(t, BoolType):
            buf.append(TK_BOOL)
        elif isinstance(t, UnitType):
            buf.append(TK_UNIT)
        elif isinstance(t, StringType):
            buf.append(TK_STRING)
        elif isinstance(t, RefType):
            buf.append(TK_REF)
            buf.extend(struct.pack("<H", t.element.type_id))
        elif isinstance(t, ArrayType):
            buf.append(TK_ARRAY)
            buf.extend(struct.pack("<HI", t.element.type_id, t.length))
        elif isinstance(t, VectorType):
            buf.append(TK_VECTOR)
            buf.extend(struct.pack("<HB", t.element.type_id, t.lanes))
        elif isinstance(t, FuncType):
            buf.append(TK_FUNC)
            buf.extend(struct.pack("<HH", len(t.params), len(t.returns)))
            for pt in t.params:
                buf.extend(struct.pack("<H", pt.type_id))
            for rt in t.returns:
                buf.extend(struct.pack("<H", rt.type_id))
        elif isinstance(t, StructType):
            buf.append(TK_STRUCT)
            name_b = t.name.encode("utf-8")
            buf.extend(struct.pack("<H", len(name_b)))
            buf.extend(name_b)
            buf.extend(struct.pack("<H", len(t.fields)))
            for fname, ftype in t.fields:
                fn_b = fname.encode("utf-8")
                buf.extend(struct.pack("<H", len(fn_b)))
                buf.extend(fn_b)
                buf.extend(struct.pack("<H", ftype.type_id))
        elif isinstance(t, EnumType):
            buf.append(TK_ENUM)
            name_b = t.name.encode("utf-8")
            buf.extend(struct.pack("<H", len(name_b)))
            buf.extend(name_b)
            buf.extend(struct.pack("<H", len(t.variants)))
            for vname, vtype in t.variants:
                vn_b = vname.encode("utf-8")
                buf.extend(struct.pack("<H", len(vn_b)))
                buf.extend(vn_b)
                buf.append(1 if vtype is not None else 0)
                if vtype is not None:
                    buf.extend(struct.pack("<H", vtype.type_id))
        elif isinstance(t, RegionType):
            buf.append(TK_REGION)
            name_b = t.name.encode("utf-8")
            buf.extend(struct.pack("<H", len(name_b)))
            buf.extend(name_b)
        elif isinstance(t, CapabilityType):
            buf.append(TK_CAPABILITY)
            p_b = t.permission.encode("utf-8")
            r_b = t.resource.encode("utf-8")
            buf.extend(struct.pack("<H", len(p_b)))
            buf.extend(p_b)
            buf.extend(struct.pack("<H", len(r_b)))
            buf.extend(r_b)
        elif isinstance(t, AgentType):
            buf.append(TK_AGENT)
        elif isinstance(t, TrustType):
            buf.append(TK_TRUST)
        else:
            buf.append(0x00)
            buf.extend(struct.pack("<H", t.type_id))

        return bytes(buf)

    # ── Function ─────────────────────────────────────────────────────────

    def _encode_function(self, func: "FIRFunction") -> bytes:
        """Encode all blocks of a FIRFunction into bytecode."""
        buf = bytearray()
        for block in func.blocks:
            for instr in block.instructions:
                buf.extend(self._encode_instruction(instr))
        return bytes(buf)

    # ── Instruction encoding ─────────────────────────────────────────────

    def _encode_instruction(self, instr: "Instruction") -> bytes:
        """Encode one FIR instruction to bytecode."""
        op_name = instr.opcode

        # ── NOP ──────────────────────────────────────────────────────────
        if op_name == "nop":
            return bytes([Op.NOP])

        # ── Binary arithmetic (Format C: [op][rs1][rs2]) ─────────────
        if op_name in _BIN_ARITH:
            bc_op = _BIN_ARITH[op_name]
            return struct.pack("<BBB", bc_op, self._vid(instr.lhs), self._vid(instr.rhs))

        # ── Binary comparison (Format C: [op][rs1][rs2]) ──────────
        if op_name in _BIN_CMP:
            bc_op = _BIN_CMP[op_name]
            return struct.pack("<BBB", bc_op, self._vid(instr.lhs), self._vid(instr.rhs))

        # INe → IEQ (same opcode, different semantic at runtime)
        if op_name == "ine":
            return struct.pack("<BBB", Op.IEQ, self._vid(instr.lhs), self._vid(instr.rhs))

        # ── Unary (Format B: [op][src]) ───────────────────────────────────
        if op_name in _UNARY:
            bc_op = _UNARY[op_name]
            return struct.pack("<BB", bc_op, self._vid(instr.lhs))

        # ── Return (Format C: [op][0][value_id]) ────────────────────────
        if op_name == "return":
            if instr.value is None:
                return struct.pack("<BBB", Op.RET, 0, 0)  # no return value
            return struct.pack("<BBB", Op.RET, 0, self._vid(instr.value))

        # ── Unreachable → HALT (Format A) ────────────────────────────────
        if op_name == "unreachable":
            return bytes([Op.HALT])

        # ── Jump (Format D: [JMP][0][offset:16]) ─────────────────────────
        if op_name == "jump":
            return struct.pack("<BBh", Op.JMP, 0, 0)

        # ── Branch (Format D: [JZ][cond_reg][offset:16]) ─────────────────
        if op_name == "branch":
            cond_id = self._vid(instr.cond) if instr.cond is not None else 0
            return struct.pack("<BBh", Op.JZ, cond_id, 0)

        # ── Switch → encoded as Format G with case data ──────────────────
        if op_name == "switch":
            data = bytearray()
            data.append(self._vid(instr.value))
            data.extend(struct.pack("<H", len(instr.cases)))
            for case_val, _ in instr.cases.items():
                data.extend(struct.pack("<i", case_val))
            default_b = instr.default_block.encode("utf-8") if instr.default_block else b""
            data.extend(struct.pack("<H", len(default_b)))
            data.extend(default_b)
            return struct.pack("<BH", Op.JMP, len(data)) + bytes(data)

        # ── Call (Format D: [CALL][0][offset_lo][offset_hi]) ────────────────
        if op_name == "call":
            return struct.pack("<BBh", Op.CALL, 0, 0)  # placeholder, resolved by linker

        # ── Memory: load (Format C: [LOAD][0][ptr_id]) ──────────────────
        if op_name == "load":
            return struct.pack("<BBB", Op.LOAD, 0, self._vid(instr.ptr))

        # ── Memory: store (Format C: [STORE][val_id][ptr_id]) ────────────
        if op_name == "store":
            return struct.pack("<BBB", Op.STORE, self._vid(instr.value), self._vid(instr.ptr))

        # ── Memory: alloca (Format B: [ALLOCA][0]) ───────────────────────
        if op_name == "alloca":
            return struct.pack("<BB", Op.ALLOCA, 0)

        # ── Memory: getfield (Format E: [LOAD][rd][src][idx]) ─────────────
        if op_name == "getfield":
            return struct.pack("<BBBB", Op.LOAD, 0, self._vid(instr.struct_val), instr.field_index)

        # ── Memory: setfield (Format E: [STORE][val][src][idx]) ──────────
        if op_name == "setfield":
            return struct.pack("<BBBB", Op.STORE, self._vid(instr.value), self._vid(instr.struct_val), instr.field_index)

        # ── Memory: getelem (Format E: [LOAD][dst][arr][idx]) ────────────
        if op_name == "getelem":
            return struct.pack("<BBBB", Op.LOAD, 0, self._vid(instr.array_val), self._vid(instr.index))

        # ── Memory: setelem (Format E: [STORE][val][arr][idx]) ───────────
        if op_name == "setelem":
            return struct.pack("<BBBB", Op.STORE, self._vid(instr.value), self._vid(instr.array_val), self._vid(instr.index))

        # ── Memory: memcpy (Format E: [MEMCOPY][0][src][dst]) ───────────
        if op_name == "memcpy":
            return struct.pack("<BBBB", Op.MEMCOPY, 0, self._vid(instr.src), self._vid(instr.dst))

        # ── Memory: memset (Format E: [MEMSET][0][dst][val]) ────────────
        if op_name == "memset":
            return struct.pack("<BBBB", Op.MEMSET, 0, self._vid(instr.dst), instr.value & 0xFF)

        # ── Conversion → CAST (Format C: [CAST][src_id][type_id_lo]) ────
        if op_name in _CONV:
            return struct.pack("<BBB", Op.CAST, self._vid(instr.value), instr.target_type.type_id & 0xFF)

        # ── A2A: tell (Format G) ─────────────────────────────────────────
        if op_name == "tell":
            agent_b = instr.target_agent.encode("utf-8")
            data = struct.pack("<BB", self._vid(instr.message), self._vid(instr.cap)) + agent_b
            return struct.pack("<BH", Op.TELL, len(data)) + data

        # ── A2A: ask (Format G) ──────────────────────────────────────────
        if op_name == "ask":
            agent_b = instr.target_agent.encode("utf-8")
            data = struct.pack("<BB", self._vid(instr.message), self._vid(instr.cap)) + agent_b
            return struct.pack("<BH", Op.ASK, len(data)) + data

        # ── A2A: delegate (Format G) ─────────────────────────────────────
        if op_name == "delegate":
            agent_b = instr.target_agent.encode("utf-8")
            data = struct.pack("<BB", self._vid(instr.authority), self._vid(instr.cap)) + agent_b
            return struct.pack("<BH", Op.DELEGATE, len(data)) + data

        # ── A2A: trustcheck (Format G) ───────────────────────────────────
        if op_name == "trustcheck":
            agent_b = instr.agent.encode("utf-8")
            data = struct.pack("<BB", self._vid(instr.threshold), self._vid(instr.cap)) + agent_b
            return struct.pack("<BH", Op.TRUST_CHECK, len(data)) + data

        # ── A2A: caprequire (Format G) ───────────────────────────────────
        if op_name == "caprequire":
            cap_str = f"{instr.capability}:{instr.resource}".encode("utf-8")
            data = struct.pack("<B", self._vid(instr.cap)) + cap_str
            return struct.pack("<BH", Op.CAP_REQUIRE, len(data)) + data

        # ── Fallback: NOP ────────────────────────────────────────────────
        return bytes([Op.NOP])

    @staticmethod
    def _vid(value) -> int:
        """Extract SSA value ID mapped to register number (0-63)."""
        return value.id & 0x3F
