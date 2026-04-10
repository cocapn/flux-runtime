# FLUX Reverse Engineering Guide

A guide to analyzing existing code and mapping it to FLUX concepts: tiles, modules, agents, and the FIR intermediate representation.

---

## Introduction

Reverse engineering in the FLUX context means **analyzing existing source code and mapping its patterns, structures, and dependencies to FLUX's native abstractions**. Rather than rewriting from scratch, you identify what each piece of your code *does* at a semantic level and find the corresponding FLUX tile, module boundary, or agent pattern that matches.

This process is powered by `flux_analyze.py`, a tool that statically inspects Python and C source files, extracts their structural patterns, and generates a migration plan with concrete FLUX.MD output. The analyzer understands control flow, data transformations, concurrency patterns, error handling, and inter-module communication — then maps each to the appropriate FLUX tile from the built-in library.

The goal is not to blindly convert every line, but to find the highest-value mappings: where a Python `for` loop that iterates millions of times maps to a `loop_tile` that can be recompiled to C+SIMD; where a `multiprocessing.Pool` maps to an `a2a_scatter_tile` that enables agent-based parallelism; where a `@cache` decorator maps to a `MemoizeTile` that the evolution engine can optimize over time.

```bash
# Analyze a project and generate a FLUX migration plan
python -m flux.tools.flux_analyze ./my_project \
    --output ./analysis_output \
    --format json \
    --heatmap

# Output structure:
#   analysis_output/
#     summary.json          -- High-level statistics
#     call_graph.json       -- Module call graph
#     tile_mapping.json     -- Pattern → Tile mappings
#     heatmap.json          -- Estimated heat levels
#     FLUX.MD               -- Generated migration document
#     migration_plan.json   -- Step-by-step migration plan
```

---

## Pattern Recognition

The core of reverse engineering is recognizing common programming patterns and mapping them to FLUX tiles. Each pattern has a corresponding tile in the `TileType` taxonomy: COMPUTE, MEMORY, CONTROL, A2A, EFFECT, or TRANSFORM.

### Python Patterns → FLUX Tiles

| Python Pattern | FLUX Tile | TileType | Notes |
|---|---|---|---|
| `map(func, iterable)` | `map_tile` | COMPUTE | Element-wise transformation. FIR blueprint emits a `builder.call(fn, [data])` |
| `filter(predicate, iterable)` | `filter_tile` | COMPUTE | Keeps elements matching predicate |
| `functools.reduce(func, data, init)` | `reduce_tile` | COMPUTE | Folds sequence to single value |
| `itertools.accumulate` | `scan_tile` | COMPUTE | Prefix scan / cumulative operation |
| `zip(a, b)` | `zip_tile` | COMPUTE | Element-wise combination of two sequences |
| `[f(x) for x in data for ...]` | `flatmap_tile` | COMPUTE | Map then flatten |
| `sorted(data, key=cmp)` | `sort_tile` | COMPUTE | Cost estimate 5.0 — relatively expensive |
| `set(data)` / dedup | `unique_tile` | COMPUTE | Deduplication |
| `for i in range(n): ...` | `loop_tile` | CONTROL | Fixed-count iteration. Params: `count`, `body` |
| `while condition: ...` | `while_tile` | CONTROL | Condition-based loop. Params: `cond`, `body`, `max_iters` |
| `if/elif/else` | `branch_tile` | CONTROL | Conditional execution |
| `match/case` (3.10+) | `switch_tile` | CONTROL | Multi-way dispatch |
| `asyncio.gather(*coros)` | `ParallelTile` | CONTROL | N parallel tile instances |
| Loop fusion (adjacent loops, same range) | `fuse_tile` | CONTROL | Combines two loops into one |
| Software pipelining | `pipeline_tile` | CONTROL | Staged execution pipeline |
| `try/except` | `ErrorBoundaryTile` (custom) | EFFECT | Wrap computation with error recovery |
| `dataclass` | `StructTile` (custom) | TRANSFORM | Structured data with typed fields |
| `@functools.cache` / `@lru_cache` | `MemoizeTile` (custom) | MEMORY | Caches results keyed by inputs |
| `multiprocessing.Pool.map` | `a2a_scatter_tile` | A2A | Distribute work across agents |
| `generator yield` | `stream_tile` | MEMORY | Sequential read/write stream |
| `with open(...) as f:` | `ResourceTile` (custom) | EFFECT | Acquire/release resource lifecycle |
| `@decorator1 @decorator2` | `CompositeTile` | CONTROL | Chain of transformations |
| `dict[key] = value` | `scatter_tile` | MEMORY | Random-access write |
| `dict[key]` | `gather_tile` | MEMORY | Random-access read |
| `data.copy()` / `memcpy` | `copy_tile` | MEMORY | Bulk memory copy |
| `array[:] = value` | `fill_tile` | MEMORY | Fill memory region |
| `numpy.transpose(data)` | `transpose_tile` | MEMORY | Matrix transpose |
| `print(value)` | `print_effect_tile` | EFFECT | Output side effect |
| `logging.info(...)` | `log_effect_tile` | EFFECT | Logging side effect |
| `state.x = y` | `state_mut_tile` | EFFECT | State mutation (read-modify-write) |
| `int(value)` / `float(value)` | `cast_tile` | TRANSFORM | Type conversion |
| `numpy.reshape(data, shape)` | `reshape_tile` | TRANSFORM | Change data shape |
| `a + b` (bitwise pack) | `pack_tile` | TRANSFORM | Pack values into wider type |
| `struct.unpack(...)` | `unpack_tile` | TRANSFORM | Unpack wide type to components |
| `list(a) + list(b)` | `join_tile` | TRANSFORM | Concatenate streams |
| `[x for x in data if cond] else [y]` | `split_tile` | TRANSFORM | Partition by predicate |
| `agent.send(msg)` | `tell_tile` | A2A | Fire-and-forget message |
| `result = await agent.ask(msg)` | `ask_tile` | A2A | Request-response message |
| `broadcast(msg, all_agents)` | `broadcast_tile` | A2A | Fan-out to all agents |
| `gather_all(results)` | `a2a_reduce_tile` | A2A | Collect results from agents |
| `await asyncio.Barrier(n)` | `barrier_tile` | A2A | Synchronization point |

### C Patterns → FLUX Tiles

| C Pattern | FLUX Tile | TileType | Notes |
|---|---|---|---|
| `for (int i = 0; i < n; i++)` | `loop_tile` + `VectorizeTile` (custom) | CONTROL | Amenable to SIMD vectorization |
| `struct { int x; float y; }` | `StructTile` (custom) | TRANSFORM | Maps to FIR struct type |
| `void (*fn)(int)` (function pointer) | `CallbackTile` (custom) | CONTROL | First-class function reference |
| `#pragma omp parallel for` | `ParallelTile` | CONTROL | OMP parallel → FLUX parallel |
| `#pragma omp simd` | `VectorizeTile` (custom) | COMPUTE | SIMD intrinsics via C_SIMD language |
| `memcpy(dst, src, n)` | `copy_tile` | MEMORY | Direct mapping |
| `memset(dst, val, n)` | `fill_tile` | MEMORY | Direct mapping |
| `dst[i] = src[idx[i]]` | `gather_tile` | MEMORY | Indirect indexing read |
| `dst[idx[i]] = src[i]` | `scatter_tile` | MEMORY | Indirect indexing write |
| `if (cond) { ... } else { ... }` | `branch_tile` | CONTROL | Conditional |
| `switch (val) { case A: ... }` | `switch_tile` | CONTROL | Multi-way dispatch |
| `while (cond) { ... }` | `while_tile` | CONTROL | Condition loop |
| `printf(...)` | `print_effect_tile` | EFFECT | Output |
| `__attribute__((simd))` | `VectorizeTile` (custom) | COMPUTE | Compiler SIMD hint |

### Composite Pattern Mappings

Real code rarely has isolated patterns. Common composite patterns map to `CompositeTile` chains:

```python
# Python: map → filter → reduce (extremely common)
result = functools.reduce(
    sum,
    filter(lambda x: x > 0, map(lambda x: x * 2, data)),
    0
)

# FLUX: Composite tile chain
pipeline = map_tile.compose(filter_tile, {"result": "data"})
pipeline = pipeline.compose(reduce_tile, {"result": "data"})
# Cost: 1.0 + 1.5 + 2.0 = 4.5 (cheaper than running separately due to fusion potential)
```

```python
# Python: scatter → compute → gather (update-in-place pattern)
for i in range(n):
    old = data[key[i]]       # gather
    new = transform(old)     # compute
    data[key[i]] = new       # scatter

# FLUX: gather → branch → scatter composition
update_chain = gather_tile.compose(branch_tile, {"result": "base"})
update_chain = update_chain.compose(scatter_tile, {"result": "value"})
```

---

## Call Graph Analysis

Understanding the call graph of your existing code is essential for identifying FLUX module boundaries and agent responsibilities.

### Extracting the Call Graph

The `flux_analyze.py` tool extracts call relationships by statically parsing imports, function calls, and class instantiations:

```bash
python -m flux.tools.flux_analyze ./my_project --call-graph --format json
```

**Input code:**

```python
# app/handlers/users.py
from app.services.auth import verify_token
from app.services.database import query_user
from app.middleware.logging import log_request

def get_user(request):
    log_request(request)
    token = verify_token(request.headers["Authorization"])
    user = query_user(token.user_id)
    return user

def create_user(request):
    log_request(request)
    token = verify_token(request.headers["Authorization"])
    # ... create logic ...
```

**Generated call graph (`call_graph.json`):**

```json
{
  "nodes": [
    {"id": "app.handlers.users.get_user", "type": "function"},
    {"id": "app.handlers.users.create_user", "type": "function"},
    {"id": "app.services.auth.verify_token", "type": "function"},
    {"id": "app.services.database.query_user", "type": "function"},
    {"id": "app.middleware.logging.log_request", "type": "function"}
  ],
  "edges": [
    {"from": "app.handlers.users.get_user", "to": "app.middleware.logging.log_request"},
    {"from": "app.handlers.users.get_user", "to": "app.services.auth.verify_token"},
    {"from": "app.handlers.users.get_user", "to": "app.services.database.query_user"},
    {"from": "app.handlers.users.create_user", "to": "app.middleware.logging.log_request"},
    {"from": "app.handlers.users.create_user", "to": "app.services.auth.verify_token"}
  ],
  "metrics": {
    "total_nodes": 5,
    "total_edges": 5,
    "max_fan_in": 2,
    "max_fan_out": 3,
    "avg_fan_out": 2.0
  }
}
```

### Mapping to FLUX Module Hierarchy

The call graph directly informs the `ModuleContainer` hierarchy:

```python
from flux.modules.container import ModuleContainer
from flux.modules.granularity import Granularity

# Root = TRAIN level
root = ModuleContainer("app", Granularity.TRAIN)

# Top-level packages = CARRIAGE level
handlers = root.add_child("handlers", Granularity.CARRIAGE)
services = root.add_child("services", Granularity.CARRIAGE)
middleware = root.add_child("middleware", Granularity.CARRIAGE)

# Sub-packages = LUGGAGE level
auth = services.add_child("auth", Granularity.LUGGAGE)
database = services.add_child("database", Granularity.LUGGAGE)

# Files = BAG level
users_bag = handlers.add_child("users", Granularity.BAG)

# Functions = CARD level
users_bag.load_card("get_user", get_user_source, "python")
users_bag.load_card("create_user", create_user_source, "python")
auth.load_card("verify_token", verify_token_source, "python")
database.load_card("query_user", query_user_source, "python")
```

### Identifying Agent Boundaries

Not every module should become an agent. Good agent boundaries have these characteristics:

1. **High fan-in** — Many callers depend on this module (e.g., `verify_token` called by 20 handlers)
2. **Low fan-out** — The module has few dependencies of its own (self-contained)
3. **Clear responsibility** — Does one well-defined thing (Single Responsibility)
4. **Stateful** — Maintains its own state (connections, caches, sessions)
5. **Network boundary** — Communicates over a protocol (HTTP, gRPC, message queue)

```python
# Agent boundary analysis from call graph:
#
# GOOD agent candidates:
#   app.services.auth.verify_token  — fan_in=20, fan_out=2, stateful (token cache)
#   app.services.database.query_user — fan_in=15, fan_out=1, stateful (connection pool)
#
# POOR agent candidates:
#   app.middleware.logging.log_request — fan_in=50, but stateless (pure effect)
#   app.handlers.users.get_user — fan_in=1, fan_out=3 (too specific)
#
# Decision: Make auth and database agents. Keep handlers as simple functions
# that delegate to agents via A2A messages.
```

---

## Complexity Analysis

### Cyclomatic Complexity → Heat Level

Cyclomatic complexity (the number of independent paths through code) directly correlates with FLUX's heat classification. Higher complexity means more execution branches, more potential bottlenecks, and greater optimization opportunity.

The mapping uses a simple formula:

```
estimated_heat = f(cyclomatic_complexity, call_frequency)

Where:
  - CC < 5  and calls < 100/min  → COOL   (simple, infrequent)
  - CC < 5  and calls > 100/min  → WARM   (simple, frequent)
  - CC 5-10 and calls < 100/min  → WARM   (moderate complexity)
  - CC 5-10 and calls > 100/min  → HOT    (moderate, frequent)
  - CC > 10                     → HOT/HEAT (complex, always optimize)
```

**Examples with specific numbers:**

```python
# CC=1 (linear) — no branches
def simple_transform(x):
    return x * 2 + 1

# Estimated heat: COOL (if infrequent) or WARM (if frequent)

# CC=4 (moderate branching)
def process_user(user, action):
    if not user:
        return error("no user")
    if action == "create":
        return create(user)
    elif action == "update":
        return update(user)
    else:
        return error("unknown action")

# Estimated heat: WARM (typical handler)

# CC=12 (complex branching)
def route_request(request):
    if request.method == "GET":
        if request.path.startswith("/api/users"):
            if request.params.get("id"):
                return get_user(request.params["id"])
            elif request.params.get("name"):
                return search_users(request.params["name"])
            else:
                return list_users()
        elif request.path.startswith("/api/orders"):
            # ... more branches ...
        else:
            return static_response(request.path)
    elif request.method == "POST":
        if request.path == "/api/users":
            return create_user(request.body)
        elif request.path == "/api/orders":
            return create_order(request.body)
        else:
            return error("not found")
    else:
        return error("method not allowed")

# Estimated heat: HOT (if called frequently) or HEAT (if in request hot path)
# → Candidate for recompilation to TypeScript or C#
```

### Decision Tree for Language Recommendation

Based on complexity, call frequency, and reload patterns:

```
Is module called > 1000 times/minute?
├── YES: Is CC > 10?
│   ├── YES → HEAT → Recompile to C+SIMD (16x estimated speedup)
│   └── NO  → HOT  → Recompile to Rust (10x) or C# (4x)
└── NO:  Is module called > 100 times/minute?
    ├── YES: Is CC > 5?
    │   ├── YES → HOT  → Recompile to Rust (10x)
    │   └── NO  → WARM → Consider TypeScript (2x)
    └── NO:  Is module called > 10 times/minute?
        ├── YES: Is CC > 5?
        │   ├── YES → WARM → Consider TypeScript (2x)
        │   └── NO  → COOL → Keep in Python
        └── NO → COOL/FROZEN → Keep in Python (expressiveness > speed)

Special cases:
  - Module reloaded > 5 times/hour → Penalize slow-compile languages
  - Module has memory safety requirements → Prefer Rust over C
  - Module needs SIMD → Use C_SIMD language target
  - Module is pure computation with no side effects → Safe to recompile aggressively
```

### Complexity Analysis Example

Here's how the analyzer processes a real function:

```python
# Source: A data processing function
def process_records(records, config):
    results = []
    for record in records:                          # CC += 1 (loop)
        if record.get("valid", False):              # CC += 1 (branch)
            score = 0
            for field in config["fields"]:          # CC += 1 (nested loop)
                if field in record:                 # CC += 1 (nested branch)
                    score += record[field] * field["weight"]
                elif field.get("default") is not None:  # CC += 1 (elif)
                    score += field["default"]
            if score > config["threshold"]:         # CC += 1 (branch)
                record["score"] = score
                results.append(record)
    return results
# Total CC = 6

# Analyzer output:
# {
#   "function": "process_records",
#   "cyclomatic_complexity": 6,
#   "loop_count": 2,
#   "branch_count": 4,
#   "nesting_depth": 3,
#   "estimated_heat": "WARM",
#   "recommended_language": "typescript",
#   "tile_mapping": {
#     "outer_loop": "loop_tile",
#     "inner_loop": "loop_tile",
#     "if_valid": "branch_tile",
#     "if_field_in_record": "branch_tile",
#     "elif_default": "branch_tile",
#     "if_threshold": "branch_tile",
#     "score_accumulation": "reduce_tile",
#     "results_append": "stream_tile",
#     "full_pattern": "CompositeTile(loop → branch → loop → branch → reduce → branch → stream)"
#   },
#   "optimization_suggestions": [
#     "Fuse outer_loop + if_valid into single loop_tile with predicate param",
#     "Replace inner loop + branch chain with map_tile + filter_tile",
#     "Consider recompiling to TypeScript for 2x speedup on WARM path"
#   ]
# }
```

---

## Case Study: Analyzing flux-repo's Own Compiler Pipeline

To demonstrate reverse engineering in action, let's analyze FLUX's own `compiler/pipeline.py` — the `FluxCompiler` class that serves as the unified entry point for compilation.

### Source Code Under Analysis

```python
# src/flux/compiler/pipeline.py

class FluxCompiler:
    """Unified compilation pipeline for multiple source languages."""

    def __init__(self):
        self._encoder = BytecodeEncoder()

    def compile_c(self, source: str, module_name: str = "c_module") -> bytes:
        from flux.frontend.c_frontend import CFrontendCompiler
        compiler = CFrontendCompiler()
        module = compiler.compile(source, module_name=module_name)
        return self._encoder.encode(module)

    def compile_python(self, source: str, module_name: str = "py_module") -> bytes:
        from flux.frontend.python_frontend import PythonFrontendCompiler
        compiler = PythonFrontendCompiler()
        module = compiler.compile(source, module_name=module_name)
        return self._encoder.encode(module)

    def compile_md(self, source: str, module_name: str = "md_module") -> bytes:
        from flux.parser import FluxMDParser
        from flux.parser.nodes import NativeBlock
        parser = FluxMDParser()
        doc = parser.parse(source)
        code_blocks = []
        for child in doc.children:
            if isinstance(child, NativeBlock):
                lang = (child.lang or "").lower().strip()
                if lang in ("c", "python"):
                    code_blocks.append((lang, child.content))
        if not code_blocks:
            ctx = TypeContext()
            builder = FIRBuilder(ctx)
            module = builder.new_module(module_name)
            return self._encoder.encode(module)
        lang, content = code_blocks[0]
        if lang == "c":
            return self.compile_c(content, module_name=module_name)
        elif lang == "python":
            return self.compile_python(content, module_name=module_name)
        ctx = TypeContext()
        builder = FIRBuilder(ctx)
        module = builder.new_module(module_name)
        return self._encoder.encode(module)
```

### Running `flux_analyze.py`

```bash
python -m flux.tools.flux_analyze src/flux/compiler/pipeline.py \
    --output ./analysis/compiler_analysis \
    --format json \
    --verbose
```

### Analysis Output

```json
{
  "file": "src/flux/compiler/pipeline.py",
  "classes": [
    {
      "name": "FluxCompiler",
      "methods": [
        {
          "name": "__init__",
          "cyclomatic_complexity": 1,
          "tile_mapping": {
            "encoder_init": "state_mut_tile",
            "pattern": "EFFECT: Initialize encoder state"
          }
        },
        {
          "name": "compile_c",
          "cyclomatic_complexity": 1,
          "tile_mapping": {
            "import_compiler": "ResourceTile",
            "instantiate": "StructTile",
            "compile_source": "map_tile",
            "encode_result": "cast_tile",
            "pattern": "ResourceTile → StructTile → map_tile → cast_tile"
          },
          "estimated_heat": "WARM",
          "recommended_language": "python",
          "notes": "I/O bound compilation — keep expressive"
        },
        {
          "name": "compile_python",
          "cyclomatic_complexity": 1,
          "tile_mapping": {
            "import_compiler": "ResourceTile",
            "instantiate": "StructTile",
            "compile_source": "map_tile",
            "encode_result": "cast_tile",
            "pattern": "ResourceTile → StructTile → map_tile → cast_tile"
          },
          "estimated_heat": "WARM",
          "recommended_language": "python"
        },
        {
          "name": "compile_md",
          "cyclomatic_complexity": 7,
          "tile_mapping": {
            "import_parser": "ResourceTile",
            "parse_doc": "map_tile",
            "iterate_children": "loop_tile",
            "isinstance_check": "branch_tile",
            "lang_check": "branch_tile",
            "empty_check": "branch_tile",
            "build_empty_module": "StructTile",
            "encode": "cast_tile",
            "lang_dispatch": "switch_tile",
            "fallback": "branch_tile",
            "pattern": "CompositeTile(ResourceTile → map_tile → loop_tile → branch_tile → switch_tile → map_tile → cast_tile)"
          },
          "estimated_heat": "WARM",
          "recommended_language": "python",
          "optimization_suggestions": [
            "Replace isinstance chain with match/case for cleaner switch_tile",
            "Cache CFrontendCompiler and PythonFrontendCompiler instances (MemoizeTile)",
            "Consider restructuring lang dispatch as PipelineTile for extensibility"
          ]
        }
      ]
    }
  ],
  "dependencies": {
    "imports": [
      "flux.fir.blocks.FIRModule",
      "flux.fir.types.TypeContext",
      "flux.fir.values.Value",
      "flux.fir.builder.FIRBuilder",
      "flux.bytecode.encoder.BytecodeEncoder"
    ],
    "lazy_imports": [
      "flux.frontend.c_frontend.CFrontendCompiler",
      "flux.frontend.python_frontend.PythonFrontendCompiler",
      "flux.parser.FluxMDParser",
      "flux.parser.nodes.NativeBlock"
    ]
  },
  "summary": {
    "total_functions": 4,
    "avg_complexity": 2.5,
    "max_complexity": 7,
    "tile_types_used": ["EFFECT", "COMPUTE", "CONTROL", "MEMORY", "TRANSFORM"],
    "estimated_module_count": 5,
    "estimated_card_count": 4
  }
}
```

### How Each Function Maps to Tiles

Let's walk through `compile_md` in detail — the most complex function (CC=7):

```python
def compile_md(self, source: str, module_name: str = "md_module") -> bytes:
    # [1] ResourceTile: Lazy import and instantiate parser
    from flux.parser import FluxMDParser
    from flux.parser.nodes import NativeBlock
    parser = FluxMDParser()

    # [2] map_tile: Parse source → document (transformation)
    doc = parser.parse(source)

    # [3] loop_tile + filter_tile: Iterate and filter children
    code_blocks = []
    for child in doc.children:
        # [3a] branch_tile: isinstance check
        if isinstance(child, NativeBlock):
            # [3b] map_tile: Extract lang string
            lang = (child.lang or "").lower().strip()
            # [3c] branch_tile: Filter by supported languages
            if lang in ("c", "python"):
                code_blocks.append((lang, child.content))

    # [4] branch_tile: Empty check
    if not code_blocks:
        # [4a] StructTile: Build empty FIR module
        ctx = TypeContext()
        builder = FIRBuilder(ctx)
        module = builder.new_module(module_name)
        # [4b] cast_tile: Encode to bytecode
        return self._encoder.encode(module)

    # [5] switch_tile: Language dispatch
    lang, content = code_blocks[0]
    if lang == "c":
        # [5a] map_tile: Delegate to compile_c
        return self.compile_c(content, module_name=module_name)
    elif lang == "python":
        # [5b] map_tile: Delegate to compile_python
        return self.compile_python(content, module_name=module_name)

    # [6] branch_tile: Fallback (same as empty case)
    ctx = TypeContext()
    builder = FIRBuilder(ctx)
    module = builder.new_module(module_name)
    return self._encoder.encode(module)
```

**Full tile composition:**

```
ResourceTile(parse_setup)
  → map_tile(parse_source → doc)
  → CompositeTile(
      loop_tile(iterate children)
      → branch_tile(isinstance NativeBlock?)
      → map_tile(extract lang)
      → branch_tile(lang in supported?)
      → stream_tile(append to code_blocks)
    )
  → branch_tile(code_blocks empty?)
    ├── YES → StructTile(empty FIR) → cast_tile(encode)
    └── NO  → switch_tile(lang dispatch)
               ├── "c"      → map_tile(compile_c)
               ├── "python" → map_tile(compile_python)
               └── default  → StructTile(empty FIR) → cast_tile(encode)
```

### Generated FLUX.MD Output

The analyzer generates a FLUX.MD file that documents the module structure:

```markdown
# FLUX.MD — Compiler Pipeline Module

## Module: flux.compiler.pipeline

### Granularity: CARRIAGE
### Language: python
### Heat Estimate: WARM

---

## Cards (Functions)

### CARD: __init__
- **Complexity:** CC=1 (linear)
- **Tiles:** state_mut_tile (encoder initialization)
- **Heat:** FROZEN (constructor, called once)
- **Language:** python (keep expressive)

### CARD: compile_c
- **Complexity:** CC=1 (linear)
- **Tiles:** ResourceTile → StructTile → map_tile → cast_tile
- **Heat:** WARM (called per C module)
- **Language:** python (I/O bound compilation)
- **Dependencies:** CFrontendCompiler, BytecodeEncoder

### CARD: compile_python
- **Complexity:** CC=1 (linear)
- **Tiles:** ResourceTile → StructTile → map_tile → cast_tile
- **Heat:** WARM (called per Python module)
- **Language:** python (I/O bound compilation)
- **Dependencies:** PythonFrontendCompiler, BytecodeEncoder

### CARD: compile_md
- **Complexity:** CC=7 (moderate branching)
- **Tiles:** ResourceTile → map_tile → loop_tile → branch_tile → switch_tile → cast_tile
- **Heat:** WARM (called per FLUX.MD document)
- **Language:** python (complex logic, keep expressive)
- **Optimization opportunities:**
  - Cache compiler instances with MemoizeTile
  - Refactor lang dispatch to PipelineTile for extensibility
  - Deduplicate empty-module creation (DRY)

---

## Migration Plan

### Priority 1: No changes needed
This module is well-structured with clear boundaries and moderate complexity.
The compilation functions are I/O bound, so recompilation to faster languages
would provide minimal benefit.

### Priority 2: Consider MemoizeTile for compiler instances
```python
# Current: New compiler instance per call
compiler = CFrontendCompiler()

# Proposed: Cached instance
@cache
def get_c_compiler():
    return CFrontendCompiler()
```

### Priority 3: Evolution engine candidate
The `compile_md` function's switch_tile dispatch pattern could be
evolved by the EvolutionEngine to discover optimal dispatch strategies
for new languages as they're added.
```

### Migration Plan Summary

```json
{
  "migration_plan": {
    "phase": "wrap",
    "estimated_effort": "2 hours",
    "steps": [
      {
        "action": "create_container",
        "path": "flux.compiler",
        "granularity": "CARRIAGE"
      },
      {
        "action": "create_container",
        "path": "flux.compiler.pipeline",
        "granularity": "LUGGAGE"
      },
      {
        "action": "load_card",
        "path": "flux.compiler.pipeline.__init__",
        "source_file": "src/flux/compiler/pipeline.py",
        "language": "python",
        "estimated_heat": "FROZEN"
      },
      {
        "action": "load_card",
        "path": "flux.compiler.pipeline.compile_c",
        "source_file": "src/flux/compiler/pipeline.py",
        "language": "python",
        "estimated_heat": "WARM"
      },
      {
        "action": "load_card",
        "path": "flux.compiler.pipeline.compile_python",
        "source_file": "src/flux/compiler/pipeline.py",
        "language": "python",
        "estimated_heat": "WARM"
      },
      {
        "action": "load_card",
        "path": "flux.compiler.pipeline.compile_md",
        "source_file": "src/flux/compiler/pipeline.py",
        "language": "python",
        "estimated_heat": "WARM",
        "optimization_candidates": [
          "Apply MemoizeTile for compiler instance caching",
          "Refactor switch_tile to PipelineTile for extensibility"
        ]
      }
    ],
    "post_wrap": {
      "profile_for": "3 days",
      "expected_findings": "compile_md may become HOT if FLUX.MD compilation is frequent",
      "evolution_candidates": ["compile_md dispatch pattern"]
    }
  }
}
```

---

## Quick Reference: Pattern-to-Tile Cheat Sheet

### By Category

**COMPUTE tiles** — Pure data transformations:
- `map_tile` — Apply function to each element
- `reduce_tile` — Fold sequence to single value
- `filter_tile` — Keep matching elements
- `scan_tile` — Prefix cumulative operation
- `flatmap_tile` — Map then flatten
- `sort_tile` — Order elements
- `unique_tile` — Deduplicate

**MEMORY tiles** — Data access patterns:
- `gather_tile` — Random-access read
- `scatter_tile` — Random-access write
- `stream_tile` — Sequential I/O
- `copy_tile` — Bulk copy
- `fill_tile` — Fill region
- `transpose_tile` — Matrix transpose

**CONTROL tiles** — Flow and branching:
- `loop_tile` — Fixed-count iteration
- `while_tile` — Condition loop
- `branch_tile` — If/else
- `switch_tile` — Multi-way dispatch
- `fuse_tile` — Loop fusion
- `pipeline_tile` — Staged execution

**A2A tiles** — Agent communication:
- `tell_tile` — Fire-and-forget
- `ask_tile` — Request-response
- `broadcast_tile` — Fan-out
- `a2a_reduce_tile` — Collect results
- `a2a_scatter_tile` — Distribute work
- `barrier_tile` — Synchronization

**EFFECT tiles** — Side effects:
- `print_effect_tile` — Output
- `log_effect_tile` — Logging
- `state_mut_tile` — State mutation

**TRANSFORM tiles** — Data shape changes:
- `cast_tile` — Type conversion
- `reshape_tile` — Shape change
- `pack_tile` / `unpack_tile` — Width conversion
- `join_tile` — Concatenation
- `split_tile` — Partition

### Analysis Commands

```bash
# Full project analysis with all outputs
python -m flux.tools.flux_analyze ./my_project \
    --output ./analysis \
    --format json \
    --heatmap \
    --call-graph \
    --verbose

# Quick pattern scan (tile mappings only)
python -m flux.tools.flux_analyze ./my_project --scan-only

# Focus on specific files
python -m flux.tools.flux_analyze ./my_project/core/pipeline.py \
    --output ./pipeline_analysis

# Generate FLUX.MD directly
python -m flux.tools.flux_analyze ./my_project --generate-flux-md
```
