"""Type compatibility checker for cross-language type interoperability.

Provides functions to check whether two FIR types can interoperate,
compute the cost of coercion between types, and find the least
upper bound (common supertype) of two types.
"""

from __future__ import annotations

from typing import Optional

from flux.fir.types import (
    FIRType, IntType, FloatType, BoolType, UnitType, StringType,
    RefType, ArrayType, VectorType, FuncType, StructType, TypeContext,
)
from flux.types.generic import GenericType, TypeVar
from flux.types.unify import TypeUnifier, _type_eq


def are_compatible(t1: FIRType, t2: FIRType) -> bool:
    """Check if two FIR types can interoperate.

    Two types are compatible if they are identical, if one can be
    implicitly coerced to the other, or if they share a common
    supertype that both can reach through widening conversions.

    Args:
        t1: First FIRType.
        t2: Second FIRType.

    Returns:
        True if the types can interoperate.
    """
    # Identity
    if _type_eq(t1, t2):
        return True

    # Both numeric (int or float) — always compatible via widening
    if isinstance(t1, (IntType, FloatType)) and isinstance(t2, (IntType, FloatType)):
        return True

    # Bool is compatible with int
    if isinstance(t1, BoolType) and isinstance(t2, (IntType, BoolType)):
        return True
    if isinstance(t2, BoolType) and isinstance(t1, (IntType, BoolType)):
        return True

    # Unit is compatible with everything (can discard any value)
    if isinstance(t1, UnitType) or isinstance(t2, UnitType):
        return True

    # String compatibility
    if isinstance(t1, StringType) and isinstance(t2, StringType):
        return True

    # Ref type compatibility (covariant element types)
    if isinstance(t1, RefType) and isinstance(t2, RefType):
        return are_compatible(t1.element, t2.element)

    # Array compatibility (same length, compatible elements)
    if isinstance(t1, ArrayType) and isinstance(t2, ArrayType):
        if t1.length != t2.length:
            return False
        return are_compatible(t1.element, t2.element)

    # Vector compatibility (same lane count, compatible elements)
    if isinstance(t1, VectorType) and isinstance(t2, VectorType):
        if t1.lanes != t2.lanes:
            return False
        return are_compatible(t1.element, t2.element)

    # Generic type compatibility (same name, compatible args)
    if isinstance(t1, GenericType) and isinstance(t2, GenericType):
        if t1.name != t2.name or len(t1.args) != len(t2.args):
            return False
        # Allow TypeVars to match anything
        for a1, a2 in zip(t1.args, t2.args):
            if isinstance(a1, TypeVar) or isinstance(a2, TypeVar):
                continue  # type vars are universally compatible
            if not are_compatible(a1, a2):
                return False
        return True

    # FuncType compatibility (contravariant params, covariant returns)
    if isinstance(t1, FuncType) and isinstance(t2, FuncType):
        if len(t1.params) != len(t2.params):
            return False
        if len(t1.returns) != len(t2.returns):
            return False
        # Parameters are contravariant
        for p1, p2 in zip(t1.params, t2.params):
            if not are_compatible(p2, p1):  # note: reversed
                return False
        # Returns are covariant
        for r1, r2 in zip(t1.returns, t2.returns):
            if not are_compatible(r1, r2):
                return False
        return True

    # TypeVar is compatible with anything
    if isinstance(t1, TypeVar) or isinstance(t2, TypeVar):
        return True

    return False


def coercion_cost(t1: FIRType, t2: FIRType, ctx: Optional[TypeContext] = None) -> int:
    """Compute the cost of coercing from t1 to t2.

    Cost scale:
    - 0: identical types
    - 1: implicit widening (i8→i16, f32→f64)
    - 2: narrowing (i64→i32) or sign change
    - 3: both narrowing and sign change
    - 5: int↔float conversion
    - 8: bool↔int conversion
    - 10: cross-category (int↔string, etc.)
    - 15: generic type arg mismatch
    - 100: incompatible types

    Args:
        t1: Source FIRType.
        t2: Target FIRType.
        ctx: Optional TypeContext for creating intermediate types.

    Returns:
        Integer cost of coercion (lower = cheaper).
    """
    unifier = TypeUnifier(ctx=ctx)
    return unifier.coercion_cost(t1, t2)


def least_upper_bound(
    t1: FIRType,
    t2: FIRType,
    ctx: Optional[TypeContext] = None,
) -> Optional[FIRType]:
    """Find the least upper bound (common supertype) of two types.

    The LUB is the most specific type that both t1 and t2 can be
    coerced to without data loss.

    Args:
        t1: First FIRType.
        t2: Second FIRType.
        ctx: Optional TypeContext for creating interned types.

    Returns:
        The LUB FIRType, or None if no common supertype exists.
    """
    unifier = TypeUnifier(ctx=ctx)
    return unifier._unify_pair(t1, t2)


def compatibility_report(t1: FIRType, t2: FIRType) -> dict:
    """Generate a detailed compatibility report between two types.

    Args:
        t1: First FIRType.
        t2: Second FIRType.

    Returns:
        Dictionary with compatibility details:
        - compatible: bool
        - cost: int (coercion cost)
        - lub: Optional[FIRType] (least upper bound)
        - implicit: bool (whether implicit coercion is possible)
    """
    unifier = TypeUnifier()
    compatible = are_compatible(t1, t2)
    cost = unifier.coercion_cost(t1, t2)
    lub = unifier._unify_pair(t1, t2)

    return {
        "compatible": compatible,
        "cost": cost,
        "lub": lub,
        "implicit": unifier.can_implicitly_coerce(t1, t2),
    }
