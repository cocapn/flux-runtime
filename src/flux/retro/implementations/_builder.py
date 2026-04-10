"""Shared FLUX bytecode builder with label/patch support."""

from __future__ import annotations

import struct
from flux.bytecode.opcodes import Op


class BytecodeBuilder:
    """Programmatic FLUX bytecode assembler with forward-reference labels."""

    def __init__(self) -> None:
        self.code: bytearray = bytearray()
        self._labels: dict[str, int] = {}
        self._patches: list[tuple[int, str]] = []  # (inst_start, label_name)

    # ── helpers ──────────────────────────────────────────────────────────

    @property
    def pos(self) -> int:
        return len(self.code)

    def _emit(self, data: bytes) -> int:
        start = len(self.code)
        self.code.extend(data)
        return start

    def label(self, name: str) -> None:
        self._labels[name] = len(self.code)

    def build(self) -> bytes:
        for inst_start, lbl in self._patches:
            target = self._labels.get(lbl)
            if target is None:
                raise ValueError(f"Undefined label: {lbl!r}")
            pc_after = inst_start + 4  # all jumps are 4 bytes
            offset = target - pc_after
            struct.pack_into("<h", self.code, inst_start + 2, offset)
        return bytes(self.code)

    # ── Format A  (1 byte) ──────────────────────────────────────────────

    def nop(self):
        self._emit(bytes([Op.NOP]))

    def halt(self):
        self._emit(bytes([Op.HALT]))

    def ret(self):
        self._emit(bytes([Op.RET]))

    # ── Format B  (2 bytes) ─────────────────────────────────────────────

    def push(self, reg: int):
        self._emit(struct.pack("<BB", Op.PUSH, reg))

    def pop(self, reg: int):
        self._emit(struct.pack("<BB", Op.POP, reg))

    def inc(self, reg: int):
        self._emit(struct.pack("<BB", Op.INC, reg))

    def dec(self, reg: int):
        self._emit(struct.pack("<BB", Op.DEC, reg))

    def ineg(self, rd: int, rs: int):
        self._emit(struct.pack("<BBB", Op.INEG, rd, rs))

    # ── Format C  (3 bytes) ─────────────────────────────────────────────

    def mov(self, rd: int, rs1: int):
        self._emit(struct.pack("<BBB", Op.MOV, rd, rs1))

    def load8(self, rd: int, rs1: int):
        self._emit(struct.pack("<BBB", Op.LOAD8, rd, rs1))

    def store8(self, rd: int, rs1: int):
        self._emit(struct.pack("<BBB", Op.STORE8, rd, rs1))

    def load(self, rd: int, rs1: int):
        self._emit(struct.pack("<BBB", Op.LOAD, rd, rs1))

    def store(self, rd: int, rs1: int):
        self._emit(struct.pack("<BBB", Op.STORE, rd, rs1))

    def cmp(self, a: int, b: int):
        self._emit(struct.pack("<BBB", Op.CMP, a, b))

    def ieq(self, rd: int, rs1: int):
        self._emit(struct.pack("<BBB", Op.IEQ, rd, rs1))

    def ilt(self, rd: int, rs1: int):
        self._emit(struct.pack("<BBB", Op.ILT, rd, rs1))

    def igt(self, rd: int, rs1: int):
        self._emit(struct.pack("<BBB", Op.IGT, rd, rs1))

    def ineg_c(self, rd: int, rs: int):
        self._emit(struct.pack("<BBB", Op.INEG, rd, rs))

    # ── Format E  (4 bytes: opcode+rd+rs1+rs2) ─────────────────────────

    def iadd(self, rd: int, rs1: int, rs2: int):
        self._emit(struct.pack("<BBBB", Op.IADD, rd, rs1, rs2))

    def isub(self, rd: int, rs1: int, rs2: int):
        self._emit(struct.pack("<BBBB", Op.ISUB, rd, rs1, rs2))

    def imul(self, rd: int, rs1: int, rs2: int):
        self._emit(struct.pack("<BBBB", Op.IMUL, rd, rs1, rs2))

    def idiv(self, rd: int, rs1: int, rs2: int):
        self._emit(struct.pack("<BBBB", Op.IDIV, rd, rs1, rs2))

    def imod(self, rd: int, rs1: int, rs2: int):
        self._emit(struct.pack("<BBBB", Op.IMOD, rd, rs1, rs2))

    def iand(self, rd: int, rs1: int, rs2: int):
        self._emit(struct.pack("<BBBB", Op.IAND, rd, rs1, rs2))

    def ior(self, rd: int, rs1: int, rs2: int):
        self._emit(struct.pack("<BBBB", Op.IOR, rd, rs1, rs2))

    def ixor(self, rd: int, rs1: int, rs2: int):
        self._emit(struct.pack("<BBBB", Op.IXOR, rd, rs1, rs2))

    # ── Format D  (4 bytes) ─────────────────────────────────────────────

    def movi(self, reg: int, imm: int):
        self._emit(struct.pack("<BBh", Op.MOVI, reg, imm))

    def jmp(self, label: str):
        s = self._emit(struct.pack("<BBh", Op.JMP, 0, 0))
        self._patches.append((s, label))

    def jz(self, reg: int, label: str):
        s = self._emit(struct.pack("<BBh", Op.JZ, reg, 0))
        self._patches.append((s, label))

    def jnz(self, reg: int, label: str):
        s = self._emit(struct.pack("<BBh", Op.JNZ, reg, 0))
        self._patches.append((s, label))

    def je(self, label: str):
        s = self._emit(struct.pack("<BBh", Op.JE, 0, 0))
        self._patches.append((s, label))

    def jne(self, label: str):
        s = self._emit(struct.pack("<BBh", Op.JNE, 0, 0))
        self._patches.append((s, label))

    def jl(self, label: str):
        s = self._emit(struct.pack("<BBh", Op.JL, 0, 0))
        self._patches.append((s, label))

    def jle(self, label: str):
        s = self._emit(struct.pack("<BBh", Op.JLE, 0, 0))
        self._patches.append((s, label))

    def jg(self, label: str):
        s = self._emit(struct.pack("<BBh", Op.JG, 0, 0))
        self._patches.append((s, label))

    def jge(self, label: str):
        s = self._emit(struct.pack("<BBh", Op.JGE, 0, 0))
        self._patches.append((s, label))

    def call(self, label: str):
        s = self._emit(struct.pack("<BBh", Op.CALL, 0, 0))
        self._patches.append((s, label))
