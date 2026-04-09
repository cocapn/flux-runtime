"""Frontend Compiler Tests — C and Python frontends + pipeline.

8 tests:
  test_c_add, test_c_if_else, test_c_while, test_c_multi_func
  test_py_add, test_py_if, test_py_for_range
  test_pipeline_c_to_bytecode
"""

import sys
import traceback

sys.path.insert(0, "src")

from flux.fir.types import TypeContext
from flux.fir.instructions import IAdd, ISub, IMul, Branch, Jump, Return
from flux.fir.blocks import FIRModule

from flux.frontend.c_frontend import CFrontendCompiler
from flux.frontend.python_frontend import PythonFrontendCompiler
from flux.compiler.pipeline import FluxCompiler


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


# ── Helper ──────────────────────────────────────────────────────────────────

def _collect_opcodes(module: FIRModule) -> list[str]:
    """Collect all instruction opcodes from all functions in a module."""
    opcodes: list[str] = []
    for func in module.functions.values():
        for block in func.blocks:
            for instr in block.instructions:
                opcodes.append(instr.opcode)
    return opcodes


# ────────────────────────────────────────────────────────────────────────────
# C Frontend Tests
# ────────────────────────────────────────────────────────────────────────────

def test_c_add():
    """C: int add(int a, int b) { return a + b; } → IAdd in FIR."""
    source = """
    int add(int a, int b) {
        return a + b;
    }
    """
    compiler = CFrontendCompiler()
    module = compiler.compile(source.strip())

    assert "add" in module.functions, "Function 'add' should exist in module"
    opcodes = _collect_opcodes(module)
    assert "iadd" in opcodes, f"Expected 'iadd' in opcodes, got: {opcodes}"
    assert "return" in opcodes, f"Expected 'return' in opcodes, got: {opcodes}"


def test_c_if_else():
    """C: if/else → Branch in FIR."""
    source = """
    int max(int a, int b) {
        if (a > b) {
            return a;
        } else {
            return b;
        }
    }
    """
    compiler = CFrontendCompiler()
    module = compiler.compile(source.strip())

    assert "max" in module.functions
    opcodes = _collect_opcodes(module)
    assert "branch" in opcodes, f"Expected 'branch' in opcodes, got: {opcodes}"
    # Should have at least 4 blocks: entry, then, else, merge
    func = module.functions["max"]
    assert len(func.blocks) >= 3, f"Expected >= 3 blocks, got {len(func.blocks)}"


def test_c_while():
    """C: while loop → Branch + Jump in FIR."""
    source = """
    int countdown(int n) {
        int sum = 0;
        while (n > 0) {
            sum = sum + n;
            n = n - 1;
        }
        return sum;
    }
    """
    compiler = CFrontendCompiler()
    module = compiler.compile(source.strip())

    assert "countdown" in module.functions
    opcodes = _collect_opcodes(module)
    assert "branch" in opcodes, f"Expected 'branch' in opcodes, got: {opcodes}"
    assert "jump" in opcodes, f"Expected 'jump' in opcodes, got: {opcodes}"
    assert "iadd" in opcodes, f"Expected 'iadd' in opcodes, got: {opcodes}"
    assert "isub" in opcodes, f"Expected 'isub' in opcodes, got: {opcodes}"
    func = module.functions["countdown"]
    assert len(func.blocks) >= 3, f"Expected >= 3 blocks, got {len(func.blocks)}"


def test_c_multi_func():
    """C: multiple functions in one source file."""
    source = """
    int square(int x) {
        return x * x;
    }
    int cube(int x) {
        return x * x * x;
    }
    """
    compiler = CFrontendCompiler()
    module = compiler.compile(source.strip())

    assert len(module.functions) >= 2, (
        f"Expected >= 2 functions, got {len(module.functions)}"
    )
    assert "square" in module.functions
    assert "cube" in module.functions
    opcodes = _collect_opcodes(module)
    assert "imul" in opcodes, f"Expected 'imul' in opcodes, got: {opcodes}"


# ────────────────────────────────────────────────────────────────────────────
# Python Frontend Tests
# ────────────────────────────────────────────────────────────────────────────

def test_py_add():
    """Python: def add(a, b): return a + b → IAdd in FIR."""
    source = """
def add(a, b):
    return a + b
"""
    compiler = PythonFrontendCompiler()
    module = compiler.compile(source.strip())

    assert "add" in module.functions, "Function 'add' should exist"
    opcodes = _collect_opcodes(module)
    assert "iadd" in opcodes, f"Expected 'iadd' in opcodes, got: {opcodes}"
    assert "return" in opcodes, f"Expected 'return' in opcodes, got: {opcodes}"


def test_py_if():
    """Python: if/else → Branch in FIR."""
    source = """
def abs_val(x):
    if x < 0:
        return -x
    else:
        return x
"""
    compiler = PythonFrontendCompiler()
    module = compiler.compile(source.strip())

    assert "abs_val" in module.functions
    opcodes = _collect_opcodes(module)
    assert "branch" in opcodes, f"Expected 'branch' in opcodes, got: {opcodes}"
    assert "ineg" in opcodes, f"Expected 'ineg' in opcodes, got: {opcodes}"
    func = module.functions["abs_val"]
    assert len(func.blocks) >= 3, f"Expected >= 3 blocks, got {len(func.blocks)}"


def test_py_for_range():
    """Python: for i in range(n) → while-like structure with Branch + Jump."""
    source = """
def sum_n(n):
    s = 0
    for i in range(n):
        s = s + i
    return s
"""
    compiler = PythonFrontendCompiler()
    module = compiler.compile(source.strip())

    assert "sum_n" in module.functions
    opcodes = _collect_opcodes(module)
    assert "branch" in opcodes, f"Expected 'branch' in opcodes, got: {opcodes}"
    assert "jump" in opcodes, f"Expected 'jump' in opcodes, got: {opcodes}"
    assert "iadd" in opcodes, f"Expected 'iadd' in opcodes, got: {opcodes}"
    func = module.functions["sum_n"]
    assert len(func.blocks) >= 3, f"Expected >= 3 blocks, got {len(func.blocks)}"


# ────────────────────────────────────────────────────────────────────────────
# Pipeline Test
# ────────────────────────────────────────────────────────────────────────────

def test_pipeline_c_to_bytecode():
    """Pipeline: compile C source → bytes starting with FLUX magic."""
    source = """
    int add(int a, int b) {
        return a + b;
    }
    """
    compiler = FluxCompiler()
    bytecode = compiler.compile_c(source.strip())

    assert isinstance(bytecode, bytes), "Result should be bytes"
    assert len(bytecode) >= 16, f"Bytecode should be >= 16 bytes, got {len(bytecode)}"
    assert bytecode[:4] == b"FLUX", (
        f"Bytecode should start with FLUX magic, got: {bytecode[:4]!r}"
    )


# ────────────────────────────────────────────────────────────────────────────
# Run all tests
# ────────────────────────────────────────────────────────────────────────────

print("=" * 60)
print("Frontend Compiler Test Suite")
print("=" * 60)

run_test("test_c_add", test_c_add)
run_test("test_c_if_else", test_c_if_else)
run_test("test_c_while", test_c_while)
run_test("test_c_multi_func", test_c_multi_func)
run_test("test_py_add", test_py_add)
run_test("test_py_if", test_py_if)
run_test("test_py_for_range", test_py_for_range)
run_test("test_pipeline_c_to_bytecode", test_pipeline_c_to_bytecode)

print("=" * 60)
print(f"Results: {passed} passed, {failed} failed")
print("=" * 60)

if failed > 0:
    sys.exit(1)
else:
    print("All frontend tests passed!")
