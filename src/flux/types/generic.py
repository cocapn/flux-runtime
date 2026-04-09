"""Generic and polymorphic type support for the FLUX type system.

Provides GenericType (parameterized types like Vec<T>, Map<K,V>),
TypeVar (type variables), and TypeScheme (type schemes for
parametric polymorphism with instantiation and substitution).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Union

from flux.fir.types import (
    FIRType, TypeContext, IntType, FloatType, BoolType, UnitType,
    StringType, RefType, ArrayType, VectorType, FuncType, StructType,
)


# ── Type Variable ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TypeVar(FIRType):
    """A type variable for parametric polymorphism.

    Type variables represent unknown types that are bound by a TypeScheme.
    They may carry upper-bound constraints (e.g., T : Numeric).

    Attributes:
        name: Variable name (e.g., "T", "K", "V").
        constraints: Tuple of upper-bound FIRTypes.
    """
    name: str
    constraints: tuple = ()  # tuple of FIRType (upper bounds)

    def __repr__(self) -> str:
        if self.constraints:
            bounds = ", ".join(str(c) for c in self.constraints)
            return f"{self.name} <: {bounds}"
        return self.name


# ── Generic Type ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GenericType(FIRType):
    """A parameterized type such as Vec<T>, Map<K, V>, Option<T>.

    GenericType wraps a base type name with type arguments that may
    be concrete FIRTypes or TypeVars.

    Attributes:
        name: Base type name (e.g., "Vec", "Map", "Option", "Result").
        args: Tuple of type arguments (FIRType or TypeVar).
    """
    name: str
    args: tuple = ()  # tuple of FIRType or TypeVar

    def __repr__(self) -> str:
        if self.args:
            args_str = ", ".join(str(a) for a in self.args)
            return f"{self.name}<{args_str}>"
        return self.name

    def is_fully_concrete(self) -> bool:
        """Check if all type arguments are concrete (no TypeVars)."""
        return all(
            not isinstance(a, TypeVar)
            for a in self.args
        )


# ── Type Scheme ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TypeScheme:
    """A type scheme for parametric polymorphism (à la Hindley-Milner).

    A type scheme quantifies over type variables: ∀ α₁, …, αₙ. τ
    where τ is the body type that may reference the quantified variables.

    Attributes:
        vars: Tuple of quantified TypeVars.
        body: The type expression (may contain TypeVars).
    """
    vars: tuple  # tuple of TypeVar
    body: FIRType

    def instantiate(
        self,
        substitutions: Optional[dict[str, FIRType]] = None,
        ctx: Optional[TypeContext] = None,
    ) -> FIRType:
        """Instantiate the scheme by replacing type variables with concrete types.

        If substitutions is None, fresh TypeVars are generated for each
        quantified variable (generic instantiation).

        Args:
            substitutions: Mapping from TypeVar name to concrete FIRType.
                If None, generates fresh type variables.
            ctx: TypeContext for creating fresh types (if needed).

        Returns:
            The instantiated type with all type variables substituted.
        """
        if substitutions is None:
            # Generate fresh type variables
            substitutions = {}
            for tv in self.vars:
                fresh = TypeVar(
                    type_id=-1,
                    name=f"${tv.name}",
                    constraints=tv.constraints,
                )
                substitutions[tv.name] = fresh

        return _substitute(self.body, substitutions)

    def apply(self, mapping: dict[str, FIRType]) -> FIRType:
        """Apply a substitution mapping to the body.

        Args:
            mapping: Mapping from TypeVar name to concrete FIRType.

        Returns:
            The body with substitutions applied.
        """
        return _substitute(self.body, mapping)

    def free_vars(self) -> set[str]:
        """Get the set of free type variable names in the body.

        Returns:
            Set of type variable names that appear in the body but
            are not bound by this scheme.
        """
        bound = {tv.name for tv in self.vars}
        return _collect_free_vars(self.body) - bound

    def __repr__(self) -> str:
        if self.vars:
            vars_str = ", ".join(str(v) for v in self.vars)
            return f"∀ {vars_str}. {self.body}"
        return str(self.body)


# ── Substitution ───────────────────────────────────────────────────────────

def _substitute(ty: FIRType, mapping: dict[str, FIRType]) -> FIRType:
    """Recursively substitute type variables in a type.

    Args:
        ty: The type to substitute in.
        mapping: Mapping from TypeVar name to replacement FIRType.

    Returns:
        A new type with substitutions applied.
    """
    if isinstance(ty, TypeVar):
        if ty.name in mapping:
            return mapping[ty.name]
        return ty

    if isinstance(ty, GenericType):
        new_args = tuple(_substitute(a, mapping) for a in ty.args)
        if new_args != ty.args:
            return GenericType(type_id=ty.type_id, name=ty.name, args=new_args)
        return ty

    if isinstance(ty, FuncType):
        new_params = tuple(_substitute(p, mapping) for p in ty.params)
        new_returns = tuple(_substitute(r, mapping) for r in ty.returns)
        if new_params != ty.params or new_returns != ty.returns:
            return FuncType(
                type_id=ty.type_id,
                params=new_params,
                returns=new_returns,
            )
        return ty

    if isinstance(ty, StructType):
        new_fields = tuple(
            (n, _substitute(f, mapping)) for n, f in ty.fields
        )
        if new_fields != ty.fields:
            return StructType(
                type_id=ty.type_id,
                name=ty.name,
                fields=new_fields,
            )
        return ty

    if isinstance(ty, ArrayType):
        new_elem = _substitute(ty.element, mapping)
        if new_elem != ty.element:
            return ArrayType(
                type_id=ty.type_id,
                element=new_elem,
                length=ty.length,
            )
        return ty

    if isinstance(ty, VectorType):
        new_elem = _substitute(ty.element, mapping)
        if new_elem != ty.element:
            return VectorType(
                type_id=ty.type_id,
                element=new_elem,
                lanes=ty.lanes,
            )
        return ty

    if isinstance(ty, RefType):
        new_elem = _substitute(ty.element, mapping)
        if new_elem != ty.element:
            return RefType(type_id=ty.type_id, element=new_elem)
        return ty

    # Base types (IntType, FloatType, BoolType, etc.) have no sub-types
    return ty


def _collect_free_vars(ty: FIRType) -> set[str]:
    """Collect all free type variable names in a type."""
    result: set[str] = set()

    if isinstance(ty, TypeVar):
        result.add(ty.name)

    elif isinstance(ty, GenericType):
        for arg in ty.args:
            result |= _collect_free_vars(arg)

    elif isinstance(ty, FuncType):
        for p in ty.params:
            result |= _collect_free_vars(p)
        for r in ty.returns:
            result |= _collect_free_vars(r)

    elif isinstance(ty, StructType):
        for _, f in ty.fields:
            result |= _collect_free_vars(f)

    elif isinstance(ty, (ArrayType, VectorType)):
        result |= _collect_free_vars(ty.element)

    elif isinstance(ty, RefType):
        result |= _collect_free_vars(ty.element)

    return result


# ── Common Generic Types ───────────────────────────────────────────────────

def make_vec(elem_type: FIRType, ctx: Optional[TypeContext] = None) -> GenericType:
    """Create a Vec<T> generic type.

    Args:
        elem_type: Element type.
        ctx: Optional TypeContext (reserved for future use).

    Returns:
        GenericType representing Vec<elem_type>.
    """
    return GenericType(type_id=-1, name="Vec", args=(elem_type,))


def make_map(
    key_type: FIRType,
    value_type: FIRType,
    ctx: Optional[TypeContext] = None,
) -> GenericType:
    """Create a Map<K, V> generic type.

    Args:
        key_type: Key type.
        value_type: Value type.
        ctx: Optional TypeContext (reserved for future use).

    Returns:
        GenericType representing Map<key_type, value_type>.
    """
    return GenericType(type_id=-1, name="Map", args=(key_type, value_type))


def make_option(
    inner_type: FIRType,
    ctx: Optional[TypeContext] = None,
) -> GenericType:
    """Create an Option<T> generic type.

    Args:
        inner_type: Inner type.

    Returns:
        GenericType representing Option<inner_type>.
    """
    return GenericType(type_id=-1, name="Option", args=(inner_type,))


def make_result(
    ok_type: FIRType,
    err_type: FIRType,
    ctx: Optional[TypeContext] = None,
) -> GenericType:
    """Create a Result<T, E> generic type.

    Args:
        ok_type: Success type.
        err_type: Error type.

    Returns:
        GenericType representing Result<ok_type, err_type>.
    """
    return GenericType(type_id=-1, name="Result", args=(ok_type, err_type))


# ── Scheme helpers ─────────────────────────────────────────────────────────

def make_scheme(
    var_names: list[str],
    body: FIRType,
    constraints: Optional[dict[str, tuple]] = None,
) -> TypeScheme:
    """Create a TypeScheme with named type variables.

    Args:
        var_names: List of type variable names (e.g., ["T", "U"]).
        body: The body type (may reference the type variables).
        constraints: Optional mapping from var name to constraint tuple.

    Returns:
        TypeScheme quantifying over the given variables.
    """
    tvars = tuple(
        TypeVar(
            type_id=-1,
            name=n,
            constraints=tuple(constraints.get(n, ())) if constraints else (),
        )
        for n in var_names
    )
    return TypeScheme(vars=tvars, body=body)
