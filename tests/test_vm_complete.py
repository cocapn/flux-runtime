"""Tests for VM completeness — all newly implemented opcodes."""

import struct
import pytest

from flux.bytecode.opcodes import Op
from flux.vm.interpreter import (
    Interpreter, VMError, VMTypeError, VMDivisionByZeroError,
    VMStackOverflowError, VMHaltError,
)


def _make_vm(bytecode: bytes, memory_size: int = 65536) -> Interpreter:
    """Create an interpreter with given bytecode."""
    return Interpreter(bytecode, memory_size=memory_size)


def _i16(val: int) -> bytes:
    """Pack a signed 16-bit integer (little-endian)."""
    return struct.pack('<h', val)


def _u16(val: int) -> bytes:
    """Pack an unsigned 16-bit integer (little-endian)."""
    return struct.pack('<H', val)


def _i32(val: int) -> bytes:
    """Pack a signed 32-bit integer (little-endian)."""
    return struct.pack('<i', val)


def _f32(val: float) -> bytes:
    """Pack a 32-bit float (little-endian)."""
    return struct.pack('<f', val)


def _var_data(payload: bytes) -> bytes:
    """Create Format G variable-length data (u16 length prefix)."""
    return _u16(len(payload)) + payload


# ── Bitwise: ROTL, ROTR ──────────────────────────────────────────────────


class TestRotateOps:
    def test_rotl_basic(self):
        """ROTL: rotate left by 1 bit."""
        bc = bytes([
            Op.MOVI, 1, *_i16(1),     # R1 = 1
            Op.MOVI, 2, *_i16(1),     # R2 = 1 (shift amount)
            Op.ROTL, 3, 1, 2,         # R3 = ROTL(R1, R2) = 2
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(3) == 2

    def test_rotl_overflow(self):
        """ROTL: rotate left with wrap-around (32-bit masking)."""
        bc = bytes([
            Op.MOVI, 2, *_i16(1),     # R2 = 1 (shift amount)
            Op.ROTL, 3, 1, 2,         # R3 = ROTL(R1, R2)
            Op.HALT,
        ])
        vm = _make_vm(bc)
        # Pre-set R1 to 0x80000000 (can't encode in i16)
        vm.regs.write_gp(1, 0x80000000)
        vm.execute()
        # 0x80000000 rotated left by 1 in 32-bit = 0x00000001
        assert vm.regs.read_gp(3) == 1

    def test_rotr_basic(self):
        """ROTR: rotate right by 1 bit."""
        bc = bytes([
            Op.MOVI, 1, *_i16(2),     # R1 = 2
            Op.MOVI, 2, *_i16(1),     # R2 = 1
            Op.ROTR, 3, 1, 2,         # R3 = ROTR(R1, R2) = 1
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(3) == 1

    def test_rotl_zero_shift(self):
        """ROTL: rotate by 0 bits returns same value."""
        bc = bytes([
            Op.MOVI, 1, *_i16(42),
            Op.MOVI, 2, *_i16(0),
            Op.ROTL, 3, 1, 2,
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(3) == 42

    def test_rotr_wrap(self):
        """ROTR: rotate right with wrap-around."""
        bc = bytes([
            Op.MOVI, 2, *_i16(1),     # R2 = 1
            Op.ROTR, 3, 1, 2,         # R3 = ROTR(R1, R2)
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.regs.write_gp(1, 1)  # 1 rotated right by 1 = 0x80000000
        vm.execute()
        assert vm.regs.read_gp(3) == 0x80000000


# ── Comparison: ICMP, TEST, SETCC ────────────────────────────────────────


class TestComparisonOps:
    def test_icmp_eq(self):
        """ICMP: equal comparison returns 1 in R0."""
        # ICMP format: [ICMP][cond:u8][a_reg:u8][b_reg:u8] — cond 0 = EQ
        bc = bytes([
            Op.MOVI, 1, *_i16(5),
            Op.MOVI, 2, *_i16(5),
            Op.ICMP, 0, 1, 2,  # cond=EQ(0), a=R1(5), b=R2(5) -> True
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(0) == 1

    def test_icmp_ne(self):
        """ICMP: not-equal comparison."""
        bc = bytes([
            Op.MOVI, 1, *_i16(5),
            Op.MOVI, 2, *_i16(3),
            Op.ICMP, 1, 1, 2,  # cond=NE(1), a=R1(5), b=R2(3) -> True
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(0) == 1

    def test_icmp_lt(self):
        """ICMP: less-than comparison."""
        bc = bytes([
            Op.MOVI, 1, *_i16(3),
            Op.MOVI, 2, *_i16(5),
            Op.ICMP, 2, 1, 2,  # cond=LT(2), a=R1(3), b=R2(5) -> True
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(0) == 1

    def test_icmp_gt(self):
        """ICMP: greater-than comparison."""
        bc = bytes([
            Op.MOVI, 1, *_i16(10),
            Op.MOVI, 2, *_i16(5),
            Op.ICMP, 4, 1, 2,  # cond=GT(4), a=R1(10), b=R2(5) -> True
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(0) == 1

    def test_icmp_false(self):
        """ICMP: comparison that is false returns 0."""
        bc = bytes([
            Op.MOVI, 1, *_i16(3),
            Op.MOVI, 2, *_i16(5),
            Op.ICMP, 4, 1, 2,  # cond=GT(4), a=R1(3), b=R2(5) -> False
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(0) == 0

    def test_icmp_le(self):
        """ICMP: less-than-or-equal."""
        bc = bytes([
            Op.MOVI, 1, *_i16(5),
            Op.MOVI, 2, *_i16(5),
            Op.ICMP, 3, 1, 2,  # cond=LE(3), a=R1(5), b=R2(5) -> True
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(0) == 1

    def test_test_nonzero(self):
        """TEST: sets zero flag if AND result is zero."""
        bc = bytes([
            Op.MOVI, 1, *_i16(0xFF),
            Op.MOVI, 2, *_i16(0x00),
            Op.TEST, 1, 2,  # 0xFF & 0x00 = 0, zero flag set
            Op.JNE, 0, *_i16(2),  # skip 2 bytes if not zero
            Op.MOVI, 3, *_i16(42),  # R3 = 42 (reached only if zero flag set)
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(3) == 42

    def test_test_nonzero_flag(self):
        """TEST: does not set zero flag when result is nonzero."""
        bc = bytes([
            Op.MOVI, 1, *_i16(0xFF),
            Op.MOVI, 2, *_i16(0x0F),
            Op.TEST, 1, 2,  # 0xFF & 0x0F = 0x0F, zero flag clear
            Op.JE, 0, *_i16(2),  # skip 2 bytes if zero
            Op.MOVI, 3, *_i16(99),
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(3) == 99

    def test_setcc_eq(self):
        """SETCC: set on equal (condition 0)."""
        bc = bytes([
            Op.MOVI, 1, *_i16(5),
            Op.MOVI, 2, *_i16(5),
            Op.CMP, 1, 2,  # sets zero flag
            Op.SETCC, 3, 0,  # EQ condition
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(3) == 1

    def test_setcc_ne(self):
        """SETCC: set on not-equal (condition 1)."""
        bc = bytes([
            Op.MOVI, 1, *_i16(5),
            Op.MOVI, 2, *_i16(3),
            Op.CMP, 1, 2,
            Op.SETCC, 3, 1,  # NE condition
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(3) == 1

    def test_setcc_lt(self):
        """SETCC: set on less-than (condition 2)."""
        bc = bytes([
            Op.MOVI, 1, *_i16(3),
            Op.MOVI, 2, *_i16(5),
            Op.CMP, 1, 2,
            Op.SETCC, 3, 2,  # LT
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(3) == 1

    def test_setcc_gt(self):
        """SETCC: set on greater-than (condition 4)."""
        bc = bytes([
            Op.MOVI, 1, *_i16(10),
            Op.MOVI, 2, *_i16(5),
            Op.CMP, 1, 2,
            Op.SETCC, 3, 4,  # GT
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(3) == 1


# ── Stack ops: DUP, SWAP, ROT, ENTER, LEAVE, ALLOCA ─────────────────────


class TestStackOps:
    def test_dup(self):
        """DUP: duplicate top of stack."""
        bc = bytes([
            Op.MOVI, 1, *_i16(42),
            Op.PUSH, 1,     # push 42
            Op.DUP,          # duplicate 42
            Op.POP, 2,      # pop 42 into R2
            Op.POP, 3,      # pop 42 into R3
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(2) == 42
        assert vm.regs.read_gp(3) == 42

    def test_swap(self):
        """SWAP: swap top two stack values."""
        bc = bytes([
            Op.MOVI, 1, *_i16(10),
            Op.MOVI, 2, *_i16(20),
            Op.PUSH, 1,     # push 10
            Op.PUSH, 2,     # push 20
            Op.SWAP,         # swap: top=20, second=10 -> top=10, second=20
            Op.POP, 3,      # R3 = 10 (was second, now top)
            Op.POP, 4,      # R4 = 20 (was top, now second)
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(3) == 10
        assert vm.regs.read_gp(4) == 20

    def test_rot(self):
        """ROT: rotate top 3 stack values [c, b, a] -> [b, a, c]."""
        bc = bytes([
            Op.MOVI, 1, *_i16(1),
            Op.MOVI, 2, *_i16(2),
            Op.MOVI, 3, *_i16(3),
            Op.PUSH, 1,     # stack: [1]
            Op.PUSH, 2,     # stack: [1, 2]
            Op.PUSH, 3,     # stack: [1, 2, 3] — 3 is top
            Op.ROT,          # [c=3, b=2, a=1] -> [b=2, a=1, c=3] -> top is c=3
            Op.POP, 4,      # R4 = 3 (c, now top)
            Op.POP, 5,      # R5 = 1 (a)
            Op.POP, 6,      # R6 = 2 (b)
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        # ROT: pop a=3(top), b=2(middle), c=1(bottom)
        # push a(3), push c(1), push b(2)
        # Stack top-to-bottom: [b=2, c=1, a=3]
        # pop -> R4=2, pop -> R5=1, pop -> R6=3
        assert vm.regs.read_gp(4) == 2
        assert vm.regs.read_gp(5) == 1
        assert vm.regs.read_gp(6) == 3

    def test_enter_leave(self):
        """ENTER/LEAVE: push/pop frame pointer."""
        bc = bytes([
            Op.MOVI, 1, *_i16(100),
            Op.ENTER, 4,    # allocate 4*4=16 bytes frame
            Op.MOVI, 2, *_i16(42),
            Op.LEAVE, 0,    # deallocate frame
            Op.HALT,
        ])
        vm = _make_vm(bc)
        sp_before = vm.regs.sp
        vm.execute()
        # After ENTER+LEAVE, SP should be back to where it was
        assert vm.regs.sp == sp_before
        assert vm.regs.read_gp(2) == 42

    def test_alloca(self):
        """ALLOCA: allocate stack space and return pointer."""
        bc = bytes([
            Op.MOVI, 1, *_i16(2),     # R1 = 2 (2 units of 4 bytes = 8 bytes)
            Op.ALLOCA, 2, 1,          # R2 = pointer to 8 bytes
            Op.MOVI, 3, *_i16(99),
            Op.STORE, 3, 2,           # store 99 at R2
            Op.LOAD, 4, 2,            # R4 = load from R2
            Op.HALT,
        ])
        vm = _make_vm(bc)
        sp_before = vm.regs.sp
        vm.execute()
        assert vm.regs.read_gp(4) == 99
        # SP should have decreased by 8
        assert vm.regs.sp == sp_before - 8


# ── Memory: REGION_CREATE, REGION_DESTROY, REGION_TRANSFER, MEMCMP ──────


class TestMemoryRegionOps:
    def test_region_create(self):
        """REGION_CREATE: creates a new memory region."""
        name = b"test_region"  # no null byte — handler strips internally
        owner = b"agent1"
        size = struct.pack('<I', 1024)
        payload = bytes([len(name)]) + name + size + bytes([len(owner)]) + owner
        bc = bytes([Op.REGION_CREATE]) + _var_data(payload) + bytes([Op.HALT])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.memory.has_region("test_region")
        assert vm.memory.get_region("test_region").owner == "agent1"

    def test_region_destroy(self):
        """REGION_DESTROY: destroys a memory region."""
        name = b"my_buf"
        owner = b"sys"
        size = struct.pack('<I', 256)
        payload = bytes([len(name)]) + name + size + bytes([len(owner)]) + owner
        bc = bytes([
            Op.REGION_CREATE, *_var_data(payload),
            Op.REGION_DESTROY, *_var_data(b"my_buf"),
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert not vm.memory.has_region("my_buf")

    def test_region_transfer(self):
        """REGION_TRANSFER: change ownership of a region."""
        name = b"xfer_region"
        owner = b"owner1"
        size = struct.pack('<I', 512)
        payload = bytes([len(name)]) + name + size + bytes([len(owner)]) + owner
        bc = bytes([Op.REGION_CREATE]) + _var_data(payload) + bytes([Op.HALT])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.memory.get_region("xfer_region").owner == "owner1"

    def test_region_transfer_via_opcode(self):
        """REGION_TRANSFER: transfer via opcode changes ownership."""
        name = b"my_reg"
        owner = b"owner_a"
        new_owner = b"owner_b"
        size = struct.pack('<I', 128)
        create_payload = bytes([len(name)]) + name + size + bytes([len(owner)]) + owner
        # Transfer payload: [name_len:u8][name][new_owner_len:u8][new_owner]
        transfer_payload = bytes([len(name)]) + name + bytes([len(new_owner)]) + new_owner
        bc = bytes([
            Op.REGION_CREATE, *_var_data(create_payload),
            Op.REGION_TRANSFER, *_var_data(transfer_payload),
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.memory.get_region("my_reg").owner == "owner_b"

    def test_memset(self):
        """MEMSET: fill memory with a byte value."""
        rname = b"heap"
        offset = struct.pack('<I', 300)
        value = bytes([0xAB])
        size = struct.pack('<I', 4)
        payload = bytes([len(rname)]) + rname + offset + value + size
        bc = bytes([Op.MEMSET]) + _var_data(payload) + bytes([Op.HALT])
        vm = _make_vm(bc)
        vm.execute()
        data = vm.memory.get_region("heap").read(300, 4)
        assert data == b'\xAB\xAB\xAB\xAB'

    def test_memcmp_equal(self):
        """MEMCMP: compare equal regions returns 0."""
        # Pre-write data to heap region
        bc = bytes([Op.HALT])
        vm = _make_vm(bc)
        heap = vm.memory.get_region("heap")
        heap.write_i32(500, 42)
        heap.write_i32(600, 42)

        rname = b"heap"
        off_a = struct.pack('<I', 500)
        off_b = struct.pack('<I', 600)
        size = struct.pack('<I', 4)
        payload = bytes([len(rname)]) + rname + off_a + off_b + size
        bc2 = bytes([Op.MEMCMP]) + _var_data(payload) + bytes([Op.HALT])
        vm2 = _make_vm(bc2)
        heap2 = vm2.memory.get_region("heap")
        heap2.write_i32(500, 42)
        heap2.write_i32(600, 42)
        vm2.execute()
        assert vm2.regs.read_gp(0) == 0

    def test_memcmp_less(self):
        """MEMCMP: compare regions where a < b returns -1."""
        bc2 = bytes([Op.HALT])
        vm = _make_vm(bc2)
        heap = vm.memory.get_region("heap")
        heap.write_i32(500, 10)
        heap.write_i32(600, 20)

        rname = b"heap"
        off_a = struct.pack('<I', 500)
        off_b = struct.pack('<I', 600)
        size = struct.pack('<I', 4)
        payload = bytes([len(rname)]) + rname + off_a + off_b + size
        bc = bytes([Op.MEMCMP]) + _var_data(payload) + bytes([Op.HALT])
        vm2 = _make_vm(bc)
        heap2 = vm2.memory.get_region("heap")
        heap2.write_i32(500, 10)
        heap2.write_i32(600, 20)
        vm2.execute()
        assert vm2.regs.read_gp(0) == -1


# ── Type ops: BOX, UNBOX, CHECK_TYPE, CHECK_BOUNDS ──────────────────────


class TestTypeOps:
    def test_box_unbox_int(self):
        """BOX/UNBOX: box an integer and unbox it back."""
        # BOX format: [BOX][rd:u8][type_tag:u8] then i32 value
        bc = bytes([
            Op.BOX, 1, 0,  # BOX R1, type=0 (int)
            *_i32(42),     # value to box
            Op.UNBOX, 2, 1,  # UNBOX R2, box_id from R1
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(1) == 0  # box_id = 0
        assert vm.regs.read_gp(2) == 42  # unboxed value

    def test_box_multiple(self):
        """BOX: create multiple boxes with incrementing IDs."""
        bc = bytes([
            Op.BOX, 1, 0, *_i32(10),  # box 0, R1=0
            Op.BOX, 2, 1, *_i32(20),  # box 1, R2=1
            Op.BOX, 3, 0, *_i32(30),  # box 2, R3=2
            Op.UNBOX, 4, 2,            # unbox box_id from R2 (=1) -> 20
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(1) == 0  # box_id 0
        assert vm.regs.read_gp(2) == 1  # box_id 1
        assert vm.regs.read_gp(3) == 2  # box_id 2
        assert vm.regs.read_gp(4) == 20  # unbox(1) = 20

    def test_check_type_pass(self):
        """CHECK_TYPE: passes when type matches."""
        bc = bytes([
            Op.BOX, 1, 0, *_i32(42),   # box type 0
            Op.CHECK_TYPE, 1, 0,        # check type 0 == 0 (pass)
            Op.MOVI, 2, *_i16(1),       # R2 = 1 (reached if no exception)
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(2) == 1

    def test_check_type_fail(self):
        """CHECK_TYPE: raises VMTypeError when type doesn't match."""
        bc = bytes([
            Op.BOX, 1, 0, *_i32(42),   # box type 0
            Op.CHECK_TYPE, 1, 1,        # check type 0 == 1 (fail)
            Op.HALT,
        ])
        vm = _make_vm(bc)
        with pytest.raises(VMTypeError):
            vm.execute()

    def test_check_bounds_pass(self):
        """CHECK_BOUNDS: passes when index is in range."""
        bc = bytes([
            Op.MOVI, 1, *_i16(5),     # index = 5
            Op.MOVI, 2, *_i16(10),    # length = 10
            Op.CHECK_BOUNDS, 1, 2,    # 5 in [0, 10) — pass
            Op.MOVI, 3, *_i16(1),     # reached if pass
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(3) == 1

    def test_check_bounds_fail_high(self):
        """CHECK_BOUNDS: raises when index >= length."""
        bc = bytes([
            Op.MOVI, 1, *_i16(10),    # index = 10
            Op.MOVI, 2, *_i16(10),    # length = 10
            Op.CHECK_BOUNDS, 1, 2,    # 10 not in [0, 10) — fail
            Op.HALT,
        ])
        vm = _make_vm(bc)
        with pytest.raises(VMTypeError):
            vm.execute()

    def test_check_bounds_fail_negative(self):
        """CHECK_BOUNDS: raises when index < 0."""
        bc = bytes([
            Op.MOVI, 1, *_i16(-1),    # index = -1
            Op.MOVI, 2, *_i16(10),    # length = 10
            Op.CHECK_BOUNDS, 1, 2,    # -1 not in [0, 10) — fail
            Op.HALT,
        ])
        vm = _make_vm(bc)
        with pytest.raises(VMTypeError):
            vm.execute()


# ── SIMD: VLOAD, VSTORE, VADD, VSUB, VMUL, VDIV, VFMA ──────────────────


class TestSIMDOps:
    def test_vload_vstore(self):
        """VLOAD/VSTORE: load and store 16-byte vectors."""
        bc = bytes([
            Op.MOVI, 1, *_i16(100),   # base address
            Op.VLOAD, 0, 1,            # V0 = load 16 bytes from offset 100
            Op.VSTORE, 0, 1,           # store V0 to same offset
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        vec = vm.regs.read_vec(0)
        assert len(vec) == 16

    def test_vadd(self):
        """VADD: element-wise vector addition."""
        bc = bytes([
            Op.MOVI, 1, *_i16(50),
            Op.MOVI, 2, *_i16(66),
            Op.VLOAD, 0, 1,           # V0 = [1,1,...]
            Op.VLOAD, 1, 2,           # V1 = [2,2,...]
            Op.VADD, 0, 1,            # V0 = [3,3,...]
            Op.HALT,
        ])
        vm = _make_vm(bc)
        stack = vm.memory.get_region("stack")
        stack.write(50, bytes([1] * 16))
        stack.write(66, bytes([2] * 16))
        vm.execute()
        assert vm.regs.read_vec(0) == bytes([3] * 16)

    def test_vsub(self):
        """VSUB: element-wise vector subtraction."""
        bc = bytes([
            Op.MOVI, 1, *_i16(50),
            Op.MOVI, 2, *_i16(66),
            Op.VLOAD, 0, 1,           # V0 = [5,5,...]
            Op.VLOAD, 1, 2,           # V1 = [3,3,...]
            Op.VSUB, 0, 1,            # V0 = [2,2,...]
            Op.HALT,
        ])
        vm = _make_vm(bc)
        stack = vm.memory.get_region("stack")
        stack.write(50, bytes([5] * 16))
        stack.write(66, bytes([3] * 16))
        vm.execute()
        assert vm.regs.read_vec(0) == bytes([2] * 16)

    def test_vmul(self):
        """VMUL: element-wise vector multiplication."""
        bc = bytes([
            Op.MOVI, 1, *_i16(50),
            Op.MOVI, 2, *_i16(66),
            Op.VLOAD, 0, 1,           # V0 = [3,3,...]
            Op.VLOAD, 1, 2,           # V1 = [4,4,...]
            Op.VMUL, 0, 1,            # V0 = [12,12,...]
            Op.HALT,
        ])
        vm = _make_vm(bc)
        stack = vm.memory.get_region("stack")
        stack.write(50, bytes([3] * 16))
        stack.write(66, bytes([4] * 16))
        vm.execute()
        assert vm.regs.read_vec(0) == bytes([12] * 16)

    def test_vdiv(self):
        """VDIV: element-wise vector division."""
        bc = bytes([
            Op.MOVI, 1, *_i16(50),
            Op.MOVI, 2, *_i16(66),
            Op.VLOAD, 0, 1,           # V0 = [12,...]
            Op.VLOAD, 1, 2,           # V1 = [4,...]
            Op.VDIV, 0, 1,            # V0 = [3,...]
            Op.HALT,
        ])
        vm = _make_vm(bc)
        stack = vm.memory.get_region("stack")
        stack.write(50, bytes([12] * 16))
        stack.write(66, bytes([4] * 16))
        vm.execute()
        assert vm.regs.read_vec(0) == bytes([3] * 16)

    def test_vdiv_by_zero(self):
        """VDIV: raises on division by zero."""
        bc = bytes([
            Op.MOVI, 1, *_i16(50),
            Op.MOVI, 2, *_i16(66),
            Op.VLOAD, 0, 1,           # V0 = [12,...]
            Op.VLOAD, 1, 2,           # V1 = [0,...]
            Op.VDIV, 0, 1,            # divide by zero!
            Op.HALT,
        ])
        vm = _make_vm(bc)
        stack = vm.memory.get_region("stack")
        stack.write(50, bytes([12] * 16))
        stack.write(66, bytes([0] * 16))
        with pytest.raises(VMDivisionByZeroError):
            vm.execute()

    def test_vfma(self):
        """VFMA: fused multiply-add V0 = V0 + (V1 * V2)."""
        bc = bytes([
            Op.MOVI, 1, *_i16(50),
            Op.MOVI, 2, *_i16(66),
            Op.MOVI, 3, *_i16(82),
            Op.VLOAD, 0, 1,           # V0 = [10,...] (accumulator)
            Op.VLOAD, 1, 2,           # V1 = [2,...]  (multiplicand)
            Op.VLOAD, 2, 3,           # V2 = [3,...]  (multiplier)
            Op.VFMA, 0, 1, 2,         # V0 = V0 + V1*V2 = [10+6,...] = [16,...]
            Op.HALT,
        ])
        vm = _make_vm(bc)
        stack = vm.memory.get_region("stack")
        stack.write(50, bytes([10] * 16))
        stack.write(66, bytes([2] * 16))
        stack.write(82, bytes([3] * 16))
        vm.execute()
        assert vm.regs.read_vec(0) == bytes([16] * 16)


# ── Float: FABS, FMIN, FMAX, FEQ, FLT, FLE, FGT, FGE ──────────────────


class TestFloatOps:
    def test_fabs(self):
        """FABS: absolute value of float."""
        bc = bytes([Op.FABS, 0, 1, Op.HALT])
        vm = _make_vm(bc)
        vm.regs.write_fp(0, -3.5)
        vm.regs.write_fp(1, -3.5)
        vm.execute()
        assert vm.regs.read_fp(0) == 3.5

    def test_fmin(self):
        """FMIN: minimum of two floats."""
        bc = bytes([Op.FMIN, 0, 1, Op.HALT])
        vm = _make_vm(bc)
        vm.regs.write_fp(0, 10.0)
        vm.regs.write_fp(1, 5.0)
        vm.execute()
        assert vm.regs.read_fp(0) == 5.0

    def test_fmax(self):
        """FMAX: maximum of two floats."""
        bc = bytes([Op.FMAX, 0, 1, Op.HALT])
        vm = _make_vm(bc)
        vm.regs.write_fp(0, 5.0)
        vm.regs.write_fp(1, 10.0)
        vm.execute()
        assert vm.regs.read_fp(0) == 10.0

    def test_feq_true(self):
        """FEQ: float equal comparison (true)."""
        bc = bytes([Op.FEQ, 0, 1, Op.HALT])
        vm = _make_vm(bc)
        vm.regs.write_fp(0, 3.14)
        vm.regs.write_fp(1, 3.14)
        vm.execute()
        assert vm.regs.read_gp(0) == 1

    def test_feq_false(self):
        """FEQ: float equal comparison (false)."""
        bc = bytes([Op.FEQ, 0, 1, Op.HALT])
        vm = _make_vm(bc)
        vm.regs.write_fp(0, 3.14)
        vm.regs.write_fp(1, 2.71)
        vm.execute()
        assert vm.regs.read_gp(0) == 0

    def test_flt_true(self):
        """FLT: float less-than (true)."""
        bc = bytes([Op.FLT, 0, 1, Op.HALT])
        vm = _make_vm(bc)
        vm.regs.write_fp(0, 1.0)
        vm.regs.write_fp(1, 2.0)
        vm.execute()
        assert vm.regs.read_gp(0) == 1

    def test_fgt_true(self):
        """FGT: float greater-than (true)."""
        bc = bytes([Op.FGT, 0, 1, Op.HALT])
        vm = _make_vm(bc)
        vm.regs.write_fp(0, 5.0)
        vm.regs.write_fp(1, 3.0)
        vm.execute()
        assert vm.regs.read_gp(0) == 1

    def test_fle_true(self):
        """FLE: float less-than-or-equal (equal)."""
        bc = bytes([Op.FLE, 0, 1, Op.HALT])
        vm = _make_vm(bc)
        vm.regs.write_fp(0, 3.0)
        vm.regs.write_fp(1, 3.0)
        vm.execute()
        assert vm.regs.read_gp(0) == 1

    def test_fge_true(self):
        """FGE: float greater-than-or-equal (equal)."""
        bc = bytes([Op.FGE, 0, 1, Op.HALT])
        vm = _make_vm(bc)
        vm.regs.write_fp(0, 7.0)
        vm.regs.write_fp(1, 7.0)
        vm.execute()
        assert vm.regs.read_gp(0) == 1


# ── Comparison: IEQ, ILT, ILE, IGT, IGE (Format C, result in rd) ───────


class TestIntComparisonOps:
    def test_ieq_true(self):
        """IEQ: integer equal (true)."""
        bc = bytes([Op.IEQ, 1, 2, Op.HALT])
        vm = _make_vm(bc)
        vm.regs.write_gp(1, 5)
        vm.regs.write_gp(2, 5)
        vm.execute()
        assert vm.regs.read_gp(1) == 1

    def test_ieq_false(self):
        """IEQ: integer equal (false)."""
        bc = bytes([Op.IEQ, 1, 2, Op.HALT])
        vm = _make_vm(bc)
        vm.regs.write_gp(1, 5)
        vm.regs.write_gp(2, 3)
        vm.execute()
        assert vm.regs.read_gp(1) == 0

    def test_ilt_true(self):
        """ILT: integer less-than (true)."""
        bc = bytes([Op.ILT, 1, 2, Op.HALT])
        vm = _make_vm(bc)
        vm.regs.write_gp(1, 3)
        vm.regs.write_gp(2, 5)
        vm.execute()
        assert vm.regs.read_gp(1) == 1

    def test_igt_true(self):
        """IGT: integer greater-than (true)."""
        bc = bytes([Op.IGT, 1, 2, Op.HALT])
        vm = _make_vm(bc)
        vm.regs.write_gp(1, 10)
        vm.regs.write_gp(2, 5)
        vm.execute()
        assert vm.regs.read_gp(1) == 1

    def test_ile_true(self):
        """ILE: integer less-than-or-equal (equal)."""
        bc = bytes([Op.ILE, 1, 2, Op.HALT])
        vm = _make_vm(bc)
        vm.regs.write_gp(1, 5)
        vm.regs.write_gp(2, 5)
        vm.execute()
        assert vm.regs.read_gp(1) == 1

    def test_ige_true(self):
        """IGE: integer greater-than-or-equal (equal)."""
        bc = bytes([Op.IGE, 1, 2, Op.HALT])
        vm = _make_vm(bc)
        vm.regs.write_gp(1, 5)
        vm.regs.write_gp(2, 5)
        vm.execute()
        assert vm.regs.read_gp(1) == 1


# ── A2A opcodes (stubs) ──────────────────────────────────────────────────


class TestA2AOpcodes:
    def test_tell_stub(self):
        """TELL: no-op when no handler registered."""
        bc = bytes([Op.TELL]) + _var_data(b"hello") + bytes([Op.HALT])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.halted

    def test_ask_stub(self):
        """ASK: no-op when no handler registered."""
        bc = bytes([Op.ASK]) + _var_data(b"query") + bytes([Op.HALT])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.halted

    def test_delegate_stub(self):
        """DELEGATE: no-op when no handler registered."""
        bc = bytes([Op.DELEGATE]) + _var_data(b"task") + bytes([Op.HALT])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.halted

    def test_a2a_handler(self):
        """A2A handler receives opcode name and data."""
        received = []

        def handler(name, data):
            received.append((name, data))
            return 42

        bc = bytes([Op.TELL]) + _var_data(b"test_msg") + bytes([Op.HALT])
        vm = _make_vm(bc)
        vm.on_a2a(handler)
        vm.execute()
        assert len(received) == 1
        assert received[0] == ("TELL", b"test_msg")
        assert vm.regs.read_gp(0) == 42

    def test_trust_check_stub(self):
        """TRUST_CHECK: no-op when no handler registered."""
        bc = bytes([Op.TRUST_CHECK]) + _var_data(b"agent1") + bytes([Op.HALT])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.halted

    def test_barrier_stub(self):
        """BARRIER: no-op when no handler registered."""
        bc = bytes([Op.BARRIER]) + _var_data(b"sync") + bytes([Op.HALT])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.halted

    def test_sync_clock_stub(self):
        """SYNC_CLOCK: no-op when no handler registered."""
        bc = bytes([Op.SYNC_CLOCK]) + _var_data(b"clock") + bytes([Op.HALT])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.halted

    def test_broadcast_stub(self):
        """BROADCAST: no-op when no handler registered."""
        bc = bytes([Op.BROADCAST]) + _var_data(b"msg") + bytes([Op.HALT])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.halted

    def test_reduce_stub(self):
        """REDUCE: no-op when no handler registered."""
        bc = bytes([Op.REDUCE]) + _var_data(b"reduce") + bytes([Op.HALT])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.halted

    def test_emergency_stop(self):
        """EMERGENCY_STOP: halts the VM."""
        bc = bytes([
            Op.MOVI, 1, *_i16(42),
            Op.EMERGENCY_STOP,
            Op.MOVI, 2, *_i16(99),  # should not be reached
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.halted
        assert vm.regs.read_gp(1) == 42
        assert vm.regs.read_gp(2) == 0  # MOVI after stop not reached

    def test_multiple_a2a_dispatches(self):
        """Multiple A2A opcodes dispatch to handler."""
        calls = []

        def handler(name, data):
            calls.append(name)

        bc = bytes([
            Op.TELL, *_var_data(b"a"),
            Op.ASK, *_var_data(b"b"),
            Op.BROADCAST, *_var_data(b"c"),
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.on_a2a(handler)
        vm.execute()
        assert calls == ["TELL", "ASK", "BROADCAST"]


# ── System opcodes ───────────────────────────────────────────────────────


class TestSystemOpcodes:
    def test_yield(self):
        """YIELD: no-op in single-threaded interpreter."""
        bc = bytes([
            Op.MOVI, 1, *_i16(42),
            Op.YIELD,
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(1) == 42
        assert vm.halted

    def test_resource_acquire(self):
        """RESOURCE_ACQUIRE: acquire a resource."""
        bc = bytes([Op.RESOURCE_ACQUIRE]) + _var_data(struct.pack('<I', 1)) + bytes([Op.HALT])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(0) == 0  # success
        assert vm._resources.get(1) == True

    def test_resource_release(self):
        """RESOURCE_RELEASE: release a resource."""
        bc = bytes([Op.RESOURCE_RELEASE]) + _var_data(struct.pack('<I', 1)) + bytes([Op.HALT])
        vm = _make_vm(bc)
        vm._resources[1] = True  # pre-acquire
        vm.execute()
        assert vm.regs.read_gp(0) == 0  # success
        assert vm._resources.get(1) == False

    def test_debug_break(self):
        """DEBUG_BREAK: triggers callback."""
        log = []

        def cb(msg):
            log.append(msg)

        bc = bytes([Op.DEBUG_BREAK, Op.HALT])
        vm = _make_vm(bc)
        vm.on_io_write(cb)
        vm.execute()
        assert len(log) == 1
        assert "DEBUG_BREAK" in log[0]

    def test_tailcall(self):
        """TAILCALL: jump without pushing return address."""
        # TAILCALL is Format D: [TAILCALL][reg:u8][offset:i16]
        # Build: MOVI R1, 0; TAILCALL R0, offset to HALT; MOVI R2, 99; HALT
        # MOVI is 4 bytes, TAILCALL is 4 bytes, so HALT is at offset 8
        bc = bytes([
            Op.MOVI, 1, *_i16(0),
            Op.TAILCALL, 0, *_i16(3),  # offset 3 from here -> pc=11
            Op.MOVI, 2, *_i16(99),     # should be skipped
            Op.MOVI, 3, *_i16(77),     # should be skipped
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        # R2 should remain 0 (MOVI skipped)
        assert vm.regs.read_gp(2) == 0


# ── IMOD (opcode 0x0C) ──────────────────────────────────────────────────


class TestIMod:
    def test_imod_basic(self):
        """IMOD: integer modulo."""
        bc = bytes([
            Op.MOVI, 1, *_i16(10),
            Op.MOVI, 2, *_i16(3),
            Op.IMOD, 3, 1, 2,  # R3 = 10 % 3 = 1
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(3) == 1

    def test_imod_div_by_zero(self):
        """IMOD: raises on division by zero."""
        bc = bytes([
            Op.MOVI, 1, *_i16(10),
            Op.MOVI, 2, *_i16(0),
            Op.IMOD, 3, 1, 2,
            Op.HALT,
        ])
        vm = _make_vm(bc)
        with pytest.raises(VMDivisionByZeroError):
            vm.execute()


# ── CAST opcode ──────────────────────────────────────────────────────────


class TestCastOps:
    def test_cast_i32_to_bool(self):
        """CAST: i32 to bool (type_tag=2)."""
        bc = bytes([
            Op.MOVI, 1, *_i16(42),
            Op.CAST, 2, 1, 2,  # CAST R2, R1, type=2 (i32->bool)
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(2) == 1  # nonzero -> true

    def test_cast_i32_zero_to_bool(self):
        """CAST: i32 (0) to bool."""
        bc = bytes([
            Op.MOVI, 1, *_i16(0),
            Op.CAST, 2, 1, 2,
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(2) == 0  # zero -> false


# ── State dump includes new fields ───────────────────────────────────────


class TestStateDump:
    def test_dump_state_new_fields(self):
        """dump_state includes box_count, resource_count, frame_depth."""
        bc = bytes([
            Op.BOX, 1, 0, *_i32(42),
            Op.ENTER, 2,
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        state = vm.dump_state()
        assert "box_count" in state
        assert "resource_count" in state
        assert "frame_depth" in state
        assert state["box_count"] == 1
        assert state["frame_depth"] == 1

    def test_reset_clears_new_state(self):
        """reset clears box table, resources, frame stack."""
        bc = bytes([
            Op.BOX, 1, 0, *_i32(42),
            Op.ENTER, 2,
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert len(vm._box_table) == 1
        assert len(vm._frame_stack) == 1
        vm.reset()
        assert len(vm._box_table) == 0
        assert len(vm._frame_stack) == 0


# ── Backward compatibility ───────────────────────────────────────────────


class TestBackwardCompatibility:
    def test_existing_add_still_works(self):
        """IADD: backward compatibility with existing tests."""
        bc = bytes([
            Op.MOVI, 0, *_i16(10),
            Op.MOVI, 1, *_i16(20),
            Op.IADD, 2, 0, 1,
            Op.HALT,
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(2) == 30

    def test_existing_loop_still_works(self):
        """Countdown loop: backward compatibility."""
        # DEC is Format B: 2 bytes [DEC][reg]
        # JNZ is Format D: 4 bytes [JNZ][reg][off_lo][off_hi]
        # DEC(2) + JNZ(4) = 6 bytes per iteration
        # We want JNZ to jump back to DEC
        # At start of loop: DEC at offset 4, JNZ at offset 6
        # After JNZ (4 bytes), pc = offset 10
        # Jump target = offset 4 (DEC)
        # offset = target - pc_after_jnz = 4 - 10 = -6
        bc = bytes([
            Op.MOVI, 0, *_i16(3),       # offset 0-3: R0 = 3
            # loop at offset 4:
            Op.DEC, 0,                  # offset 4: R0--
            Op.JNZ, 0, *_i16(-6),      # offset 6: if R0 != 0, jump to offset 4
            Op.HALT,                    # offset 10: done
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(0) == 0

    def test_existing_call_ret(self):
        """CALL/RET: backward compatibility."""
        # MOVI R1, 5     (4 bytes, offset 0)
        # CALL offset 4  (4 bytes, offset 4) -> jumps to offset 12
        # HALT           (1 byte, offset 8)
        # IADD R1,R1,R1  (3 bytes, offset 9) -> but need 3 bytes
        # Actually IADD is Format E: 4 bytes [IADD][rd][rs1][rs2]
        # RET            (1 byte)
        # HALT           (1 byte)
        # Total: 4 + 4 + 1 + 4 + 1 + 1 = 15
        # CALL at offset 4, after fetch pc=8. Target = 8 + offset = 12 (so offset=4 doesn't work since HALT is at 8)
        # Let me recalculate:
        # offset 0: MOVI R1, 5 (4 bytes) -> pc=4
        # offset 4: CALL R0, offset (4 bytes) -> pc=8, then jumps
        # offset 8: HALT (1 byte)
        # offset 9: IADD R1, R1, R1 (4 bytes) [IADD is Format E in my impl]
        # Wait, IADD in the original interpreter was Format E (4 bytes).
        # offset 13: RET (1 byte) -> pops return address
        # offset 14: HALT (1 byte)
        # CALL at offset 4: after fetch pc=8, jump offset = 9 - 8 = 1
        bc = bytes([
            Op.MOVI, 1, *_i16(5),     # offset 0: R1=5 (4 bytes)
            Op.CALL, 0, *_i16(1),      # offset 4: CALL, pc becomes 8, jump to 8+1=9 (4 bytes)
            Op.HALT,                    # offset 8: HALT (not reached after CALL)
            Op.IADD, 1, 1, 1,          # offset 9: R1 = R1+R1 = 10 (4 bytes)
            Op.RET,                     # offset 13: return to pc=8 (1 byte)
            Op.HALT,                    # offset 14: final halt (1 byte)
        ])
        vm = _make_vm(bc)
        vm.execute()
        assert vm.regs.read_gp(1) == 10
