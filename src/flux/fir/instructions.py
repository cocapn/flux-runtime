"""FIR Instructions — all instruction types for the FLUX intermediate representation."""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .types import FIRType
    from .values import Value


# ── Base ────────────────────────────────────────────────────────────────────

class Instruction(ABC):
    """Base class for all FIR instructions."""

    @property
    @abstractmethod
    def opcode(self) -> str:
        ...

    @property
    def result_type(self) -> Optional[FIRType]:
        """Return the type produced by this instruction, or None if void."""
        return None


# ── Arithmetic (integer) ───────────────────────────────────────────────────

@dataclass
class IAdd(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "iadd"
    @property
    def result_type(self): return self.lhs.type


@dataclass
class ISub(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "isub"
    @property
    def result_type(self): return self.lhs.type


@dataclass
class IMul(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "imul"
    @property
    def result_type(self): return self.lhs.type


@dataclass
class IDiv(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "idiv"
    @property
    def result_type(self): return self.lhs.type


@dataclass
class IMod(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "imod"
    @property
    def result_type(self): return self.lhs.type


@dataclass
class INeg(Instruction):
    lhs: Value
    @property
    def opcode(self): return "ineg"
    @property
    def result_type(self): return self.lhs.type


# ── Arithmetic (float) ────────────────────────────────────────────────────

@dataclass
class FAdd(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "fadd"
    @property
    def result_type(self): return self.lhs.type


@dataclass
class FSub(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "fsub"
    @property
    def result_type(self): return self.lhs.type


@dataclass
class FMul(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "fmul"
    @property
    def result_type(self): return self.lhs.type


@dataclass
class FDiv(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "fdiv"
    @property
    def result_type(self): return self.lhs.type


@dataclass
class FNeg(Instruction):
    lhs: Value
    @property
    def opcode(self): return "fneg"
    @property
    def result_type(self): return self.lhs.type


# ── Bitwise ────────────────────────────────────────────────────────────────

@dataclass
class IAnd(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "iand"
    @property
    def result_type(self): return self.lhs.type


@dataclass
class IOr(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "ior"
    @property
    def result_type(self): return self.lhs.type


@dataclass
class IXor(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "ixor"
    @property
    def result_type(self): return self.lhs.type


@dataclass
class IShl(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "ishl"
    @property
    def result_type(self): return self.lhs.type


@dataclass
class IShr(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "ishr"
    @property
    def result_type(self): return self.lhs.type


@dataclass
class INot(Instruction):
    lhs: Value
    @property
    def opcode(self): return "inot"
    @property
    def result_type(self): return self.lhs.type


# ── Comparison ─────────────────────────────────────────────────────────────

@dataclass
class IEq(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "ieq"
    @property
    def result_type(self):
        from .types import BoolType
        return BoolType(type_id=-1)


@dataclass
class INe(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "ine"
    @property
    def result_type(self):
        from .types import BoolType
        return BoolType(type_id=-1)


@dataclass
class ILt(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "ilt"
    @property
    def result_type(self):
        from .types import BoolType
        return BoolType(type_id=-1)


@dataclass
class IGt(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "igt"
    @property
    def result_type(self):
        from .types import BoolType
        return BoolType(type_id=-1)


@dataclass
class ILe(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "ile"
    @property
    def result_type(self):
        from .types import BoolType
        return BoolType(type_id=-1)


@dataclass
class IGe(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "ige"
    @property
    def result_type(self):
        from .types import BoolType
        return BoolType(type_id=-1)


@dataclass
class FEq(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "feq"
    @property
    def result_type(self):
        from .types import BoolType
        return BoolType(type_id=-1)


@dataclass
class FLt(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "flt"
    @property
    def result_type(self):
        from .types import BoolType
        return BoolType(type_id=-1)


@dataclass
class FGt(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "fgt"
    @property
    def result_type(self):
        from .types import BoolType
        return BoolType(type_id=-1)


@dataclass
class FLe(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "fle"
    @property
    def result_type(self):
        from .types import BoolType
        return BoolType(type_id=-1)


@dataclass
class FGe(Instruction):
    lhs: Value
    rhs: Value
    @property
    def opcode(self): return "fge"
    @property
    def result_type(self):
        from .types import BoolType
        return BoolType(type_id=-1)


# ── Conversion ─────────────────────────────────────────────────────────────

@dataclass
class ITrunc(Instruction):
    value: Value
    target_type: FIRType
    @property
    def opcode(self): return "itrunc"
    @property
    def result_type(self): return self.target_type


@dataclass
class ZExt(Instruction):
    value: Value
    target_type: FIRType
    @property
    def opcode(self): return "zext"
    @property
    def result_type(self): return self.target_type


@dataclass
class SExt(Instruction):
    value: Value
    target_type: FIRType
    @property
    def opcode(self): return "sext"
    @property
    def result_type(self): return self.target_type


@dataclass
class FTrunc(Instruction):
    value: Value
    target_type: FIRType
    @property
    def opcode(self): return "ftrunc"
    @property
    def result_type(self): return self.target_type


@dataclass
class FExt(Instruction):
    value: Value
    target_type: FIRType
    @property
    def opcode(self): return "fext"
    @property
    def result_type(self): return self.target_type


@dataclass
class Bitcast(Instruction):
    value: Value
    target_type: FIRType
    @property
    def opcode(self): return "bitcast"
    @property
    def result_type(self): return self.target_type


# ── Memory ─────────────────────────────────────────────────────────────────

@dataclass
class Load(Instruction):
    type: FIRType
    ptr: Value
    offset: int = 0
    @property
    def opcode(self): return "load"
    @property
    def result_type(self): return self.type


@dataclass
class Store(Instruction):
    value: Value
    ptr: Value
    offset: int = 0
    @property
    def opcode(self): return "store"


@dataclass
class Alloca(Instruction):
    type: FIRType
    count: int = 1
    @property
    def opcode(self): return "alloca"
    @property
    def result_type(self):
        from .types import RefType
        return RefType(type_id=-1, element=self.type)  # sentinel — real type via TypeContext


@dataclass
class GetField(Instruction):
    struct_val: Value
    field_name: str
    field_index: int
    field_type: FIRType
    @property
    def opcode(self): return "getfield"
    @property
    def result_type(self): return self.field_type


@dataclass
class SetField(Instruction):
    struct_val: Value
    field_name: str
    field_index: int
    value: Value
    @property
    def opcode(self): return "setfield"


@dataclass
class GetElem(Instruction):
    array_val: Value
    index: Value
    elem_type: FIRType
    @property
    def opcode(self): return "getelem"
    @property
    def result_type(self): return self.elem_type


@dataclass
class SetElem(Instruction):
    array_val: Value
    index: Value
    value: Value
    @property
    def opcode(self): return "setelem"


@dataclass
class MemCopy(Instruction):
    src: Value
    dst: Value
    size: int
    @property
    def opcode(self): return "memcpy"


@dataclass
class MemSet(Instruction):
    dst: Value
    value: int
    size: int
    @property
    def opcode(self): return "memset"


# ── Control flow ───────────────────────────────────────────────────────────

@dataclass
class Jump(Instruction):
    target_block: str
    args: list[Value] = field(default_factory=list)
    @property
    def opcode(self): return "jump"


@dataclass
class Branch(Instruction):
    cond: Value
    true_block: str
    false_block: str
    args: list[Value] = field(default_factory=list)
    @property
    def opcode(self): return "branch"


@dataclass
class Switch(Instruction):
    value: Value
    cases: dict[int, str] = field(default_factory=dict)
    default_block: str = ""
    @property
    def opcode(self): return "switch"


@dataclass
class Call(Instruction):
    func: str
    args: list[Value] = field(default_factory=list)
    return_type: Optional[FIRType] = None
    @property
    def opcode(self): return "call"
    @property
    def result_type(self): return self.return_type


@dataclass
class Return(Instruction):
    value: Optional[Value] = None
    @property
    def opcode(self): return "return"


@dataclass
class Unreachable(Instruction):
    @property
    def opcode(self): return "unreachable"


# ── A2A Primitives ─────────────────────────────────────────────────────────

@dataclass
class Tell(Instruction):
    target_agent: str
    message: Value
    cap: Value
    @property
    def opcode(self): return "tell"


@dataclass
class Ask(Instruction):
    target_agent: str
    message: Value
    return_type: FIRType
    cap: Value
    @property
    def opcode(self): return "ask"
    @property
    def result_type(self): return self.return_type


@dataclass
class Delegate(Instruction):
    target_agent: str
    authority: Value
    cap: Value
    @property
    def opcode(self): return "delegate"


@dataclass
class TrustCheck(Instruction):
    agent: str
    threshold: Value
    cap: Value
    @property
    def opcode(self): return "trustcheck"
    @property
    def result_type(self):
        from .types import BoolType
        return BoolType(type_id=-1)  # sentinel


@dataclass
class CapRequire(Instruction):
    capability: str
    resource: str
    cap: Value
    @property
    def opcode(self): return "caprequire"


# ── Terminator check ───────────────────────────────────────────────────────

TERMINATOR_OPCODES = frozenset({"jump", "branch", "switch", "return", "unreachable"})


def is_terminator(instr: Instruction) -> bool:
    """Return True if the instruction is a block terminator."""
    return instr.opcode in TERMINATOR_OPCODES
