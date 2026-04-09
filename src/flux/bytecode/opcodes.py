"""FLUX bytecode opcodes. Variable-length encoding (1-8 bytes)."""

from enum import IntEnum


class Op(IntEnum):
    """FLUX bytecode opcodes. Variable-length encoding (1-8 bytes)."""

    # Control flow (0x00-0x07)
    NOP = 0x00
    MOV = 0x01
    LOAD = 0x02
    STORE = 0x03
    JMP = 0x04
    JZ = 0x05
    JNZ = 0x06
    CALL = 0x07

    # Integer arithmetic (0x08-0x0F)
    IADD = 0x08
    ISUB = 0x09
    IMUL = 0x0A
    IDIV = 0x0B
    IMOD = 0x0C
    INEG = 0x0D
    INC = 0x0E
    DEC = 0x0F

    # Bitwise (0x10-0x17)
    IAND = 0x10
    IOR = 0x11
    IXOR = 0x12
    INOT = 0x13
    ISHL = 0x14
    ISHR = 0x15
    ROTL = 0x16
    ROTR = 0x17

    # Comparison (0x18-0x1F)
    ICMP = 0x18
    IEQ = 0x19
    ILT = 0x1A
    ILE = 0x1B
    IGT = 0x1C
    IGE = 0x1D
    TEST = 0x1E
    SETCC = 0x1F

    # Stack ops (0x20-0x27)
    PUSH = 0x20
    POP = 0x21
    DUP = 0x22
    SWAP = 0x23
    ROT = 0x24
    ENTER = 0x25
    LEAVE = 0x26
    ALLOCA = 0x27

    # Function ops (0x28-0x2F)
    RET = 0x28
    CALL_IND = 0x29
    TAILCALL = 0x2A
    MOVI = 0x2B
    IREM = 0x2C
    CMP = 0x2D
    JE = 0x2E
    JNE = 0x2F

    # Memory mgmt (0x30-0x37)
    REGION_CREATE = 0x30
    REGION_DESTROY = 0x31
    REGION_TRANSFER = 0x32
    MEMCOPY = 0x33
    MEMSET = 0x34
    MEMCMP = 0x35
    JL = 0x36
    JGE = 0x37

    # Type ops (0x38-0x3F)
    CAST = 0x38
    BOX = 0x39
    UNBOX = 0x3A
    CHECK_TYPE = 0x3B
    CHECK_BOUNDS = 0x3C

    # Float arithmetic (0x40-0x47)
    FADD = 0x40
    FSUB = 0x41
    FMUL = 0x42
    FDIV = 0x43
    FNEG = 0x44
    FABS = 0x45
    FMIN = 0x46
    FMAX = 0x47

    # Float comparison (0x48-0x4F)
    FEQ = 0x48
    FLT = 0x49
    FLE = 0x4A
    FGT = 0x4B
    FGE = 0x4C
    JG = 0x4D
    JLE = 0x4E
    LOAD8 = 0x4F

    # SIMD vector ops (0x50-0x5F)
    VLOAD = 0x50
    VSTORE = 0x51
    VADD = 0x52
    VSUB = 0x53
    VMUL = 0x54
    VDIV = 0x55
    VFMA = 0x56  # fused multiply-add
    STORE8 = 0x57

    # A2A protocol (0x60-0x7F)
    TELL = 0x60
    ASK = 0x61
    DELEGATE = 0x62
    DELEGATE_RESULT = 0x63
    REPORT_STATUS = 0x64
    REQUEST_OVERRIDE = 0x65
    BROADCAST = 0x66
    REDUCE = 0x67
    DECLARE_INTENT = 0x68
    ASSERT_GOAL = 0x69
    VERIFY_OUTCOME = 0x6A
    EXPLAIN_FAILURE = 0x6B
    SET_PRIORITY = 0x6C
    TRUST_CHECK = 0x70
    TRUST_UPDATE = 0x71
    TRUST_QUERY = 0x72
    REVOKE_TRUST = 0x73
    CAP_REQUIRE = 0x74
    CAP_REQUEST = 0x75
    CAP_GRANT = 0x76
    CAP_REVOKE = 0x77
    BARRIER = 0x78
    SYNC_CLOCK = 0x79
    FORMATION_UPDATE = 0x7A
    EMERGENCY_STOP = 0x7B

    # System (0x80-0x9F)
    HALT = 0x80
    YIELD = 0x81
    RESOURCE_ACQUIRE = 0x82
    RESOURCE_RELEASE = 0x83
    DEBUG_BREAK = 0x84


# ── Opcode classification ──────────────────────────────────────────────────
# Matches the VM interpreter's actual fetch-decode patterns.

# Format A: 1 byte — opcode only
FORMAT_A = frozenset({
    Op.NOP, Op.HALT, Op.YIELD,
    Op.DUP, Op.SWAP, Op.DEBUG_BREAK, Op.EMERGENCY_STOP,
})

# Format B: 2 bytes — opcode + reg:u8
FORMAT_B = frozenset({
    Op.INC, Op.DEC, Op.ENTER, Op.LEAVE,
    Op.PUSH, Op.POP,
    Op.INEG, Op.FNEG, Op.INOT,
})

# Format C: 3 bytes — opcode + rd:u8 + rs1:u8
FORMAT_C = frozenset({
    Op.MOV, Op.LOAD, Op.STORE, Op.CMP,
    Op.LOAD8, Op.STORE8,
    Op.ALLOCA, Op.CAST,
    Op.RET,
    # Binary arithmetic: [op][rs1][rs2]
    Op.IADD, Op.ISUB, Op.IMUL, Op.IDIV, Op.IMOD, Op.IREM,
    Op.IAND, Op.IOR, Op.IXOR, Op.ISHL, Op.ISHR,
    Op.FADD, Op.FSUB, Op.FMUL, Op.FDIV,
    # Comparison: [op][lhs][rhs]
    Op.IEQ, Op.ILT, Op.ILE, Op.IGT, Op.IGE,
    Op.FEQ, Op.FLT, Op.FLE, Op.FGT, Op.FGE,
    Op.ICMP,
})

# Format D: 4 bytes — opcode + reg:u8 + imm16:i16 (signed offset)
FORMAT_D = frozenset({
    Op.JMP, Op.JZ, Op.JNZ,
    Op.JE, Op.JNE, Op.JG, Op.JL, Op.JGE, Op.JLE,
    Op.MOVI, Op.CALL,
})

# Format E: 4 bytes — opcode + rd:u8 + rs1:u8 + rs2:u8 (ternary ops)
FORMAT_E = frozenset({
    Op.VFMA,
})

# Format G: variable — opcode + len:u16 + data:len bytes
FORMAT_G = frozenset({
    Op.REGION_CREATE, Op.REGION_DESTROY, Op.REGION_TRANSFER,
    Op.MEMCOPY, Op.MEMSET, Op.MEMCMP,
    Op.TELL, Op.ASK, Op.DELEGATE, Op.DELEGATE_RESULT,
    Op.REPORT_STATUS, Op.REQUEST_OVERRIDE, Op.BROADCAST, Op.REDUCE,
    Op.DECLARE_INTENT, Op.ASSERT_GOAL, Op.VERIFY_OUTCOME,
    Op.EXPLAIN_FAILURE, Op.SET_PRIORITY,
    Op.TRUST_CHECK, Op.TRUST_UPDATE, Op.TRUST_QUERY, Op.REVOKE_TRUST,
    Op.CAP_REQUIRE, Op.CAP_REQUEST, Op.CAP_GRANT, Op.CAP_REVOKE,
    Op.BARRIER, Op.SYNC_CLOCK, Op.FORMATION_UPDATE,
    Op.RESOURCE_ACQUIRE, Op.RESOURCE_RELEASE,
})

# Everything else defaults to Format C: 3 bytes


def get_format(op: Op) -> str:
    """Return the encoding format letter for an opcode."""
    if op in FORMAT_A:
        return "A"
    if op in FORMAT_B:
        return "B"
    if op in FORMAT_D:
        return "D"
    if op in FORMAT_E:
        return "E"
    if op in FORMAT_G:
        return "G"
    return "C"  # default 3-byte format


def instruction_size(op: Op) -> int:
    """Return the fixed size in bytes for an opcode (or -1 for variable)."""
    fmt = get_format(op)
    return {"A": 1, "B": 2, "C": 3, "D": 4, "E": 4}.get(fmt, -1)


# Alias used by the VM interpreter
opcode_size = instruction_size
