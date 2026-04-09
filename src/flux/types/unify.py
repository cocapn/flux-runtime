"""Type unification engine for cross-language type mapping.

Maps types from C, Python, and Rust to FLUX FIR types, enabling
interoperability across the polyglot type system. Provides a
TypeUnifier class that handles bidirectional type mapping and
cross-language coercion rules.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional, Union

from flux.fir.types import (
    FIRType, TypeContext, IntType, FloatType, BoolType, UnitType,
    StringType, RefType, ArrayType, VectorType, FuncType, StructType,
)
from flux.types.generic import GenericType, TypeVar

logger = logging.getLogger(__name__)


# ── Language Type Mapping Tables ────────────────────────────────────────────

# C type name → (constructor_kwargs, FIRType_class)
_C_TYPE_MAP: dict[str, tuple[dict, type]] = {
    "char":             ({"bits": 8,  "signed": True},  IntType),
    "signed char":      ({"bits": 8,  "signed": True},  IntType),
    "unsigned char":    ({"bits": 8,  "signed": False}, IntType),
    "short":            ({"bits": 16, "signed": True},  IntType),
    "unsigned short":   ({"bits": 16, "signed": False}, IntType),
    "int":              ({"bits": 32, "signed": True},  IntType),
    "unsigned int":     ({"bits": 32, "signed": False}, IntType),
    "long":             ({"bits": 64, "signed": True},  IntType),
    "unsigned long":    ({"bits": 64, "signed": False}, IntType),
    "long long":        ({"bits": 64, "signed": True},  IntType),
    "unsigned long long": ({"bits": 64, "signed": False}, IntType),
    "float":            ({"bits": 32}, FloatType),
    "double":           ({"bits": 64}, FloatType),
    "long double":      ({"bits": 64}, FloatType),
    "_Bool":            ({}, BoolType),
    "bool":             ({}, BoolType),
    "void":             ({}, UnitType),
}

# C pointer types → special kind (key is the base type without *)
_C_POINTER_MAP: dict[str, str] = {
    "char":  "string",
    "void":  "opaque_ptr",
    "int":   "int_ptr",
}


# Python type → FIR type
_PYTHON_TYPE_MAP: dict[type, tuple[dict, type]] = {
    int:   ({"bits": 64, "signed": True}, IntType),
    float: ({"bits": 64}, FloatType),
    bool:  ({}, BoolType),
    str:   ({}, StringType),
}

# Python type name (for string-based lookup) → FIR type
_PYTHON_NAME_MAP: dict[str, tuple[dict, type]] = {
    "int":    ({"bits": 64, "signed": True}, IntType),
    "float":  ({"bits": 64}, FloatType),
    "bool":   ({}, BoolType),
    "str":    ({}, StringType),
    "None":   ({}, UnitType),
    "NoneType": ({}, UnitType),
}


# Rust type name → FIR type
_RUST_TYPE_MAP: dict[str, tuple[dict, type]] = {
    "i8":   ({"bits": 8,  "signed": True},  IntType),
    "i16":  ({"bits": 16, "signed": True},  IntType),
    "i32":  ({"bits": 32, "signed": True},  IntType),
    "i64":  ({"bits": 64, "signed": True},  IntType),
    "i128": ({"bits": 128, "signed": True}, IntType),
    "u8":   ({"bits": 8,  "signed": False}, IntType),
    "u16":  ({"bits": 16, "signed": False}, IntType),
    "u32":  ({"bits": 32, "signed": False}, IntType),
    "u64":  ({"bits": 64, "signed": False}, IntType),
    "u128": ({"bits": 128, "signed": False}, IntType),
    "f32":  ({"bits": 32}, FloatType),
    "f64":  ({"bits": 64}, FloatType),
    "bool": ({}, BoolType),
    "String": ({}, StringType),
    "&str":  ({}, StringType),
    "()":   ({}, UnitType),
}

# Rust generic types (handled separately for Vec<T>, etc.)


# ── Coercion Cost Table ────────────────────────────────────────────────────

# Coercion costs:
#   0 = identical types
#   1 = implicit widening (e.g., i32 → i64)
#   2 = implicit narrowing with potential data loss (e.g., i64 → i32)
#   3 = sign change (e.g., i32 → u32)
#   5 = integer ↔ float
#   10 = cross-language coercion requiring runtime check

_INTEGER_WIDENING: dict[int, int] = {
    (8, 16): 1, (8, 32): 1, (8, 64): 1,
    (16, 32): 1, (16, 64): 1,
    (32, 64): 1,
    (64, 128): 1,
}

_INTEGER_NARROWING: dict[int, int] = {
    (16, 8): 2, (32, 8): 2, (64, 8): 2,
    (32, 16): 2, (64, 16): 2,
    (64, 32): 2,
    (128, 64): 2,
}

_FLOAT_WIDENING: dict[int, int] = {
    (32, 64): 1,
}

_FLOAT_NARROWING: dict[int, int] = {
    (64, 32): 2,
}


@dataclass
class CoercionRule:
    """Represents a type coercion between two types."""
    source: FIRType
    target: FIRType
    cost: int
    is_explicit: bool = False
    description: str = ""


class TypeUnifier:
    """Maps types from different languages to FLUX FIR types.

    Provides bidirectional type mapping for C, Python, and Rust types,
    along with cross-language coercion rules and type unification.

    The unifier uses a TypeContext for interning types, ensuring that
    equivalent types share the same object identity.

    Args:
        ctx: TypeContext for creating interned FIR types.
            If None, a new one is created.
    """

    def __init__(self, ctx: Optional[TypeContext] = None) -> None:
        self.ctx = ctx or TypeContext()
        self._coercion_rules: list[CoercionRule] = []

    # ── C Type Mapping ──────────────────────────────────────────────────

    def from_c(self, c_type: str) -> FIRType:
        """Map a C type name to a FIR type.

        Args:
            c_type: C type name (e.g., "int", "float", "char*").

        Returns:
            Corresponding FIRType.

        Raises:
            ValueError: If the type is not recognized.
        """
        c_type = c_type.strip()

        # Handle const qualifiers (strip before other checks)
        if c_type.startswith("const "):
            return self.from_c(c_type[6:].strip())

        # Handle pointer types
        if c_type.endswith("*"):
            base = c_type[:-1].strip()
            if base in _C_POINTER_MAP:
                kind = _C_POINTER_MAP[base]
                if kind == "string":
                    return self.ctx.get_string()
                else:
                    # Generic pointer type
                    elem = self.from_c(base) if base in _C_TYPE_MAP else self.ctx.get_int(8)
                    return self.ctx.get_ref(elem)

            # Generic pointer
            base_type = self.from_c(base) if base in _C_TYPE_MAP else self.ctx.get_int(8)
            return self.ctx.get_ref(base_type)

        # Handle struct types
        if c_type.startswith("struct "):
            struct_name = c_type[7:].strip()
            return self.ctx.get_struct(struct_name, ())

        # Handle enum types
        if c_type.startswith("enum "):
            enum_name = c_type[5:].strip()
            return self.ctx.get_enum(enum_name, ())

        # Look up primitive type
        entry = _C_TYPE_MAP.get(c_type)
        if entry is None:
            raise ValueError(f"Unknown C type: {c_type!r}")

        kwargs, cls = entry
        if cls is IntType:
            return self.ctx.get_int(kwargs["bits"], kwargs["signed"])
        elif cls is FloatType:
            return self.ctx.get_float(kwargs["bits"])
        elif cls is BoolType:
            return self.ctx.get_bool()
        elif cls is UnitType:
            return self.ctx.get_unit()
        else:
            return cls(type_id=-1, **kwargs)

    def to_c(self, fir_type: FIRType) -> str:
        """Map a FIR type back to a C type name.

        Args:
            fir_type: FIRType to convert.

        Returns:
            C type name string.
        """
        if isinstance(fir_type, IntType):
            if fir_type.bits == 8 and fir_type.signed:
                return "char"
            elif fir_type.bits == 8 and not fir_type.signed:
                return "unsigned char"
            elif fir_type.bits == 16 and fir_type.signed:
                return "short"
            elif fir_type.bits == 16 and not fir_type.signed:
                return "unsigned short"
            elif fir_type.bits == 32 and fir_type.signed:
                return "int"
            elif fir_type.bits == 32 and not fir_type.signed:
                return "unsigned int"
            elif fir_type.bits == 64 and fir_type.signed:
                return "long"
            elif fir_type.bits == 64 and not fir_type.signed:
                return "unsigned long"
            else:
                suffix = "" if fir_type.signed else "unsigned "
                return f"{suffix}int{fir_type.bits}_t"
        elif isinstance(fir_type, FloatType):
            if fir_type.bits == 32:
                return "float"
            elif fir_type.bits == 64:
                return "double"
            else:
                return f"float{fir_type.bits}_t"
        elif isinstance(fir_type, BoolType):
            return "_Bool"
        elif isinstance(fir_type, StringType):
            return "const char*"
        elif isinstance(fir_type, UnitType):
            return "void"
        elif isinstance(fir_type, RefType):
            return self.to_c(fir_type.element) + "*"
        elif isinstance(fir_type, ArrayType):
            return f"{self.to_c(fir_type.element)}[{fir_type.length}]"
        elif isinstance(fir_type, FuncType):
            params = ", ".join(self.to_c(p) for p in fir_type.params)
            ret = self.to_c(fir_type.returns[0]) if fir_type.returns else "void"
            return f"{ret} (*)({params})"
        else:
            return "void*"

    # ── Python Type Mapping ─────────────────────────────────────────────

    def from_python(self, py_type: Any) -> FIRType:
        """Map a Python type to a FIR type.

        Accepts either a Python type object (int, float, bool, str)
        or a type name string.

        Args:
            py_type: Python type or type name string.

        Returns:
            Corresponding FIRType.

        Raises:
            ValueError: If the type is not recognized.
        """
        # Handle string-based lookup
        if isinstance(py_type, str):
            entry = _PYTHON_NAME_MAP.get(py_type)
            if entry is None:
                raise ValueError(f"Unknown Python type: {py_type!r}")
            kwargs, cls = entry
            if cls is IntType:
                return self.ctx.get_int(kwargs["bits"], kwargs["signed"])
            elif cls is FloatType:
                return self.ctx.get_float(kwargs["bits"])
            elif cls is BoolType:
                return self.ctx.get_bool()
            elif cls is UnitType:
                return self.ctx.get_unit()
            elif cls is StringType:
                return self.ctx.get_string()
            else:
                return cls(type_id=-1, **kwargs)

        # Handle type objects
        entry = _PYTHON_TYPE_MAP.get(py_type)
        if entry is None:
            # Handle generic types (list, dict, tuple, etc.)
            type_name = getattr(py_type, "__name__", str(py_type))
            if type_name == "list":
                return GenericType(type_id=-1, name="List", args=(TypeVar(type_id=-1, name="T"),))
            elif type_name == "dict":
                return GenericType(
                    type_id=-1, name="Dict",
                    args=(
                        TypeVar(type_id=-1, name="K"),
                        TypeVar(type_id=-1, name="V"),
                    ),
                )
            elif type_name == "tuple":
                return GenericType(type_id=-1, name="Tuple", args=(TypeVar(type_id=-1, name="T"),))
            elif type_name == "set":
                return GenericType(type_id=-1, name="Set", args=(TypeVar(type_id=-1, name="T"),))
            elif type_name == "Optional":
                return GenericType(type_id=-1, name="Option", args=(TypeVar(type_id=-1, name="T"),))
            raise ValueError(f"Unknown Python type: {py_type!r}")

        kwargs, cls = entry
        if cls is IntType:
            return self.ctx.get_int(kwargs["bits"], kwargs["signed"])
        elif cls is FloatType:
            return self.ctx.get_float(kwargs["bits"])
        elif cls is BoolType:
            return self.ctx.get_bool()
        elif cls is StringType:
            return self.ctx.get_string()
        else:
            return cls(type_id=-1, **kwargs)

    def to_python(self, fir_type: FIRType) -> str:
        """Map a FIR type back to a Python type name.

        Args:
            fir_type: FIRType to convert.

        Returns:
            Python type name string.
        """
        if isinstance(fir_type, IntType):
            return "int"
        elif isinstance(fir_type, FloatType):
            return "float"
        elif isinstance(fir_type, BoolType):
            return "bool"
        elif isinstance(fir_type, StringType):
            return "str"
        elif isinstance(fir_type, UnitType):
            return "None"
        elif isinstance(fir_type, RefType):
            return "Any"  # pointers don't have direct Python equivalent
        elif isinstance(fir_type, ArrayType):
            return f"list[{self.to_python(fir_type.element)}]"
        elif isinstance(fir_type, GenericType):
            if fir_type.is_fully_concrete() and fir_type.args:
                args_str = ", ".join(
                    self.to_python(a) if not isinstance(a, TypeVar) else "Any"
                    for a in fir_type.args
                )
                return f"{fir_type.name}[{args_str}]"
            return fir_type.name
        elif isinstance(fir_type, FuncType):
            return "callable"
        else:
            return "Any"

    # ── Rust Type Mapping ───────────────────────────────────────────────

    def from_rust(self, rust_type: str) -> FIRType:
        """Map a Rust type name to a FIR type.

        Handles primitive types, references, tuples, and generic types
        like Vec<T>, Option<T>, Result<T, E>.

        Args:
            rust_type: Rust type name (e.g., "i32", "Vec<i32>", "&str").

        Returns:
            Corresponding FIRType.

        Raises:
            ValueError: If the type is not recognized.
        """
        rust_type = rust_type.strip()

        # Handle reference types
        if rust_type.startswith("&"):
            inner = rust_type[1:].strip()
            if inner.startswith("mut "):
                inner = inner[4:].strip()
            # &str → StringType, &T → RefType
            if inner == "str":
                return self.ctx.get_string()
            try:
                elem = self.from_rust(inner)
                return self.ctx.get_ref(elem)
            except ValueError:
                return self.ctx.get_ref(self.ctx.get_int(8))

        # Handle tuple types
        if rust_type.startswith("(") and rust_type.endswith(")"):
            inner = rust_type[1:-1].strip()
            if inner == "":
                return self.ctx.get_unit()
            # Simple tuple → struct-like representation
            parts = [p.strip() for p in inner.split(",")]
            fields = tuple((f"_{i}", self.from_rust(p)) for i, p in enumerate(parts))
            return self.ctx.get_struct(f"Tuple{len(parts)}", fields)

        # Handle array types [T; N]
        if rust_type.startswith("[") and ";" in rust_type:
            inner = rust_type[1:-1]
            elem_str, len_str = inner.split(";", 1)
            elem = self.from_rust(elem_str.strip())
            length = int(len_str.strip())
            return self.ctx.get_array(elem, length)

        # Handle generic types (Vec<T>, Option<T>, HashMap<K, V>, etc.)
        if "<" in rust_type and rust_type.endswith(">"):
            base, args_str = rust_type.split("<", 1)
            args_str = args_str[:-1]  # remove trailing ">"
            base = base.strip()

            # Parse generic args (handle nested generics simply)
            arg_types = self._parse_rust_generic_args(args_str)

            if base == "Vec":
                if len(arg_types) == 1:
                    return GenericType(type_id=-1, name="Vec", args=(arg_types[0],))
                raise ValueError(f"Vec expects 1 type argument, got {len(arg_types)}")
            elif base == "Option":
                if len(arg_types) == 1:
                    return GenericType(type_id=-1, name="Option", args=(arg_types[0],))
                raise ValueError(f"Option expects 1 type argument, got {len(arg_types)}")
            elif base == "Result":
                if len(arg_types) == 2:
                    return GenericType(
                        type_id=-1, name="Result", args=tuple(arg_types)
                    )
                raise ValueError(f"Result expects 2 type arguments, got {len(arg_types)}")
            elif base in ("HashMap", "BTreeMap", "Map"):
                if len(arg_types) >= 2:
                    return GenericType(
                        type_id=-1, name="Map", args=(arg_types[0], arg_types[1])
                    )
                raise ValueError(f"{base} expects 2 type arguments")
            elif base in ("HashSet", "BTreeSet", "Set"):
                if len(arg_types) >= 1:
                    return GenericType(
                        type_id=-1, name="Set", args=(arg_types[0],)
                    )
                raise ValueError(f"{base} expects 1 type argument")
            elif base == "Box":
                if len(arg_types) == 1:
                    return self.ctx.get_ref(arg_types[0])
                raise ValueError(f"Box expects 1 type argument")
            elif base == "Rc" or base == "Arc":
                if len(arg_types) == 1:
                    return self.ctx.get_ref(arg_types[0])
                raise ValueError(f"{base} expects 1 type argument")
            else:
                # Unknown generic — return a GenericType
                return GenericType(
                    type_id=-1, name=base, args=tuple(arg_types)
                )

        # Handle const qualifiers
        if rust_type.startswith("const "):
            return self.from_rust(rust_type[6:].strip())

        # Look up primitive type
        entry = _RUST_TYPE_MAP.get(rust_type)
        if entry is None:
            # Try as a struct name
            return self.ctx.get_struct(rust_type, ())

        kwargs, cls = entry
        if cls is IntType:
            return self.ctx.get_int(kwargs["bits"], kwargs["signed"])
        elif cls is FloatType:
            return self.ctx.get_float(kwargs["bits"])
        elif cls is BoolType:
            return self.ctx.get_bool()
        elif cls is UnitType:
            return self.ctx.get_unit()
        elif cls is StringType:
            return self.ctx.get_string()
        else:
            return cls(type_id=-1, **kwargs)

    def _parse_rust_generic_args(self, args_str: str) -> list[FIRType]:
        """Parse comma-separated Rust generic type arguments.

    Handles simple cases (no nested generics in args).
    For nested generics, a basic depth-tracking split is used.
        """
        args: list[str] = []
        depth = 0
        current: list[str] = []

        for ch in args_str:
            if ch == '<':
                depth += 1
                current.append(ch)
            elif ch == '>':
                depth -= 1
                current.append(ch)
            elif ch == ',' and depth == 0:
                args.append("".join(current).strip())
                current = []
            else:
                current.append(ch)

        if current:
            args.append("".join(current).strip())

        return [self.from_rust(a) for a in args if a]

    def to_rust(self, fir_type: FIRType) -> str:
        """Map a FIR type back to a Rust type name.

        Args:
            fir_type: FIRType to convert.

        Returns:
            Rust type name string.
        """
        if isinstance(fir_type, IntType):
            if fir_type.signed:
                return f"i{fir_type.bits}"
            else:
                return f"u{fir_type.bits}"
        elif isinstance(fir_type, FloatType):
            return f"f{fir_type.bits}"
        elif isinstance(fir_type, BoolType):
            return "bool"
        elif isinstance(fir_type, StringType):
            return "String"
        elif isinstance(fir_type, UnitType):
            return "()"
        elif isinstance(fir_type, RefType):
            return f"&{self.to_rust(fir_type.element)}"
        elif isinstance(fir_type, ArrayType):
            return f"[{self.to_rust(fir_type.element)}; {fir_type.length}]"
        elif isinstance(fir_type, GenericType):
            if fir_type.args:
                args_str = ", ".join(
                    self.to_rust(a) if not isinstance(a, TypeVar) else str(a)
                    for a in fir_type.args
                )
                return f"{fir_type.name}<{args_str}>"
            return fir_type.name
        elif isinstance(fir_type, StructType):
            return fir_type.name
        elif isinstance(fir_type, FuncType):
            params = ", ".join(self.to_rust(p) for p in fir_type.params)
            ret = self.to_rust(fir_type.returns[0]) if fir_type.returns else "()"
            return f"fn({params}) -> {ret}"
        else:
            return "i32"  # fallback

    # ── Cross-language Coercion ─────────────────────────────────────────

    def coercion_cost(self, source: FIRType, target: FIRType) -> int:
        """Compute the cost of coercing between two FIR types.

        Lower cost = easier coercion. Cost 0 means types are identical.

        Cost scale:
        - 0: identical types
        - 1: implicit widening (i8→i16, f32→f64)
        - 2: narrowing (i64→i32) or sign change (i32→u32)
        - 3: both narrowing and sign change
        - 5: int↔float conversion
        - 8: bool↔int conversion
        - 10: cross-category (int↔string, etc.)
        - 100: incompatible types

        Args:
            source: Source FIRType.
            target: Target FIRType.

        Returns:
            Integer cost of coercion.
        """
        # Identity
        if source == target or (isinstance(source, FIRType) and isinstance(target, FIRType)
                                and type(source) == type(target)
                                and _type_eq(source, target)):
            return 0

        # Both integers
        if isinstance(source, IntType) and isinstance(target, IntType):
            cost = 0
            if source.bits < target.bits:
                cost += _INTEGER_WIDENING.get((source.bits, target.bits), 1)
            elif source.bits > target.bits:
                cost += _INTEGER_NARROWING.get((target.bits, source.bits), 2)
            if source.signed != target.signed:
                cost += 1  # sign change
            return cost

        # Both floats
        if isinstance(source, FloatType) and isinstance(target, FloatType):
            if source.bits < target.bits:
                return _FLOAT_WIDENING.get((source.bits, target.bits), 1)
            elif source.bits > target.bits:
                return _FLOAT_NARROWING.get((target.bits, source.bits), 2)
            return 0

        # Int ↔ Float
        if isinstance(source, IntType) and isinstance(target, FloatType):
            return 5
        if isinstance(source, FloatType) and isinstance(target, IntType):
            return 5

        # Bool ↔ Int
        if isinstance(source, BoolType) and isinstance(target, IntType):
            return 8
        if isinstance(source, IntType) and isinstance(target, BoolType):
            return 8

        # String ↔ anything (expensive)
        if isinstance(source, StringType) or isinstance(target, StringType):
            return 10

        # Unit type
        if isinstance(target, UnitType):
            return 1  # discarding value is cheap

        # Ref types
        if isinstance(source, RefType) and isinstance(target, RefType):
            return self.coercion_cost(source.element, target.element)

        # Array types
        if isinstance(source, ArrayType) and isinstance(target, ArrayType):
            base_cost = self.coercion_cost(source.element, target.element)
            if source.length == target.length:
                return base_cost
            return base_cost + 5  # length mismatch is expensive

        # Generic types with same name
        if (isinstance(source, GenericType) and isinstance(target, GenericType)
                and source.name == target.name):
            if len(source.args) == len(target.args):
                return sum(
                    self.coercion_cost(s, t)
                    for s, t in zip(source.args, target.args)
                )

        # Incompatible
        return 100

    def can_implicitly_coerce(self, source: FIRType, target: FIRType) -> bool:
        """Check if implicit (zero-annotation) coercion is possible.

        Only widening conversions and same-category conversions are implicit.

        Args:
            source: Source FIRType.
            target: Target FIRType.

        Returns:
            True if implicit coercion is safe.
        """
        cost = self.coercion_cost(source, target)
        # Implicit coercions: widening (cost 1) and identity (cost 0)
        return cost <= 1

    def unify(self, *types: FIRType) -> Optional[FIRType]:
        """Unify multiple types into a single common type.

        Finds the least general type that all input types can be
        coerced to. Returns None if no common type exists.

        Args:
            *types: Variable number of FIRTypes to unify.

        Returns:
            Common FIRType, or None if unification fails.
        """
        if not types:
            return None
        if len(types) == 1:
            return types[0]

        result = types[0]
        for t in types[1:]:
            result = self._unify_pair(result, t)
            if result is None:
                return None
        return result

    def _unify_pair(self, t1: FIRType, t2: FIRType) -> Optional[FIRType]:
        """Unify two types, finding their least upper bound."""
        if _type_eq(t1, t2):
            return t1

        # Both integers — pick the wider one
        if isinstance(t1, IntType) and isinstance(t2, IntType):
            if t1.bits >= t2.bits and t1.signed:
                return t1
            if t2.bits >= t1.bits and t2.signed:
                return t2
            # Same bits, different sign — pick signed
            if t1.bits == t2.bits:
                return self.ctx.get_int(t1.bits, signed=True)
            # Pick wider
            if t1.bits > t2.bits:
                return t1
            return t2

        # Both floats — pick the wider one
        if isinstance(t1, FloatType) and isinstance(t2, FloatType):
            if t1.bits >= t2.bits:
                return t1
            return t2

        # Int and float — promote to float
        if isinstance(t1, IntType) and isinstance(t2, FloatType):
            return t2
        if isinstance(t1, FloatType) and isinstance(t2, IntType):
            return t1

        # Bool and int — promote to int
        if isinstance(t1, BoolType) and isinstance(t2, IntType):
            return t2
        if isinstance(t1, IntType) and isinstance(t2, BoolType):
            return t1

        # Ref types — unify element types
        if isinstance(t1, RefType) and isinstance(t2, RefType):
            elem = self._unify_pair(t1.element, t2.element)
            if elem is not None:
                return self.ctx.get_ref(elem)

        # Generic types with same name — unify args
        if (isinstance(t1, GenericType) and isinstance(t2, GenericType)
                and t1.name == t2.name and len(t1.args) == len(t2.args)):
            unified_args = []
            for a1, a2 in zip(t1.args, t2.args):
                ua = self._unify_pair(a1, a2)
                if ua is None:
                    return None
                unified_args.append(ua)
            return GenericType(type_id=-1, name=t1.name, args=tuple(unified_args))

        return None

    # ── Language-agnostic query ─────────────────────────────────────────

    def map_type(self, type_str: str, language: str) -> FIRType:
        """Map a type string from a specific language to FIR.

        Args:
            type_str: Type name string.
            language: Source language ("c", "python", "rust").

        Returns:
            Corresponding FIRType.
        """
        lang = language.lower().strip()
        if lang in ("c", "clang"):
            return self.from_c(type_str)
        elif lang in ("python", "py"):
            return self.from_python(type_str)
        elif lang in ("rust", "rs"):
            return self.from_rust(type_str)
        else:
            raise ValueError(f"Unknown language: {language!r}")


# ── Helpers ────────────────────────────────────────────────────────────────

def _type_eq(t1: FIRType, t2: FIRType) -> bool:
    """Deep equality check for FIR types."""
    if type(t1) != type(t2):
        return False

    if isinstance(t1, IntType):
        return t1.bits == t2.bits and t1.signed == t2.signed
    if isinstance(t1, FloatType):
        return t1.bits == t2.bits
    if isinstance(t1, (BoolType, UnitType, StringType)):
        return True
    if isinstance(t1, RefType):
        return _type_eq(t1.element, t2.element)
    if isinstance(t1, ArrayType):
        return _type_eq(t1.element, t2.element) and t1.length == t2.length
    if isinstance(t1, VectorType):
        return _type_eq(t1.element, t2.element) and t1.lanes == t2.lanes
    if isinstance(t1, FuncType):
        return (len(t1.params) == len(t2.params)
                and len(t1.returns) == len(t2.returns)
                and all(_type_eq(a, b) for a, b in zip(t1.params, t2.params))
                and all(_type_eq(a, b) for a, b in zip(t1.returns, t2.returns)))
    if isinstance(t1, StructType):
        return (t1.name == t2.name
                and len(t1.fields) == len(t2.fields)
                and all(
                    n1 == n2 and _type_eq(f1, f2)
                    for (n1, f1), (n2, f2) in zip(t1.fields, t2.fields)
                ))
    if isinstance(t1, GenericType):
        return (t1.name == t2.name
                and len(t1.args) == len(t2.args)
                and all(_type_eq(a, b) for a, b in zip(t1.args, t2.args)))
    if isinstance(t1, TypeVar):
        return t1.name == t2.name

    # Fallback: use dataclass equality
    return t1 == t2
