"""Shared FLUX bytecode assembler for retro game implementations.

Two-pass assembler: first pass collects labels and emits placeholder jumps,
second pass resolves all fixups to correct relative offsets.
"""

from __future__ import annotations

import struct
from flux.bytecode.opcodes import Op


class Assembler:
    """Two-pass FLUX bytecode assembler with label resolution."""

    def __init__(self) -> None:
        self.code: bytearray = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str, int]] = []  # (pos, label, instr_size)

    # ── Label management ────────────────────────────────────────────────

    def label(self, name: str) -> None:
        """Record label at current code position."""
        self.labels[name] = len(self.code)

    # ── Raw emit ────────────────────────────────────────────────────────

    def emit(self, data: bytes) -> None:
        """Append raw bytes."""
        self.code.extend(data)

    # ── Format A (1 byte) ──────────────────────────────────────────────

    def nop(self) -> None:
        self.emit(bytes([Op.NOP]))

    def halt(self) -> None:
        self.emit(bytes([Op.HALT]))

    # ── Format B (2 bytes) ─────────────────────────────────────────────

    def inc(self, reg: int) -> None:
        self.emit(struct.pack("<BB", Op.INC, reg))

    def dec(self, reg: int) -> None:
        self.emit(struct.pack("<BB", Op.DEC, reg))

    def push(self, reg: int) -> None:
        self.emit(struct.pack("<BB", Op.PUSH, reg))

    def pop(self, reg: int) -> None:
        self.emit(struct.pack("<BB", Op.POP, reg))

    def ineg(self, rd: int, rs1: int) -> None:
        self.emit(struct.pack("<BBB", Op.INEG, rd, rs1))

    # ── Format C (3 bytes) ─────────────────────────────────────────────

    def mov(self, rd: int, rs1: int) -> None:
        self.emit(struct.pack("<BBB", Op.MOV, rd, rs1))

    def iadd(self, rd: int, rs1: int, rs2: int) -> None:
        self.emit(struct.pack("<BBBB", Op.IADD, rd, rs1, rs2))

    def isub(self, rd: int, rs1: int, rs2: int) -> None:
        self.emit(struct.pack("<BBBB", Op.ISUB, rd, rs1, rs2))

    def imul(self, rd: int, rs1: int, rs2: int) -> None:
        self.emit(struct.pack("<BBBB", Op.IMUL, rd, rs1, rs2))

    def idiv(self, rd: int, rs1: int, rs2: int) -> None:
        self.emit(struct.pack("<BBBB", Op.IDIV, rd, rs1, rs2))

    def imod(self, rd: int, rs1: int, rs2: int) -> None:
        self.emit(struct.pack("<BBBB", Op.IMOD, rd, rs1, rs2))

    def iand(self, rd: int, rs1: int, rs2: int) -> None:
        self.emit(struct.pack("<BBBB", Op.IAND, rd, rs1, rs2))

    def ior(self, rd: int, rs1: int, rs2: int) -> None:
        self.emit(struct.pack("<BBBB", Op.IOR, rd, rs1, rs2))

    def ixor(self, rd: int, rs1: int, rs2: int) -> None:
        self.emit(struct.pack("<BBBB", Op.IXOR, rd, rs1, rs2))

    def ishl(self, rd: int, rs1: int, rs2: int) -> None:
        self.emit(struct.pack("<BBBB", Op.ISHL, rd, rs1, rs2))

    def ishr(self, rd: int, rs1: int, rs2: int) -> None:
        self.emit(struct.pack("<BBBB", Op.ISHR, rd, rs1, rs2))

    def cmp(self, rd: int, rs1: int) -> None:
        """Compare rd with rs1, set condition flags."""
        self.emit(struct.pack("<BBB", Op.CMP, rd, rs1))

    def load(self, rd: int, addr_reg: int) -> None:
        """Load i32 from memory[addr_reg] into rd."""
        self.emit(struct.pack("<BBB", Op.LOAD, rd, addr_reg))

    def store(self, val_reg: int, addr_reg: int) -> None:
        """Store val_reg into memory[addr_reg]."""
        self.emit(struct.pack("<BBB", Op.STORE, val_reg, addr_reg))

    def load8(self, rd: int, addr_reg: int) -> None:
        """Load byte from memory[addr_reg] into rd."""
        self.emit(struct.pack("<BBB", Op.LOAD8, rd, addr_reg))

    def store8(self, val_reg: int, addr_reg: int) -> None:
        """Store low byte of val_reg into memory[addr_reg]."""
        self.emit(struct.pack("<BBB", Op.STORE8, val_reg, addr_reg))

    def ieq(self, rd: int, rs1: int) -> None:
        """rd = (rd == rs1) ? 1 : 0"""
        self.emit(struct.pack("<BBB", Op.IEQ, rd, rs1))

    def ilt(self, rd: int, rs1: int) -> None:
        """rd = (rd < rs1) ? 1 : 0"""
        self.emit(struct.pack("<BBB", Op.ILT, rd, rs1))

    def igt(self, rd: int, rs1: int) -> None:
        """rd = (rd > rs1) ? 1 : 0"""
        self.emit(struct.pack("<BBB", Op.IGT, rd, rs1))

    # ── Format D (4 bytes) ─────────────────────────────────────────────

    def movi(self, reg: int, imm16: int) -> None:
        """Load signed i16 immediate into register."""
        self.emit(struct.pack("<BBh", Op.MOVI, reg, imm16))

    def jmp(self, target_label: str) -> None:
        """Unconditional jump to label."""
        pos = len(self.code)
        self.emit(struct.pack("<BBh", Op.JMP, 0, 0))
        self.fixups.append((pos, target_label, 4))

    def jz(self, reg: int, target_label: str) -> None:
        """Jump if register == 0."""
        pos = len(self.code)
        self.emit(struct.pack("<BBh", Op.JZ, reg, 0))
        self.fixups.append((pos, target_label, 4))

    def jnz(self, reg: int, target_label: str) -> None:
        """Jump if register != 0."""
        pos = len(self.code)
        self.emit(struct.pack("<BBh", Op.JNZ, reg, 0))
        self.fixups.append((pos, target_label, 4))

    def je(self, target_label: str) -> None:
        """Jump if flag_zero (equal)."""
        pos = len(self.code)
        self.emit(struct.pack("<BBh", Op.JE, 0, 0))
        self.fixups.append((pos, target_label, 4))

    def jne(self, target_label: str) -> None:
        """Jump if not flag_zero (not equal)."""
        pos = len(self.code)
        self.emit(struct.pack("<BBh", Op.JNE, 0, 0))
        self.fixups.append((pos, target_label, 4))

    def jg(self, target_label: str) -> None:
        """Jump if greater than (not zero, not sign)."""
        pos = len(self.code)
        self.emit(struct.pack("<BBh", Op.JG, 0, 0))
        self.fixups.append((pos, target_label, 4))

    def jl(self, target_label: str) -> None:
        """Jump if less than (flag_sign set)."""
        pos = len(self.code)
        self.emit(struct.pack("<BBh", Op.JL, 0, 0))
        self.fixups.append((pos, target_label, 4))

    def jge(self, target_label: str) -> None:
        """Jump if greater or equal (not flag_sign)."""
        pos = len(self.code)
        self.emit(struct.pack("<BBh", Op.JGE, 0, 0))
        self.fixups.append((pos, target_label, 4))

    def jle(self, target_label: str) -> None:
        """Jump if less or equal (zero or sign)."""
        pos = len(self.code)
        self.emit(struct.pack("<BBh", Op.JLE, 0, 0))
        self.fixups.append((pos, target_label, 4))

    def call(self, target_label: str) -> None:
        """Call subroutine at label (pushes return address)."""
        pos = len(self.code)
        self.emit(struct.pack("<BBh", Op.CALL, 0, 0))
        self.fixups.append((pos, target_label, 4))

    # ── RET (1 byte as handled by interpreter) ──────────────────────────

    def ret(self) -> None:
        self.emit(bytes([Op.RET]))

    # ── Build / resolve ────────────────────────────────────────────────

    def resolve(self) -> None:
        """Resolve all label fixups to correct relative offsets."""
        for pos, label, instr_size in self.fixups:
            if label not in self.labels:
                raise ValueError(
                    f"Unresolved label: {label!r} at offset {pos}"
                )
            target = self.labels[label]
            offset = target - (pos + instr_size)
            if offset < -32768 or offset > 32767:
                raise ValueError(
                    f"Jump offset out of range: {offset} for label {label!r}"
                )
            struct.pack_into("<h", self.code, pos + 2, offset)
        self.fixups.clear()

    def to_bytes(self) -> bytes:
        """Resolve labels and return the final bytecode."""
        self.resolve()
        return bytes(self.code)

    def __len__(self) -> int:
        return len(self.code)
