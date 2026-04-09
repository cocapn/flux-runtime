"""Bytecode Decoder — decodes FLUX binary bytecode into structured representation.

See encoder.py for the binary format specification.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Optional

from .opcodes import Op, get_format, instruction_size


# ── Decoded data structures ──────────────────────────────────────────────────

@dataclass
class DecodedInstruction:
    """A single decoded bytecode instruction."""
    opcode: Op
    operands: list = field(default_factory=list)  # ints, strings, or bytes
    offset: int = 0  # byte offset in the code section


@dataclass
class DecodedFunction:
    """A decoded function from the bytecode."""
    name: str
    entry_offset: int
    instructions: list[DecodedInstruction] = field(default_factory=list)


@dataclass
class DecodedType:
    """A decoded type from the type table."""
    type_kind: int
    payload: dict = field(default_factory=dict)


@dataclass
class DecodedModule:
    """Full decoded module from bytecode."""
    version: int
    flags: int
    functions: list[DecodedFunction] = field(default_factory=list)
    types: list[DecodedType] = field(default_factory=list)


# ── Decoder ──────────────────────────────────────────────────────────────────

MAGIC = b"FLUX"
HEADER_SIZE = 18  # 4s(4) + H(2) + H(2) + H(2) + I(4) + I(4) = 18
FUNC_TABLE_ENTRY_SIZE = 12  # 3 × uint32


class BytecodeDecoder:
    """Decodes FLUX bytecode bytes into structured representation."""

    def decode(self, data: bytes) -> DecodedModule:
        """Decode FLUX bytecode into a DecodedModule."""
        if len(data) < HEADER_SIZE:
            raise ValueError(f"Bytecode too short for header: {len(data)} bytes")

        header = self._decode_header(data)
        code_off = header["code_off"]
        type_off = header["type_off"]
        n_funcs = header["n_funcs"]

        # Decode type table
        types = self._decode_type_table(data, type_off)

        # Compute section offsets
        # Layout: [Header][Type Table][Name Pool][Function Table][Code]
        func_table_off = code_off - n_funcs * FUNC_TABLE_ENTRY_SIZE
        name_pool_off = type_off + header["type_table_size"]

        # Decode each function
        functions: list[DecodedFunction] = []
        for i in range(n_funcs):
            ft_off = func_table_off + i * FUNC_TABLE_ENTRY_SIZE
            name_off, entry_off, code_size = struct.unpack_from("<III", data, ft_off)

            # Read function name from name pool
            name = self._read_string(data, name_pool_off + name_off)

            # Decode instructions
            code_start = code_off + entry_off
            code_end = code_start + code_size
            instructions = self._decode_instructions(data, code_start, code_end)

            functions.append(DecodedFunction(
                name=name,
                entry_offset=entry_off,
                instructions=instructions,
            ))

        return DecodedModule(
            version=header["version"],
            flags=header["flags"],
            functions=functions,
            types=types,
        )

    def decode_functions(self, data: bytes) -> list[DecodedFunction]:
        """Convenience: decode and return just the list of functions."""
        module = self.decode(data)
        return module.functions

    # ── Header ───────────────────────────────────────────────────────────

    def _decode_header(self, data: bytes) -> dict:
        """Parse the 16-byte header."""
        magic, version, flags, n_funcs, type_off, code_off = struct.unpack_from(
            "<4sHHHII", data, 0
        )
        if magic != MAGIC:
            raise ValueError(f"Invalid magic: {magic!r} (expected {MAGIC!r})")

        # Compute type table size by finding the function table
        # Function table starts right after the name pool
        # The name pool is between type table and function table
        # We can compute: func_table_off = code_off - n_funcs * 12
        # But we need to account for type table first
        # type_table + name_pool ends at: code_off - n_funcs * 12
        # For now, compute type table size by scanning
        type_table_raw = self._decode_type_table_raw(data, type_off)
        type_table_size = len(type_table_raw)

        return {
            "magic": magic,
            "version": version,
            "flags": flags,
            "n_funcs": n_funcs,
            "type_off": type_off,
            "code_off": code_off,
            "type_table_size": type_table_size,
        }

    # ── Type table ───────────────────────────────────────────────────────

    def _decode_type_table_raw(self, data: bytes, offset: int) -> bytearray:
        """Get the raw bytes of the type table for size computation."""
        if offset >= len(data) or offset + 2 > len(data):
            return bytearray()
        n_types = struct.unpack_from("<H", data, offset)[0]
        pos = offset + 2
        for _ in range(n_types):
            if pos >= len(data):
                break
            pos = self._skip_type(data, pos)
        return bytearray(data[offset:pos])

    def _skip_type(self, data: bytes, pos: int) -> int:
        """Skip past a single type entry, return new position."""
        if pos >= len(data):
            return pos
        kind = data[pos]
        pos += 1

        if kind == 0x01:  # INT
            pos += 2  # bits:u8, signed:u8
        elif kind == 0x02:  # FLOAT
            pos += 1  # bits:u8
        elif kind in (0x03, 0x04, 0x05, 0x0E, 0x0F):  # BOOL, UNIT, STRING, AGENT, TRUST
            pass  # no payload
        elif kind == 0x06:  # REF
            pos += 2  # element type_id:u16
        elif kind == 0x07:  # ARRAY
            pos += 6  # element type_id:u16 + length:u32
        elif kind == 0x08:  # VECTOR
            pos += 3  # element type_id:u16 + lanes:u8
        elif kind == 0x09:  # FUNC
            if pos + 4 > len(data):
                return pos
            n_params, n_returns = struct.unpack_from("<HH", data, pos)
            pos += 4 + (n_params + n_returns) * 2
        elif kind in (0x0A, 0x0B):  # STRUCT, ENUM
            if pos + 2 > len(data):
                return pos
            name_len = struct.unpack_from("<H", data, pos)[0]
            pos += 2 + name_len
            if pos + 2 > len(data):
                return pos
            n_items = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            for _ in range(n_items):
                if pos + 2 > len(data):
                    return pos
                item_name_len = struct.unpack_from("<H", data, pos)[0]
                pos += 2 + item_name_len
                if kind == 0x0A:  # STRUCT: type_id:u16
                    pos += 2
                else:  # ENUM: has_type:u1
                    if pos < len(data):
                        has_type = data[pos]
                        pos += 1
                        if has_type:
                            pos += 2
        elif kind == 0x0C:  # REGION
            if pos + 2 > len(data):
                return pos
            name_len = struct.unpack_from("<H", data, pos)[0]
            pos += 2 + name_len
        elif kind == 0x0D:  # CAPABILITY
            for _ in range(2):  # permission + resource
                if pos + 2 > len(data):
                    return pos
                s_len = struct.unpack_from("<H", data, pos)[0]
                pos += 2 + s_len
        return pos

    def _decode_type_table(self, data: bytes, offset: int) -> list[DecodedType]:
        """Decode the type table into DecodedType objects."""
        types: list[DecodedType] = []
        if offset + 2 > len(data):
            return types
        n_types = struct.unpack_from("<H", data, offset)[0]
        pos = offset + 2

        for _ in range(n_types):
            if pos >= len(data):
                break
            dtype, pos = self._decode_one_type(data, pos)
            types.append(dtype)

        return types

    def _decode_one_type(self, data: bytes, pos: int) -> tuple[DecodedType, int]:
        """Decode one type entry. Returns (DecodedType, new_pos)."""
        kind = data[pos]
        pos += 1
        payload: dict = {}

        if kind == 0x01:  # INT
            bits, signed = struct.unpack_from("<BB", data, pos)
            payload = {"bits": bits, "signed": bool(signed)}
            pos += 2
        elif kind == 0x02:  # FLOAT
            bits = data[pos]
            payload = {"bits": bits}
            pos += 1
        elif kind == 0x06:  # REF
            elem_id = struct.unpack_from("<H", data, pos)[0]
            payload = {"element_type_id": elem_id}
            pos += 2
        elif kind == 0x07:  # ARRAY
            elem_id, length = struct.unpack_from("<HI", data, pos)
            payload = {"element_type_id": elem_id, "length": length}
            pos += 6
        elif kind == 0x08:  # VECTOR
            elem_id, lanes = struct.unpack_from("<HB", data, pos)
            payload = {"element_type_id": elem_id, "lanes": lanes}
            pos += 3
        elif kind == 0x09:  # FUNC
            n_params, n_returns = struct.unpack_from("<HH", data, pos)
            pos += 4
            param_ids = []
            for _ in range(n_params):
                param_ids.append(struct.unpack_from("<H", data, pos)[0])
                pos += 2
            return_ids = []
            for _ in range(n_returns):
                return_ids.append(struct.unpack_from("<H", data, pos)[0])
                pos += 2
            payload = {"param_type_ids": param_ids, "return_type_ids": return_ids}
        elif kind == 0x0C:  # REGION
            name_len = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            payload = {"name": data[pos:pos + name_len].decode("utf-8")}
            pos += name_len
        elif kind == 0x0D:  # CAPABILITY
            perm_len = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            perm = data[pos:pos + perm_len].decode("utf-8")
            pos += perm_len
            res_len = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            res = data[pos:pos + res_len].decode("utf-8")
            pos += res_len
            payload = {"permission": perm, "resource": res}

        return DecodedType(type_kind=kind, payload=payload), pos

    # ── Instructions ─────────────────────────────────────────────────────

    def _decode_instructions(
        self, data: bytes, start: int, end: int
    ) -> list[DecodedInstruction]:
        """Decode all instructions in a code range."""
        instructions: list[DecodedInstruction] = []
        pos = start

        while pos < end:
            instr, pos = self._decode_instruction(data, pos, end)
            instructions.append(instr)

        return instructions

    def _decode_instruction(
        self, data: bytes, offset: int, end: int
    ) -> tuple[DecodedInstruction, int]:
        """Decode one instruction at the given offset.
        Returns (DecodedInstruction, next_offset).
        """
        if offset >= end:
            raise ValueError(f"Unexpected end of code at offset {offset}")

        raw_op = data[offset]

        # Validate opcode
        try:
            op = Op(raw_op)
        except ValueError:
            # Unknown opcode — treat as NOP-sized (1 byte)
            return DecodedInstruction(
                opcode=Op.NOP,
                operands=[raw_op],  # store raw value for diagnostics
                offset=offset,
            ), offset + 1

        fmt = get_format(op)

        if fmt == "A":
            # 1 byte: [opcode]
            return DecodedInstruction(opcode=op, offset=offset), offset + 1

        elif fmt == "B":
            # 2 bytes: [opcode][rd:u8]
            if offset + 2 > end:
                raise ValueError(f"Truncated Format B instruction at {offset}")
            rd = data[offset + 1]
            return DecodedInstruction(opcode=op, operands=[rd], offset=offset), offset + 2

        elif fmt == "C":
            # 3 bytes: [opcode][rd:u8][rs1:u8]
            if offset + 3 > end:
                raise ValueError(f"Truncated Format C instruction at {offset}")
            rd = data[offset + 1]
            rs1 = data[offset + 2]
            return DecodedInstruction(opcode=op, operands=[rd, rs1], offset=offset), offset + 3

        elif fmt == "D":
            # 4 bytes: [opcode][rs1:u8][imm16:i16]
            if offset + 4 > end:
                raise ValueError(f"Truncated Format D instruction at {offset}")
            rs1 = data[offset + 1]
            imm16 = struct.unpack_from("<h", data, offset + 2)[0]
            return DecodedInstruction(opcode=op, operands=[rs1, imm16], offset=offset), offset + 4

        elif fmt == "E":
            # 4 bytes: [opcode][rd:u8][rs1:u8][rs2:u8]
            if offset + 4 > end:
                raise ValueError(f"Truncated Format E instruction at {offset}")
            rd = data[offset + 1]
            rs1 = data[offset + 2]
            rs2 = data[offset + 3]
            return DecodedInstruction(opcode=op, operands=[rd, rs1, rs2], offset=offset), offset + 4

        elif fmt == "G":
            # Variable: [opcode][len:u16][data:len bytes]
            if offset + 3 > end:
                raise ValueError(f"Truncated Format G instruction at {offset}")
            data_len = struct.unpack_from("<H", data, offset + 1)[0]
            if offset + 3 + data_len > end:
                raise ValueError(f"Format G data overflows at {offset}")
            payload = bytes(data[offset + 3: offset + 3 + data_len])
            new_offset = offset + 3 + data_len
            return DecodedInstruction(opcode=op, operands=[payload], offset=offset), new_offset

        else:
            # Should not happen
            return DecodedInstruction(opcode=op, offset=offset), offset + 1

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _read_string(data: bytes, offset: int) -> str:
        """Read a null-terminated UTF-8 string from data at offset."""
        try:
            end = data.index(0x00, offset)
        except ValueError:
            # If no null terminator found, read to end
            end = len(data)
        return data[offset:end].decode("utf-8")
