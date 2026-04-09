"""FLUX Types Module — polyglot type unification and compatibility.

Provides:
- TypeUnifier: maps C/Python/Rust types to FIR types
- Type compatibility checking (are_compatible, coercion_cost, least_upper_bound)
- Generic/polymorphic type support (GenericType, TypeVar, TypeScheme)
"""

from .unify import TypeUnifier, CoercionRule
from .compat import are_compatible, coercion_cost, least_upper_bound, compatibility_report
from .generic import (
    TypeVar,
    GenericType,
    TypeScheme,
    make_vec,
    make_map,
    make_option,
    make_result,
    make_scheme,
    _substitute,
    _collect_free_vars,
)

__all__ = [
    "TypeUnifier",
    "CoercionRule",
    "are_compatible",
    "coercion_cost",
    "least_upper_bound",
    "compatibility_report",
    "TypeVar",
    "GenericType",
    "TypeScheme",
    "make_vec",
    "make_map",
    "make_option",
    "make_result",
    "make_scheme",
    "_substitute",
    "_collect_free_vars",
]
