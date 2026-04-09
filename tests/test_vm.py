"""FLUX Micro-VM Interpreter Tests.

Constructs raw bytecode bytes manually and verifies the interpreter
produces correct register / memory / state results.

Encoding reference:
    Format A (1 byte):  [opcode]
    Format B (2 bytes): [opcode][reg]
    Format C (3 bytes): [opcode][rd][rs1]
    Format D (4 bytes): [opcode][rs1][off_lo][off_hi]   (signed i16, LE)
    Format E (4 bytes): [opcode][rd][rs1][rs2]
    MOVI   (4 bytes):  [opcode][reg][imm_lo][imm_hi]     (signed i16, LE)
"""

import struct
import sys
import os

# Ensure the project source root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from flux.bytecode.opcodes import Op
from flux.vm.interpreter import (
    Interpreter,
    VMError,
    VMHaltError,
    VMStackOverflowError,
    VMInvalidOpcodeError,
    VMDivisionByZeroError,
)
from flux.vm.registers import RegisterFile
from flux.vm.memory import MemoryRegion, MemoryManager


# ── Helper ─────────────────────────────────────────────────────────────────

def _i16_le(val: int) -> bytes:
    """Pack a signed 16-bit integer as little-endian bytes."""
    return struct.pack("<h", val)


def _u16_le(val: int) -> bytes:
    """Pack an unsigned 16-bit integer as little-endian bytes."""
    return struct.pack("<H", val)


# ── Tests ──────────────────────────────────────────────────────────────────

def test_nop() -> None:
    """NOP executes and increments cycle count."""
    # NOP (1 byte) + HALT (1 byte) = 2 cycles
    bytecode = bytes([Op.NOP, Op.HALT])
    vm = Interpreter(bytecode)
    cycles = vm.execute()
    assert cycles == 2, f"Expected 2 cycles, got {cycles}"
    assert vm.halted is True


def test_halt() -> None:
    """HALT stops execution after 1 cycle."""
    bytecode = bytes([Op.HALT])
    vm = Interpreter(bytecode)
    cycles = vm.execute()
    assert cycles == 1, f"Expected 1 cycle, got {cycles}"
    assert vm.halted is True
    assert vm.running is False


def test_mov() -> None:
    """MOV R0, R1 copies R1's value into R0."""
    bytecode = bytes([Op.MOV, 0x00, 0x01, Op.HALT])  # MOV R0, R1; HALT
    vm = Interpreter(bytecode)
    vm.regs.write_gp(1, 42)
    vm.execute()
    assert vm.regs.read_gp(0) == 42, f"Expected R0=42, got R0={vm.regs.read_gp(0)}"


def test_add() -> None:
    """IADD R0, R1, R2 computes R0 = R1 + R2."""
    bytecode = bytes([Op.IADD, 0x00, 0x01, 0x02, Op.HALT])
    vm = Interpreter(bytecode)
    vm.regs.write_gp(1, 10)
    vm.regs.write_gp(2, 20)
    vm.execute()
    assert vm.regs.read_gp(0) == 30, f"Expected R0=30, got R0={vm.regs.read_gp(0)}"


def test_push_pop() -> None:
    """PUSH and POP work correctly on the stack."""
    # PUSH R0; POP R1; HALT
    bytecode = bytes([Op.PUSH, 0x00, Op.POP, 0x01, Op.HALT])
    vm = Interpreter(bytecode)
    initial_sp = vm.regs.sp
    vm.regs.write_gp(0, 42)

    vm.execute()

    assert vm.regs.read_gp(1) == 42, f"Expected R1=42, got R1={vm.regs.read_gp(1)}"
    assert vm.regs.sp == initial_sp, f"SP not restored: expected {initial_sp}, got {vm.regs.sp}"


def test_jump_forward() -> None:
    """JMP skips over instructions ahead."""
    # Byte 0: JMP +5  (skip to byte 9)
    # Byte 4: INC R0  (should be skipped)
    # Byte 6: INC R0  (should be skipped)
    # Byte 8: INC R0  (should be skipped)
    # Byte 10: HALT
    # offset = 6  (PC after JMP=4, target=10, so offset=10-4=6)
    bytecode = bytes([
        Op.JMP, 0x00, 0x06, 0x00,   # 0: JMP +6 -> PC becomes 10
        Op.INC, 0x00,                # 4: INC R0 (skipped)
        Op.INC, 0x00,                # 6: INC R0 (skipped)
        Op.INC, 0x00,                # 8: INC R0 (skipped)
        Op.HALT,                     # 10: HALT
    ])
    vm = Interpreter(bytecode)
    vm.regs.write_gp(0, 0)
    vm.execute()
    assert vm.regs.read_gp(0) == 0, f"R0 should be 0 (INCs skipped), got {vm.regs.read_gp(0)}"


def test_jump_zero() -> None:
    """JZ jumps when the register value is zero."""
    # Byte 0: JZ R0, +6 -> jump to byte 10 (skip INCs)
    # Byte 4: INC R0 (skipped)
    # Byte 6: INC R0 (skipped)
    # Byte 8: INC R0 (skipped)
    # Byte 10: HALT
    bytecode = bytes([
        Op.JZ, 0x00, 0x06, 0x00,    # 0: JZ R0, +6
        Op.INC, 0x00,                # 4: INC R0 (skipped)
        Op.INC, 0x00,                # 6: INC R0 (skipped)
        Op.INC, 0x00,                # 8: INC R0 (skipped)
        Op.HALT,                     # 10: HALT
    ])
    vm = Interpreter(bytecode)
    vm.regs.write_gp(0, 0)  # R0 is zero -> jump taken
    vm.execute()
    assert vm.regs.read_gp(0) == 0, f"R0 should be 0 (jump taken), got {vm.regs.read_gp(0)}"


def test_jump_not_taken() -> None:
    """JZ does NOT jump when the register is non-zero."""
    # Same bytecode as test_jump_zero but R0 is non-zero
    bytecode = bytes([
        Op.JZ, 0x00, 0x06, 0x00,
        Op.INC, 0x00,
        Op.INC, 0x00,
        Op.INC, 0x00,
        Op.HALT,
    ])
    vm = Interpreter(bytecode)
    vm.regs.write_gp(0, 7)  # R0 is non-zero -> jump NOT taken, INCs execute
    vm.execute()
    assert vm.regs.read_gp(0) == 10, f"R0 should be 10 (3 INCs), got {vm.regs.read_gp(0)}"


def test_call_return() -> None:
    """CALL pushes return address; RET jumps back."""
    # Byte 0:  CALL +5  -> push PC=4, jump to PC=9
    # Byte 4:  HALT     <- return lands here
    # Byte 5:  NOP
    # Byte 6:  NOP
    # Byte 7:  NOP
    # Byte 8:  NOP
    # Byte 9:  MOV R0, R1  <- subroutine body
    # Byte 12: RET          <- pop 4, PC=4
    bytecode = bytes([
        Op.CALL, 0x00, 0x05, 0x00,  # 0:  CALL +5 -> PC=9
        Op.HALT,                     # 4:  HALT (return target)
        Op.NOP,                      # 5:  padding
        Op.NOP,                      # 6:  padding
        Op.NOP,                      # 7:  padding
        Op.NOP,                      # 8:  padding
        Op.MOV, 0x00, 0x01,          # 9:  MOV R0, R1
        Op.RET,                      # 12: RET
    ])
    vm = Interpreter(bytecode)
    vm.regs.write_gp(1, 99)
    vm.execute()
    assert vm.regs.read_gp(0) == 99, f"R0 should be 99, got {vm.regs.read_gp(0)}"
    assert vm.halted is True


def test_loop() -> None:
    """DEC + JNZ implements a countdown loop."""
    # Byte 0: DEC R0
    # Byte 2: JNZ R0, -6  -> back to byte 0
    # Byte 6: HALT
    # -6 as i16 LE = 0xFA, 0xFF
    bytecode = bytes([
        Op.DEC, 0x00,                # 0: DEC R0
        Op.JNZ, 0x00, 0xFA, 0xFF,    # 2: JNZ R0, -6 -> back to byte 0
        Op.HALT,                     # 6: HALT
    ])
    vm = Interpreter(bytecode)
    vm.regs.write_gp(0, 3)  # countdown from 3
    vm.execute()
    assert vm.regs.read_gp(0) == 0, f"R0 should be 0 after loop, got {vm.regs.read_gp(0)}"
    assert vm.halted is True
    # 3 DECs + 3 JNZs (not taken last) + 1 HALT = 7 cycles
    assert vm.cycle_count == 7, f"Expected 7 cycles, got {vm.cycle_count}"


def test_division_by_zero() -> None:
    """IDIV by zero raises VMDivisionByZeroError."""
    # IDIV R0, R1, R2: R0 = R1 / R2, with R2 = 0
    bytecode = bytes([Op.IDIV, 0x00, 0x01, 0x02])
    vm = Interpreter(bytecode)
    vm.regs.write_gp(1, 10)
    vm.regs.write_gp(2, 0)

    try:
        vm.execute()
        assert False, "Expected VMDivisionByZeroError"
    except VMDivisionByZeroError as e:
        assert e.opcode == Op.IDIV
        assert e.pc == 0


def test_cycle_budget() -> None:
    """Exceeding max cycles stops execution gracefully."""
    # Byte 0: JMP -4  -> infinite loop (PC=4, offset=-4, PC=0)
    bytecode = bytes([Op.JMP, 0x00, 0xFC, 0xFF])
    vm = Interpreter(bytecode, max_cycles=100)
    cycles = vm.execute()
    assert cycles == 100, f"Expected 100 cycles (budget), got {cycles}"
    assert vm.running is False
    assert vm.halted is False  # stopped by budget, not HALT


def test_memory_read_write() -> None:
    """STORE and LOAD work correctly through memory regions."""
    # MOVI R0, 100   -> R0 = 100 (address offset in stack region)
    # MOVI R1, 42    -> R1 = 42 (value)
    # STORE R1, R0   -> mem[R0] = R1
    # LOAD R2, R0    -> R2 = mem[R0]
    # HALT
    bytecode = bytes([
        Op.MOVI, 0x00, 100, 0x00,   # 0: MOVI R0, 100
        Op.MOVI, 0x01, 42, 0x00,    # 4: MOVI R1, 42
        Op.STORE, 0x01, 0x00,       # 8: STORE R1, R0 -> mem[100] = 42
        Op.LOAD, 0x02, 0x00,        # 11: LOAD R2, R0 -> R2 = mem[100]
        Op.HALT,                    # 14: HALT
    ])
    vm = Interpreter(bytecode)
    vm.execute()
    assert vm.regs.read_gp(2) == 42, f"R2 should be 42, got {vm.regs.read_gp(2)}"


def test_cmp_je() -> None:
    """CMP sets zero flag; JE jumps when equal."""
    # CMP R0, R1 where R0=5, R1=5 -> zero flag set
    # JE +3 -> should jump to HALT
    # INC R0 (skipped)
    # INC R0 (skipped)
    # HALT
    bytecode = bytes([
        Op.CMP, 0x00, 0x01,         # 0: CMP R0, R1
        Op.JE, 0x00, 0x05, 0x00,    # 3: JE +5 -> PC=7+5=12... wait
    ])
    # Let me recalculate:
    # CMP at byte 0 (3 bytes), after fetch PC=3
    # JE at byte 3 (4 bytes), after fetch PC=7
    # offset = target - PC_after = target - 7
    # INC at byte 7, INC at byte 9, HALT at byte 11
    # We want to skip the INCs and land at HALT at byte 11
    # offset = 11 - 7 = 4
    bytecode = bytes([
        Op.CMP, 0x00, 0x01,         # 0: CMP R0, R1 (3 bytes)
        Op.JE, 0x00, 0x04, 0x00,    # 3: JE +4 -> PC after JE=7, target=7+4=11
        Op.INC, 0x00,                # 7: INC R0 (skipped)
        Op.INC, 0x00,                # 9: INC R0 (skipped)
        Op.HALT,                     # 11: HALT
    ])
    vm = Interpreter(bytecode)
    vm.regs.write_gp(0, 5)
    vm.regs.write_gp(1, 5)
    vm.execute()
    assert vm.regs.read_gp(0) == 5, f"R0 should be 5 (JE taken, INCs skipped), got {vm.regs.read_gp(0)}"


def test_cmp_jne() -> None:
    """JNE jumps when values are not equal after CMP."""
    bytecode = bytes([
        Op.CMP, 0x00, 0x01,         # 0: CMP R0, R1
        Op.JNE, 0x00, 0x04, 0x00,   # 3: JNE +4 -> target=11
        Op.INC, 0x00,                # 7: INC R0 (skipped)
        Op.INC, 0x00,                # 9: INC R0 (skipped)
        Op.HALT,                     # 11: HALT
    ])
    vm = Interpreter(bytecode)
    vm.regs.write_gp(0, 5)
    vm.regs.write_gp(1, 3)
    vm.execute()
    assert vm.regs.read_gp(0) == 5, f"R0 should be 5 (JNE taken), got {vm.regs.read_gp(0)}"


def test_neg() -> None:
    """INEG negates a register value."""
    bytecode = bytes([Op.INEG, 0x00, 0x01, Op.HALT])  # INEG R0, R1
    vm = Interpreter(bytecode)
    vm.regs.write_gp(1, 7)
    vm.execute()
    assert vm.regs.read_gp(0) == -7, f"Expected R0=-7, got {vm.regs.read_gp(0)}"


def test_bitwise() -> None:
    """IAND, IOR, IXOR, INOT work correctly."""
    # IAND R0, R1, R2: R0 = R1 & R2
    # IOR  R3, R1, R2: R3 = R1 | R2
    # IXOR R4, R1, R2: R4 = R1 ^ R2
    # INOT R5, R1:     R5 = ~R1
    # HALT
    bytecode = bytes([
        Op.IAND, 0x00, 0x01, 0x02,  # R0 = R1 & R2
        Op.IOR,  0x03, 0x01, 0x02,  # R3 = R1 | R2
        Op.IXOR, 0x04, 0x01, 0x02,  # R4 = R1 ^ R2
        Op.INOT, 0x05, 0x01,         # R5 = ~R1
        Op.HALT,
    ])
    vm = Interpreter(bytecode)
    vm.regs.write_gp(1, 0b1100)  # 12
    vm.regs.write_gp(2, 0b1010)  # 10
    vm.execute()
    assert vm.regs.read_gp(0) == (0b1100 & 0b1010), f"IAND failed"
    assert vm.regs.read_gp(3) == (0b1100 | 0b1010), f"IOR failed"
    assert vm.regs.read_gp(4) == (0b1100 ^ 0b1010), f"IXOR failed"
    assert vm.regs.read_gp(5) == (~0b1100), f"INOT failed"


def test_mov_registers() -> None:
    """MOV and IADD use encoded register values correctly."""
    # IADD R10, R8, R9: R10 = R8 + R9
    bytecode = bytes([Op.IADD, 10, 8, 9, Op.HALT])
    vm = Interpreter(bytecode)
    vm.regs.write_gp(8, 100)
    vm.regs.write_gp(9, 200)
    vm.execute()
    assert vm.regs.read_gp(10) == 300, f"Expected R10=300, got {vm.regs.read_gp(10)}"


def test_sp_property() -> None:
    """SP property correctly aliases R11."""
    bytecode = bytes([Op.HALT])
    vm = Interpreter(bytecode)
    vm.regs.sp = 12345
    assert vm.regs.read_gp(11) == 12345, "SP should alias R11"
    vm.regs.write_gp(11, 99999)
    assert vm.regs.sp == 99999, "R11 write should reflect in SP"


def test_snapshot_restore() -> None:
    """Register snapshot/restore round-trips correctly."""
    rf = RegisterFile()
    rf.write_gp(0, 42)
    rf.write_gp(5, -1)
    rf.write_fp(3, 3.14)
    rf.write_vec(0, b"\x01\x02\x03\x04" + b"\x00" * 12)

    snap = rf.snapshot()

    # Modify registers
    rf.write_gp(0, 0)
    rf.write_gp(5, 0)
    rf.write_fp(3, 0.0)
    rf.write_vec(0, b"\x00" * 16)

    # Restore
    rf.restore(snap)
    assert rf.read_gp(0) == 42
    assert rf.read_gp(5) == -1
    assert rf.read_fp(3) == 3.14
    assert rf.read_vec(0)[:4] == b"\x01\x02\x03\x04"


def test_memory_region_read_write() -> None:
    """MemoryRegion read/write with typed helpers."""
    region = MemoryRegion("test", 256, "owner1")
    region.write_i32(0, 0xDEADBEEF if 0xDEADBEEF < (1 << 31) else 0xDEADBEEF - (1 << 32))
    val = region.read_i32(0)
    assert val == -559038737 or val == 0xDEADBEEF  # signed interpretation

    region.write_f32(4, 2.5)
    assert abs(region.read_f32(4) - 2.5) < 1e-6

    assert region.read(8, 3) == b"\x00\x00\x00"

    # Out of bounds
    try:
        region.read(255, 2)
        assert False, "Should raise IndexError"
    except IndexError:
        pass


def test_memory_manager() -> None:
    """MemoryManager region lifecycle."""
    mm = MemoryManager()
    r = mm.create_region("heap", 1024, "system")
    assert r.name == "heap"
    assert r.size == 1024

    assert mm.has_region("heap")
    assert mm.get_region("heap") is r

    mm.transfer_region("heap", "user1")
    assert r.owner == "user1"

    mm.destroy_region("heap")
    assert not mm.has_region("heap")


def test_stack_push_pop_static() -> None:
    """MemoryManager static stack helpers."""
    region = MemoryRegion("stack", 64, "system")
    sp = 64  # stack starts at top

    sp = MemoryManager.stack_push(0x12345678, region, sp)
    assert sp == 60
    assert region.read_i32(60) == 0x12345678

    val, sp = MemoryManager.stack_pop(region, sp)
    assert val == 0x12345678
    assert sp == 64


def test_dump_state() -> None:
    """dump_state returns a complete VM snapshot."""
    bytecode = bytes([Op.HALT])
    vm = Interpreter(bytecode)
    vm.regs.write_gp(0, 42)
    vm.execute()

    state = vm.dump_state()
    assert state["cycle_count"] == 1
    assert state["halted"] is True
    assert state["registers"]["gp"][0] == 42


def test_unknown_opcode() -> None:
    """Unknown opcode raises VMInvalidOpcodeError."""
    bytecode = bytes([0xFF])  # not a valid opcode
    vm = Interpreter(bytecode)
    try:
        vm.execute()
        assert False, "Expected VMInvalidOpcodeError"
    except VMInvalidOpcodeError as e:
        assert e.opcode == 0xFF
        assert e.pc == 0


# ── Runner ─────────────────────────────────────────────────────────────────

def _run_all() -> None:
    """Execute all tests and report results."""
    tests = [
        test_nop,
        test_halt,
        test_mov,
        test_add,
        test_push_pop,
        test_jump_forward,
        test_jump_zero,
        test_jump_not_taken,
        test_call_return,
        test_loop,
        test_division_by_zero,
        test_cycle_budget,
        test_memory_read_write,
        test_cmp_je,
        test_cmp_jne,
        test_neg,
        test_bitwise,
        test_mov_registers,
        test_sp_property,
        test_snapshot_restore,
        test_memory_region_read_write,
        test_memory_manager,
        test_stack_push_pop_static,
        test_dump_state,
        test_unknown_opcode,
    ]

    passed = 0
    failed = 0
    errors: list[str] = []

    for t in tests:
        name = t.__name__
        try:
            t()
            passed += 1
            print(f"  ✓ {name}")
        except Exception as e:
            failed += 1
            errors.append(f"  ✗ {name}: {e}")

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    print(f"{'='*60}")

    if errors:
        for err in errors:
            print(err)
        sys.exit(1)
    else:
        print("All VM tests passed!")


if __name__ == "__main__":
    _run_all()
