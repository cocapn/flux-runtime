"""FLUX Standard Library — built-in intrinsics, collections, math, strings, and agent utilities.

Each stdlib function is represented as a callable that produces FIR instructions
when invoked through a :class:`FIRBuilder`.  This lets the compiler inline stdlib
operations at the IR level before lowering to bytecode.
"""

from .intrinsics import (
    IntrinsicFunction,
    PrintFn,
    AssertFn,
    PanicFn,
    SizeofFn,
    AlignofFn,
    TypeOfFn,
    STDLIB_INTRINSICS,
)
from .collections import (
    ListImpl,
    MapImpl,
    SetImpl,
    QueueImpl,
    StackImpl,
    STDLIB_COLLECTIONS,
)
from .math import (
    MinFn,
    MaxFn,
    AbsFn,
    ClampFn,
    LerpFn,
    SqrtFn,
    STDLIB_MATH,
)
from .strings import (
    ConcatFn,
    SubstringFn,
    SplitFn,
    JoinFn,
    LengthFn,
    FormatFn,
    STDLIB_STRINGS,
)
from .agents import (
    AgentRegistryImpl,
    MessageQueueImpl,
    TaskSchedulerImpl,
    STDLIB_AGENTS,
)

__all__ = [
    # Intrinsics
    "IntrinsicFunction", "PrintFn", "AssertFn", "PanicFn",
    "SizeofFn", "AlignofFn", "TypeOfFn", "STDLIB_INTRINSICS",
    # Collections
    "ListImpl", "MapImpl", "SetImpl", "QueueImpl", "StackImpl",
    "STDLIB_COLLECTIONS",
    # Math
    "MinFn", "MaxFn", "AbsFn", "ClampFn", "LerpFn", "SqrtFn",
    "STDLIB_MATH",
    # Strings
    "ConcatFn", "SubstringFn", "SplitFn", "JoinFn", "LengthFn",
    "FormatFn", "STDLIB_STRINGS",
    # Agents
    "AgentRegistryImpl", "MessageQueueImpl", "TaskSchedulerImpl",
    "STDLIB_AGENTS",
]
