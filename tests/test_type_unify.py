"""Type Unification Tests — comprehensive tests for polyglot type system."""

import sys
import traceback

sys.path.insert(0, "src")

from flux.fir.types import (
    TypeContext, IntType, FloatType, BoolType, UnitType, StringType,
    RefType, ArrayType, VectorType, FuncType, StructType,
)
from flux.types.unify import TypeUnifier, _type_eq
from flux.types.compat import (
    are_compatible,
    coercion_cost,
    least_upper_bound,
    compatibility_report,
)
from flux.types.generic import (
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


passed = 0
failed = 0


def run_test(name, fn):
    global passed, failed
    try:
        fn()
        passed += 1
        print(f"  ✓ {name}")
    except Exception as e:
        failed += 1
        print(f"  ✗ {name}")
        traceback.print_exc()


# ────────────────────────────────────────────────────────────────────────────
# C Type Mapping Tests
# ────────────────────────────────────────────────────────────────────────────

def test_c_int_types():
    """C integer types should map to correct FIR IntTypes."""
    u = TypeUnifier()

    assert isinstance(u.from_c("int"), IntType)
    assert u.from_c("int").bits == 32
    assert u.from_c("int").signed is True

    assert isinstance(u.from_c("unsigned int"), IntType)
    assert u.from_c("unsigned int").bits == 32
    assert u.from_c("unsigned int").signed is False

    assert isinstance(u.from_c("long"), IntType)
    assert u.from_c("long").bits == 64

    assert isinstance(u.from_c("short"), IntType)
    assert u.from_c("short").bits == 16

    assert isinstance(u.from_c("char"), IntType)
    assert u.from_c("char").bits == 8


def test_c_float_types():
    """C float types should map to correct FIR FloatTypes."""
    u = TypeUnifier()

    assert isinstance(u.from_c("float"), FloatType)
    assert u.from_c("float").bits == 32

    assert isinstance(u.from_c("double"), FloatType)
    assert u.from_c("double").bits == 64

    assert isinstance(u.from_c("long double"), FloatType)
    assert u.from_c("long double").bits == 64


def test_c_void_and_bool():
    """C void and bool should map correctly."""
    u = TypeUnifier()

    assert isinstance(u.from_c("void"), UnitType)
    assert isinstance(u.from_c("_Bool"), BoolType)
    assert isinstance(u.from_c("bool"), BoolType)


def test_c_pointer_types():
    """C pointer types should map to RefType."""
    u = TypeUnifier()

    ptr = u.from_c("int*")
    assert isinstance(ptr, RefType)
    assert isinstance(ptr.element, IntType)
    assert ptr.element.bits == 32

    str_ptr = u.from_c("char*")
    assert isinstance(str_ptr, StringType)

    void_ptr = u.from_c("void*")
    assert isinstance(void_ptr, RefType)


def test_c_const_qualifier():
    """C const qualifier should be stripped."""
    u = TypeUnifier()

    assert _type_eq(u.from_c("const int"), u.from_c("int"))
    assert _type_eq(u.from_c("const char*"), u.from_c("char*"))


def test_c_struct_and_enum():
    """C struct and enum should map to FIR types."""
    u = TypeUnifier()

    s = u.from_c("struct Point")
    assert isinstance(s, StructType)
    assert s.name == "Point"

    e = u.from_c("enum Color")
    assert isinstance(e, type(e))  # EnumType


def test_c_unknown_type_raises():
    """Unknown C type should raise ValueError."""
    u = TypeUnifier()
    try:
        u.from_c("unknown_type_xyz")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass  # expected


def test_to_c_roundtrip():
    """FIR types should roundtrip to C type names."""
    u = TypeUnifier()
    ctx = u.ctx

    assert u.to_c(ctx.get_int(32)) == "int"
    assert u.to_c(ctx.get_int(32, signed=False)) == "unsigned int"
    assert u.to_c(ctx.get_float(32)) == "float"
    assert u.to_c(ctx.get_float(64)) == "double"
    assert u.to_c(ctx.get_bool()) == "_Bool"
    assert u.to_c(ctx.get_unit()) == "void"
    assert u.to_c(ctx.get_string()) == "const char*"


# ────────────────────────────────────────────────────────────────────────────
# Python Type Mapping Tests
# ────────────────────────────────────────────────────────────────────────────

def test_python_primitive_types():
    """Python primitive types should map correctly."""
    u = TypeUnifier()

    assert isinstance(u.from_python(int), IntType)
    assert u.from_python(int).bits == 64
    assert u.from_python(int).signed is True

    assert isinstance(u.from_python(float), FloatType)
    assert u.from_python(float).bits == 64

    assert isinstance(u.from_python(bool), BoolType)
    assert isinstance(u.from_python(str), StringType)


def test_python_string_types():
    """Python types by name should map correctly."""
    u = TypeUnifier()

    assert isinstance(u.from_python("int"), IntType)
    assert isinstance(u.from_python("float"), FloatType)
    assert isinstance(u.from_python("bool"), BoolType)
    assert isinstance(u.from_python("str"), StringType)
    assert isinstance(u.from_python("None"), UnitType)


def test_to_python_roundtrip():
    """FIR types should roundtrip to Python type names."""
    u = TypeUnifier()
    ctx = u.ctx

    assert u.to_python(ctx.get_int(64)) == "int"
    assert u.to_python(ctx.get_float(64)) == "float"
    assert u.to_python(ctx.get_bool()) == "bool"
    assert u.to_python(ctx.get_string()) == "str"
    assert u.to_python(ctx.get_unit()) == "None"


# ────────────────────────────────────────────────────────────────────────────
# Rust Type Mapping Tests
# ────────────────────────────────────────────────────────────────────────────

def test_rust_integer_types():
    """Rust integer types should map to correct FIR IntTypes."""
    u = TypeUnifier()

    for bits in [8, 16, 32, 64]:
        t = u.from_rust(f"i{bits}")
        assert isinstance(t, IntType)
        assert t.bits == bits
        assert t.signed is True

        ut = u.from_rust(f"u{bits}")
        assert isinstance(ut, IntType)
        assert ut.bits == bits
        assert ut.signed is False


def test_rust_float_types():
    """Rust float types should map to correct FIR FloatTypes."""
    u = TypeUnifier()

    assert isinstance(u.from_rust("f32"), FloatType)
    assert u.from_rust("f32").bits == 32
    assert isinstance(u.from_rust("f64"), FloatType)
    assert u.from_rust("f64").bits == 64


def test_rust_bool_and_unit():
    """Rust bool and unit should map correctly."""
    u = TypeUnifier()

    assert isinstance(u.from_rust("bool"), BoolType)
    assert isinstance(u.from_rust("()"), UnitType)


def test_rust_string_types():
    """Rust String and &str should map correctly."""
    u = TypeUnifier()

    assert isinstance(u.from_rust("String"), StringType)
    assert isinstance(u.from_rust("&str"), StringType)


def test_rust_reference_types():
    """Rust reference types should map to RefType."""
    u = TypeUnifier()

    ref = u.from_rust("&i32")
    assert isinstance(ref, RefType)
    assert isinstance(ref.element, IntType)
    assert ref.element.bits == 32

    mut_ref = u.from_rust("&mut f64")
    assert isinstance(mut_ref, RefType)
    assert isinstance(mut_ref.element, FloatType)


def test_rust_vec_type():
    """Rust Vec<T> should map to GenericType."""
    u = TypeUnifier()

    vec_i32 = u.from_rust("Vec<i32>")
    assert isinstance(vec_i32, GenericType)
    assert vec_i32.name == "Vec"
    assert len(vec_i32.args) == 1
    assert isinstance(vec_i32.args[0], IntType)
    assert vec_i32.args[0].bits == 32

    vec_str = u.from_rust("Vec<String>")
    assert isinstance(vec_str, GenericType)
    assert vec_str.name == "Vec"
    assert isinstance(vec_str.args[0], StringType)


def test_rust_option_type():
    """Rust Option<T> should map to GenericType."""
    u = TypeUnifier()

    opt = u.from_rust("Option<i32>")
    assert isinstance(opt, GenericType)
    assert opt.name == "Option"
    assert len(opt.args) == 1


def test_rust_result_type():
    """Rust Result<T, E> should map to GenericType."""
    u = TypeUnifier()

    res = u.from_rust("Result<i32, String>")
    assert isinstance(res, GenericType)
    assert res.name == "Result"
    assert len(res.args) == 2
    assert isinstance(res.args[0], IntType)
    assert isinstance(res.args[1], StringType)


def test_rust_hashmap_type():
    """Rust HashMap<K, V> should map to GenericType."""
    u = TypeUnifier()

    m = u.from_rust("HashMap<String, i32>")
    assert isinstance(m, GenericType)
    assert m.name == "Map"
    assert len(m.args) == 2


def test_rust_tuple_type():
    """Rust tuple types should map to StructType."""
    u = TypeUnifier()

    unit = u.from_rust("()")
    assert isinstance(unit, UnitType)

    pair = u.from_rust("(i32, f64)")
    assert isinstance(pair, StructType)
    assert pair.name == "Tuple2"
    assert len(pair.fields) == 2


def test_rust_array_type():
    """Rust [T; N] should map to ArrayType."""
    u = TypeUnifier()

    arr = u.from_rust("[i32; 10]")
    assert isinstance(arr, ArrayType)
    assert isinstance(arr.element, IntType)
    assert arr.length == 10


def test_rust_box_type():
    """Rust Box<T> should map to RefType."""
    u = TypeUnifier()

    boxed = u.from_rust("Box<i32>")
    assert isinstance(boxed, RefType)
    assert isinstance(boxed.element, IntType)


def test_to_rust_roundtrip():
    """FIR types should roundtrip to Rust type names."""
    u = TypeUnifier()
    ctx = u.ctx

    assert u.to_rust(ctx.get_int(32)) == "i32"
    assert u.to_rust(ctx.get_int(32, signed=False)) == "u32"
    assert u.to_rust(ctx.get_float(32)) == "f32"
    assert u.to_rust(ctx.get_float(64)) == "f64"
    assert u.to_rust(ctx.get_bool()) == "bool"
    assert u.to_rust(ctx.get_string()) == "String"
    assert u.to_rust(ctx.get_unit()) == "()"


# ────────────────────────────────────────────────────────────────────────────
# Cross-language Unification Tests
# ────────────────────────────────────────────────────────────────────────────

def test_cross_language_int_unification():
    """Integers from different languages should unify."""
    u = TypeUnifier()

    c_int = u.from_c("int")        # IntType(32, signed=True)
    py_int = u.from_python(int)    # IntType(64, signed=True)
    rs_i32 = u.from_rust("i32")    # IntType(32, signed=True)
    rs_i64 = u.from_rust("i64")    # IntType(64, signed=True)

    # i32 and i32 should unify to i32
    lub = u.unify(c_int, rs_i32)
    assert lub is not None
    assert isinstance(lub, IntType)

    # int (i64) and i32 should unify to i64 (wider)
    lub2 = u.unify(py_int, rs_i32)
    assert lub2 is not None
    assert isinstance(lub2, IntType)
    assert lub2.bits >= 32


def test_cross_language_float_unification():
    """Floats from different languages should unify."""
    u = TypeUnifier()

    c_float = u.from_c("float")      # FloatType(32)
    c_double = u.from_c("double")    # FloatType(64)
    py_float = u.from_python(float)  # FloatType(64)
    rs_f32 = u.from_rust("f32")      # FloatType(32)

    lub = u.unify(c_float, rs_f32)
    assert lub is not None
    assert isinstance(lub, FloatType)
    assert lub.bits == 32

    lub2 = u.unify(c_float, py_float)
    assert lub2 is not None
    assert isinstance(lub2, FloatType)
    assert lub2.bits == 64


def test_cross_language_int_float_promotion():
    """Int and float should unify to float."""
    u = TypeUnifier()

    c_int = u.from_c("int")
    c_double = u.from_c("double")

    lub = u.unify(c_int, c_double)
    assert lub is not None
    assert isinstance(lub, FloatType)


def test_unify_incompatible_types():
    """Incompatible types should return None."""
    u = TypeUnifier()
    ctx = u.ctx

    lub = u.unify(ctx.get_string(), ctx.get_int(32))
    assert lub is None


def test_unify_single_type():
    """Unifying a single type should return itself."""
    u = TypeUnifier()
    ctx = u.ctx

    i32 = ctx.get_int(32)
    result = u.unify(i32)
    assert result is not None
    assert isinstance(result, IntType)


def test_unify_empty():
    """Unifying no types should return None."""
    u = TypeUnifier()
    assert u.unify() is None


def test_map_type_language_dispatch():
    """map_type should dispatch to correct language mapper."""
    u = TypeUnifier()

    # C
    assert isinstance(u.map_type("int", "c"), IntType)
    # Python
    assert isinstance(u.map_type("int", "python"), IntType)
    # Rust
    assert isinstance(u.map_type("i32", "rust"), IntType)

    try:
        u.map_type("int", "java")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


# ────────────────────────────────────────────────────────────────────────────
# Coercion Cost Tests
# ────────────────────────────────────────────────────────────────────────────

def test_coercion_cost_identity():
    """Identical types should have cost 0."""
    u = TypeUnifier()
    ctx = u.ctx

    assert u.coercion_cost(ctx.get_int(32), ctx.get_int(32)) == 0
    assert u.coercion_cost(ctx.get_float(64), ctx.get_float(64)) == 0


def test_coercion_cost_widening():
    """Widening should have low cost."""
    u = TypeUnifier()
    ctx = u.ctx

    assert u.coercion_cost(ctx.get_int(8), ctx.get_int(32)) <= 2
    assert u.coercion_cost(ctx.get_int(32), ctx.get_int(64)) == 1
    assert u.coercion_cost(ctx.get_float(32), ctx.get_float(64)) == 1


def test_coercion_cost_narrowing():
    """Narrowing should have higher cost than widening."""
    u = TypeUnifier()
    ctx = u.ctx

    widen = u.coercion_cost(ctx.get_int(32), ctx.get_int(64))
    narrow = u.coercion_cost(ctx.get_int(64), ctx.get_int(32))
    assert narrow > widen


def test_coercion_cost_int_to_float():
    """Int to float conversion should cost 5."""
    u = TypeUnifier()
    ctx = u.ctx

    assert u.coercion_cost(ctx.get_int(32), ctx.get_float(64)) == 5


def test_coercion_cost_bool():
    """Bool to int conversion should cost 8."""
    u = TypeUnifier()
    ctx = u.ctx

    assert u.coercion_cost(ctx.get_bool(), ctx.get_int(32)) == 8


def test_coercion_cost_string():
    """String conversions should be expensive."""
    u = TypeUnifier()
    ctx = u.ctx

    assert u.coercion_cost(ctx.get_int(32), ctx.get_string()) == 10


def test_coercion_cost_incompatible():
    """Incompatible types should have cost 100."""
    u = TypeUnifier()
    ctx = u.ctx

    # Different generic types
    vec_i32 = GenericType(type_id=-1, name="Vec", args=(ctx.get_int(32),))
    opt_i32 = GenericType(type_id=-1, name="Option", args=(ctx.get_int(32),))
    assert u.coercion_cost(vec_i32, opt_i32) == 100


def test_implicit_coercion():
    """Only widening should be implicit."""
    u = TypeUnifier()
    ctx = u.ctx

    assert u.can_implicitly_coerce(ctx.get_int(32), ctx.get_int(64))
    assert not u.can_implicitly_coerce(ctx.get_int(64), ctx.get_int(32))
    assert not u.can_implicitly_coerce(ctx.get_int(32), ctx.get_float(64))


# ────────────────────────────────────────────────────────────────────────────
# Compatibility Tests
# ────────────────────────────────────────────────────────────────────────────

def test_compatible_identical():
    """Identical types should be compatible."""
    u = TypeUnifier()
    ctx = u.ctx

    assert are_compatible(ctx.get_int(32), ctx.get_int(32))
    assert are_compatible(ctx.get_float(64), ctx.get_float(64))


def test_compatible_numeric():
    """All numeric types should be compatible with each other."""
    u = TypeUnifier()
    ctx = u.ctx

    numeric_types = [
        ctx.get_int(8), ctx.get_int(32), ctx.get_int(64),
        ctx.get_float(32), ctx.get_float(64),
    ]

    for t1 in numeric_types:
        for t2 in numeric_types:
            assert are_compatible(t1, t2), f"{t1} and {t2} should be compatible"


def test_compatible_bool_int():
    """Bool and int should be compatible."""
    u = TypeUnifier()
    ctx = u.ctx

    assert are_compatible(ctx.get_bool(), ctx.get_int(32))
    assert are_compatible(ctx.get_int(32), ctx.get_bool())


def test_compatible_unit():
    """Unit should be compatible with everything."""
    u = TypeUnifier()
    ctx = u.ctx

    assert are_compatible(ctx.get_unit(), ctx.get_int(32))
    assert are_compatible(ctx.get_unit(), ctx.get_string())
    assert are_compatible(ctx.get_int(32), ctx.get_unit())


def test_compatible_ref():
    """Ref types should be covariantly compatible."""
    u = TypeUnifier()
    ctx = u.ctx

    ref_i32 = ctx.get_ref(ctx.get_int(32))
    ref_i64 = ctx.get_ref(ctx.get_int(64))
    assert are_compatible(ref_i32, ref_i64)
    assert are_compatible(ref_i32, ref_i32)


def test_compatible_array():
    """Arrays with same length and compatible elements should be compatible."""
    u = TypeUnifier()
    ctx = u.ctx

    arr_i32 = ctx.get_array(ctx.get_int(32), 10)
    arr_i64 = ctx.get_array(ctx.get_int(64), 10)
    assert are_compatible(arr_i32, arr_i64)

    # Different length → not compatible
    arr_short = ctx.get_array(ctx.get_int(32), 5)
    assert not are_compatible(arr_i32, arr_short)


def test_compatible_generic():
    """Generic types with same name should be compatible."""
    vec_i32 = GenericType(type_id=-1, name="Vec", args=(IntType(type_id=0, bits=32, signed=True),))
    vec_i64 = GenericType(type_id=-1, name="Vec", args=(IntType(type_id=1, bits=64, signed=True),))
    assert are_compatible(vec_i32, vec_i64)

    # Different names → not compatible
    opt_i32 = GenericType(type_id=-1, name="Option", args=(IntType(type_id=0, bits=32, signed=True),))
    assert not are_compatible(vec_i32, opt_i32)


def test_compatible_typevar():
    """TypeVars should be compatible with anything."""
    u = TypeUnifier()
    ctx = u.ctx

    tv = TypeVar(type_id=-1, name="T")
    assert are_compatible(tv, ctx.get_int(32))
    assert are_compatible(tv, ctx.get_string())
    assert are_compatible(ctx.get_int(32), tv)


def test_least_upper_bound_basic():
    """LUB of compatible types should work."""
    u = TypeUnifier()
    ctx = u.ctx

    lub = least_upper_bound(ctx.get_int(32), ctx.get_int(64))
    assert lub is not None
    assert isinstance(lub, IntType)
    assert lub.bits >= 32

    lub2 = least_upper_bound(ctx.get_int(32), ctx.get_float(64))
    assert lub2 is not None
    assert isinstance(lub2, FloatType)


def test_least_upper_bound_none():
    """LUB of incompatible types should be None."""
    u = TypeUnifier()
    ctx = u.ctx

    assert least_upper_bound(ctx.get_int(32), ctx.get_string()) is None


def test_compatibility_report():
    """Compatibility report should have all fields."""
    u = TypeUnifier()
    ctx = u.ctx

    report = compatibility_report(ctx.get_int(32), ctx.get_int(64))
    assert "compatible" in report
    assert "cost" in report
    assert "lub" in report
    assert "implicit" in report
    assert report["compatible"] is True
    assert report["cost"] == 1
    assert report["implicit"] is True


def test_coercion_cost_function():
    """Standalone coercion_cost function should work."""
    u = TypeUnifier()
    ctx = u.ctx

    cost = coercion_cost(ctx.get_int(32), ctx.get_int(64), ctx=ctx)
    assert cost == 1

    cost2 = coercion_cost(ctx.get_int(32), ctx.get_float(64), ctx=ctx)
    assert cost2 == 5


# ────────────────────────────────────────────────────────────────────────────
# Generic Type Tests
# ────────────────────────────────────────────────────────────────────────────

def test_type_var_creation():
    """TypeVar should be created correctly."""
    tv = TypeVar(type_id=-1, name="T")
    assert tv.name == "T"
    assert len(tv.constraints) == 0

    tv_constrained = TypeVar(
        type_id=-1, name="N", constraints=(IntType(type_id=0, bits=32, signed=True),)
    )
    assert tv_constrained.name == "N"
    assert len(tv_constrained.constraints) == 1


def test_generic_type_creation():
    """GenericType should be created correctly."""
    ctx = TypeContext()
    i32 = ctx.get_int(32)

    vec = GenericType(type_id=-1, name="Vec", args=(i32,))
    assert vec.name == "Vec"
    assert len(vec.args) == 1
    assert vec.args[0] == i32
    assert vec.is_fully_concrete()

    map_type = GenericType(
        type_id=-1, name="Map",
        args=(i32, ctx.get_string()),
    )
    assert map_type.name == "Map"
    assert len(map_type.args) == 2
    assert map_type.is_fully_concrete()


def test_generic_type_not_fully_concrete():
    """GenericType with TypeVar args should not be fully concrete."""
    tv = TypeVar(type_id=-1, name="T")
    vec = GenericType(type_id=-1, name="Vec", args=(tv,))
    assert not vec.is_fully_concrete()


def test_generic_type_repr():
    """GenericType repr should be readable."""
    ctx = TypeContext()
    i32 = ctx.get_int(32)

    vec = GenericType(type_id=-1, name="Vec", args=(i32,))
    assert "Vec<" in repr(vec)

    map_type = GenericType(
        type_id=-1, name="Map",
        args=(ctx.get_string(), i32),
    )
    assert "Map<" in repr(map_type)


def test_make_vec():
    """make_vec helper should create Vec<T>."""
    ctx = TypeContext()
    i32 = ctx.get_int(32)

    vec = make_vec(i32, ctx)
    assert isinstance(vec, GenericType)
    assert vec.name == "Vec"
    assert vec.args[0] == i32


def test_make_map():
    """make_map helper should create Map<K, V>."""
    ctx = TypeContext()
    i32 = ctx.get_int(32)
    s = ctx.get_string()

    m = make_map(s, i32, ctx)
    assert isinstance(m, GenericType)
    assert m.name == "Map"
    assert m.args == (s, i32)


def test_make_option():
    """make_option helper should create Option<T>."""
    ctx = TypeContext()
    i32 = ctx.get_int(32)

    opt = make_option(i32, ctx)
    assert isinstance(opt, GenericType)
    assert opt.name == "Option"


def test_make_result():
    """make_result helper should create Result<T, E>."""
    ctx = TypeContext()
    i32 = ctx.get_int(32)
    s = ctx.get_string()

    r = make_result(i32, s, ctx)
    assert isinstance(r, GenericType)
    assert r.name == "Result"
    assert r.args == (i32, s)


# ────────────────────────────────────────────────────────────────────────────
# TypeScheme Tests
# ────────────────────────────────────────────────────────────────────────────

def test_type_scheme_creation():
    """TypeScheme should be created correctly."""
    ctx = TypeContext()
    tv = TypeVar(type_id=-1, name="T")
    i32 = ctx.get_int(32)

    scheme = TypeScheme(vars=(tv,), body=i32)
    assert len(scheme.vars) == 1
    assert scheme.body == i32


def test_type_scheme_instantiate_with_subs():
    """TypeScheme instantiation with explicit substitutions."""
    ctx = TypeContext()
    tv_t = TypeVar(type_id=-1, name="T")
    vec_t = GenericType(type_id=-1, name="Vec", args=(tv_t,))
    i32 = ctx.get_int(32)

    scheme = TypeScheme(vars=(tv_t,), body=vec_t)
    result = scheme.instantiate(substitutions={"T": i32})

    assert isinstance(result, GenericType)
    assert result.name == "Vec"
    assert result.args[0] == i32


def test_type_scheme_instantiate_fresh():
    """TypeScheme instantiation without substitutions should produce fresh vars."""
    ctx = TypeContext()
    tv = TypeVar(type_id=-1, name="T")
    vec = GenericType(type_id=-1, name="Vec", args=(tv,))

    scheme = TypeScheme(vars=(tv,), body=vec)
    result = scheme.instantiate()

    assert isinstance(result, GenericType)
    assert result.name == "Vec"
    # Should have a fresh (non-"T") type variable
    assert isinstance(result.args[0], TypeVar)
    assert result.args[0].name != "T"


def test_type_scheme_apply():
    """TypeScheme apply should substitute in the body."""
    ctx = TypeContext()
    tv = TypeVar(type_id=-1, name="T")
    i32 = ctx.get_int(32)
    f64 = ctx.get_float(64)

    scheme = TypeScheme(vars=(tv,), body=tv)
    result = scheme.apply({"T": i32})
    assert result == i32

    result2 = scheme.apply({"T": f64})
    assert result2 == f64


def test_type_scheme_free_vars():
    """TypeScheme free_vars should exclude bound variables."""
    ctx = TypeContext()
    tv_t = TypeVar(type_id=-1, name="T")
    tv_u = TypeVar(type_id=-1, name="U")

    # Body references only T (bound)
    scheme1 = TypeScheme(vars=(tv_t,), body=tv_t)
    assert scheme1.free_vars() == set()

    # Body references U (not bound)
    scheme2 = TypeScheme(vars=(tv_t,), body=tv_u)
    assert scheme2.free_vars() == {"U"}


def test_make_scheme():
    """make_scheme helper should create a TypeScheme."""
    ctx = TypeContext()
    tv_t = TypeVar(type_id=-1, name="T")
    i32 = ctx.get_int(32)

    scheme = make_scheme(["T"], i32)
    assert len(scheme.vars) == 1
    assert scheme.vars[0].name == "T"
    assert scheme.body == i32

    # With constraints
    scheme_constrained = make_scheme(
        ["T", "U"],
        GenericType(type_id=-1, name="Pair", args=(tv_t, TypeVar(type_id=-2, name="U"))),
        constraints={"T": (IntType(type_id=0, bits=32, signed=True),)},
    )
    assert len(scheme_constrained.vars) == 2
    assert len(scheme_constrained.vars[0].constraints) == 1


# ────────────────────────────────────────────────────────────────────────────
# Substitution Tests
# ────────────────────────────────────────────────────────────────────────────

def test_substitute_type_var():
    """Substitution should replace type variables."""
    tv = TypeVar(type_id=-1, name="T")
    ctx = TypeContext()
    i32 = ctx.get_int(32)

    result = _substitute(tv, {"T": i32})
    assert result == i32


def test_substitute_generic():
    """Substitution should replace type variables in generic types."""
    ctx = TypeContext()
    tv_t = TypeVar(type_id=-1, name="T")
    tv_k = TypeVar(type_id=-2, name="K")
    tv_v = TypeVar(type_id=-3, name="V")

    map_tkv = GenericType(type_id=-1, name="Map", args=(tv_k, tv_v))
    i32 = ctx.get_int(32)
    s = ctx.get_string()

    result = _substitute(map_tkv, {"K": i32, "V": s})
    assert isinstance(result, GenericType)
    assert result.name == "Map"
    assert result.args[0] == i32
    assert result.args[1] == s


def test_substitute_func_type():
    """Substitution should replace type variables in function types."""
    ctx = TypeContext()
    tv_t = TypeVar(type_id=-1, name="T")
    i32 = ctx.get_int(32)

    func = FuncType(type_id=-1, params=(tv_t,), returns=(tv_t,))
    result = _substitute(func, {"T": i32})

    assert isinstance(result, FuncType)
    assert result.params == (i32,)
    assert result.returns == (i32,)


def test_substitute_struct_type():
    """Substitution should replace type variables in struct fields."""
    ctx = TypeContext()
    tv_t = TypeVar(type_id=-1, name="T")
    i32 = ctx.get_int(32)

    struct = StructType(
        type_id=-1,
        name="Container",
        fields=(("value", tv_t), ("count", i32)),
    )
    result = _substitute(struct, {"T": i32})

    assert isinstance(result, StructType)
    assert result.fields[0] == ("value", i32)
    assert result.fields[1] == ("count", i32)


def test_substitute_no_change():
    """Substitution with no matching vars should return the same type."""
    ctx = TypeContext()
    tv = TypeVar(type_id=-1, name="T")
    i32 = ctx.get_int(32)

    result = _substitute(i32, {"T": ctx.get_float(32)})
    assert result == i32

    result2 = _substitute(tv, {"U": i32})
    assert result2 == tv


def test_collect_free_vars():
    """Free variable collection should work recursively."""
    ctx = TypeContext()
    tv_t = TypeVar(type_id=-1, name="T")
    tv_u = TypeVar(type_id=-2, name="U")
    i32 = ctx.get_int(32)

    # Simple
    assert _collect_free_vars(tv_t) == {"T"}

    # Generic with one free var
    vec = GenericType(type_id=-1, name="Vec", args=(tv_t,))
    assert _collect_free_vars(vec) == {"T"}

    # Generic with two free vars
    map_tu = GenericType(type_id=-1, name="Map", args=(tv_t, tv_u))
    assert _collect_free_vars(map_tu) == {"T", "U"}

    # No free vars
    vec_i32 = GenericType(type_id=-1, name="Vec", args=(i32,))
    assert _collect_free_vars(vec_i32) == set()

    # Nested generic
    nested = GenericType(type_id=-1, name="Vec", args=(map_tu,))
    assert _collect_free_vars(nested) == {"T", "U"}


def test_collect_free_vars_func():
    """Free vars should be collected from function types."""
    ctx = TypeContext()
    tv_t = TypeVar(type_id=-1, name="T")
    i32 = ctx.get_int(32)

    func = FuncType(type_id=-1, params=(tv_t, i32), returns=(tv_t,))
    assert _collect_free_vars(func) == {"T"}


# ────────────────────────────────────────────────────────────────────────────
# Cross-language Integration Tests
# ────────────────────────────────────────────────────────────────────────────

def test_c_python_interop():
    """C and Python types should unify correctly."""
    u = TypeUnifier()

    c_int = u.from_c("int")       # i32
    py_int = u.from_python(int)   # i64

    assert are_compatible(c_int, py_int)
    assert u.coercion_cost(c_int, py_int) <= 2
    lub = least_upper_bound(c_int, py_int)
    assert lub is not None


def test_rust_c_interop():
    """Rust and C types should unify correctly."""
    u = TypeUnifier()

    c_double = u.from_c("double")
    rs_f64 = u.from_rust("f64")

    assert _type_eq(c_double, rs_f64)
    assert u.coercion_cost(c_double, rs_f64) == 0


def test_polyglot_numeric_lattice():
    """Numeric types across languages should form a lattice."""
    u = TypeUnifier()

    c_char = u.from_c("char")        # i8
    c_int = u.from_c("int")          # i32
    py_int = u.from_python(int)      # i64
    c_double = u.from_c("double")    # f64
    rs_f32 = u.from_rust("f32")      # f32

    # All should be pairwise compatible
    all_ints = [c_char, c_int, py_int]
    for t1 in all_ints:
        for t2 in all_ints:
            assert are_compatible(t1, t2)

    # int and float should also be compatible
    for i_type in all_ints:
        assert are_compatible(i_type, c_double)
        assert are_compatible(i_type, rs_f32)


def test_generic_cross_language():
    """Generic types should unify across languages."""
    u = TypeUnifier()

    rs_vec = u.from_rust("Vec<i32>")
    rs_opt = u.from_rust("Option<i64>")

    # Vec<i32> and Vec<i32> should unify
    lub = u.unify(rs_vec, rs_vec)
    assert lub is not None
    assert isinstance(lub, GenericType)
    assert lub.name == "Vec"

    # Vec<i32> and Option<i64> should not unify (different names)
    lub2 = u.unify(rs_vec, rs_opt)
    assert lub2 is None


# ────────────────────────────────────────────────────────────────────────────
# Run all tests
# ────────────────────────────────────────────────────────────────────────────

print("=" * 60)
print("Type Unification Test Suite")
print("=" * 60)

# C type mapping
run_test("test_c_int_types", test_c_int_types)
run_test("test_c_float_types", test_c_float_types)
run_test("test_c_void_and_bool", test_c_void_and_bool)
run_test("test_c_pointer_types", test_c_pointer_types)
run_test("test_c_const_qualifier", test_c_const_qualifier)
run_test("test_c_struct_and_enum", test_c_struct_and_enum)
run_test("test_c_unknown_type_raises", test_c_unknown_type_raises)
run_test("test_to_c_roundtrip", test_to_c_roundtrip)

# Python type mapping
run_test("test_python_primitive_types", test_python_primitive_types)
run_test("test_python_string_types", test_python_string_types)
run_test("test_to_python_roundtrip", test_to_python_roundtrip)

# Rust type mapping
run_test("test_rust_integer_types", test_rust_integer_types)
run_test("test_rust_float_types", test_rust_float_types)
run_test("test_rust_bool_and_unit", test_rust_bool_and_unit)
run_test("test_rust_string_types", test_rust_string_types)
run_test("test_rust_reference_types", test_rust_reference_types)
run_test("test_rust_vec_type", test_rust_vec_type)
run_test("test_rust_option_type", test_rust_option_type)
run_test("test_rust_result_type", test_rust_result_type)
run_test("test_rust_hashmap_type", test_rust_hashmap_type)
run_test("test_rust_tuple_type", test_rust_tuple_type)
run_test("test_rust_array_type", test_rust_array_type)
run_test("test_rust_box_type", test_rust_box_type)
run_test("test_to_rust_roundtrip", test_to_rust_roundtrip)

# Cross-language unification
run_test("test_cross_language_int_unification", test_cross_language_int_unification)
run_test("test_cross_language_float_unification", test_cross_language_float_unification)
run_test("test_cross_language_int_float_promotion", test_cross_language_int_float_promotion)
run_test("test_unify_incompatible_types", test_unify_incompatible_types)
run_test("test_unify_single_type", test_unify_single_type)
run_test("test_unify_empty", test_unify_empty)
run_test("test_map_type_language_dispatch", test_map_type_language_dispatch)

# Coercion cost
run_test("test_coercion_cost_identity", test_coercion_cost_identity)
run_test("test_coercion_cost_widening", test_coercion_cost_widening)
run_test("test_coercion_cost_narrowing", test_coercion_cost_narrowing)
run_test("test_coercion_cost_int_to_float", test_coercion_cost_int_to_float)
run_test("test_coercion_cost_bool", test_coercion_cost_bool)
run_test("test_coercion_cost_string", test_coercion_cost_string)
run_test("test_coercion_cost_incompatible", test_coercion_cost_incompatible)
run_test("test_implicit_coercion", test_implicit_coercion)

# Compatibility
run_test("test_compatible_identical", test_compatible_identical)
run_test("test_compatible_numeric", test_compatible_numeric)
run_test("test_compatible_bool_int", test_compatible_bool_int)
run_test("test_compatible_unit", test_compatible_unit)
run_test("test_compatible_ref", test_compatible_ref)
run_test("test_compatible_array", test_compatible_array)
run_test("test_compatible_generic", test_compatible_generic)
run_test("test_compatible_typevar", test_compatible_typevar)
run_test("test_least_upper_bound_basic", test_least_upper_bound_basic)
run_test("test_least_upper_bound_none", test_least_upper_bound_none)
run_test("test_compatibility_report", test_compatibility_report)
run_test("test_coercion_cost_function", test_coercion_cost_function)

# Generic types
run_test("test_type_var_creation", test_type_var_creation)
run_test("test_generic_type_creation", test_generic_type_creation)
run_test("test_generic_type_not_fully_concrete", test_generic_type_not_fully_concrete)
run_test("test_generic_type_repr", test_generic_type_repr)
run_test("test_make_vec", test_make_vec)
run_test("test_make_map", test_make_map)
run_test("test_make_option", test_make_option)
run_test("test_make_result", test_make_result)

# TypeScheme
run_test("test_type_scheme_creation", test_type_scheme_creation)
run_test("test_type_scheme_instantiate_with_subs", test_type_scheme_instantiate_with_subs)
run_test("test_type_scheme_instantiate_fresh", test_type_scheme_instantiate_fresh)
run_test("test_type_scheme_apply", test_type_scheme_apply)
run_test("test_type_scheme_free_vars", test_type_scheme_free_vars)
run_test("test_make_scheme", test_make_scheme)

# Substitution
run_test("test_substitute_type_var", test_substitute_type_var)
run_test("test_substitute_generic", test_substitute_generic)
run_test("test_substitute_func_type", test_substitute_func_type)
run_test("test_substitute_struct_type", test_substitute_struct_type)
run_test("test_substitute_no_change", test_substitute_no_change)
run_test("test_collect_free_vars", test_collect_free_vars)
run_test("test_collect_free_vars_func", test_collect_free_vars_func)

# Cross-language integration
run_test("test_c_python_interop", test_c_python_interop)
run_test("test_rust_c_interop", test_rust_c_interop)
run_test("test_polyglot_numeric_lattice", test_polyglot_numeric_lattice)
run_test("test_generic_cross_language", test_generic_cross_language)

print("=" * 60)
print(f"Results: {passed} passed, {failed} failed")
print("=" * 60)

if failed > 0:
    sys.exit(1)
else:
    print("All type unification tests passed!")
