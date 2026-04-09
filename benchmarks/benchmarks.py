"""FLUX benchmark suite — performance and correctness metrics."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from flux.bytecode.opcodes import Op
from flux.vm.interpreter import Interpreter
from flux.compiler.pipeline import FluxCompiler


def _make_bytecode(program: list[tuple]) -> bytes:
    """Helper to build bytecode from instruction tuples."""
    buf = bytearray()
    for item in program:
        if isinstance(item, int):
            buf.append(item)
        elif isinstance(item, (bytes, bytearray)):
            buf.extend(item)
    return bytes(buf)


def benchmark_vm_throughput(instructions_per_iter: int = 3, iterations: int = 100000) -> dict:
    """Measure raw VM instruction throughput."""
    loop = [
        Op.INC, 0x00, Op.DEC, 0x00, Op.JNZ, 0x00, 0xFA, 0xFF, Op.HALT,
    ]
    program = [Op.MOVI, 0x00, iterations & 0xFF, (iterations >> 8) & 0xFF] + loop
    bytecode = _make_bytecode(program)
    vm = Interpreter(bytecode, max_cycles=iterations * 4 + 100)
    start = time.perf_counter_ns()
    cycles = vm.execute()
    elapsed = time.perf_counter_ns() - start
    ops = iterations * instructions_per_iter
    return {
        "name": "vm_loop_throughput",
        "iterations": iterations, "total_cycles": cycles,
        "elapsed_ns": elapsed, "ops_per_sec": ops / (elapsed / 1e9) if elapsed > 0 else 0,
        "ops_per_sec_millions": ops / (elapsed / 1e9) / 1e6 if elapsed > 0 else 0,
    }


def benchmark_arithmetic(iterations: int = 1000000) -> dict:
    ops = [Op.IADD, 0, 1, 2, Op.IADD, 0, 1, 3, Op.IADD, 0, 1, 4, Op.HALT]
    bytecode = _make_bytecode(ops)
    vm = Interpreter(bytecode)
    vm.regs.write_gp(1, 10); vm.regs.write_gp(2, 20)
    vm.regs.write_gp(3, 30); vm.regs.write_gp(4, 40)
    start = time.perf_counter_ns()
    for _ in range(iterations):
        vm.reset(); vm.execute()
    elapsed = time.perf_counter_ns() - start
    return {
        "name": "arithmetic_1M", "iterations": iterations,
        "elapsed_ns": elapsed, "ns_per_iter": elapsed / iterations,
        "ops_per_sec": iterations * 3 / (elapsed / 1e9) if elapsed > 0 else 0,
    }


def benchmark_compile_c(iterations: int = 100) -> dict:
    source = "int add(int a, int b) { return a + b; } int main() { return add(100, 200); }\n" * 50
    compiler = FluxCompiler()
    start = time.perf_counter_ns()
    for _ in range(iterations):
        compiler.compile_c(source)
    elapsed = time.perf_counter_ns() - start
    return {"name": "compile_c_50x", "elapsed_ns": elapsed, "ns_per_compile": elapsed / iterations}


def benchmark_compile_py(iterations: int = 100) -> dict:
    source = "def add(a, b): return a + b\ndef main(): return add(100, 200)\n" * 50
    compiler = FluxCompiler()
    start = time.perf_counter_ns()
    for _ in range(iterations):
        compiler.compile_python(source)
    elapsed = time.perf_counter_ns() - start
    return {"name": "compile_py_50x", "elapsed_ns": elapsed, "ns_per_compile": elapsed / iterations}


def benchmark_e2e(iterations: int = 10000) -> dict:
    source = "int add(int a, int b) { return a + b; } int main() { return add(100, 200); }\n"
    compiler = FluxCompiler()
    start = time.perf_counter_ns()
    for _ in range(iterations):
        bytecode = compiler.compile_c(source)
    ct = time.perf_counter_ns() - start
    vm = Interpreter(bytecode)
    start = time.perf_counter_ns()
    for _ in range(iterations):
        vm.reset(); vm.execute()
    et = time.perf_counter_ns() - start
    return {
        "name": "e2e_10k", "compile_ns_total": ct, "compile_ns_per": ct / iterations,
        "exec_ns_total": et, "exec_ns_per": et / iterations, "bytecode_size": len(bytecode),
    }


def run_all() -> list[dict]:
    print("FLUX Benchmark Suite")
    results = []
    for bench in [benchmark_vm_throughput, benchmark_arithmetic, benchmark_compile_c, benchmark_compile_py, benchmark_e2e]:
        try:
            r = bench()
            results.append(r)
            n = r["name"]
            if "ops_per_sec_millions" in r:
                print(f"  {n}: {r['ops_per_sec_millions']:.2f} M ops/sec")
            elif "ns_per_compile" in r:
                print(f"  {n}: {r['ns_per_compile']:.0f} ns/compile")
            elif "ns_per_iter" in r:
                print(f"  {n}: {r['ns_per_iter']:.0f} ns/iter")
            elif "exec_ns_per" in r:
                print(f"  {n}: compile={r['compile_ns_per']:.0f}ns exec={r['exec_ns_per']:.0f}ns bytecode={r['bytecode_size']}B")
        except Exception as e:
            results.append({"name": bench.__name__, "error": str(e)})
            print(f"  {bench.__name__}: ERROR - {e}")
    return results


if __name__ == "__main__":
    run_all()
