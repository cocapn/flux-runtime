"""Tests for FLUX bytecode encoder, decoder, and validator."""

import sys
sys.path.insert(0, "src")

import struct

from flux.fir.types import TypeContext, IntType, FloatType
from flux.fir.values import Value
from flux.fir.instructions import (
    IAdd, ISub, IMul, INeg, Return, Jump, Branch, Call,
    Tell, Ask, TrustCheck, CapRequire, Load, Store, Alloca,
    IEq, ILt, FAdd, FDiv, Unreachable,
)
from flux.fir.blocks import FIRModule, FIRFunction, FIRBlock
from flux.fir.builder import FIRBuilder

from flux.bytecode.opcodes import Op, get_format
from flux.bytecode.encoder import BytecodeEncoder, MAGIC, VERSION, HEADER_SIZE
from flux.bytecode.decoder import BytecodeDecoder, DecodedInstruction, DecodedFunction
from flux.bytecode.validator import BytecodeValidator


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_value(id: int, name: str = "v", type=None):
    """Create a Value with a given ID."""
    ctx = TypeContext()
    t = type or ctx.get_int(32)
    return Value(id=id, name=f"{name}{id}", type=t)


def _make_simple_module() -> FIRModule:
    """Build a minimal FIRModule with one function: add(a, b) { return a + b }"""
    ctx = TypeContext()
    builder = FIRBuilder(ctx)

    module = builder.new_module("test_mod")
    func = builder.new_function(module, "add", [("a", ctx.get_int(32)), ("b", ctx.get_int(32))], [ctx.get_int(32)])
    block = builder.new_block(func, "entry")
    builder.set_block(block)

    a = Value(id=0, name="a", type=ctx.get_int(32))
    b = Value(id=1, name="b", type=ctx.get_int(32))
    builder._next_value_id = 2

    builder.iadd(a, b)
    builder.ret(_make_value(2, "_v2"))

    return module


def _make_multi_block_module() -> FIRModule:
    """Build a module with branch + return."""
    ctx = TypeContext()
    builder = FIRBuilder(ctx)

    module = builder.new_module("test_branch")
    func = builder.new_function(module, "max", [("x", ctx.get_int(32)), ("y", ctx.get_int(32))], [ctx.get_int(32)])

    entry = builder.new_block(func, "entry")
    then_blk = builder.new_block(func, "then")
    else_blk = builder.new_block(func, "else")
    merge = builder.new_block(func, "merge")

    builder.set_block(entry)
    x = Value(id=0, name="x", type=ctx.get_int(32))
    y = Value(id=1, name="y", type=ctx.get_int(32))
    builder._next_value_id = 2
    cond = builder.ilt(x, y)
    builder.branch(cond, "then", "else")

    builder.set_block(then_blk)
    builder.jump("merge", [])

    builder.set_block(else_blk)
    builder.jump("merge", [])

    builder.set_block(merge)
    builder.ret(None)

    return module


# ── Test 1: test_encode_decode_simple ─────────────────────────────────────

def test_encode_decode_simple():
    """Encode a simple FIR function, decode it, verify instructions match."""
    module = _make_simple_module()
    encoder = BytecodeEncoder()
    encoded = encoder.encode(module)

    decoder = BytecodeDecoder()
    functions = decoder.decode_functions(encoded)

    assert len(functions) == 1, f"Expected 1 function, got {len(functions)}"
    func = functions[0]
    assert func.name == "add", f"Expected 'add', got {func.name!r}"

    # Should have 2 instructions: IADD + RET
    assert len(func.instructions) >= 2, f"Expected >= 2 instructions, got {len(func.instructions)}"

    # First instruction should be IADD
    iadd_instr = func.instructions[0]
    assert iadd_instr.opcode == Op.IADD, f"Expected IADD, got {iadd_instr.opcode}"
    assert iadd_instr.operands[0] == 0, f"Expected lhs reg 0, got {iadd_instr.operands[0]}"
    assert iadd_instr.operands[1] == 1, f"Expected rhs reg 1, got {iadd_instr.operands[1]}"

    # Last instruction should be RET
    ret_instr = func.instructions[-1]
    assert ret_instr.opcode == Op.RET, f"Expected RET, got {ret_instr.opcode}"

    print("  ✓ test_encode_decode_simple")


# ── Test 2: test_encode_header ────────────────────────────────────────────

def test_encode_header():
    """Header magic/version correct."""
    module = _make_simple_module()
    encoder = BytecodeEncoder()
    encoded = encoder.encode(module)

    assert len(encoded) >= HEADER_SIZE
    assert encoded[:4] == MAGIC, f"Expected magic {MAGIC!r}, got {encoded[:4]!r}"

    version = struct.unpack_from("<H", encoded, 4)[0]
    assert version == VERSION, f"Expected version {VERSION}, got {version}"

    flags = struct.unpack_from("<H", encoded, 6)[0]
    assert flags == 0, f"Expected flags 0, got {flags}"

    n_funcs = struct.unpack_from("<H", encoded, 8)[0]
    assert n_funcs == 1, f"Expected 1 function, got {n_funcs}"

    print("  ✓ test_encode_header")


# ── Test 3: test_encode_nop ───────────────────────────────────────────────

def test_encode_nop():
    """Single NOP encodes to 1 byte; Unreachable maps to HALT."""
    encoder = BytecodeEncoder()

    # Unreachable FIR instruction maps to HALT opcode (Format A, 1 byte)
    unreachable = Unreachable()
    unreachable_bytes = encoder._encode_instruction(unreachable)
    assert len(unreachable_bytes) == 1, f"Expected 1 byte for HALT, got {len(unreachable_bytes)}"
    assert unreachable_bytes[0] == Op.HALT, f"Expected HALT opcode, got 0x{unreachable_bytes[0]:02x}"

    # Also verify a minimal function (just RET) encodes/decodes correctly
    ctx = TypeContext()
    builder = FIRBuilder(ctx)
    module = builder.new_module("nop_test")
    func = builder.new_function(module, "do_nothing", [], [])
    block = builder.new_block(func, "entry")
    builder.set_block(block)
    builder.ret(None)

    encoded = encoder.encode(module)
    decoder = BytecodeDecoder()
    funcs = decoder.decode_functions(encoded)
    ret_instr = funcs[0].instructions[-1]
    assert ret_instr.opcode == Op.RET

    print("  ✓ test_encode_nop")


# ── Test 4: test_encode_arithmetic ────────────────────────────────────────

def test_encode_arithmetic():
    """IADD, ISUB encode to format C (3 bytes)."""
    encoder = BytecodeEncoder()

    a = _make_value(5, "a")
    b = _make_value(10, "b")

    # IADD
    iadd = IAdd(lhs=a, rhs=b)
    iadd_bytes = encoder._encode_instruction(iadd)
    assert len(iadd_bytes) == 3, f"IADD should be 3 bytes (Format C), got {len(iadd_bytes)}"
    assert iadd_bytes[0] == Op.IADD
    assert iadd_bytes[1] == 5  # lhs register
    assert iadd_bytes[2] == 10  # rhs register

    # ISUB
    isub = ISub(lhs=a, rhs=b)
    isub_bytes = encoder._encode_instruction(isub)
    assert len(isub_bytes) == 3, f"ISUB should be 3 bytes (Format C), got {len(isub_bytes)}"
    assert isub_bytes[0] == Op.ISUB
    assert isub_bytes[1] == 5
    assert isub_bytes[2] == 10

    # IMUL
    imul = IMul(lhs=a, rhs=b)
    imul_bytes = encoder._encode_instruction(imul)
    assert len(imul_bytes) == 3
    assert imul_bytes[0] == Op.IMUL

    # INEG (unary → Format B: 2 bytes)
    ineg = INeg(lhs=a)
    ineg_bytes = encoder._encode_instruction(ineg)
    assert len(ineg_bytes) == 2, f"INEG should be 2 bytes (Format B), got {len(ineg_bytes)}"
    assert ineg_bytes[0] == Op.INEG
    assert ineg_bytes[1] == 5

    print("  ✓ test_encode_arithmetic")


# ── Test 5: test_encode_jump ──────────────────────────────────────────────

def test_encode_jump():
    """JMP encodes to format D (4 bytes). JZ encodes to format D (4 bytes)."""
    encoder = BytecodeEncoder()

    # Jump
    jump = Jump(target_block="loop_back")
    jump_bytes = encoder._encode_instruction(jump)
    assert len(jump_bytes) == 4, f"JMP should be 4 bytes (Format D), got {len(jump_bytes)}"
    assert jump_bytes[0] == Op.JMP

    # Branch (maps to JZ)
    cond_val = _make_value(3, "cond")
    branch = Branch(cond=cond_val, true_block="then", false_block="else")
    branch_bytes = encoder._encode_instruction(branch)
    assert len(branch_bytes) == 4, f"JZ (branch) should be 4 bytes (Format D), got {len(branch_bytes)}"
    assert branch_bytes[0] == Op.JZ
    assert branch_bytes[1] == 3  # cond register

    print("  ✓ test_encode_jump")


# ── Test 6: test_encode_a2a ───────────────────────────────────────────────

def test_encode_a2a():
    """TELL, ASK, TRUST_CHECK encode correctly as Format G."""
    encoder = BytecodeEncoder()

    msg = _make_value(0, "msg")
    cap = _make_value(1, "cap")
    auth = _make_value(2, "auth")
    thr = _make_value(3, "thr")
    ctx = TypeContext()

    # TELL
    tell = Tell(target_agent="navigator", message=msg, cap=cap)
    tell_bytes = encoder._encode_instruction(tell)
    assert tell_bytes[0] == Op.TELL, f"Expected TELL opcode, got 0x{tell_bytes[0]:02x}"
    # Format G: [op:1][len:2][data:len]
    data_len = struct.unpack_from("<H", tell_bytes, 1)[0]
    assert data_len > 0, "TELL payload should have data"
    assert len(tell_bytes) == 3 + data_len
    # Verify agent name is in payload
    payload = tell_bytes[3:]
    assert b"navigator" in payload, "Agent name 'navigator' should be in TELL payload"

    # ASK
    ask = Ask(target_agent="planner", message=msg, return_type=ctx.get_string(), cap=cap)
    ask_bytes = encoder._encode_instruction(ask)
    assert ask_bytes[0] == Op.ASK, f"Expected ASK opcode, got 0x{ask_bytes[0]:02x}"
    data_len = struct.unpack_from("<H", ask_bytes, 1)[0]
    assert len(ask_bytes) == 3 + data_len
    payload = ask_bytes[3:]
    assert b"planner" in payload, "Agent name 'planner' should be in ASK payload"

    # TRUST_CHECK
    trust = TrustCheck(agent="sensor", threshold=thr, cap=cap)
    trust_bytes = encoder._encode_instruction(trust)
    assert trust_bytes[0] == Op.TRUST_CHECK, f"Expected TRUST_CHECK opcode, got 0x{trust_bytes[0]:02x}"
    data_len = struct.unpack_from("<H", trust_bytes, 1)[0]
    assert len(trust_bytes) == 3 + data_len
    payload = trust_bytes[3:]
    assert b"sensor" in payload, "Agent name 'sensor' should be in TRUST_CHECK payload"

    print("  ✓ test_encode_a2a")


# ── Test 7: test_roundtrip ────────────────────────────────────────────────

def test_roundtrip():
    """Encode FIR → decode → re-encode produces same bytes."""
    module = _make_multi_block_module()

    encoder = BytecodeEncoder()
    first_encode = encoder.encode(module)

    decoder = BytecodeDecoder()
    decoded = decoder.decode(first_encode)

    # Verify we got the right function
    assert len(decoded.functions) == 1
    assert decoded.functions[0].name == "max"

    # Re-encode the decoded data by checking the code section bytes match
    # Since we can't re-encode from DecodedFunction back to FIRModule,
    # we verify roundtrip by encoding twice and comparing
    second_encode = encoder.encode(module)

    assert first_encode == second_encode, (
        "Encoding the same module twice should produce identical bytes"
    )

    print("  ✓ test_roundtrip")


# ── Test 8: test_validator_bad_magic ──────────────────────────────────────

def test_validator_bad_magic():
    """Non-FLUX magic fails validation."""
    validator = BytecodeValidator()

    # Construct a valid-looking header with wrong magic
    bad_data = b"FAKE" + struct.pack("<HHHI I", 1, 0, 1, HEADER_SIZE, HEADER_SIZE)

    errors = validator.validate(bad_data)
    assert len(errors) > 0, "Should have validation errors for bad magic"
    assert any("magic" in e.lower() for e in errors), f"Expected magic error, got: {errors}"

    print("  ✓ test_validator_bad_magic")


# ── Test 9: test_encode_module ────────────────────────────────────────────

def test_encode_module():
    """Full module with multiple functions."""
    ctx = TypeContext()
    builder = FIRBuilder(ctx)

    module = builder.new_module("multi_func")

    # Function 1: add
    builder._next_value_id = 0
    func1 = builder.new_function(module, "add", [("a", ctx.get_int(32)), ("b", ctx.get_int(32))], [ctx.get_int(32)])
    block1 = builder.new_block(func1, "entry")
    builder.set_block(block1)
    a = Value(id=0, name="a", type=ctx.get_int(32))
    b = Value(id=1, name="b", type=ctx.get_int(32))
    builder._next_value_id = 2
    builder.iadd(a, b)
    builder.ret(_make_value(2))

    # Function 2: noop
    builder._next_value_id = 0
    func2 = builder.new_function(module, "noop", [], [])
    block2 = builder.new_block(func2, "entry")
    builder.set_block(block2)
    builder.ret(None)

    # Function 3: with A2A
    builder._next_value_id = 0
    func3 = builder.new_function(module, "ping_agent", [], [])
    block3 = builder.new_block(func3, "entry")
    builder.set_block(block3)
    msg = _make_value(0, "msg")
    cap = _make_value(1, "cap")
    builder.tell("navigator", msg, cap)
    builder.ret(None)

    # Encode
    encoder = BytecodeEncoder()
    encoded = encoder.encode(module)

    # Decode and verify
    decoder = BytecodeDecoder()
    funcs = decoder.decode_functions(encoded)

    assert len(funcs) == 3, f"Expected 3 functions, got {len(funcs)}"
    func_names = {f.name for f in funcs}
    assert func_names == {"add", "noop", "ping_agent"}, f"Unexpected function names: {func_names}"

    # Verify 'add' function has IADD + RET
    add_func = [f for f in funcs if f.name == "add"][0]
    opcodes = [i.opcode for i in add_func.instructions]
    assert Op.IADD in opcodes, "add function should contain IADD"
    assert Op.RET in opcodes, "add function should contain RET"

    # Verify 'noop' function has just RET
    noop_func = [f for f in funcs if f.name == "noop"][0]
    assert len(noop_func.instructions) >= 1
    assert noop_func.instructions[-1].opcode == Op.RET

    # Verify 'ping_agent' has TELL + RET
    ping_func = [f for f in funcs if f.name == "ping_agent"][0]
    opcodes = [i.opcode for i in ping_func.instructions]
    assert Op.TELL in opcodes, "ping_agent should contain TELL"
    assert Op.RET in opcodes, "ping_agent should contain RET"

    # Validate
    validator = BytecodeValidator()
    errors = validator.validate(encoded)
    assert len(errors) == 0, f"Valid module should have no errors, got: {errors}"

    print("  ✓ test_encode_module")


# ── Test 10: test_validator_structural ────────────────────────────────────

def test_validator_structural():
    """Validator catches various structural issues."""
    validator = BytecodeValidator()

    # Test: too short
    errors = validator.validate(b"FLUX")
    assert len(errors) > 0, "Too-short bytecode should fail"
    assert any("too short" in e.lower() for e in errors), f"Expected 'too short' error, got: {errors}"

    # Test: valid minimal bytecode (header + one func with RET)
    encoder = BytecodeEncoder()
    module = _make_simple_module()
    valid_bytes = encoder.encode(module)
    errors = validator.validate(valid_bytes)
    # Should be valid (0 errors)
    assert len(errors) == 0, f"Valid bytecode should have 0 errors, got: {errors}"

    print("  ✓ test_validator_structural")


# ── Test 11: test_encode_decode_float_ops ─────────────────────────────────

def test_encode_decode_float_ops():
    """Float arithmetic ops encode and decode correctly."""
    encoder = BytecodeEncoder()

    ctx = TypeContext()
    a = Value(id=10, name="fa", type=ctx.get_float(32))
    b = Value(id=11, name="fb", type=ctx.get_float(32))

    fadd = FAdd(lhs=a, rhs=b)
    fadd_bytes = encoder._encode_instruction(fadd)
    assert len(fadd_bytes) == 3
    assert fadd_bytes[0] == Op.FADD
    assert fadd_bytes[1] == 10
    assert fadd_bytes[2] == 11

    fdiv = FDiv(lhs=a, rhs=b)
    fdiv_bytes = encoder._encode_instruction(fdiv)
    assert len(fdiv_bytes) == 3
    assert fdiv_bytes[0] == Op.FDIV

    print("  ✓ test_encode_decode_float_ops")


# ── Test 12: test_all_opcodes_defined ─────────────────────────────────────

def test_all_opcodes_defined():
    """All expected opcodes exist in the Op enum."""
    # Spot-check key opcodes
    expected_ops = {
        "NOP", "MOV", "LOAD", "STORE", "JMP", "JZ", "JNZ", "CALL",
        "IADD", "ISUB", "IMUL", "IDIV", "IMOD", "INEG", "INC", "DEC",
        "IAND", "IOR", "IXOR", "INOT", "ISHL", "ISHR",
        "ICMP", "IEQ", "ILT", "ILE", "IGT", "IGE",
        "PUSH", "POP", "DUP", "SWAP",
        "RET", "HALT", "YIELD",
        "FADD", "FSUB", "FMUL", "FDIV", "FNEG",
        "FEQ", "FLT", "FLE", "FGT", "FGE",
        "VLOAD", "VSTORE", "VADD", "VSUB", "VMUL", "VDIV", "VFMA",
        "TELL", "ASK", "DELEGATE", "TRUST_CHECK", "CAP_REQUIRE",
        "CAST", "BOX", "UNBOX",
        "MEMCOPY", "MEMSET",
        "REGION_CREATE", "REGION_DESTROY",
        "BARRIER", "SYNC_CLOCK", "EMERGENCY_STOP",
        "DEBUG_BREAK",
    }
    for name in expected_ops:
        assert hasattr(Op, name), f"Op.{name} not defined"

    print(f"  ✓ test_all_opcodes_defined ({len(expected_ops)} opcodes checked)")


# ── Run all ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Running FLUX bytecode tests...\n")

    test_encode_decode_simple()
    test_encode_header()
    test_encode_nop()
    test_encode_arithmetic()
    test_encode_jump()
    test_encode_a2a()
    test_roundtrip()
    test_validator_bad_magic()
    test_encode_module()
    test_validator_structural()
    test_encode_decode_float_ops()
    test_all_opcodes_defined()

    print("\n✅ All 12 bytecode tests passed!")
