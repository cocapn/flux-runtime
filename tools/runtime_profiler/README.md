# FLUX Runtime Profiler

Performance profiling and benchmarking tools for the FLUX bytecode virtual machine. Provides opcode-level instrumentation, memory profiling, hot-path detection, visual reports, and a comprehensive benchmark suite.

## Quick Start

```bash
# Profile a bytecode file
python -m tools.runtime_profiler.profiler profile program.bin --mode full -o results/profile

# Run the built-in benchmark suite
python -m tools.runtime_profiler.benchmark_runner -n 10 -o results/benchmarks

# Visualize a profile report
python -m tools.runtime_profiler.profile_visualizer view results/profile.json

# Compare two profiles
python -m tools.runtime_profiler.profile_visualizer compare before.json after.json

# Quick inline profile
python -m tools.runtime_profiler.profiler quick --cycles 100000
```

## Architecture

```
tools/runtime-profiler/
  profiler.py             # Core profiling engine (opcode/function/memory instrumentation)
  profile_visualizer.py   # Visual reports (bar charts, flame graphs, comparisons)
  benchmark_runner.py     # Standard benchmark suite with statistical analysis
  README.md               # This file
```

## Profiling Modes

The profiler supports four modes, selectable via `--mode`:

| Mode | Description | What It Tracks |
|------|-------------|----------------|
| `opcode` | Per-opcode statistics | Execution count, cumulative time, avg/min/max time, hot PCs |
| `function` | Call-graph analysis | Call count, inclusive/exclusive time, call depth |
| `memory` | Memory profiling | Per-opcode allocation/deallocation, stack/heap snapshots, RSS |
| `full` | All of the above | Combined opcode + function + memory profiling |

## Profiling Any FLUX Program

### From a Bytecode File

```bash
# Basic opcode-level profiling
python -m tools.runtime_profiler.profiler profile my_program.bin

# Full profiling with custom settings
python -m tools.runtime_profiler.profiler profile my_program.bin \
  --mode full \
  --top-n 25 \
  --sample-interval 500 \
  --max-cycles 50000000 \
  -o profiles/my_program

# Run multiple iterations and keep the best result
python -m tools.runtime_profiler.profiler profile my_program.bin \
  --iterations 10 \
  --mode full \
  -o profiles/my_program_best
```

### From Python Code

```python
from flux.bytecode.opcodes import Op
from tools.runtime_profiler.profiler import FluxProfiler

# Build your bytecode
bytecode = bytes([
    Op.MOVI, 0x01, 100, 0,   # R1 = 100
    Op.MOVI, 0x00, 0, 0,     # R0 = 0
    Op.IADD, 0x00, 0x00, 0x01,  # R0 += R1
    Op.DEC, 0x01,            # R1--
    Op.JNZ, 0x01, -7, 255,   # if R1 != 0, goto loop (patch offset)
    Op.HALT,
])

# Profile it
profiler = FluxProfiler(mode="full", sample_interval=100)
result = profiler.profile_bytecode(bytecode, program_name="sum_loop")

# Export results
profiler.export_json("profile.json", result)
profiler.export_markdown("profile.md", result)

# Access data programmatically
print(f"Total instructions: {result.total_instructions:,}")
print(f"Total time: {result.total_time_ns / 1e6:.2f} ms")

# Top time-consuming opcodes
for name, stats in sorted(
    result.opcode_stats.items(),
    key=lambda x: x[1].total_time_ns,
    reverse=True,
)[:5]:
    print(f"  {name}: {stats.execution_count:,} executions, "
          f"{stats.pct_total_time:.1f}% of time")
```

## Running Benchmarks

### All Benchmarks

```bash
# Run all benchmarks with 10 statistical iterations
python -m tools.runtime_profiler.benchmark_runner -n 10 -o results/full_run

# Verbose output with detailed statistics
python -m tools.runtime_profiler.benchmark_runner -n 10 -v

# List available benchmarks
python -m tools.runtime_profiler.benchmark_runner --list
```

### Specific Benchmarks

```bash
# Run only compute benchmarks
python -m tools.runtime_profiler.benchmark_runner -n 5 \
  -b fibonacci_iterative fibonacci_recursive arithmetic_heavy_50k matrix_multiply_8x8
```

### From Python Code

```python
from tools.runtime_profiler.benchmark_runner import BenchmarkRunner

runner = BenchmarkRunner()

# Run all benchmarks
results = runner.run_all(iterations=10)
runner.print_results(results, verbose=True)

# Run specific benchmarks
results = runner.run_all(
    iterations=10,
    benchmark_names=["fibonacci_iterative", "matrix_multiply_8x8"],
)

# Export
runner.export_json("benchmarks.json", results)
runner.export_markdown("benchmarks.md", results)

# Compare with another runtime
other_runtime_times = {
    "fibonacci_iterative": 45000,     # ns
    "matrix_multiply_8x8": 120000,    # ns
}
comparison = runner.compare_with_runtime("C_Runtime", other_runtime_times, results)
print(comparison)
```

## Benchmark Suite

| Benchmark | Description | Category |
|-----------|-------------|----------|
| `fibonacci_iterative` | Iterative Fibonacci (fib(25)) | compute |
| `fibonacci_recursive` | Recursive Fibonacci simulation (depth 15) | compute |
| `matrix_multiply_8x8` | 8x8 matrix multiplication | compute |
| `bubble_sort_32` | Bubble sort on 32 elements | algorithm |
| `tree_traversal_d10` | Binary tree traversal (depth 10) | data_structure |
| `string_processing_64` | String copy/length/compare (64 chars) | string |
| `arithmetic_heavy_50k` | Mixed integer arithmetic (50K iterations) | compute |
| `control_flow_30k` | Switch dispatch + nested conditionals (30K) | control_flow |
| `memory_intensive_20k` | Heavy push/pop operations (20K) | memory |

## Visualizing Profiles

### View a Full Report

```bash
python -m tools.runtime_profiler.profile_visualizer view profile.json --top-n 20
```

This displays:
- Summary with key metrics (cycles, instructions, throughput, peak memory)
- ASCII bar chart of execution counts by opcode
- ASCII bar chart of cumulative time by opcode
- Category breakdown (control flow, arithmetic, memory, etc.)
- Text-based flame graph
- Top-N tables (most executed, most time-consuming)
- Memory profile (allocations/deallocations per opcode)
- Hot path analysis

### Compare Two Profiles

```bash
python -m tools.runtime_profiler.profile_visualizer compare before.json after.json
```

Shows side-by-side comparison of:
- Summary metrics with delta and percentage change
- Per-opcode execution count and time changes
- Color-coded improvements (green) and regressions (red)

### Trend Analysis

```bash
# Analyze performance across multiple runs
python -m tools.runtime_profiler.profile_visualizer trend \
  run1.json run2.json run3.json run4.json run5.json \
  --metric total_time_ns
```

Shows:
- Overall metric trend (time, cycles, memory) across runs
- Per-opcode trends with direction arrows
- Highlights improving and regressing opcodes

## Interpreting Results

### Profile Reports

The Markdown report contains these sections:

1. **Summary** — High-level metrics: total cycles, instructions, wall time, throughput
2. **Top N Most Executed** — Which opcodes run most frequently
3. **Top N Time-Consuming** — Which opcodes consume the most CPU time
4. **Hot Path Analysis** — Opcodes that appear most in repeating sequences
5. **Category Breakdown** — Time/instruction distribution across categories
6. **Memory Profile** — Per-opcode memory allocation patterns
7. **Function Profile** — Call graph with inclusive/exclusive timing
8. **Recommendations** — Auto-generated optimization suggestions

### Benchmark Results

- **Mean/Median** — Use median for reported numbers; mean can be skewed by outliers
- **StdDev** — Lower is better; high variance may indicate system noise
- **P95/P99** — 95th/99th percentile; important for latency-sensitive workloads
- **Outliers** — Detected via IQR method; high outlier count suggests system instability
- **Throughput** — Instructions/second; the primary performance indicator
- **ns/instruction** — Lower is better; the inverse of throughput

### Common Optimization Patterns

| Observation | Recommendation |
|-------------|---------------|
| High comparison ratio (>30%) | Restructure control flow to reduce redundant comparisons |
| High memory operation ratio (>40%) | Improve register allocation to reduce loads/stores |
| Excessive NOP instructions (>5%) | Remove padding from compiled bytecode |
| Deep call stack (>50) | Convert recursion to iteration |
| Heavy boxing (>10% BOX ops) | Use unboxed arithmetic where possible |
| No SIMD usage | Consider VADD/VSUB/VMUL for data-parallel workloads |

## Integration with Conformance Runner

The profiler can be integrated into the conformance test workflow:

```python
# In your conformance test setup
from tools.runtime_profiler.profiler import FluxProfiler
from tools.runtime_profiler.benchmark_runner import BenchmarkRunner

def run_conformance_with_profiling(test_vectors):
    profiler = FluxProfiler(mode="opcode")

    for name, bytecode, expected in test_vectors:
        result = profiler.profile_bytecode(bytecode, program_name=name)

        # Verify correctness
        assert result.halted, f"{name}: did not halt"

        # Check performance bounds
        if result.total_time_ns > 1_000_000_000:  # 1 second
            print(f"WARNING: {name} took {result.total_time_ns / 1e6:.0f}ms")

    # Generate aggregate report
    profiler.export_markdown("conformance_profile.md")
```

### CI Integration

```bash
# In CI, run benchmarks and compare with baseline
python -m tools.runtime_profiler.benchmark_runner -n 5 -o ci_results/run_$(date +%Y%m%d)

# Compare with baseline
python -m tools.runtime_profiler.profile_visualizer compare \
  ci_baseline.json ci_results/run_20260101.json
```

## Output Formats

### JSON (machine-readable)

```json
{
  "metadata": {
    "mode": "full",
    "total_cycles": 1234567,
    "total_time_ns": 45678900,
    "total_instructions": 1234567
  },
  "opcode_stats": {
    "IADD": {
      "execution_count": 500000,
      "total_time_ns": 15000000,
      "avg_time_ns": 30.0,
      "category": "integer_arithmetic"
    }
  },
  "hot_path": [
    {"opcode": "IADD", "count": 50000},
    {"opcode": "CMP", "count": 49000}
  ]
}
```

### Markdown (human-readable)

The Markdown report includes formatted tables, ASCII bar charts, and analysis sections suitable for documentation and code review.

## File Reference

| File | Lines | Purpose |
|------|-------|---------|
| `profiler.py` | 800+ | Core profiling engine: `ProfilingInterpreter`, `FluxProfiler`, `ProfileResult` |
| `profile_visualizer.py` | 400+ | Visual reports: bar charts, flame graphs, comparisons, trends |
| `benchmark_runner.py` | 500+ | Benchmark suite: 9 benchmarks, statistical analysis, export |
| `README.md` | 120+ | Documentation and usage guide |
