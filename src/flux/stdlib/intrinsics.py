"""Built-in intrinsic functions for the FLUX standard library.

Each intrinsic is a callable that appends FIR instructions to the current
builder block.  Intrinsics represent runtime primitives that map directly
to VM syscalls or built-in operations.
"""

from __future__ import annotations

from typing import Optional

from flux.fir.types import (
    FIRType, TypeContext, IntType, BoolType, UnitType, StringType,
)
from flux.fir.values import Value
from flux.fir.instructions import Call, Unreachable
from flux.fir.builder import FIRBuilder


# ── Base ────────────────────────────────────────────────────────────────────


class IntrinsicFunction:
    """Base class for all standard library intrinsic functions.

    An intrinsic wraps a FIR ``call`` instruction to a known runtime symbol.
    Subclasses override :meth:`emit` to produce type-checked FIR instructions
    via the builder.
    """

    name: str = ""
    description: str = ""

    def emit(
        self,
        builder: FIRBuilder,
        args: list[Value],
        **kwargs,
    ) -> Optional[Value]:
        """Emit FIR instructions for this intrinsic.

        Parameters
        ----------
        builder : FIRBuilder
            The active FIR builder with a current block set.
        args : list[Value]
            SSA values representing the function arguments.
        **kwargs
            Extra parameters specific to the intrinsic.

        Returns
        -------
        Value or None
            The result SSA value, or ``None`` for void intrinsics.
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<intrinsic {self.name}>"


# ── print(value) → void ────────────────────────────────────────────────────


class PrintFn(IntrinsicFunction):
    """Print a value to the VM's output stream."""

    name = "print"
    description = "Print a value to the VM output stream."

    def emit(
        self,
        builder: FIRBuilder,
        args: list[Value],
        **kwargs,
    ) -> None:
        if len(args) < 1:
            raise ValueError("print() requires at least 1 argument")
        builder.call("flux.print", args, return_type=None)


# ── assert(condition, message?) → void ─────────────────────────────────────


class AssertFn(IntrinsicFunction):
    """Assert that a boolean condition is true; panic otherwise."""

    name = "assert"
    description = "Assert a boolean condition; panic on failure."

    def emit(
        self,
        builder: FIRBuilder,
        args: list[Value],
        message: str = "assertion failed",
        **kwargs,
    ) -> None:
        if len(args) < 1:
            raise ValueError("assert() requires a condition argument")
        cond = args[0]
        # Emit: call flux.assert(cond, message_id)
        msg_val = Value(id=-1, name=message, type=builder._ctx.get_string())
        builder.call("flux.assert", [cond, msg_val], return_type=None)


# ── panic(message) → ! ─────────────────────────────────────────────────────


class PanicFn(IntrinsicFunction):
    """Halt execution with an error message."""

    name = "panic"
    description = "Halt execution immediately with an error message."

    def emit(
        self,
        builder: FIRBuilder,
        args: list[Value],
        **kwargs,
    ) -> None:
        msg_val = args[0] if args else Value(
            id=-1, name="panic", type=builder._ctx.get_string()
        )
        builder.call("flux.panic", [msg_val], return_type=None)
        builder.unreachable()


# ── sizeof(type) → i32 ─────────────────────────────────────────────────────


class SizeofFn(IntrinsicFunction):
    """Return the size in bytes of a FIR type."""

    name = "sizeof"
    description = "Return the size in bytes of a FIR type."

    def emit(
        self,
        builder: FIRBuilder,
        args: list[Value],
        target_type: Optional[FIRType] = None,
        **kwargs,
    ) -> Value:
        if target_type is None and len(args) > 0:
            target_type = args[0].type
        if target_type is None:
            raise ValueError("sizeof() requires a type or typed value")
        # sizeof is computed at compile time; emit a constant call
        size = _compute_sizeof(target_type)
        result_type = builder._ctx.get_int(32)
        # Emit call to runtime for dynamic sizeof
        type_tag = Value(id=-1, name=f"__type_{id(target_type)}", type=target_type)
        builder.call("flux.sizeof", [type_tag], return_type=result_type)
        return Value(id=builder._next_value_id, name="sizeof_result", type=result_type)


# ── alignof(type) → i32 ────────────────────────────────────────────────────


class AlignofFn(IntrinsicFunction):
    """Return the alignment in bytes of a FIR type."""

    name = "alignof"
    description = "Return the alignment in bytes of a FIR type."

    def emit(
        self,
        builder: FIRBuilder,
        args: list[Value],
        target_type: Optional[FIRType] = None,
        **kwargs,
    ) -> Value:
        if target_type is None and len(args) > 0:
            target_type = args[0].type
        if target_type is None:
            raise ValueError("alignof() requires a type or typed value")
        result_type = builder._ctx.get_int(32)
        type_tag = Value(id=-1, name=f"__type_{id(target_type)}", type=target_type)
        builder.call("flux.alignof", [type_tag], return_type=result_type)
        return Value(id=builder._next_value_id, name="alignof_result", type=result_type)


# ── type_of(value) → string ────────────────────────────────────────────────


class TypeOfFn(IntrinsicFunction):
    """Return the type name of a value as a string."""

    name = "type_of"
    description = "Return the type name of a value as a string."

    def emit(
        self,
        builder: FIRBuilder,
        args: list[Value],
        **kwargs,
    ) -> Value:
        if len(args) < 1:
            raise ValueError("type_of() requires a value argument")
        result_type = builder._ctx.get_string()
        builder.call("flux.type_of", args, return_type=result_type)
        return Value(id=builder._next_value_id, name="typeof_result", type=result_type)


# ── Size computation helper ────────────────────────────────────────────────


def _compute_sizeof(t: FIRType) -> int:
    """Compute a reasonable size for a FIR type in bytes."""
    if isinstance(t, IntType):
        return t.bits // 8
    if isinstance(t, BoolType):
        return 1
    if isinstance(t, UnitType):
        return 0
    if isinstance(t, StringType):
        return 16  # pointer + length
    # For composite types, return a placeholder
    return 8


# ── Registry of all intrinsics ─────────────────────────────────────────────

STDLIB_INTRINSICS: dict[str, IntrinsicFunction] = {
    "print": PrintFn(),
    "assert": AssertFn(),
    "panic": PanicFn(),
    "sizeof": SizeofFn(),
    "alignof": AlignofFn(),
    "type_of": TypeOfFn(),
}
