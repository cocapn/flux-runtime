"""FLUX Micro-VM Bytecode Interpreter.

Implements a fetch-decode-execute loop that runs directly on raw bytecode
bytes.  Supports 40+ opcodes spanning integer / float arithmetic, bitwise
logic, stack manipulation, control flow, memory access, and comparison.

Instruction encoding formats (see ``bytecode.opcodes`` for opcode values):

    Format A (1 byte):  [opcode]
    Format B (2 bytes): [opcode][reg]
    Format C (3 bytes): [opcode][rd][rs1]
    Format D (4 bytes): [opcode][rs1][off_lo][off_hi]   (signed i16 offset)
    Format E (4 bytes): [opcode][rd][rs1][rs2]

Jump offsets in Format D are **relative to the PC after the jump instruction**
has been fetched (i.e. PC already points past the instruction).
"""

from __future__ import annotations

import struct
from typing import Callable, Optional

from flux.bytecode.opcodes import Op, opcode_size
from flux.vm.memory import MemoryManager
from flux.vm.registers import RegisterFile


# ── Exceptions ─────────────────────────────────────────────────────────────


class VMError(Exception):
    """Base exception for all VM runtime errors."""

    def __init__(self, message: str, opcode: Optional[int] = None, pc: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.opcode = opcode
        self.pc = pc

    def __str__(self) -> str:
        parts = [self.message]
        if self.opcode is not None:
            parts.append(f"opcode=0x{self.opcode:02X}")
        if self.pc is not None:
            parts.append(f"pc={self.pc}")
        return " | ".join(parts)


class VMHaltError(VMError):
    """Raised when the VM executes a HALT instruction."""


class VMStackOverflowError(VMError):
    """Raised when the stack exceeds its configured maximum size."""


class VMInvalidOpcodeError(VMError):
    """Raised when the interpreter encounters an unknown opcode byte."""


class VMDivisionByZeroError(VMError):
    """Raised on division or modulo by zero."""


# ── Interpreter ────────────────────────────────────────────────────────────


class Interpreter:
    """FLUX Micro-VM bytecode interpreter.

    Parameters
    ----------
    bytecode:
        The raw compiled bytecode to execute.
    memory_size:
        Size in bytes for each of the default ``stack`` and ``heap`` regions.
    max_cycles:
        Execution cycle budget.  The VM will stop when this is exceeded.
    """

    MAX_STACK_SIZE = 4096
    MAX_CYCLES = 10_000_000  # 10M cycle budget

    def __init__(
        self,
        bytecode: bytes,
        memory_size: int = 65536,
        max_cycles: int = MAX_CYCLES,
    ) -> None:
        self.regs = RegisterFile()
        self.memory = MemoryManager()
        self.bytecode = bytecode
        self.pc = 0                     # program counter (byte offset)
        self.cycle_count = 0
        self.running = False
        self.halted = False
        self.max_cycles = max_cycles

        # Condition flags (set by CMP, checked by JE/JNE/JG/JL/JGE/JLE)
        self._flag_zero = False
        self._flag_sign = False

        # I/O callbacks
        self._io_read_cb: Optional[Callable] = None
        self._io_write_cb: Optional[Callable] = None

        # Create default memory regions
        self.memory.create_region("stack", memory_size, "system")
        self.memory.create_region("heap", memory_size, "system")

        # Stack starts at the top and grows downward
        self.regs.sp = memory_size

    # ── Public API ─────────────────────────────────────────────────────────

    def execute(self) -> int:
        """Execute bytecode until HALT, cycle budget exceeded, or error.

        Returns the total number of cycles consumed.
        """
        self.running = True
        while self.running and self.cycle_count < self.max_cycles:
            self._step()
            self.cycle_count += 1
        self.running = False
        return self.cycle_count

    def reset(self) -> None:
        """Reset the VM to its initial state (keeping bytecode)."""
        self.pc = 0
        self.cycle_count = 0
        self.running = False
        self.halted = False
        self._flag_zero = False
        self._flag_sign = False
        self.regs = RegisterFile()
        memory_size = self.memory.get_region("stack").size
        self.regs.sp = memory_size

    def dump_state(self) -> dict:
        """Return a serializable snapshot of the full VM state."""
        return {
            "pc": self.pc,
            "cycle_count": self.cycle_count,
            "running": self.running,
            "halted": self.halted,
            "flag_zero": self._flag_zero,
            "flag_sign": self._flag_sign,
            "registers": self.regs.snapshot(),
        }

    # ── I/O callback registration ──────────────────────────────────────────

    def on_io_read(self, callback: Callable) -> None:
        """Register a callback for IO_READ events."""
        self._io_read_cb = callback

    def on_io_write(self, callback: Callable) -> None:
        """Register a callback for IO_WRITE events."""
        self._io_write_cb = callback

    # ── Fetch helpers ──────────────────────────────────────────────────────

    def _fetch_u8(self) -> int:
        """Fetch one unsigned byte and advance PC."""
        b = self.bytecode[self.pc]
        self.pc += 1
        return b

    def _fetch_i8(self) -> int:
        """Fetch one signed byte and advance PC."""
        b = self._fetch_u8()
        return b if b < 128 else b - 256

    def _fetch_u16(self) -> int:
        """Fetch two unsigned bytes (little-endian) and advance PC."""
        lo = self._fetch_u8()
        hi = self._fetch_u8()
        return lo | (hi << 8)

    def _fetch_i16(self) -> int:
        """Fetch two signed bytes (little-endian) and advance PC."""
        val = self._fetch_u16()
        return val if val < 0x8000 else val - 0x10000

    def _fetch_i32(self) -> int:
        """Fetch four signed bytes (little-endian) and advance PC."""
        b0 = self._fetch_u8()
        b1 = self._fetch_u8()
        b2 = self._fetch_u8()
        b3 = self._fetch_u8()
        val = b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)
        return val if val < 0x80000000 else val - 0x100000000

    # ── Decode helpers ─────────────────────────────────────────────────────

    def _decode_operands_A(self) -> tuple:
        """No operands (Format A)."""
        return ()

    def _decode_operands_B(self) -> tuple[int]:
        """One register (Format B)."""
        reg = self._fetch_u8()
        return (reg,)

    def _decode_operands_C(self) -> tuple[int, int]:
        """Two registers: rd, rs1 (Format C)."""
        rd = self._fetch_u8()
        rs1 = self._fetch_u8()
        return (rd, rs1)

    def _decode_operands_D(self) -> tuple[int, int]:
        """Register + signed i16 offset (Format D)."""
        rs1 = self._fetch_u8()
        offset = self._fetch_i16()
        return (rs1, offset)

    def _decode_operands_E(self) -> tuple[int, int, int]:
        """Three registers: rd, rs1, rs2 (Format E)."""
        rd = self._fetch_u8()
        rs1 = self._fetch_u8()
        rs2 = self._fetch_u8()
        return (rd, rs1, rs2)

    def _decode_operands_MOVI(self) -> tuple[int, int]:
        """Register + signed i16 immediate (MOVI format)."""
        reg = self._fetch_u8()
        imm = self._fetch_i16()
        return (reg, imm)

    # ── Flags ──────────────────────────────────────────────────────────────

    def _set_flags(self, result: int) -> None:
        """Update condition flags based on an arithmetic result."""
        self._flag_zero = (result == 0)
        self._flag_sign = (result < 0)

    # ── Single-step execution ──────────────────────────────────────────────

    def _step(self) -> None:
        """Fetch, decode, and execute one instruction."""
        start_pc = self.pc
        opcode_byte = self._fetch_u8()

        # ── NOP ────────────────────────────────────────────────────────────
        if opcode_byte == Op.NOP:
            return

        # ── HALT ───────────────────────────────────────────────────────────
        if opcode_byte == Op.HALT:
            self.running = False
            self.halted = True
            return

        # ── MOV rd, rs1 ────────────────────────────────────────────────────
        if opcode_byte == Op.MOV:
            rd, rs1 = self._decode_operands_C()
            self.regs.write_gp(rd, self.regs.read_gp(rs1))
            return

        # ── MOVI reg, imm16 ───────────────────────────────────────────────
        if opcode_byte == Op.MOVI:
            reg, imm = self._decode_operands_MOVI()
            self.regs.write_gp(reg, imm)
            return

        # ── Integer Arithmetic ─────────────────────────────────────────────
        if opcode_byte == Op.IADD:
            rd, rs1, rs2 = self._decode_operands_E()
            result = self.regs.read_gp(rs1) + self.regs.read_gp(rs2)
            self.regs.write_gp(rd, result)
            self._set_flags(result)
            return

        if opcode_byte == Op.ISUB:
            rd, rs1, rs2 = self._decode_operands_E()
            result = self.regs.read_gp(rs1) - self.regs.read_gp(rs2)
            self.regs.write_gp(rd, result)
            self._set_flags(result)
            return

        if opcode_byte == Op.IMUL:
            rd, rs1, rs2 = self._decode_operands_E()
            result = self.regs.read_gp(rs1) * self.regs.read_gp(rs2)
            self.regs.write_gp(rd, result)
            self._set_flags(result)
            return

        if opcode_byte == Op.IDIV:
            rd, rs1, rs2 = self._decode_operands_E()
            divisor = self.regs.read_gp(rs2)
            if divisor == 0:
                raise VMDivisionByZeroError(
                    "Integer division by zero",
                    opcode=opcode_byte,
                    pc=start_pc,
                )
            # Truncate toward zero (C-style)
            dividend = self.regs.read_gp(rs1)
            result = int(dividend / divisor)  # truncate toward zero
            self.regs.write_gp(rd, result)
            self._set_flags(result)
            return

        if opcode_byte == Op.IREM:
            rd, rs1, rs2 = self._decode_operands_E()
            divisor = self.regs.read_gp(rs2)
            if divisor == 0:
                raise VMDivisionByZeroError(
                    "Integer modulo by zero",
                    opcode=opcode_byte,
                    pc=start_pc,
                )
            dividend = self.regs.read_gp(rs1)
            # C-style: result has sign of dividend
            result = dividend - int(dividend / divisor) * divisor
            self.regs.write_gp(rd, result)
            self._set_flags(result)
            return

        if opcode_byte == Op.INEG:
            rd, rs1 = self._decode_operands_C()
            result = -self.regs.read_gp(rs1)
            self.regs.write_gp(rd, result)
            self._set_flags(result)
            return

        # ── INC / DEC ──────────────────────────────────────────────────────
        if opcode_byte == Op.INC:
            (reg,) = self._decode_operands_B()
            result = self.regs.read_gp(reg) + 1
            self.regs.write_gp(reg, result)
            self._set_flags(result)
            return

        if opcode_byte == Op.DEC:
            (reg,) = self._decode_operands_B()
            result = self.regs.read_gp(reg) - 1
            self.regs.write_gp(reg, result)
            self._set_flags(result)
            return

        # ── Bitwise ────────────────────────────────────────────────────────
        if opcode_byte == Op.IAND:
            rd, rs1, rs2 = self._decode_operands_E()
            result = self.regs.read_gp(rs1) & self.regs.read_gp(rs2)
            self.regs.write_gp(rd, result)
            self._set_flags(result)
            return

        if opcode_byte == Op.IOR:
            rd, rs1, rs2 = self._decode_operands_E()
            result = self.regs.read_gp(rs1) | self.regs.read_gp(rs2)
            self.regs.write_gp(rd, result)
            self._set_flags(result)
            return

        if opcode_byte == Op.IXOR:
            rd, rs1, rs2 = self._decode_operands_E()
            result = self.regs.read_gp(rs1) ^ self.regs.read_gp(rs2)
            self.regs.write_gp(rd, result)
            self._set_flags(result)
            return

        if opcode_byte == Op.INOT:
            rd, rs1 = self._decode_operands_C()
            result = ~self.regs.read_gp(rs1)
            self.regs.write_gp(rd, result)
            self._set_flags(result)
            return

        if opcode_byte == Op.ISHL:
            rd, rs1, rs2 = self._decode_operands_E()
            result = self.regs.read_gp(rs1) << (self.regs.read_gp(rs2) & 0x3F)
            self.regs.write_gp(rd, result)
            self._set_flags(result)
            return

        if opcode_byte == Op.ISHR:
            rd, rs1, rs2 = self._decode_operands_E()
            # Arithmetic right shift (preserves sign bit)
            val = self.regs.read_gp(rs1)
            shift = self.regs.read_gp(rs2) & 0x3F
            result = val >> shift
            self.regs.write_gp(rd, result)
            self._set_flags(result)
            return

        # ── Stack: PUSH / POP ──────────────────────────────────────────────
        if opcode_byte == Op.PUSH:
            (reg,) = self._decode_operands_B()
            stack = self.memory.get_region("stack")
            value = self.regs.read_gp(reg)
            new_sp = self.memory.stack_push(value, stack, self.regs.sp)
            self.regs.sp = new_sp
            return

        if opcode_byte == Op.POP:
            (reg,) = self._decode_operands_B()
            stack = self.memory.get_region("stack")
            value, new_sp = self.memory.stack_pop(stack, self.regs.sp)
            self.regs.write_gp(reg, value)
            self.regs.sp = new_sp
            return

        # ── Control Flow ───────────────────────────────────────────────────
        if opcode_byte == Op.JMP:
            _, offset = self._decode_operands_D()
            self.pc += offset
            return

        if opcode_byte == Op.JZ:
            rs1, offset = self._decode_operands_D()
            if self.regs.read_gp(rs1) == 0:
                self.pc += offset
            return

        if opcode_byte == Op.JNZ:
            rs1, offset = self._decode_operands_D()
            if self.regs.read_gp(rs1) != 0:
                self.pc += offset
            return

        if opcode_byte == Op.JE:
            _, offset = self._decode_operands_D()
            if self._flag_zero:
                self.pc += offset
            return

        if opcode_byte == Op.JNE:
            _, offset = self._decode_operands_D()
            if not self._flag_zero:
                self.pc += offset
            return

        if opcode_byte == Op.JG:
            _, offset = self._decode_operands_D()
            if not self._flag_zero and (self._flag_sign != True):
                # greater: sign clear and zero clear
                self.pc += offset
            return

        if opcode_byte == Op.JL:
            _, offset = self._decode_operands_D()
            if self._flag_sign:
                self.pc += offset
            return

        if opcode_byte == Op.JGE:
            _, offset = self._decode_operands_D()
            if not self._flag_sign:
                self.pc += offset
            return

        if opcode_byte == Op.JLE:
            _, offset = self._decode_operands_D()
            if self._flag_zero or self._flag_sign:
                self.pc += offset
            return

        if opcode_byte == Op.CALL:
            _, offset = self._decode_operands_D()
            # Push return address (current PC, which points past the CALL)
            stack = self.memory.get_region("stack")
            new_sp = self.memory.stack_push(self.pc, stack, self.regs.sp)
            self.regs.sp = new_sp
            self.pc += offset
            return

        if opcode_byte == Op.RET:
            # Pop return address from stack into PC
            stack = self.memory.get_region("stack")
            addr, new_sp = self.memory.stack_pop(stack, self.regs.sp)
            self.regs.sp = new_sp
            self.pc = addr
            return

        # ── Memory: LOAD / STORE ───────────────────────────────────────────
        if opcode_byte == Op.LOAD:
            rd, rs1 = self._decode_operands_C()
            addr = self.regs.read_gp(rs1)
            stack = self.memory.get_region("stack")
            value = stack.read_i32(addr)
            self.regs.write_gp(rd, value)
            return

        if opcode_byte == Op.STORE:
            rd, rs1 = self._decode_operands_C()
            value = self.regs.write_gp
            addr = self.regs.read_gp(rs1)
            val = self.regs.read_gp(rd)
            stack = self.memory.get_region("stack")
            stack.write_i32(addr, val)
            return

        if opcode_byte == Op.LOAD8:
            rd, rs1 = self._decode_operands_C()
            addr = self.regs.read_gp(rs1)
            stack = self.memory.get_region("stack")
            value = stack.read(addr, 1)[0]
            self.regs.write_gp(rd, value)
            return

        if opcode_byte == Op.STORE8:
            rd, rs1 = self._decode_operands_C()
            addr = self.regs.read_gp(rs1)
            val = self.regs.read_gp(rd) & 0xFF
            stack = self.memory.get_region("stack")
            stack.write(addr, bytes([val]))
            return

        # ── Comparison ─────────────────────────────────────────────────────
        if opcode_byte == Op.CMP:
            rd, rs1 = self._decode_operands_C()
            result = self.regs.read_gp(rd) - self.regs.read_gp(rs1)
            self._set_flags(result)
            return

        # ── Float Arithmetic ───────────────────────────────────────────────
        if opcode_byte == Op.FADD:
            fd, fs1, fs2 = self._decode_operands_E()
            result = self.regs.read_fp(fs1) + self.regs.read_fp(fs2)
            self.regs.write_fp(fd, result)
            return

        if opcode_byte == Op.FSUB:
            fd, fs1, fs2 = self._decode_operands_E()
            result = self.regs.read_fp(fs1) - self.regs.read_fp(fs2)
            self.regs.write_fp(fd, result)
            return

        if opcode_byte == Op.FMUL:
            fd, fs1, fs2 = self._decode_operands_E()
            result = self.regs.read_fp(fs1) * self.regs.read_fp(fs2)
            self.regs.write_fp(fd, result)
            return

        if opcode_byte == Op.FDIV:
            fd, fs1, fs2 = self._decode_operands_E()
            divisor = self.regs.read_fp(fs2)
            if divisor == 0.0:
                raise VMDivisionByZeroError(
                    "Float division by zero",
                    opcode=opcode_byte,
                    pc=start_pc,
                )
            result = self.regs.read_fp(fs1) / divisor
            self.regs.write_fp(fd, result)
            return

        if opcode_byte == Op.FNEG:
            fd, fs1 = self._decode_operands_C()
            result = -self.regs.read_fp(fs1)
            self.regs.write_fp(fd, result)
            return

        # ── Unknown opcode ─────────────────────────────────────────────────
        raise VMInvalidOpcodeError(
            f"Unknown opcode: 0x{opcode_byte:02X}",
            opcode=opcode_byte,
            pc=start_pc,
        )
