"""Bytecode Validator — validates structural integrity of FLUX bytecode."""

from __future__ import annotations

import struct

from .opcodes import Op, get_format, instruction_size

MAGIC = b"FLUX"
HEADER_SIZE = 16
FUNC_TABLE_ENTRY_SIZE = 12
MAX_REGISTER = 63  # 64 registers: 0-63


class BytecodeValidator:
    """Validates FLUX bytecode structural integrity."""

    def validate(self, data: bytes) -> list[str]:
        """Validate bytecode and return a list of error messages (empty = valid)."""
        errors: list[str] = []

        if len(data) < HEADER_SIZE:
            errors.append(f"Bytecode too short: {len(data)} bytes (minimum {HEADER_SIZE})")
            return errors

        # ── 1. Check magic bytes ─────────────────────────────────────────
        magic = data[:4]
        if magic != MAGIC:
            errors.append(f"Invalid magic bytes: {magic!r} (expected {MAGIC!r})")

        # ── 2. Parse and verify header fields ────────────────────────────
        try:
            _, version, flags, n_funcs, type_off, code_off = struct.unpack_from(
                "<4sHHHI I", data, 0
            )
        except struct.error as e:
            errors.append(f"Failed to parse header: {e}")
            return errors

        if version == 0:
            errors.append(f"Invalid version: {version}")

        if n_funcs > 0 and code_off >= len(data):
            errors.append(f"Code section offset {code_off} exceeds data length {len(data)}")

        if type_off < HEADER_SIZE:
            errors.append(f"Type table offset {type_off} overlaps header")

        if type_off >= len(data):
            errors.append(f"Type table offset {type_off} exceeds data length")

        if n_funcs == 0:
            return errors

        # ── 3. Validate function table ───────────────────────────────────
        # Compute where function table starts: after type table + name pool
        # We approximate: func_table starts at code_off - n_funcs * 12
        func_table_off = code_off - n_funcs * FUNC_TABLE_ENTRY_SIZE

        if func_table_off < 0:
            errors.append("Function table offset is negative (corrupted header)")
            return errors

        if func_table_off + n_funcs * FUNC_TABLE_ENTRY_SIZE > code_off:
            errors.append("Function table overlaps with code section")

        # ── 4. Validate each function ────────────────────────────────────
        func_names_seen: set[str] = set()
        func_entry_offsets: list[int] = []

        for i in range(n_funcs):
            ft_off = func_table_off + i * FUNC_TABLE_ENTRY_SIZE
            if ft_off + FUNC_TABLE_ENTRY_SIZE > len(data):
                errors.append(f"Function table entry {i} truncated")
                continue

            name_off, entry_off, code_size = struct.unpack_from("<III", data, ft_off)

            # Check entry offset bounds
            if entry_off >= len(data) - code_off:
                errors.append(f"Function {i}: entry offset {entry_off} out of code section bounds")
                continue

            func_entry_offsets.append(entry_off)

            # Check code size
            if code_off + entry_off + code_size > len(data):
                errors.append(f"Function {i}: code extends past end of bytecode")
                continue

            # Read function name
            try:
                name_pool_abs = func_table_off + name_off
                if name_pool_abs >= len(data):
                    errors.append(f"Function {i}: name offset out of bounds")
                    continue
                null_pos = data.index(0x00, name_pool_abs)
                func_name = data[name_pool_abs:null_pos].decode("utf-8")
            except (ValueError, UnicodeDecodeError) as e:
                errors.append(f"Function {i}: invalid name: {e}")
                continue

            if func_name in func_names_seen:
                errors.append(f"Duplicate function name: {func_name}")
            func_names_seen.add(func_name)

            # ── 5. Walk all instructions ─────────────────────────────────
            self._validate_function_code(
                data, code_off + entry_off, code_off + entry_off + code_size,
                f"function '{func_name}'", errors,
            )

        return errors

    def _validate_function_code(
        self,
        data: bytes,
        start: int,
        end: int,
        context: str,
        errors: list[str],
    ) -> None:
        """Walk instructions in a code range and validate them."""
        pos = start
        last_opcode: Op | None = None
        has_terminator = False
        instr_offsets: list[int] = []  # for jump target validation

        while pos < end:
            instr_offsets.append(pos)

            if pos >= len(data):
                errors.append(f"{context}: instruction at offset {pos - start} out of data bounds")
                break

            raw_op = data[pos]

            # Check if opcode is known
            try:
                op = Op(raw_op)
            except ValueError:
                errors.append(
                    f"{context}: unknown opcode 0x{raw_op:02x} at offset {pos - start}"
                )
                pos += 1  # skip unknown byte
                continue

            last_opcode = op
            fmt = get_format(op)

            if fmt == "A":
                if op in (Op.RET, Op.HALT):
                    has_terminator = True
                pos += 1

            elif fmt == "B":
                if pos + 2 > end:
                    errors.append(f"{context}: truncated Format B at offset {pos - start}")
                    break
                reg = data[pos + 1]
                if reg > MAX_REGISTER:
                    errors.append(
                        f"{context}: register {reg} > {MAX_REGISTER} at offset {pos - start}"
                    )
                if op in (Op.RET, Op.HALT):
                    has_terminator = True
                pos += 2

            elif fmt == "C":
                if pos + 3 > end:
                    errors.append(f"{context}: truncated Format C at offset {pos - start}")
                    break
                rd = data[pos + 1]
                rs1 = data[pos + 2]
                if rd > MAX_REGISTER:
                    errors.append(
                        f"{context}: register rd={rd} > {MAX_REGISTER} at offset {pos - start}"
                    )
                if rs1 > MAX_REGISTER:
                    errors.append(
                        f"{context}: register rs1={rs1} > {MAX_REGISTER} at offset {pos - start}"
                    )
                pos += 3

            elif fmt == "D":
                if pos + 4 > end:
                    errors.append(f"{context}: truncated Format D at offset {pos - start}")
                    break
                rs1 = data[pos + 1]
                if rs1 > MAX_REGISTER:
                    errors.append(
                        f"{context}: register {rs1} > {MAX_REGISTER} at offset {pos - start}"
                    )
                # Validate jump target (offset must land on an instruction boundary)
                imm16 = struct.unpack_from("<h", data, pos + 2)[0]
                target = (pos - start) + imm16
                if target < 0 or target >= (end - start):
                    errors.append(
                        f"{context}: jump target {target} out of bounds at offset {pos - start}"
                    )
                pos += 4

            elif fmt == "E":
                if pos + 5 > end:
                    errors.append(f"{context}: truncated Format E at offset {pos - start}")
                    break
                for reg_idx, byte_off in [(0, pos + 1), (1, pos + 2), (2, pos + 3)]:
                    reg = data[byte_off]
                    if reg > MAX_REGISTER:
                        errors.append(
                            f"{context}: register {reg} > {MAX_REGISTER} at offset {pos - start}"
                        )
                pos += 5

            elif fmt == "G":
                if pos + 3 > end:
                    errors.append(f"{context}: truncated Format G header at offset {pos - start}")
                    break
                data_len = struct.unpack_from("<H", data, pos + 1)[0]
                if pos + 3 + data_len > end:
                    errors.append(
                        f"{context}: Format G data extends past code end at offset {pos - start}"
                    )
                    break
                # Validate register references in payload (first few bytes may be reg IDs)
                payload_start = pos + 3
                payload_end = pos + 3 + data_len
                p = payload_start
                while p < min(payload_end, payload_start + 4):
                    if data[p] > MAX_REGISTER:
                        errors.append(
                            f"{context}: register {data[p]} > {MAX_REGISTER} in payload at offset {pos - start}"
                        )
                    p += 1
                pos = payload_end

            else:
                pos += 1

        # ── 6. Check terminator ──────────────────────────────────────────
        if not has_terminator and instr_offsets:
            errors.append(f"{context}: function does not end with RET or HALT")
