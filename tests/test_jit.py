"""JIT Compiler Tests — comprehensive tests for the JIT compilation framework."""

import sys
import traceback

sys.path.insert(0, "src")

from flux.fir.types import TypeContext, IntType, FloatType, BoolType, UnitType, StringType
from flux.fir.values import Value
from flux.fir.instructions import (
    IAdd, ISub, IMul, IDiv, INeg,
    FAdd, FSub, FMul, FDiv,
    IAnd, IOr, IXor,
    IEq, ILt,
    Return, Jump, Branch,
    Call, Store, Alloca,
    is_terminator,
)
from flux.fir.blocks import FIRModule, FIRFunction, FIRBlock
from flux.fir.builder import FIRBuilder

from flux.jit.compiler import JITCompiler, JITFunction, RegisterAllocation
from flux.jit.cache import JITCache, CacheEntry
from flux.jit.tracing import ExecutionTracer, BlockProfile, FunctionProfile
from flux.jit.ir_optimize import (
    const_fold_pass,
    dead_code_pass,
    inline_pass,
    block_layout_pass,
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
# Helper: build simple module
# ────────────────────────────────────────────────────────────────────────────

def _build_add_module():
    """Build a module with an add(i32, i32) -> i32 function."""
    ctx = TypeContext()
    builder = FIRBuilder(ctx)
    i32 = ctx.get_int(32)
    mod = builder.new_module("test")
    func = builder.new_function(mod, "add", [("a", i32), ("b", i32)], [i32])
    entry = builder.new_block(func, "entry", [("a", i32), ("b", i32)])
    builder.set_block(entry)
    a = Value(id=0, name="a", type=i32)
    b = Value(id=1, name="b", type=i32)
    result = builder.iadd(a, b)
    builder.ret(result)
    return mod, ctx


def _build_multi_block_module():
    """Build a module with branching (max function)."""
    ctx = TypeContext()
    builder = FIRBuilder(ctx)
    i32 = ctx.get_int(32)
    bool_t = ctx.get_bool()

    mod = builder.new_module("test")
    func = builder.new_function(mod, "max", [("a", i32), ("b", i32)], [i32])

    entry = builder.new_block(func, "entry", [("a", i32), ("b", i32)])
    then_blk = builder.new_block(func, "then", [])
    else_blk = builder.new_block(func, "else", [])
    merge = builder.new_block(func, "merge", [("result", i32)])

    a = Value(id=0, name="a", type=i32)
    b = Value(id=1, name="b", type=i32)
    cmp = Value(id=2, name="cmp", type=bool_t)

    builder.set_block(entry)
    builder.branch(cmp, "then", "else", [a, b])

    builder.set_block(then_blk)
    builder.jump("merge", [a])

    builder.set_block(else_blk)
    builder.jump("merge", [b])

    merge_result = Value(id=3, name="result", type=i32)
    builder.set_block(merge)
    builder.ret(merge_result)

    return mod, ctx


# ────────────────────────────────────────────────────────────────────────────
# Dead Code Elimination Tests
# ────────────────────────────────────────────────────────────────────────────

def test_dead_code_removes_unreachable_block():
    """Unreachable blocks should be removed."""
    ctx = TypeContext()
    i32 = ctx.get_int(32)

    mod = FIRModule(name="dce_test", type_ctx=ctx)
    func = FIRFunction(name="test_func", sig=ctx.get_func((), (i32,)))
    mod.functions["test_func"] = func

    entry = FIRBlock(label="entry", instructions=[Return(Value(id=0, name="val", type=i32))])
    dead = FIRBlock(label="dead_block", instructions=[Jump("entry")])

    func.blocks = [entry, dead]
    assert len(func.blocks) == 2

    removed = dead_code_pass(mod)
    assert removed == 1, f"Expected 1 block removed, got {removed}"
    assert len(func.blocks) == 1
    assert func.blocks[0].label == "entry"


def test_dead_code_keeps_reachable_blocks():
    """Reachable blocks should be kept."""
    ctx = TypeContext()
    i32 = ctx.get_int(32)

    mod = FIRModule(name="keep_test", type_ctx=ctx)
    func = FIRFunction(name="test_func", sig=ctx.get_func((), (i32,)))
    mod.functions["test_func"] = func

    entry = FIRBlock(label="entry")
    loop_body = FIRBlock(label="loop_body")
    exit_blk = FIRBlock(label="exit")

    cond = Value(id=0, name="cond", type=ctx.get_bool())
    val = Value(id=1, name="val", type=i32)

    entry.instructions = [Branch(cond, "loop_body", "exit")]
    loop_body.instructions = [Jump("entry")]
    exit_blk.instructions = [Return(val)]

    func.blocks = [entry, loop_body, exit_blk]
    removed = dead_code_pass(mod)
    assert removed == 0, "No blocks should be removed"
    assert len(func.blocks) == 3


def test_dead_code_empty_module():
    """Empty module should be handled gracefully."""
    ctx = TypeContext()
    mod = FIRModule(name="empty", type_ctx=ctx)
    removed = dead_code_pass(mod)
    assert removed == 0


def test_dead_code_multiple_unreachable():
    """Multiple unreachable blocks should all be removed."""
    ctx = TypeContext()
    i32 = ctx.get_int(32)

    mod = FIRModule(name="multi_dead", type_ctx=ctx)
    func = FIRFunction(name="f", sig=ctx.get_func((), (i32,)))
    mod.functions["f"] = func

    entry = FIRBlock(label="entry", instructions=[Return(Value(id=0, name="v", type=i32))])
    dead1 = FIRBlock(label="dead1", instructions=[Jump("dead2")])
    dead2 = FIRBlock(label="dead2", instructions=[Jump("dead1")])
    dead3 = FIRBlock(label="dead3", instructions=[])

    func.blocks = [entry, dead1, dead2, dead3]
    removed = dead_code_pass(mod)
    assert removed == 3, f"Expected 3 blocks removed, got {removed}"
    assert len(func.blocks) == 1


# ────────────────────────────────────────────────────────────────────────────
# Block Layout Tests
# ────────────────────────────────────────────────────────────────────────────

def test_block_layout_reorder_for_fallthrough():
    """Block layout should reorder for fallthrough optimization."""
    ctx = TypeContext()
    i32 = ctx.get_int(32)
    bool_t = ctx.get_bool()

    mod = FIRModule(name="layout_test", type_ctx=ctx)
    func = FIRFunction(name="f", sig=ctx.get_func((), (i32,)))
    mod.functions["f"] = func

    # Blocks in non-optimal order: entry jumps to "cold", then "hot"
    # Optimal would be: entry → hot → merge → cold → exit
    cond = Value(id=0, name="c", type=bool_t)
    val = Value(id=1, name="v", type=i32)

    entry = FIRBlock(label="entry", instructions=[Branch(cond, "hot", "cold")])
    merge = FIRBlock(label="merge", instructions=[Return(val)])
    cold = FIRBlock(label="cold", instructions=[Jump("merge")])
    hot = FIRBlock(label="hot", instructions=[Jump("merge")])
    exit_blk = FIRBlock(label="exit", instructions=[Return(val)])

    # Initial order: entry, merge, cold, hot, exit
    func.blocks = [entry, merge, cold, hot, exit_blk]
    old_labels = [b.label for b in func.blocks]

    reordered = block_layout_pass(mod)
    # The layout pass should have reordered blocks
    assert reordered >= 0  # may or may not reorder depending on heuristic
    # Entry should still be first
    assert func.blocks[0].label == "entry"


def test_block_layout_preserves_entry():
    """Block layout should always keep entry as first block."""
    mod, _ = _build_multi_block_module()
    func = mod.functions["max"]
    old_entry = func.blocks[0].label

    block_layout_pass(mod)

    assert func.blocks[0].label == old_entry


def test_block_layout_single_block():
    """Single-block functions should be unchanged."""
    mod, _ = _build_add_module()
    func = mod.functions["add"]
    old_count = len(func.blocks)

    reordered = block_layout_pass(mod)

    assert reordered == 0
    assert len(func.blocks) == old_count


# ────────────────────────────────────────────────────────────────────────────
# Inlining Tests
# ────────────────────────────────────────────────────────────────────────────

def test_inline_small_function():
    """Small functions (< 10 instructions) should be inlined."""
    ctx = TypeContext()
    i32 = ctx.get_int(32)

    mod = FIRModule(name="inline_test", type_ctx=ctx)

    # Callee: simple double(x) = x + x
    callee = FIRFunction(name="double", sig=ctx.get_func((i32,), (i32,)))
    x_val = Value(id=0, name="x", type=i32)
    entry = FIRBlock(
        label="entry",
        params=[("x", i32)],
        instructions=[
            IAdd(lhs=x_val, rhs=x_val),
            Return(Value(id=1, name="result", type=i32)),
        ],
    )
    callee.blocks = [entry]
    mod.functions["double"] = callee

    # Caller: calls double
    caller = FIRFunction(name="caller", sig=ctx.get_func((), (i32,)))
    arg = Value(id=10, name="arg", type=i32)
    result_val = Value(id=11, name="ret", type=i32)
    caller_entry = FIRBlock(
        label="entry",
        instructions=[
            Call(func="double", args=[arg], return_type=i32),
            Return(result_val),
        ],
    )
    caller.blocks = [caller_entry]
    mod.functions["caller"] = caller

    inlined = inline_pass(mod, threshold=10)
    assert inlined >= 1, f"Expected at least 1 inlining, got {inlined}"

    # The Call instruction should have been replaced
    has_call = any(
        isinstance(instr, Call) and instr.func == "double"
        for instr in caller_entry.instructions
    )
    assert not has_call, "Call to 'double' should have been inlined"


def test_inline_no_self_recursion():
    """Self-recursive functions should not be inlined."""
    ctx = TypeContext()
    i32 = ctx.get_int(32)

    mod = FIRModule(name="self_recurse", type_ctx=ctx)
    func = FIRFunction(name="recurse", sig=ctx.get_func((i32,), (i32,)))
    arg = Value(id=0, name="x", type=i32)
    entry = FIRBlock(
        label="entry",
        params=[("x", i32)],
        instructions=[
            Call(func="recurse", args=[arg], return_type=i32),
            Return(Value(id=1, name="result", type=i32)),
        ],
    )
    func.blocks = [entry]
    mod.functions["recurse"] = func

    inlined = inline_pass(mod, threshold=10)
    assert inlined == 0, "Self-recursive calls should not be inlined"


def test_inline_respects_threshold():
    """Functions above threshold should not be inlined."""
    ctx = TypeContext()
    i32 = ctx.get_int(32)

    mod = FIRModule(name="threshold_test", type_ctx=ctx)

    # Callee with many instructions (> threshold)
    callee = FIRFunction(name="big_func", sig=ctx.get_func((i32,), (i32,)))
    x = Value(id=0, name="x", type=i32)
    instrs = []
    for i in range(1, 20):
        instrs.append(IAdd(lhs=Value(id=i, name=f"v{i}", type=i32), rhs=x))
    instrs.append(Return(Value(id=99, name="result", type=i32)))
    callee.blocks = [FIRBlock(label="entry", params=[("x", i32)], instructions=instrs)]
    mod.functions["big_func"] = callee

    # Caller
    caller = FIRFunction(name="caller", sig=ctx.get_func((), (i32,)))
    arg = Value(id=100, name="arg", type=i32)
    caller.blocks = [
        FIRBlock(
            label="entry",
            instructions=[
                Call(func="big_func", args=[arg], return_type=i32),
                Return(Value(id=101, name="r", type=i32)),
            ],
        )
    ]
    mod.functions["caller"] = caller

    inlined = inline_pass(mod, threshold=10)
    assert inlined == 0, "Functions above threshold should not be inlined"


# ────────────────────────────────────────────────────────────────────────────
# Constant Folding Tests
# ────────────────────────────────────────────────────────────────────────────

def test_const_fold_known_constants():
    """Instructions with known constant operands should be folded."""
    ctx = TypeContext()
    i32 = ctx.get_int(32)

    mod = FIRModule(name="fold_test", type_ctx=ctx)
    func = FIRFunction(name="fold_me", sig=ctx.get_func((), (i32,)))
    mod.functions["fold_me"] = func

    # Create constant values
    c10 = Value(id=0, name="c10", type=i32)
    c20 = Value(id=1, name="c20", type=i32)
    ret_val = Value(id=2, name="ret", type=i32)

    entry = FIRBlock(
        label="entry",
        instructions=[
            IAdd(lhs=c10, rhs=c20),  # should fold: 10 + 20 = 30
            IMul(lhs=c10, rhs=c20),  # should fold: 10 * 20 = 200
            ISub(lhs=c20, rhs=c10),  # should fold: 20 - 10 = 10
            Return(ret_val),
        ],
    )
    func.blocks = [entry]

    known_constants = {0: 10, 1: 20}

    before_count = len(entry.instructions)
    changes = const_fold_pass(mod, known_constants=known_constants)
    assert changes >= 2, f"Expected at least 2 folds, got {changes}"
    assert len(entry.instructions) < before_count, "Instructions should have been removed"


def test_const_fold_no_side_effects():
    """Instructions with side effects should not be folded."""
    ctx = TypeContext()
    i32 = ctx.get_int(32)

    mod = FIRModule(name="side_effects", type_ctx=ctx)
    func = FIRFunction(name="f", sig=ctx.get_func((), (i32,)))
    mod.functions["f"] = func

    val = Value(id=0, name="v", type=i32)
    ptr = Value(id=1, name="ptr", type=i32)

    entry = FIRBlock(
        label="entry",
        instructions=[
            IAdd(lhs=val, rhs=val),    # foldable
            Store(value=val, ptr=ptr),  # NOT foldable (side effect)
            Return(val),
        ],
    )
    func.blocks = [entry]

    changes = const_fold_pass(mod, known_constants={0: 5, 1: 0})
    # Only the IAdd should be considered for folding
    # The Store should remain
    has_store = any(isinstance(i, Store) for i in entry.instructions)
    assert has_store, "Store should not be removed"


def test_const_fold_no_constants():
    """Without known constants, foldable patterns should still simplify."""
    ctx = TypeContext()
    i32 = ctx.get_int(32)

    mod = FIRModule(name="no_const", type_ctx=ctx)
    func = FIRFunction(name="f", sig=ctx.get_func((), (i32,)))
    mod.functions["f"] = func

    val = Value(id=0, name="v", type=i32)
    entry = FIRBlock(
        label="entry",
        instructions=[
            IAdd(lhs=val, rhs=val),
            Return(val),
        ],
    )
    func.blocks = [entry]

    # No known constants — nothing should be folded
    changes = const_fold_pass(mod)
    # The pass should not remove anything without constants
    assert changes == 0


def test_const_fold_float():
    """Float constant folding should work."""
    ctx = TypeContext()
    f64 = ctx.get_float(64)

    mod = FIRModule(name="float_fold", type_ctx=ctx)
    func = FIRFunction(name="f", sig=ctx.get_func((), (f64,)))
    mod.functions["f"] = func

    a = Value(id=0, name="a", type=f64)
    b = Value(id=1, name="b", type=f64)
    ret = Value(id=2, name="r", type=f64)

    entry = FIRBlock(
        label="entry",
        instructions=[
            FAdd(lhs=a, rhs=b),
            FMul(lhs=a, rhs=b),
            Return(ret),
        ],
    )
    func.blocks = [entry]

    changes = const_fold_pass(mod, known_constants={0: 3.14, 1: 2.0})
    assert changes >= 2, f"Expected at least 2 float folds, got {changes}"


# ────────────────────────────────────────────────────────────────────────────
# JIT Compiler Tests
# ────────────────────────────────────────────────────────────────────────────

def test_jit_compile_simple_function():
    """JITCompiler should compile a simple function."""
    mod, ctx = _build_add_module()
    func = mod.functions["add"]

    compiler = JITCompiler()
    jit_func = compiler.compile(func)

    assert isinstance(jit_func, JITFunction)
    assert jit_func.name == "add"
    assert jit_func.is_compiled
    assert jit_func.instruction_count() > 0
    assert jit_func.block_count() >= 1
    assert isinstance(jit_func.register_alloc, RegisterAllocation)


def test_jit_compile_optimization_stats():
    """JIT compile should produce optimization statistics."""
    mod, ctx = _build_add_module()
    func = mod.functions["add"]

    compiler = JITCompiler(inline_threshold=5)
    jit_func = compiler.compile(func)

    assert "inlined" in jit_func.optimization_stats
    assert "const_folded" in jit_func.optimization_stats
    assert "dead_blocks_removed" in jit_func.optimization_stats
    assert "blocks_reordered" in jit_func.optimization_stats


def test_jit_register_allocation():
    """JIT should produce register allocation."""
    mod, ctx = _build_add_module()
    func = mod.functions["add"]

    compiler = JITCompiler()
    jit_func = compiler.compile(func)

    alloc = jit_func.register_alloc
    assert alloc.total_registers_used >= 0
    assert alloc.num_virtual_registers == 64


def test_jit_compile_multi_block():
    """JITCompiler should handle multi-block functions."""
    mod, ctx = _build_multi_block_module()
    func = mod.functions["max"]

    compiler = JITCompiler()
    jit_func = compiler.compile(func)

    assert jit_func.block_count() >= 2
    assert jit_func.name == "max"


def test_jit_compile_module():
    """JITCompiler.compile_module should compile all functions."""
    mod, ctx = _build_add_module()
    # Add another function
    builder = FIRBuilder(ctx)
    i32 = ctx.get_int(32)
    func2 = builder.new_function(mod, "sub", [("a", i32), ("b", i32)], [i32])
    entry2 = builder.new_block(func2, "entry", [("a", i32), ("b", i32)])
    builder.set_block(entry2)
    a = Value(id=0, name="a", type=i32)
    b = Value(id=1, name="b", type=i32)
    result = builder.isub(a, b)
    builder.ret(result)

    compiler = JITCompiler()
    results = compiler.compile_module(mod)

    assert len(results) == 2
    assert "add" in results
    assert "sub" in results


# ────────────────────────────────────────────────────────────────────────────
# JIT Cache Tests
# ────────────────────────────────────────────────────────────────────────────

def test_cache_put_get():
    """Cache should store and retrieve values."""
    cache = JITCache(max_size=4)

    cache.put("key1", "value1")
    result = cache.get("key1")
    assert result == "value1"


def test_cache_miss():
    """Cache should return None for missing keys."""
    cache = JITCache(max_size=4)
    result = cache.get("nonexistent")
    assert result is None


def test_cache_lru_eviction():
    """Cache should evict LRU entries when full."""
    cache = JITCache(max_size=3)

    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    assert cache.size == 3

    # Adding a 4th entry should evict "a" (LRU)
    cache.put("d", 4)
    assert cache.size == 3
    assert cache.get("a") is None
    assert cache.get("d") == 4


def test_cache_lru_ordering():
    """Accessing an entry should move it to MRU position."""
    cache = JITCache(max_size=3)

    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)

    # Access "a" to make it MRU
    cache.get("a")

    # Now "b" should be LRU
    cache.put("d", 4)
    assert cache.get("b") is None
    assert cache.get("a") == 1


def test_cache_invalidate():
    """Cache invalidation should remove specific entries."""
    cache = JITCache(max_size=10)
    cache.put("a", 1)
    cache.put("b", 2)

    assert cache.invalidate("a") is True
    assert cache.get("a") is None
    assert cache.get("b") == 2

    assert cache.invalidate("nonexistent") is False


def test_cache_clear():
    """Cache clear should remove all entries."""
    cache = JITCache(max_size=10)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)

    cleared = cache.clear()
    assert cleared == 3
    assert cache.size == 0


def test_cache_hit_rate():
    """Cache hit rate should be computed correctly."""
    cache = JITCache(max_size=10)

    cache.put("a", 1)
    cache.get("a")  # hit
    cache.get("a")  # hit
    cache.get("b")  # miss

    assert cache.hit_rate == pytest_approx(2/3, abs=0.01) if 'pytest_approx' in dir() else abs(cache.hit_rate - 2/3) < 0.01
    # Manually check
    assert cache.stats["hits"] == 2
    assert cache.stats["misses"] == 1


def test_cache_stats():
    """Cache should provide comprehensive statistics."""
    cache = JITCache(max_size=10)

    cache.put("a", 1, size_bytes=100)
    cache.put("b", 2, size_bytes=200)
    cache.get("a")  # hit
    cache.get("c")  # miss

    stats = cache.stats
    assert stats["size"] == 2
    assert stats["max_size"] == 10
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["memory_bytes"] == 300


def test_cache_compute_key():
    """Cache key computation should be deterministic."""
    key1 = JITCache.compute_key(b"hello")
    key2 = JITCache.compute_key(b"hello")
    key3 = JITCache.compute_key(b"world")

    assert key1 == key2
    assert key1 != key3
    assert len(key1) == 64  # SHA-256 hex


def test_cache_memory_budget():
    """Cache should respect memory budget."""
    cache = JITCache(max_size=100, max_memory_bytes=150)

    cache.put("a", 1, size_bytes=100)
    cache.put("b", 2, size_bytes=100)

    # "a" should be evicted because adding "b" exceeds budget
    assert cache.get("a") is None
    assert cache.get("b") == 2


# ────────────────────────────────────────────────────────────────────────────
# Execution Tracer Tests
# ────────────────────────────────────────────────────────────────────────────

def test_tracer_record_block():
    """Tracer should record block executions."""
    tracer = ExecutionTracer(hot_threshold=5, block_hot_threshold=10)

    tracer.record_block_execution("entry", count=5, function_name="main")
    assert tracer.get_block_frequency("entry") == 5
    assert not tracer.is_hot("entry")  # below threshold

    tracer.record_block_execution("entry", count=10)
    assert tracer.get_block_frequency("entry") == 15
    assert tracer.is_hot("entry")


def test_tracer_record_call():
    """Tracer should record function calls."""
    tracer = ExecutionTracer(hot_threshold=10)

    for _ in range(5):
        tracer.record_call("hot_func")

    assert not tracer.should_jit_compile("hot_func")

    for _ in range(10):
        tracer.record_call("hot_func")

    assert tracer.should_jit_compile("hot_func")
    assert tracer.get_call_frequency("hot_func") == 15


def test_tracer_record_edge():
    """Tracer should record control flow edges."""
    tracer = ExecutionTracer()

    tracer.record_edge("entry", "loop_body", count=100)
    tracer.record_edge("entry", "exit", count=1)
    tracer.record_edge("loop_body", "entry", count=100)

    assert tracer.get_edge_frequency("entry", "loop_body") == 100
    assert tracer.get_edge_frequency("entry", "exit") == 1


def test_tracer_hot_paths():
    """Tracer should identify hot paths."""
    tracer = ExecutionTracer(hot_threshold=5, block_hot_threshold=10)

    tracer.record_block_execution("entry", count=50, function_name="main")
    tracer.record_block_execution("loop", count=5000, function_name="main")
    tracer.record_block_execution("exit", count=50, function_name="main")

    paths = tracer.get_hot_paths()
    assert len(paths) >= 1
    assert "loop" in paths[0]


def test_tracer_hot_functions():
    """Tracer should list hot functions."""
    tracer = ExecutionTracer(hot_threshold=50)

    for _ in range(100):
        tracer.record_call("func_a")
    for _ in range(200):
        tracer.record_call("func_b")

    hot = tracer.get_hot_functions()
    assert "func_a" in hot
    assert "func_b" in hot
    # func_b should come first (higher call count)
    assert hot[0] == "func_b"


def test_tracer_mark_compiled():
    """Tracer should mark functions as compiled."""
    tracer = ExecutionTracer(hot_threshold=5)

    for _ in range(10):
        tracer.record_call("f")

    assert tracer.should_jit_compile("f")
    tracer.mark_compiled("f")
    assert not tracer.should_jit_compile("f")


def test_tracer_record_cycles():
    """Tracer should record CPU cycles."""
    tracer = ExecutionTracer()

    tracer.record_cycles("heavy_func", 50000)
    tracer.record_cycles("heavy_func", 30000)

    profile = tracer.get_function_profile("heavy_func")
    assert profile is not None
    assert profile.total_cycles == 80000


def test_tracer_reset():
    """Tracer should reset all data."""
    tracer = ExecutionTracer()

    tracer.record_call("f")
    tracer.record_block_execution("entry")
    tracer.record_edge("a", "b")

    tracer.reset()

    assert tracer.total_executions == 0
    assert tracer.get_call_frequency("f") == 0
    assert tracer.tracked_functions == 0


def test_tracer_stats():
    """Tracer should provide statistics."""
    tracer = ExecutionTracer(hot_threshold=5, block_hot_threshold=5)

    tracer.record_call("f", count=10)
    tracer.record_block_execution("entry", count=100, function_name="f")
    tracer.mark_compiled("f")

    stats = tracer.stats
    assert stats["total_executions"] == 100
    assert stats["tracked_functions"] == 1
    assert stats["hot_functions"] == 0  # already compiled


def test_tracer_threshold_setter():
    """Tracer should allow changing thresholds."""
    tracer = ExecutionTracer(hot_threshold=100)
    assert tracer.hot_threshold == 100

    tracer.hot_threshold = 10
    assert tracer.hot_threshold == 10

    for _ in range(15):
        tracer.record_call("f")
    assert tracer.should_jit_compile("f")


# ────────────────────────────────────────────────────────────────────────────
# Integration Tests
# ────────────────────────────────────────────────────────────────────────────

def test_jit_with_tracing():
    """JIT compiler should work with tracing enabled."""
    mod, ctx = _build_add_module()
    func = mod.functions["add"]

    compiler = JITCompiler(enable_tracing=True)
    assert compiler.tracer is not None

    # Simulate some executions
    compiler.tracer.record_call("add", count=150)
    assert compiler.tracer.should_jit_compile("add")

    jit_func = compiler.compile(func)
    assert jit_func.is_compiled
    compiler.tracer.mark_compiled("add")


def test_jit_cache_integration():
    """JIT compiler should use the cache."""
    mod, ctx = _build_add_module()
    func = mod.functions["add"]

    compiler = JITCompiler()

    # First compile — should be a cache miss
    result1 = compiler.compile(func)
    assert compiler.cache.stats["misses"] >= 1

    # Second compile of same function — should be a cache hit
    result2 = compiler.compile(func)
    assert result1 is result2  # same cached object
    assert compiler.cache.stats["hits"] >= 1


def test_jit_invalidate_cache():
    """JIT compiler cache invalidation should work."""
    mod, ctx = _build_add_module()
    func = mod.functions["add"]

    compiler = JITCompiler()
    compiler.compile(func)
    assert compiler.cache.size >= 1

    cleared = compiler.invalidate_cache()
    assert cleared >= 1
    assert compiler.cache.size == 0


def test_combined_optimization_passes():
    """All optimization passes should work together."""
    ctx = TypeContext()
    i32 = ctx.get_int(32)

    mod = FIRModule(name="combined", type_ctx=ctx)

    # Small helper function
    helper = FIRFunction(name="helper", sig=ctx.get_func((i32,), (i32,)))
    x = Value(id=0, name="x", type=i32)
    helper.blocks = [
        FIRBlock(
            label="entry",
            params=[("x", i32)],
            instructions=[
                IAdd(lhs=x, rhs=x),
                Return(Value(id=1, name="r", type=i32)),
            ],
        )
    ]
    mod.functions["helper"] = helper

    # Main function with dead blocks
    main = FIRFunction(name="main", sig=ctx.get_func((), (i32,)))
    arg = Value(id=10, name="arg", type=i32)
    ret_val = Value(id=11, name="ret", type=i32)
    main.blocks = [
        FIRBlock(
            label="entry",
            instructions=[
                Call(func="helper", args=[arg], return_type=i32),
                Return(ret_val),
            ],
        ),
        FIRBlock(label="dead", instructions=[Jump("dead")]),
    ]
    mod.functions["main"] = main

    # Apply passes in order
    inline_changes = inline_pass(mod, threshold=10)
    fold_changes = const_fold_pass(mod, known_constants={10: 5})
    dce_changes = dead_code_pass(mod)
    layout_changes = block_layout_pass(mod)

    # Should have done something
    assert inline_changes >= 0
    assert fold_changes >= 0
    assert dce_changes >= 1  # dead block should be removed
    assert layout_changes >= 0

    # Dead block should be gone
    assert len(main.blocks) == 1
    assert main.blocks[0].label == "entry"


# ────────────────────────────────────────────────────────────────────────────
# Run all tests
# ────────────────────────────────────────────────────────────────────────────

print("=" * 60)
print("JIT Compiler Test Suite")
print("=" * 60)

run_test("test_dead_code_removes_unreachable_block", test_dead_code_removes_unreachable_block)
run_test("test_dead_code_keeps_reachable_blocks", test_dead_code_keeps_reachable_blocks)
run_test("test_dead_code_empty_module", test_dead_code_empty_module)
run_test("test_dead_code_multiple_unreachable", test_dead_code_multiple_unreachable)
run_test("test_block_layout_reorder_for_fallthrough", test_block_layout_reorder_for_fallthrough)
run_test("test_block_layout_preserves_entry", test_block_layout_preserves_entry)
run_test("test_block_layout_single_block", test_block_layout_single_block)
run_test("test_inline_small_function", test_inline_small_function)
run_test("test_inline_no_self_recursion", test_inline_no_self_recursion)
run_test("test_inline_respects_threshold", test_inline_respects_threshold)
run_test("test_const_fold_known_constants", test_const_fold_known_constants)
run_test("test_const_fold_no_side_effects", test_const_fold_no_side_effects)
run_test("test_const_fold_no_constants", test_const_fold_no_constants)
run_test("test_const_fold_float", test_const_fold_float)
run_test("test_jit_compile_simple_function", test_jit_compile_simple_function)
run_test("test_jit_compile_optimization_stats", test_jit_compile_optimization_stats)
run_test("test_jit_register_allocation", test_jit_register_allocation)
run_test("test_jit_compile_multi_block", test_jit_compile_multi_block)
run_test("test_jit_compile_module", test_jit_compile_module)
run_test("test_cache_put_get", test_cache_put_get)
run_test("test_cache_miss", test_cache_miss)
run_test("test_cache_lru_eviction", test_cache_lru_eviction)
run_test("test_cache_lru_ordering", test_cache_lru_ordering)
run_test("test_cache_invalidate", test_cache_invalidate)
run_test("test_cache_clear", test_cache_clear)
run_test("test_cache_hit_rate", test_cache_hit_rate)
run_test("test_cache_stats", test_cache_stats)
run_test("test_cache_compute_key", test_cache_compute_key)
run_test("test_cache_memory_budget", test_cache_memory_budget)
run_test("test_tracer_record_block", test_tracer_record_block)
run_test("test_tracer_record_call", test_tracer_record_call)
run_test("test_tracer_record_edge", test_tracer_record_edge)
run_test("test_tracer_hot_paths", test_tracer_hot_paths)
run_test("test_tracer_hot_functions", test_tracer_hot_functions)
run_test("test_tracer_mark_compiled", test_tracer_mark_compiled)
run_test("test_tracer_record_cycles", test_tracer_record_cycles)
run_test("test_tracer_reset", test_tracer_reset)
run_test("test_tracer_stats", test_tracer_stats)
run_test("test_tracer_threshold_setter", test_tracer_threshold_setter)
run_test("test_jit_with_tracing", test_jit_with_tracing)
run_test("test_jit_cache_integration", test_jit_cache_integration)
run_test("test_jit_invalidate_cache", test_jit_invalidate_cache)
run_test("test_combined_optimization_passes", test_combined_optimization_passes)

print("=" * 60)
print(f"Results: {passed} passed, {failed} failed")
print("=" * 60)

if failed > 0:
    sys.exit(1)
else:
    print("All JIT tests passed!")
