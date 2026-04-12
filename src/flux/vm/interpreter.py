"""FLUX Micro-VM Bytecode Interpreter.

Implements a fetch-decode-execute loop that runs directly on raw bytecode
bytes.  Supports all 100+ opcodes spanning integer / float arithmetic, bitwise
logic, stack manipulation, control flow, memory access, comparison, type
operations, SIMD vector ops, A2A protocol, and system calls.

Instruction encoding formats (see ``bytecode.opcodes`` for opcode values):

    Format A (1 byte):  [opcode]
    Format B (2 bytes): [opcode][reg]
    Format C (3 bytes): [opcode][rd][rs1]
    Format D (4 bytes): [opcode][rs1][off_lo][off_hi]   (signed i16 offset)
    Format E (4 bytes): [opcode][rd][rs1][rs2]
    Format G (variable): [opcode][len:u16][data:len bytes]

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


class VMTypeError(VMError):
    """Raised on type check or bounds check failure."""


class VMA2AError(VMError):
    """Raised on A2A protocol errors."""


class VMResourceError(VMError):
    """Raised on resource acquisition failure."""


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

    # Internal box table: maps boxed_id -> (type_tag, value)
    # Used by BOX/UNBOX/CHECK_TYPE opcodes
    _BOX_TYPE_INT = 0
    _BOX_TYPE_FLOAT = 1
    _BOX_TYPE_BOOL = 2

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

        # Condition flags (set by CMP/ICMP/TEST, checked by JE/JNE/JG/JL/JGE/JLE/SETCC)
        self._flag_zero = False
        self._flag_sign = False
        # Additional condition flags for richer comparisons
        self._flag_carry = False  # set when unsigned overflow/borrow
        self._flag_overflow = False  # set when signed overflow

        # I/O callbacks
        self._io_read_cb: Optional[Callable] = None
        self._io_write_cb: Optional[Callable] = None

        # A2A handler (plugin/callback for A2A opcodes)
        self._a2a_handler: Optional[Callable] = None

        # Box table for BOX/UNBOX/CHECK_TYPE
        self._box_table: list[tuple[int, object]] = []  # (type_tag, value)
        self._box_counter: int = 0

        # Resource tracking for RESOURCE_ACQUIRE / RESOURCE_RELEASE
        self._resources: dict[int, bool] = {}  # resource_id -> acquired

        # Call stack for ENTER/LEAVE frame tracking
        self._frame_stack: list[int] = []  # stack of saved SP values

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
        while self.running and not self.halted and self.cycle_count < self.max_cycles:
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
        self._flag_carry = False
        self._flag_overflow = False
        self.regs = RegisterFile()
        memory_size = self.memory.get_region("stack").size
        self.regs.sp = memory_size
        self._box_table.clear()
        self._box_counter = 0
        self._resources.clear()
        self._frame_stack.clear()

    def dump_state(self) -> dict:
        """Return a serializable snapshot of the full VM state."""
        return {
            "pc": self.pc,
            "cycle_count": self.cycle_count,
            "running": self.running,
            "halted": self.halted,
            "flag_zero": self._flag_zero,
            "flag_sign": self._flag_sign,
            "flag_carry": self._flag_carry,
            "flag_overflow": self._flag_overflow,
            "registers": self.regs.snapshot(),
            "box_count": len(self._box_table),
            "resource_count": len(self._resources),
            "frame_depth": len(self._frame_stack),
        }

    # ── I/O callback registration ──────────────────────────────────────────

    def on_io_read(self, callback: Callable) -> None:
        """Register a callback for IO_READ events."""
        self._io_read_cb = callback

    def on_io_write(self, callback: Callable) -> None:
        """Register a callback for IO_WRITE events."""
        self._io_write_cb = callback

    def on_a2a(self, handler: Callable) -> None:
        """Register an A2A message handler.

        The handler receives (opcode_name, data_bytes) and may return
        an optional result placed in R0.
        """
        self._a2a_handler = handler

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

    def _fetch_var_data(self) -> bytes:
        """Fetch variable-length data (Format G): u16 length prefix + data."""
        length = self._fetch_u16()
        data = self.bytecode[self.pc:self.pc + length]
        self.pc += length
        return data

    def _fetch_var_string(self) -> str:
        """Fetch a null-terminated string from variable data."""
        data = self._fetch_var_data()
        idx = data.find(b'\x00')
        if idx >= 0:
            data = data[:idx]
        return data.decode('utf-8', errors='replace')

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
        self._flag_carry = (result < 0)  # simplified carry model
        self._flag_overflow = False  # simplified overflow model

    def _set_cmp_flags(self, a: int, b: int) -> None:
        """Update flags from a subtraction (a - b), tracking carry/overflow."""
        result = a - b
        self._flag_zero = (a == b)
        self._flag_sign = (a < b)
        # Unsigned comparison support
        self._flag_carry = (a < b)  # borrow
        # Signed overflow: (a positive, b negative, result negative) or (a negative, b positive, result positive)
        self._flag_overflow = ((a > 0 and b < 0 and result < 0) or
                               (a < 0 and b > 0 and result > 0))

    # ── Stack frame helpers ────────────────────────────────────────────────

    def _stack_push(self, value: int) -> None:
        """Push a 32-bit value onto the stack (grows downward)."""
        stack = self.memory.get_region("stack")
        new_sp = self.memory.stack_push(value, stack, self.regs.sp)
        self.regs.sp = new_sp

    def _stack_pop(self) -> int:
        """Pop a 32-bit value from the stack."""
        stack = self.memory.get_region("stack")
        value, new_sp = self.memory.stack_pop(stack, self.regs.sp)
        self.regs.sp = new_sp
        return value

    # ── A2A dispatch helper ────────────────────────────────────────────────

    def _dispatch_a2a(self, opcode_name: str, data: bytes) -> None:
        """Dispatch an A2A opcode to the registered handler.

        If no handler is registered, the opcode is logged as a no-op stub.
        The handler may optionally return a value to place in R0.
        """
        if self._a2a_handler is not None:
            result = self._a2a_handler(opcode_name, data)
            if result is not None:
                self.regs.write_gp(0, int(result))
        # If no handler, silently no-op (stub behavior for self-hosting)

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
            dividend = self.regs.read_gp(rs1)
            result = int(dividend / divisor)
            self.regs.write_gp(rd, result)
            self._set_flags(result)
            return

        if opcode_byte == Op.IMOD:
            rd, rs1, rs2 = self._decode_operands_E()
            divisor = self.regs.read_gp(rs2)
            if divisor == 0:
                raise VMDivisionByZeroError(
                    "Integer modulo by zero",
                    opcode=opcode_byte,
                    pc=start_pc,
                )
            dividend = self.regs.read_gp(rs1)
            result = dividend - int(dividend / divisor) * divisor
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
            val = self.regs.read_gp(rs1)
            shift = self.regs.read_gp(rs2) & 0x3F
            result = val >> shift
            self.regs.write_gp(rd, result)
            self._set_flags(result)
            return

        # ── ROTL / ROTR (rotate left/right) ───────────────────────────────
        if opcode_byte == Op.ROTL:
            rd, rs1, rs2 = self._decode_operands_E()
            val = self.regs.read_gp(rs1) & 0xFFFFFFFF  # 32-bit
            shift = self.regs.read_gp(rs2) & 0x1F
            result = ((val << shift) | (val >> (32 - shift))) & 0xFFFFFFFF
            self.regs.write_gp(rd, result)
            self._set_flags(result)
            return

        if opcode_byte == Op.ROTR:
            rd, rs1, rs2 = self._decode_operands_E()
            val = self.regs.read_gp(rs1) & 0xFFFFFFFF
            shift = self.regs.read_gp(rs2) & 0x1F
            result = ((val >> shift) | (val << (32 - shift))) & 0xFFFFFFFF
            self.regs.write_gp(rd, result)
            self._set_flags(result)
            return

        # ── Comparison: ICMP (generic compare with condition) ──────────────
        if opcode_byte == Op.ICMP:
            # Format C: [ICMP][cond:u8][rhs_reg:u8]
            # cond: 0=EQ, 1=NE, 2=LT, 3=LE, 4=GT, 5=GE, 6=ULT, 7=ULE, 8=UGT, 9=UGE
            cond = self._fetch_u8()
            rs1 = self._fetch_u8()
            a = self.regs.read_gp(rs1)
            b = self._fetch_u8()  # next byte is immediate or register
            # Treat as: [ICMP][cond][a_reg][b_reg] — 4 bytes
            # Actually re-read: we already fetched cond and rs1. The third byte is rs2.
            # We already consumed the third byte above. Let's use it.
            b_val = self.regs.read_gp(b & 0x3F)
            conditions = {
                0: a == b_val,   # EQ
                1: a != b_val,   # NE
                2: a < b_val,    # LT (signed)
                3: a <= b_val,   # LE
                4: a > b_val,    # GT
                5: a >= b_val,   # GE
                6: (a & 0xFFFFFFFF) < (b_val & 0xFFFFFFFF),  # ULT
                7: (a & 0xFFFFFFFF) <= (b_val & 0xFFFFFFFF), # ULE
                8: (a & 0xFFFFFFFF) > (b_val & 0xFFFFFFFF),  # UGT
                9: (a & 0xFFFFFFFF) >= (b_val & 0xFFFFFFFF), # UGE
            }
            result = 1 if conditions.get(cond, False) else 0
            self.regs.write_gp(rs1, result)
            self._set_flags(result)
            return

        # ── Comparison: IEQ, ILT, ILE, IGT, IGE ───────────────────────────
        if opcode_byte == Op.IEQ:
            rd, rs1 = self._decode_operands_C()
            result = 1 if self.regs.read_gp(rd) == self.regs.read_gp(rs1) else 0
            self.regs.write_gp(rd, result)
            self._set_flags(result)
            return

        if opcode_byte == Op.ILT:
            rd, rs1 = self._decode_operands_C()
            result = 1 if self.regs.read_gp(rd) < self.regs.read_gp(rs1) else 0
            self.regs.write_gp(rd, result)
            self._set_flags(result)
            return

        if opcode_byte == Op.ILE:
            rd, rs1 = self._decode_operands_C()
            result = 1 if self.regs.read_gp(rd) <= self.regs.read_gp(rs1) else 0
            self.regs.write_gp(rd, result)
            self._set_flags(result)
            return

        if opcode_byte == Op.IGT:
            rd, rs1 = self._decode_operands_C()
            result = 1 if self.regs.read_gp(rd) > self.regs.read_gp(rs1) else 0
            self.regs.write_gp(rd, result)
            self._set_flags(result)
            return

        if opcode_byte == Op.IGE:
            rd, rs1 = self._decode_operands_C()
            result = 1 if self.regs.read_gp(rd) >= self.regs.read_gp(rs1) else 0
            self.regs.write_gp(rd, result)
            self._set_flags(result)
            return

        # ── Comparison: TEST (logical AND without storing result) ──────────
        if opcode_byte == Op.TEST:
            rd, rs1 = self._decode_operands_C()
            result = self.regs.read_gp(rd) & self.regs.read_gp(rs1)
            self._set_flags(result)
            return

        # ── Comparison: SETCC (set register based on condition flags) ──────
        if opcode_byte == Op.SETCC:
            (rd,) = self._decode_operands_B()
            # Next byte is condition code:
            # 0=EQ(z), 1=NE(!z), 2=LT(s), 3=GE(!s), 4=GT(!z&!s), 5=LE(z|s)
            cond = self._fetch_u8()
            conditions = {
                0: self._flag_zero,                      # EQ
                1: not self._flag_zero,                   # NE
                2: self._flag_sign,                       # LT
                3: not self._flag_sign,                   # GE
                4: not self._flag_zero and not self._flag_sign,  # GT
                5: self._flag_zero or self._flag_sign,    # LE
                6: self._flag_carry,                      # CS/HS
                7: not self._flag_carry,                  # CC/LO
                8: self._flag_overflow,                   # VS
                9: not self._flag_overflow,               # VC
            }
            result = 1 if conditions.get(cond, False) else 0
            self.regs.write_gp(rd, result)
            return

        # ── Stack: PUSH / POP ──────────────────────────────────────────────
        if opcode_byte == Op.PUSH:
            (reg,) = self._decode_operands_B()
            self._stack_push(self.regs.read_gp(reg))
            return

        if opcode_byte == Op.POP:
            (reg,) = self._decode_operands_B()
            self.regs.write_gp(reg, self._stack_pop())
            return

        # ── Stack: DUP (duplicate top of stack) ────────────────────────────
        if opcode_byte == Op.DUP:
            # Format A: reads top of stack, pushes a copy
            stack = self.memory.get_region("stack")
            val, _ = self.memory.stack_pop(stack, self.regs.sp)
            new_sp = self.memory.stack_push(val, stack, self.regs.sp)
            self.regs.sp = new_sp
            new_sp2 = self.memory.stack_push(val, stack, self.regs.sp)
            self.regs.sp = new_sp2
            return

        # ── Stack: SWAP (swap top two stack values) ───────────────────────
        if opcode_byte == Op.SWAP:
            # Format A: swap top two stack elements
            stack = self.memory.get_region("stack")
            a, sp1 = self.memory.stack_pop(stack, self.regs.sp)
            b, sp2 = self.memory.stack_pop(stack, sp1)
            sp3 = self.memory.stack_push(a, stack, sp2)
            sp4 = self.memory.stack_push(b, stack, sp3)
            self.regs.sp = sp4
            return

        # ── Stack: ROT (rotate top 3 stack values) ────────────────────────
        if opcode_byte == Op.ROT:
            # Format A: rotates top 3 stack elements: [c, b, a] -> [b, a, c]
            stack = self.memory.get_region("stack")
            a, sp1 = self.memory.stack_pop(stack, self.regs.sp)
            b, sp2 = self.memory.stack_pop(stack, sp1)
            c, sp3 = self.memory.stack_pop(stack, sp2)
            sp4 = self.memory.stack_push(a, stack, sp3)
            sp5 = self.memory.stack_push(c, stack, sp4)
            sp6 = self.memory.stack_push(b, stack, sp5)
            self.regs.sp = sp6
            return

        # ── Stack: ENTER (push frame pointer, set new frame) ───────────────
        if opcode_byte == Op.ENTER:
            # Format B: [ENTER][frame_size:u8]
            # frame_size is in units of 4 bytes
            (frame_size,) = self._decode_operands_B()
            # Save old FP, push it
            self._frame_stack.append(self.regs.fp)
            self._stack_push(self.regs.fp)
            # Set FP to current SP
            self.regs.fp = self.regs.sp
            # Allocate frame space
            alloc_bytes = frame_size * 4
            if self.regs.sp - alloc_bytes < 0:
                raise VMStackOverflowError(
                    "ENTER: frame allocation exceeds stack",
                    opcode=opcode_byte,
                    pc=start_pc,
                )
            self.regs.sp -= alloc_bytes
            return

        # ── Stack: LEAVE (restore frame pointer, deallocate) ───────────────
        if opcode_byte == Op.LEAVE:
            # Format B: [LEAVE][unused:u8]
            (unused,) = self._decode_operands_B()
            # Restore SP to FP
            self.regs.sp = self.regs.fp
            # Pop old FP
            old_fp = self._stack_pop()
            self.regs.fp = old_fp
            return

        # ── Stack: ALLOCA (allocate stack space) ───────────────────────────
        if opcode_byte == Op.ALLOCA:
            # Format C: [ALLOCA][rd:u8][size_reg:u8]
            rd, size_reg = self._decode_operands_C()
            size = self.regs.read_gp(size_reg) * 4  # size in 4-byte units
            new_sp = self.regs.sp - size
            if new_sp < 0:
                raise VMStackOverflowError(
                    "ALLOCA: allocation exceeds stack",
                    opcode=opcode_byte,
                    pc=start_pc,
                )
            self.regs.sp = new_sp
            self.regs.write_gp(rd, self.regs.sp)  # return pointer to allocation
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
            if not self._flag_zero and not self._flag_sign:
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
            # Push return address (current PC)
            self._stack_push(self.pc)
            self.pc += offset
            return

        if opcode_byte == Op.CALL_IND:
            # Format C: [CALL_IND][rd:u8][target_reg:u8]
            rd, target_reg = self._decode_operands_C()
            target = self.regs.read_gp(target_reg)
            self._stack_push(self.pc)
            self.pc = target
            return

        if opcode_byte == Op.TAILCALL:
            # Format D: [TAILCALL][unused:u8][offset:i16]
            _, offset = self._decode_operands_D()
            # Jump without pushing return address (tail call optimization)
            self.pc += offset
            return

        if opcode_byte == Op.RET:
            stack = self.memory.get_region("stack")
            # Check if stack is empty (returning from main function)
            if self.regs.sp >= stack.size - 4:
                # Stack is empty, halt the VM
                self.halted = True
                return
            addr = self._stack_pop()
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

        # ── Memory: REGION_CREATE (Format G) ──────────────────────────────
        if opcode_byte == Op.REGION_CREATE:
            data = self._fetch_var_data()
            # data: [name_len:u8][name_bytes][size:u32_le][owner_len:u8][owner_bytes]
            idx = 0
            name_len = data[idx]; idx += 1
            name = data[idx:idx + name_len].decode('utf-8', errors='replace').rstrip('\x00'); idx += name_len
            size = struct.unpack_from('<I', data, idx)[0]; idx += 4
            owner_len = data[idx]; idx += 1
            owner = data[idx:idx + owner_len].decode('utf-8', errors='replace').rstrip('\x00')
            region = self.memory.create_region(name, size, owner)
            # Store region base pointer in R0
            self.regs.write_gp(0, 0)  # regions are addressed by name
            return

        # ── Memory: REGION_DESTROY (Format G) ─────────────────────────────
        if opcode_byte == Op.REGION_DESTROY:
            data = self._fetch_var_data()
            name = data.decode('utf-8', errors='replace').rstrip('\x00')
            self.memory.destroy_region(name)
            return

        # ── Memory: REGION_TRANSFER (Format G) ────────────────────────────
        if opcode_byte == Op.REGION_TRANSFER:
            data = self._fetch_var_data()
            # [name_len:u8][name][new_owner_len:u8][new_owner]
            idx = 0
            name_len = data[idx]; idx += 1
            name = data[idx:idx + name_len].decode('utf-8', errors='replace').rstrip('\x00'); idx += name_len
            new_owner_len = data[idx]; idx += 1
            new_owner = data[idx:idx + new_owner_len].decode('utf-8', errors='replace').rstrip('\x00')
            self.memory.transfer_region(name, new_owner)
            return

        # ── Memory: MEMCOPY (Format G) ────────────────────────────────────
        if opcode_byte == Op.MEMCOPY:
            data = self._fetch_var_data()
            # [region_name_len:u8][region_name][src_offset:u32][dst_offset:u32][size:u32]
            idx = 0
            rname_len = data[idx]; idx += 1
            rname = data[idx:idx + rname_len].decode('utf-8', errors='replace').rstrip('\x00'); idx += rname_len
            src_off = struct.unpack_from('<I', data, idx)[0]; idx += 4
            dst_off = struct.unpack_from('<I', data, idx)[0]; idx += 4
            size = struct.unpack_from('<I', data, idx)[0]
            region = self.memory.get_region(rname)
            chunk = region.read(src_off, size)
            region.write(dst_off, chunk)
            return

        # ── Memory: MEMSET (Format G) ─────────────────────────────────────
        if opcode_byte == Op.MEMSET:
            data = self._fetch_var_data()
            # [region_name_len:u8][region_name][offset:u32][value:u8][size:u32]
            idx = 0
            rname_len = data[idx]; idx += 1
            rname = data[idx:idx + rname_len].decode('utf-8', errors='replace').rstrip('\x00'); idx += rname_len
            offset = struct.unpack_from('<I', data, idx)[0]; idx += 4
            value = data[idx]; idx += 1
            size = struct.unpack_from('<I', data, idx)[0]
            region = self.memory.get_region(rname)
            region.write(offset, bytes([value]) * size)
            return

        # ── Memory: MEMCMP (Format G) ─────────────────────────────────────
        if opcode_byte == Op.MEMCMP:
            data = self._fetch_var_data()
            # [region_name_len:u8][region_name][off_a:u32][off_b:u32][size:u32]
            idx = 0
            rname_len = data[idx]; idx += 1
            rname = data[idx:idx + rname_len].decode('utf-8', errors='replace').rstrip('\x00'); idx += rname_len
            off_a = struct.unpack_from('<I', data, idx)[0]; idx += 4
            off_b = struct.unpack_from('<I', data, idx)[0]; idx += 4
            size = struct.unpack_from('<I', data, idx)[0]
            region = self.memory.get_region(rname)
            a = region.read(off_a, size)
            b = region.read(off_b, size)
            result = (a > b) - (a < b)  # -1, 0, or 1
            self.regs.write_gp(0, result)
            return

        # ── Comparison: CMP (set flags from subtraction) ───────────────────
        if opcode_byte == Op.CMP:
            rd, rs1 = self._decode_operands_C()
            self._set_cmp_flags(self.regs.read_gp(rd), self.regs.read_gp(rs1))
            return

        # ── Type: CAST (format C) ─────────────────────────────────────────
        if opcode_byte == Op.CAST:
            # Format C: [CAST][rd:u8][rs1:u8]
            # Also reads a type tag from the next byte after operands
            rd, rs1 = self._decode_operands_C()
            # Cast: interpret bits as different type
            # Type tag: 0=i32->f32, 1=f32->i32, 2=i32->bool, 3=bool->i32
            type_tag = self._fetch_u8()
            val = self.regs.read_gp(rs1)
            if type_tag == 0:  # i32 -> f32
                bytes_val = struct.pack('<i', val)
                fval = struct.unpack('<f', bytes_val)[0]
                self.regs.write_gp(rd, int(fval * 1000))  # approximate
            elif type_tag == 1:  # f32 -> i32
                self.regs.write_gp(rd, val)
            elif type_tag == 2:  # i32 -> bool
                self.regs.write_gp(rd, 1 if val != 0 else 0)
            elif type_tag == 3:  # bool -> i32
                self.regs.write_gp(rd, val)
            else:
                self.regs.write_gp(rd, val)
            return

        # ── Type: BOX (allocate a boxed value) ─────────────────────────────
        if opcode_byte == Op.BOX:
            # Format C: [BOX][rd:u8][type_tag:u8] + reads value from next u32
            rd, type_tag = self._decode_operands_C()
            # Read boxed value from next 4 bytes in bytecode stream
            raw = self._fetch_i32()
            box_id = self._box_counter
            self._box_counter += 1
            self._box_table.append((type_tag, raw))
            self.regs.write_gp(rd, box_id)
            return

        # ── Type: UNBOX (retrieve boxed value) ─────────────────────────────
        if opcode_byte == Op.UNBOX:
            # Format C: [UNBOX][rd:u8][box_id_reg:u8]
            rd, box_reg = self._decode_operands_C()
            box_id = self.regs.read_gp(box_reg)
            if box_id < 0 or box_id >= len(self._box_table):
                raise VMTypeError(
                    f"UNBOX: invalid box id {box_id}",
                    opcode=opcode_byte,
                    pc=start_pc,
                )
            _, value = self._box_table[box_id]
            self.regs.write_gp(rd, int(value))
            return

        # ── Type: CHECK_TYPE ───────────────────────────────────────────────
        if opcode_byte == Op.CHECK_TYPE:
            # Format C: [CHECK_TYPE][box_reg:u8][expected_type:u8]
            box_reg, expected = self._decode_operands_C()
            box_id = self.regs.read_gp(box_reg)
            if box_id < 0 or box_id >= len(self._box_table):
                raise VMTypeError(
                    f"CHECK_TYPE: invalid box id {box_id}",
                    opcode=opcode_byte,
                    pc=start_pc,
                )
            actual_type, _ = self._box_table[box_id]
            if actual_type != expected:
                raise VMTypeError(
                    f"CHECK_TYPE: expected type {expected}, got {actual_type}",
                    opcode=opcode_byte,
                    pc=start_pc,
                )
            return

        # ── Type: CHECK_BOUNDS ─────────────────────────────────────────────
        if opcode_byte == Op.CHECK_BOUNDS:
            # Format C: [CHECK_BOUNDS][index_reg:u8][length_reg:u8]
            idx_reg, len_reg = self._decode_operands_C()
            index = self.regs.read_gp(idx_reg)
            length = self.regs.read_gp(len_reg)
            if index < 0 or index >= length:
                raise VMTypeError(
                    f"CHECK_BOUNDS: index {index} out of bounds [0, {length})",
                    opcode=opcode_byte,
                    pc=start_pc,
                )
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

        # ── Float: FABS ────────────────────────────────────────────────────
        if opcode_byte == Op.FABS:
            fd, fs1 = self._decode_operands_C()
            result = abs(self.regs.read_fp(fs1))
            self.regs.write_fp(fd, result)
            return

        # ── Float: FMIN ────────────────────────────────────────────────────
        if opcode_byte == Op.FMIN:
            fd, fs1 = self._decode_operands_C()
            result = min(self.regs.read_fp(fs1), self.regs.read_fp(fd))
            self.regs.write_fp(fd, result)
            return

        # ── Float: FMAX ────────────────────────────────────────────────────
        if opcode_byte == Op.FMAX:
            fd, fs1 = self._decode_operands_C()
            result = max(self.regs.read_fp(fs1), self.regs.read_fp(fd))
            self.regs.write_fp(fd, result)
            return

        # ── Float Comparison: FEQ, FLT, FLE, FGT, FGE ─────────────────────
        if opcode_byte == Op.FEQ:
            fd, fs1 = self._decode_operands_C()
            result = 1.0 if self.regs.read_fp(fd) == self.regs.read_fp(fs1) else 0.0
            # Store as integer 0/1 in GP register mapped from fd
            self.regs.write_gp(fd, 1 if self.regs.read_fp(fd) == self.regs.read_fp(fs1) else 0)
            return

        if opcode_byte == Op.FLT:
            fd, fs1 = self._decode_operands_C()
            self.regs.write_gp(fd, 1 if self.regs.read_fp(fd) < self.regs.read_fp(fs1) else 0)
            return

        if opcode_byte == Op.FLE:
            fd, fs1 = self._decode_operands_C()
            self.regs.write_gp(fd, 1 if self.regs.read_fp(fd) <= self.regs.read_fp(fs1) else 0)
            return

        if opcode_byte == Op.FGT:
            fd, fs1 = self._decode_operands_C()
            self.regs.write_gp(fd, 1 if self.regs.read_fp(fd) > self.regs.read_fp(fs1) else 0)
            return

        if opcode_byte == Op.FGE:
            fd, fs1 = self._decode_operands_C()
            self.regs.write_gp(fd, 1 if self.regs.read_fp(fd) >= self.regs.read_fp(fs1) else 0)
            return

        # ── SIMD: VLOAD ────────────────────────────────────────────────────
        if opcode_byte == Op.VLOAD:
            # Format C: [VLOAD][vd:u8][addr_reg:u8]
            # Load 16 bytes from memory into vector register
            vd, addr_reg = self._decode_operands_C()
            addr = self.regs.read_gp(addr_reg)
            stack = self.memory.get_region("stack")
            vec_data = stack.read(addr, 16)
            self.regs.write_vec(vd, vec_data)
            return

        # ── SIMD: VSTORE ───────────────────────────────────────────────────
        if opcode_byte == Op.VSTORE:
            # Format C: [VSTORE][vs:u8][addr_reg:u8]
            vs, addr_reg = self._decode_operands_C()
            addr = self.regs.read_gp(addr_reg)
            vec_data = self.regs.read_vec(vs)
            stack = self.memory.get_region("stack")
            stack.write(addr, vec_data)
            return

        # ── SIMD: VADD ─────────────────────────────────────────────────────
        if opcode_byte == Op.VADD:
            # Format C: [VADD][vd:u8][vs1:u8] — adds vs1 into vd
            vd, vs1 = self._decode_operands_C()
            a = self.regs.read_vec(vd)
            b = self.regs.read_vec(vs1)
            result = bytes(x + y for x, y in zip(a, b))
            self.regs.write_vec(vd, result)
            return

        # ── SIMD: VSUB ─────────────────────────────────────────────────────
        if opcode_byte == Op.VSUB:
            vd, vs1 = self._decode_operands_C()
            a = self.regs.read_vec(vd)
            b = self.regs.read_vec(vs1)
            result = bytes(x - y for x, y in zip(a, b))
            self.regs.write_vec(vd, result)
            return

        # ── SIMD: VMUL ─────────────────────────────────────────────────────
        if opcode_byte == Op.VMUL:
            vd, vs1 = self._decode_operands_C()
            a = self.regs.read_vec(vd)
            b = self.regs.read_vec(vs1)
            result = bytes(x * y for x, y in zip(a, b))
            self.regs.write_vec(vd, result)
            return

        # ── SIMD: VDIV ─────────────────────────────────────────────────────
        if opcode_byte == Op.VDIV:
            vd, vs1 = self._decode_operands_C()
            a = self.regs.read_vec(vd)
            b = self.regs.read_vec(vs1)
            # Check for division by zero
            if any(y == 0 for y in b):
                raise VMDivisionByZeroError(
                    "VDIV: division by zero in vector element",
                    opcode=opcode_byte,
                    pc=start_pc,
                )
            result = bytes(int(x / y) for x, y in zip(a, b))
            self.regs.write_vec(vd, result)
            return

        # ── SIMD: VFMA (fused multiply-add) ────────────────────────────────
        if opcode_byte == Op.VFMA:
            # Format E: [VFMA][vd:u8][vs1:u8][vs2:u8]
            # vd = vd + (vs1 * vs2)
            vd, vs1, vs2 = self._decode_operands_E()
            acc = self.regs.read_vec(vd)
            a = self.regs.read_vec(vs1)
            b = self.regs.read_vec(vs2)
            result = bytes(acc[i] + a[i] * b[i] for i in range(16))
            self.regs.write_vec(vd, result)
            return

        # ═══════════════════════════════════════════════════════════════════
        # A2A Protocol Opcodes (0x60-0x7F) — all Format G
        # ═══════════════════════════════════════════════════════════════════

        # ── A2A: TELL ──────────────────────────────────────────────────────
        if opcode_byte == Op.TELL:
            data = self._fetch_var_data()
            self._dispatch_a2a("TELL", data)
            return

        # ── A2A: ASK ───────────────────────────────────────────────────────
        if opcode_byte == Op.ASK:
            data = self._fetch_var_data()
            self._dispatch_a2a("ASK", data)
            return

        # ── A2A: DELEGATE ──────────────────────────────────────────────────
        if opcode_byte == Op.DELEGATE:
            data = self._fetch_var_data()
            self._dispatch_a2a("DELEGATE", data)
            return

        # ── A2A: DELEGATE_RESULT ───────────────────────────────────────────
        if opcode_byte == Op.DELEGATE_RESULT:
            data = self._fetch_var_data()
            self._dispatch_a2a("DELEGATE_RESULT", data)
            return

        # ── A2A: REPORT_STATUS ─────────────────────────────────────────────
        if opcode_byte == Op.REPORT_STATUS:
            data = self._fetch_var_data()
            self._dispatch_a2a("REPORT_STATUS", data)
            return

        # ── A2A: REQUEST_OVERRIDE ──────────────────────────────────────────
        if opcode_byte == Op.REQUEST_OVERRIDE:
            data = self._fetch_var_data()
            self._dispatch_a2a("REQUEST_OVERRIDE", data)
            return

        # ── A2A: BROADCAST ─────────────────────────────────────────────────
        if opcode_byte == Op.BROADCAST:
            data = self._fetch_var_data()
            self._dispatch_a2a("BROADCAST", data)
            return

        # ── A2A: REDUCE ────────────────────────────────────────────────────
        if opcode_byte == Op.REDUCE:
            data = self._fetch_var_data()
            self._dispatch_a2a("REDUCE", data)
            return

        # ── A2A: DECLARE_INTENT ────────────────────────────────────────────
        if opcode_byte == Op.DECLARE_INTENT:
            data = self._fetch_var_data()
            self._dispatch_a2a("DECLARE_INTENT", data)
            return

        # ── A2A: ASSERT_GOAL ───────────────────────────────────────────────
        if opcode_byte == Op.ASSERT_GOAL:
            data = self._fetch_var_data()
            self._dispatch_a2a("ASSERT_GOAL", data)
            return

        # ── A2A: VERIFY_OUTCOME ────────────────────────────────────────────
        if opcode_byte == Op.VERIFY_OUTCOME:
            data = self._fetch_var_data()
            self._dispatch_a2a("VERIFY_OUTCOME", data)
            return

        # ── A2A: EXPLAIN_FAILURE ───────────────────────────────────────────
        if opcode_byte == Op.EXPLAIN_FAILURE:
            data = self._fetch_var_data()
            self._dispatch_a2a("EXPLAIN_FAILURE", data)
            return

        # ── A2A: SET_PRIORITY ──────────────────────────────────────────────
        if opcode_byte == Op.SET_PRIORITY:
            data = self._fetch_var_data()
            self._dispatch_a2a("SET_PRIORITY", data)
            return

        # ── A2A Trust: TRUST_CHECK ─────────────────────────────────────────
        if opcode_byte == Op.TRUST_CHECK:
            data = self._fetch_var_data()
            self._dispatch_a2a("TRUST_CHECK", data)
            return

        # ── A2A Trust: TRUST_UPDATE ────────────────────────────────────────
        if opcode_byte == Op.TRUST_UPDATE:
            data = self._fetch_var_data()
            self._dispatch_a2a("TRUST_UPDATE", data)
            return

        # ── A2A Trust: TRUST_QUERY ─────────────────────────────────────────
        if opcode_byte == Op.TRUST_QUERY:
            data = self._fetch_var_data()
            self._dispatch_a2a("TRUST_QUERY", data)
            return

        # ── A2A Trust: REVOKE_TRUST ────────────────────────────────────────
        if opcode_byte == Op.REVOKE_TRUST:
            data = self._fetch_var_data()
            self._dispatch_a2a("REVOKE_TRUST", data)
            return

        # ── A2A Capability: CAP_REQUIRE ────────────────────────────────────
        if opcode_byte == Op.CAP_REQUIRE:
            data = self._fetch_var_data()
            self._dispatch_a2a("CAP_REQUIRE", data)
            return

        # ── A2A Capability: CAP_REQUEST ────────────────────────────────────
        if opcode_byte == Op.CAP_REQUEST:
            data = self._fetch_var_data()
            self._dispatch_a2a("CAP_REQUEST", data)
            return

        # ── A2A Capability: CAP_GRANT ──────────────────────────────────────
        if opcode_byte == Op.CAP_GRANT:
            data = self._fetch_var_data()
            self._dispatch_a2a("CAP_GRANT", data)
            return

        # ── A2A Capability: CAP_REVOKE ─────────────────────────────────────
        if opcode_byte == Op.CAP_REVOKE:
            data = self._fetch_var_data()
            self._dispatch_a2a("CAP_REVOKE", data)
            return

        # ── A2A Synchronization: BARRIER ───────────────────────────────────
        if opcode_byte == Op.BARRIER:
            data = self._fetch_var_data()
            self._dispatch_a2a("BARRIER", data)
            return

        # ── A2A Synchronization: SYNC_CLOCK ────────────────────────────────
        if opcode_byte == Op.SYNC_CLOCK:
            data = self._fetch_var_data()
            self._dispatch_a2a("SYNC_CLOCK", data)
            return

        # ── A2A: FORMATION_UPDATE ──────────────────────────────────────────
        if opcode_byte == Op.FORMATION_UPDATE:
            data = self._fetch_var_data()
            self._dispatch_a2a("FORMATION_UPDATE", data)
            return

        # ── A2A: EMERGENCY_STOP ───────────────────────────────────────────
        if opcode_byte == Op.EMERGENCY_STOP:
            # Format A: immediate stop
            self.running = False
            self.halted = True
            self._dispatch_a2a("EMERGENCY_STOP", b"")
            return

        # ═══════════════════════════════════════════════════════════════════
        # System Opcodes (0x80-0x9F)
        # ═══════════════════════════════════════════════════════════════════

        # ── System: YIELD ──────────────────────────────────────────────────
        if opcode_byte == Op.YIELD:
            # Format A: cooperative yield (no-op in single-threaded interpreter)
            return

        # ── System: RESOURCE_ACQUIRE (Format G) ───────────────────────────
        if opcode_byte == Op.RESOURCE_ACQUIRE:
            data = self._fetch_var_data()
            # data contains resource_id as u32
            if len(data) >= 4:
                res_id = struct.unpack_from('<I', data, 0)[0]
                self._resources[res_id] = True
                self.regs.write_gp(0, 0)  # success
            else:
                self.regs.write_gp(0, 1)  # failure
            return

        # ── System: RESOURCE_RELEASE (Format G) ───────────────────────────
        if opcode_byte == Op.RESOURCE_RELEASE:
            data = self._fetch_var_data()
            if len(data) >= 4:
                res_id = struct.unpack_from('<I', data, 0)[0]
                if res_id in self._resources:
                    self._resources[res_id] = False
                self.regs.write_gp(0, 0)  # success
            else:
                self.regs.write_gp(0, 1)  # failure
            return

        # ── System: DEBUG_BREAK ────────────────────────────────────────────
        if opcode_byte == Op.DEBUG_BREAK:
            # Format A: trigger debug callback if registered
            if self._io_write_cb is not None:
                self._io_write_cb(f"DEBUG_BREAK at pc={start_pc}")
            return

        # ── Unknown opcode ─────────────────────────────────────────────────
        raise VMInvalidOpcodeError(
            f"Unknown opcode: 0x{opcode_byte:02X}",
            opcode=opcode_byte,
            pc=start_pc,
        )
