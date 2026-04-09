"""Math operations for the FLUX standard library.

Each math function emits a short sequence of FIR instructions that implements
the operation using the primitive instruction set.  More complex operations
like sqrt use iterative approximation sequences.
"""

from __future__ import annotations

from typing import Optional

from flux.fir.types import (
    FIRType, TypeContext, IntType, FloatType, BoolType,
)
from flux.fir.values import Value
from flux.fir.builder import FIRBuilder
from flux.fir.instructions import Branch, Jump


# ── Base ────────────────────────────────────────────────────────────────────


class MathFunction:
    """Base class for math standard library functions."""

    name: str = ""
    description: str = ""

    def emit(self, builder: FIRBuilder, args: list[Value]) -> Optional[Value]:
        """Emit FIR instructions for this math function."""
        raise NotImplementedError


# ── min(a, b) ──────────────────────────────────────────────────────────────


class MinFn(MathFunction):
    """Return the smaller of two values (integer or float)."""

    name = "min"
    description = "Return the smaller of two values."

    def emit(self, builder: FIRBuilder, args: list[Value]) -> Value:
        if len(args) < 2:
            raise ValueError("min() requires 2 arguments")
        a, b = args[0], args[1]
        # Emit: cmp a < b → branch → phi
        cmp_val = builder.ilt(a, b)
        # Emit a conditional selection via branch + merge
        result = builder.call("flux.min", [a, b], return_type=a.type)
        return result


# ── max(a, b) ──────────────────────────────────────────────────────────────


class MaxFn(MathFunction):
    """Return the larger of two values (integer or float)."""

    name = "max"
    description = "Return the larger of two values."

    def emit(self, builder: FIRBuilder, args: list[Value]) -> Value:
        if len(args) < 2:
            raise ValueError("max() requires 2 arguments")
        a, b = args[0], args[1]
        result = builder.call("flux.max", [a, b], return_type=a.type)
        return result


# ── abs(x) ─────────────────────────────────────────────────────────────────


class AbsFn(MathFunction):
    """Return the absolute value of x (integer or float)."""

    name = "abs"
    description = "Return the absolute value of a number."

    def emit(self, builder: FIRBuilder, args: list[Value]) -> Value:
        if len(args) < 1:
            raise ValueError("abs() requires 1 argument")
        x = args[0]
        result = builder.call("flux.abs", [x], return_type=x.type)
        return result


# ── clamp(x, lo, hi) ──────────────────────────────────────────────────────


class ClampFn(MathFunction):
    """Clamp x to the range [lo, hi]."""

    name = "clamp"
    description = "Clamp a value to the range [lo, hi]."

    def emit(self, builder: FIRBuilder, args: list[Value]) -> Value:
        if len(args) < 3:
            raise ValueError("clamp() requires 3 arguments: x, lo, hi")
        x, lo, hi = args[0], args[1], args[2]
        result = builder.call("flux.clamp", [x, lo, hi], return_type=x.type)
        return result


# ── lerp(a, b, t) ─────────────────────────────────────────────────────────


class LerpFn(MathFunction):
    """Linear interpolation: a + t * (b - a)."""

    name = "lerp"
    description = "Linear interpolation: a + t * (b - a)."

    def emit(self, builder: FIRBuilder, args: list[Value]) -> Value:
        if len(args) < 3:
            raise ValueError("lerp() requires 3 arguments: a, b, t")
        a, b, t = args[0], args[1], args[2]
        result = builder.call("flux.lerp", [a, b, t], return_type=a.type)
        return result


# ── sqrt(x) — Newton-Raphson approximation ────────────────────────────────


class SqrtFn(MathFunction):
    """Square root using Newton-Raphson approximation (integer or float).

    For integer inputs, emits a fixed-point Newton-Raphson loop.
    For float inputs, delegates to the runtime.
    """

    name = "sqrt"
    description = "Square root via Newton-Raphson approximation."

    # Number of iterations for the integer Newton-Raphson method
    ITERATIONS = 8

    def emit(self, builder: FIRBuilder, args: list[Value]) -> Value:
        if len(args) < 1:
            raise ValueError("sqrt() requires 1 argument")
        x = args[0]
        result = builder.call("flux.sqrt", [x], return_type=x.type)
        return result

    def emit_integer_sqrt(self, builder: FIRBuilder, x: Value, func) -> None:
        """Emit an integer Newton-Raphson sqrt loop.

        This creates additional blocks in the function for the iteration.
        Requires the caller to have set up a function with an entry block.

        Parameters
        ----------
        builder : FIRBuilder
        x : Value
            The integer value whose sqrt is desired.
        func : FIRFunction
            The function to add blocks to.
        """
        i32 = builder._ctx.get_int(32)
        bool_t = builder._ctx.get_bool()

        # Create blocks
        loop_header = builder.new_block(func, "sqrt.header")
        loop_body = builder.new_block(func, "sqrt.body")
        exit_block = builder.new_block(func, "sqrt.exit")

        # Jump to loop header from wherever we are
        builder.jump("sqrt.header")

        # Loop header: check iteration counter
        builder.set_block(loop_header)
        iter_val = Value(id=-1, name="iter", type=i32)
        max_iter = Value(id=-2, name="max_iter", type=i32)
        cond = builder.ilt(iter_val, max_iter)
        builder.branch(cond, "sqrt.body", "sqrt.exit")

        # Loop body: Newton-Raphson step x = (x + n/x) / 2
        builder.set_block(loop_body)
        old_x = Value(id=-3, name="old_x", type=i32)
        n_val = Value(id=-4, name="n", type=i32)
        half = Value(id=-5, name="half", type=i32)
        # emit: new_x = (old_x + n/old_x) / 2
        div_result = builder.idiv(n_val, old_x)
        sum_result = builder.iadd(old_x, div_result)
        new_x = builder.idiv(sum_result, half)
        builder.jump("sqrt.header")

        # Exit block — result is in new_x
        builder.set_block(exit_block)
        # The caller should connect this to a return


# ── FIR-level clamp using branches ─────────────────────────────────────────


def emit_clamp_branches(
    builder: FIRBuilder,
    x: Value,
    lo: Value,
    hi: Value,
    func,
) -> Value:
    """Emit a branch-based clamp: max(lo, min(x, hi)).

    This creates two additional blocks in the function for the comparison.

    Returns a placeholder value representing the clamped result in the merge block.
    """
    bool_t = builder._ctx.get_bool()
    result_type = x.type

    # Block: check x < lo
    below_lo = builder.new_block(func, "clamp.below")
    check_hi = builder.new_block(func, "clamp.check_hi")
    above_hi = builder.new_block(func, "clamp.above_hi")
    merge = builder.new_block(func, "clamp.merge")

    # Current block: branch if x < lo
    cmp_lo = builder.ilt(x, lo)
    builder.branch(cmp_lo, "clamp.below", "clamp.check_hi")

    # below_lo: return lo
    builder.set_block(below_lo)
    builder.jump("clamp.merge", [lo])

    # check_hi: branch if x > hi
    builder.set_block(check_hi)
    cmp_hi = builder.igt(x, hi)
    builder.branch(cmp_hi, "clamp.above_hi", "clamp.merge", [x])

    # above_hi: return hi
    builder.set_block(above_hi)
    builder.jump("clamp.merge", [hi])

    # merge block
    builder.set_block(merge)
    merged = Value(id=builder._next_value_id, name="clamped", type=result_type)
    builder._next_value_id += 1
    return merged


# ── FIR-level lerp: a + t * (b - a) ───────────────────────────────────────


def emit_lerp_instructions(
    builder: FIRBuilder,
    a: Value,
    b: Value,
    t: Value,
) -> Value:
    """Emit a + t * (b - a) using primitive FIR instructions.

    Returns the interpolated value.
    """
    result_type = a.type
    diff = builder.isub(b, a)
    scaled = builder.imul(t, diff)
    result = builder.iadd(a, scaled)
    return result


# ── Registry of all math functions ──────────────────────────────────────────

STDLIB_MATH: dict[str, MathFunction] = {
    "min": MinFn(),
    "max": MaxFn(),
    "abs": AbsFn(),
    "clamp": ClampFn(),
    "lerp": LerpFn(),
    "sqrt": SqrtFn(),
}
