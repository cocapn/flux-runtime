# FLUX Migration Guide

A practical, step-by-step guide for bringing existing projects into the FLUX polyglot runtime.

---

## Introduction

### Why Migrate to FLUX?

Most software systems start in a single language. A Python web API, a C data pipeline, a Rust game engine — each begins life as a monolingual codebase. Over time, performance bottlenecks emerge, new languages gain traction, and teams find themselves torn between two bad options: accept the performance ceiling of their current language, or rewrite entire systems in a faster one at enormous cost.

FLUX eliminates this false dichotomy. It provides a **polyglot optimization runtime** where every module in your system can live in the language that best suits its purpose. A configuration parser stays in Python for maximum expressiveness. A hot inner loop compiles to C+SIMD for raw throughput. A data transformation pipeline runs in Rust for safety and speed. All of these modules coexist in a single system, communicate through a shared FIR (FLUX Intermediate Representation), and can be hot-reloaded independently.

**Adaptive execution** means FLUX doesn't require you to make these language decisions upfront. The `AdaptiveProfiler` monitors your running system, classifies every module by execution heat (FROZEN, COOL, WARM, HOT, HEAT), and the `AdaptiveSelector` recommends the optimal target language based on real profiling data — not guesswork. The `CompilerBridge` then recompiles modules between languages via FIR, the universal intermediate representation that serves as the bridge between any source and any target.

**Agent-first architecture** goes further. FLUX treats modules not just as code, but as agents that can communicate via A2A (Agent-to-Agent) messages, establish trust relationships through the INCREMENTS+2 trust engine, delegate tasks, and evolve over time. The `EvolutionEngine` captures genome snapshots, mines execution patterns, proposes mutations, validates correctness, and commits improvements — a system that literally builds a better version of itself.

### Who Should Migrate?

- **Teams with performance bottlenecks** — If you have Python code that's too slow but too complex to rewrite, FLUX can surgically recompile only the hot paths while keeping everything else in Python.
- **Multi-language codebases** — If you're already using Python + C + Rust but fighting with FFI boundaries, FLUX gives you a unified compilation and execution model.
- **Agent and microservice systems** — If you're building distributed agents or microservices that need trust, delegation, and self-optimization, FLUX's A2A layer and evolution engine provide first-class support.
- **Teams that want to evolve, not rewrite** — FLUX's phased migration lets you wrap existing code first, then profile, optimize, agentify, and evolve incrementally.

### What FLUX Gives You That Standard Runtimes Don't

| Feature | Standard Runtime | FLUX |
|---|---|---|
| Polyglot execution | FFI / bindings | Native multi-language via FIR |
| Adaptive profiling | External tools | Built-in `AdaptiveProfiler` |
| Language recommendation | Manual | `AdaptiveSelector` with heat classification |
| Cross-language compilation | N/A | `CompilerBridge` (source → FIR → bytecode) |
| Hot reload | Partial (Python) | Fractal hot-reload at CARD granularity |
| Agent communication | External (HTTP/gRPC) | Built-in A2A binary messages |
| Trust management | N/A | INCREMENTS+2 trust engine |
| Self-evolution | N/A | `EvolutionEngine` with mutation + validation |

---

## Phase 1: Wrap (Day 1)

The first step is to **wrap** your existing code as FLUX modules. You don't need to rewrite anything yet — just give FLUX a handle on each module so it can profile and optimize it later.

### Understanding FLUX Modules

FLUX organizes code into a fractal hierarchy of `ModuleContainer` and `ModuleCard` objects:

```
TRAIN → CARRIAGE → LUGGAGE → BAG → POCKET → WALLET → SLOT → [CARDs]
```

A `ModuleCard` is the atomic hot-reloadable unit. It holds source code in a specific language and caches compiled artifacts. Each card is identified by a dot-separated path like `api.handlers.users`.

### Wrapping a FastAPI App

Here's how to wrap an existing FastAPI handler as a FLUX module:

```python
# BEFORE: Standard FastAPI handler
# app/handlers/users.py

from fastapi import FastAPI

app = FastAPI()

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    # Simulate DB lookup
    users = {1: "Alice", 2: "Bob", 3: "Charlie"}
    return {"user_id": user_id, "name": users.get(user_id, "Unknown")}

@app.post("/users")
async def create_user(name: str):
    return {"name": name, "created": True}
```

```python
# AFTER: Wrapped as FLUX modules
# flux_app.py

from flux.modules.card import ModuleCard
from flux.modules.container import ModuleContainer
from flux.modules.granularity import Granularity
from flux.compiler.pipeline import FluxCompiler

# Create the module hierarchy
root = ModuleContainer("my_app", Granularity.TRAIN)

# Create a CARRIAGE for the API layer
api_carriage = root.add_child("api", Granularity.CARRIAGE)

# Create a LUGGAGE for handlers
handlers_luggage = api_carriage.add_child("handlers", Granularity.LUGGAGE)

# Load each handler as a CARD
users_handler_source = """
from fastapi import FastAPI

app = FastAPI()

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    users = {1: "Alice", 2: "Bob", 3: "Charlie"}
    return {"user_id": user_id, "name": users.get(user_id, "Unknown")}

@app.post("/users")
async def create_user(name: str):
    return {"name": name, "created": True}
"""

handlers_luggage.load_card(
    name="users",
    source=users_handler_source,
    language="python",
)

print(f"Module tree: {root.path}")
print(f"Cards loaded: {list(root.cards.keys())}")

# Print the tree structure
import json
print(json.dumps(root.to_dict(), indent=2))
```

### Using `flux_migrate.py` to Auto-Generate Wrappers

For larger projects, use the migration tool to automatically wrap modules:

```bash
# Analyze a Python project and generate FLUX wrappers
python -m flux.tools.flux_migrate ./my_project --output ./flux_modules

# The tool creates:
#   flux_modules/
#     FLUX.MD            -- Module documentation
#     api/
#       handlers/
#         users.flux     -- Wrapped user handler
#       middleware/
#         auth.flux      -- Wrapped auth middleware
#     services/
#       database.flux    -- Wrapped DB layer
#     models/
#       user.flux        -- Wrapped data models
```

### Loading Modules into the Synthesizer

Once wrapped, load modules into `FluxSynthesizer` for unified management:

```python
from flux.synthesis.synthesizer import FluxSynthesizer

synth = FluxSynthesizer()

# Register each module container
synth.register_container(root)

# Or load from FLUX.MD documentation files
synth.load_from_md("flux_modules/FLUX.MD")

# The synthesizer now knows about all modules and can:
# - Profile them with AdaptiveProfiler
# - Recommend languages with AdaptiveSelector
# - Recompile hot paths with CompilerBridge
```

### What to Wrap

Start with your **module boundaries** — the natural separation points in your code:

1. **API handlers** — each endpoint or handler group
2. **Service layer** — business logic modules
3. **Data access** — database queries, ORM operations
4. **Utility functions** — shared helpers and transforms
5. **Configuration** — settings, feature flags
6. **Middleware** — auth, logging, rate limiting

Don't try to be granular on Day 1. Wrap at the file or class level. You'll refine the granularity in Phase 2 based on profiling data.

---

## Phase 2: Profile (Day 2-3)

With modules wrapped, the next step is to **profile** your workload under realistic conditions. The `AdaptiveProfiler` classifies every module by execution heat.

### Running the Adaptive Profiler

```python
from flux.adaptive.profiler import AdaptiveProfiler, HeatLevel

profiler = AdaptiveProfiler(
    hot_threshold=0.8,   # Top 20% = HEAT
    warm_threshold=0.5,   # Top 50% = HOT
)

# Wrap your workload functions with profiler hooks
def run_api_workload():
    # Simulate typical API traffic
    for i in range(1000):
        handle = profiler.start_sample("api.handlers.users.get_user")
        # ... actual handler logic ...
        profiler.end_sample(handle)

    for i in range(500):
        handle = profiler.start_sample("api.handlers.users.create_user")
        # ... actual handler logic ...
        profiler.end_sample(handle)

    for i in range(200):
        handle = profiler.start_sample("api.middleware.auth.verify_token")
        # ... actual middleware logic ...
        profiler.end_sample(handle)

    for i in range(5000):
        handle = profiler.start_sample("services.database.query")
        # ... actual DB logic ...
        profiler.end_sample(handle)

# Run the workload
run_api_workload()

# Get the heatmap
heatmap = profiler.get_heatmap()

# Pretty-print the results
print("=" * 60)
print("HEATMAP — Module Execution Classification")
print("=" * 60)
for mod, heat in sorted(heatmap.items(), key=lambda x: x[1].value, reverse=True):
    bar = {"HEAT": "████████████", "HOT": "████████░░░",
           "WARM": "████░░░░░░░", "COOL": "██░░░░░░░░░",
           "FROZEN": "░░░░░░░░░░░"}
    print(f"  {mod:45s} {heat.name:6s} {bar.get(heat.name, '')}")
```

**Output:**

```
============================================================
HEATMAP — Module Execution Classification
============================================================
  services.database.query                       HEAT   ████████████
  api.middleware.auth.verify_token               HOT    ████████░░░
  api.handlers.users.get_user                   WARM   ████░░░░░░░
  api.handlers.users.create_user                COOL   ██░░░░░░░░░
```

### Understanding Heat Levels

The profiler classifies modules using percentile-based thresholds:

| Heat Level | Percentile | Meaning | Recommended Action |
|---|---|---|---|
| **HEAT** | Top 20% | Critical bottleneck | Recompile to C+SIMD (16x speedup) |
| **HOT** | Next 30% | Frequently called | Recompile to Rust (10x) or C# (4x) |
| **WARM** | Next 30% | Moderate activity | Consider TypeScript (2x) |
| **COOL** | Bottom 20% | Rarely called | Keep in Python |
| **FROZEN** | Never called | Dead code | Consider removal |

### Getting the Bottleneck Report

```python
report = profiler.get_bottleneck_report(top_n=5)

print(f"\nTotal modules profiled: {report.total_modules}")
print(f"Total samples: {report.total_samples}")
print(f"Total time: {report.total_time_ns / 1e9:.3f}s\n")

for entry in report.entries:
    print(f"  [{entry.heat_level.name:6s}] {entry.module_path}")
    print(f"    Calls: {entry.call_count:>8,}")
    print(f"    Total: {entry.total_time_ns / 1e6:>10.2f}ms")
    print(f"    Avg:   {entry.avg_time_ns / 1e6:>10.4f}ms")
    print(f"    Rec:   {entry.recommendation}")
    print()

# Check if specific modules should be recompiled
for mod_path in ["services.database.query", "api.middleware.auth.verify_token"]:
    should, reason = profiler.should_recompile(mod_path)
    print(f"{mod_path}: recompile={should} ({reason})")

# Estimate speedups
for mod_path in ["services.database.query"]:
    for lang in ["typescript", "csharp", "rust", "c", "c_simd"]:
        speedup = profiler.estimate_speedup(mod_path, lang)
        print(f"  {lang:12s}: ~{speedup:.0f}x speedup")
```

### Profiling a Data Pipeline

Here's a more detailed example profiling a data processing pipeline:

```python
# Profile a realistic data pipeline
def process_record(record: dict) -> dict:
    """Transform a single record."""
    handle = profiler.start_sample("pipeline.transform.map_fields")
    record = {k: v.strip() if isinstance(v, str) else v
              for k, v in record.items()}
    profiler.end_sample(handle)

    handle = profiler.start_sample("pipeline.transform.validate")
    required = ["id", "name", "email"]
    valid = all(k in record for k in required)
    profiler.end_sample(handle)

    if not valid:
        handle = profiler.start_sample("pipeline.errors.log_invalid")
        # Log to error tracking
        profiler.end_sample(handle)
        return {}

    handle = profiler.start_sample("pipeline.enrich.lookup_geo")
    # Geo IP lookup
    record["country"] = "US"
    profiler.end_sample(handle)

    handle = profiler.start_sample("pipeline.compute.scoring")
    score = len(record.get("name", "")) * 0.1
    record["score"] = score
    profiler.end_sample(handle)

    handle = profiler.start_sample("pipeline.store.write_db")
    # Write to database
    profiler.end_sample(handle)

    return record

# Run pipeline on batch
for _ in range(1000):
    process_record({"id": 1, "name": "Alice", "email": "alice@example.com"})

# Analyze results
ranking = profiler.get_ranking()
print("\nModule Ranking (by execution frequency):")
for mod, weight in ranking[:10]:
    print(f"  {mod:45s} {weight*100:5.1f}% of calls")
```

---

## Phase 3: Optimize (Day 3-5)

Once you have profiling data, the `AdaptiveSelector` recommends target languages and the `CompilerBridge` performs cross-language recompilation.

### Setting Up Language Recommendations

```python
from flux.adaptive.selector import AdaptiveSelector

selector = AdaptiveSelector(profiler)

# Get recommendations for all modules
recommendations = selector.select_all()

print("=" * 70)
print("LANGUAGE RECOMMENDATIONS")
print("=" * 70)
for mod, rec in sorted(recommendations.items(),
                       key=lambda x: x[1].estimated_speedup,
                       reverse=True):
    change_marker = " <-- CHANGE" if rec.should_change else ""
    print(f"\n  {mod}")
    print(f"    Current:  {rec.current_language}")
    print(f"    Rec:      {rec.recommended_language}")
    print(f"    Heat:     {rec.heat_level.name}")
    print(f"    Speed:    {rec.speed_score:.1f}/10")
    print(f"    Express:  {rec.expressiveness_score:.1f}/10")
    print(f"    Module:   {rec.modularity_score:.1f}/10")
    print(f"    Speedup:  ~{rec.estimated_speedup:.0f}x")
    print(f"    Reason:   {rec.reason}{change_marker}")
```

### Recompiling Hot Paths with CompilerBridge

```python
from flux.adaptive.compiler_bridge import CompilerBridge, LanguageCompiler

bridge = CompilerBridge(enable_cache=True)

# Register compilers for the languages you need
bridge.register_compiler("python", LanguageCompiler(
    lang="python",
    can_compile_to_fir=True,
    can_emit_from_fir=True,
    supported_source_extensions=(".py",),
))

bridge.register_compiler("c", LanguageCompiler(
    lang="c",
    can_compile_to_fir=True,
    can_emit_from_fir=True,
    supported_source_extensions=(".c",),
))

bridge.register_compiler("rust", LanguageCompiler(
    lang="rust",
    can_compile_to_fir=True,
    can_emit_from_fir=True,
    supported_source_extensions=(".rs",),
))

# Check if recompilation is supported
can, reason = bridge.can_recompile("python", "c")
print(f"Python -> C: {can} ({reason})")

# Recompile a hot module from Python to C
hot_module_source = """
def compute_score(records):
    total = 0
    for r in records:
        total += r["value"] * r["weight"]
    return total / len(records) if records else 0
"""

result = bridge.recompile(
    source=hot_module_source,
    from_lang="python",
    to_lang="c",
)

if result.success:
    print(f"Recompilation successful!")
    print(f"  Bytecode size: {len(result.bytecode)} bytes")
    print(f"  Compilation time: {result.compilation_time_ns / 1e6:.2f}ms")
    print(f"  Cache key: {result.source_hash}")
else:
    print(f"Recompilation failed: {result.error}")
```

### Moving a Hot Loop from Python to C

Here's a concrete before/after example of optimizing a critical computation:

```python
# BEFORE: Hot Python loop (identified as HEAT by profiler)
def hot_loop(data: list[float], weights: list[float]) -> float:
    """Weighted sum — called 5000+ times per second."""
    total = 0.0
    for i in range(len(data)):
        total += data[i] * weights[i]
    return total

# Profile shows this is HEAT-level:
# profiler.get_heatmap()["pipeline.compute.hot_loop"] == HeatLevel.HEAT
# profiler.should_recompile("pipeline.compute.hot_loop") == (True, "...")

# AFTER: Recompiled to C via CompilerBridge
hot_c_source = """
float hot_loop(float* data, float* weights, int n) {
    float total = 0.0f;
    #pragma omp simd reduction(+:total)
    for (int i = 0; i < n; i++) {
        total += data[i] * weights[i];
    }
    return total;
}
"""

result = bridge.recompile(
    source=hot_c_source,
    from_lang="python",
    to_lang="c",
)

# Apply the recommendation
if result.success:
    selector.apply_recommendation("pipeline.compute.hot_loop", "c")
    print(f"Applied: pipeline.compute.hot_loop → C")
    print(f"Estimated speedup: ~8x")
```

### Applying Tile Patterns

For common computation patterns, use FLUX's built-in tile library instead of custom code:

```python
from flux.tiles.library import (
    map_tile, reduce_tile, filter_tile,
    loop_tile, fuse_tile, pipeline_tile,
)
from flux.tiles.graph import TileGraph

# BEFORE: Custom pipeline with nested loops
def process_batch(records):
    # Map step
    mapped = []
    for r in records:
        mapped.append({"value": r["x"] * 2, "key": r["id"]})

    # Filter step
    filtered = [r for r in mapped if r["value"] > 10]

    # Reduce step
    total = 0
    for r in filtered:
        total += r["value"]
    return total

# AFTER: Compose FLUX tiles
graph = TileGraph("data_pipeline")

# map → filter → reduce composition
processing = map_tile.compose(filter_tile, {"result": "data"})
processing = processing.compose(reduce_tile, {"result": "data"})

graph.add_tile(processing)
print(f"Pipeline cost estimate: {processing.cost_estimate}")
```

### Performance Improvements

The speedup factors estimated by the profiler are empirical:

| Source Language | Target Language | Speedup Factor |
|---|---|---|
| Python | TypeScript | ~2x |
| Python | C# | ~4x |
| Python | Rust | ~10x |
| Python | C | ~8x |
| Python | C+SIMD | ~16x |

Combined with tile fusion and pipeline optimizations, real-world improvements of 5-20x are achievable on hot paths without touching the rest of the codebase.

---

## Phase 4: Agentify (Week 1)

With optimized performance, the next step is to convert function calls into **A2A (Agent-to-Agent) messages**, enabling independent agents to communicate, delegate, and coordinate.

### Converting Function Calls to A2A Messages

```python
import uuid
from flux.a2a.messages import A2AMessage

# BEFORE: Direct function calls between services
class UserService:
    def get_user(self, user_id):
        # Direct call to database service
        return db_service.query("SELECT * FROM users WHERE id = ?", user_id)

class OrderService:
    def create_order(self, user_id, items):
        user = user_service.get_user(user_id)  # <-- direct coupling
        # process order...

# AFTER: A2A message-based communication
USER_AGENT = uuid.uuid4()
ORDER_AGENT = uuid.uuid4()
conv_id = uuid.uuid4()

# Order agent asks user agent for user data
msg = A2AMessage(
    sender=ORDER_AGENT,
    receiver=USER_AGENT,
    conversation_id=conv_id,
    in_reply_to=None,
    message_type=0x61,  # ASK type (request-response)
    priority=5,
    trust_token=100,
    capability_token=200,
    payload=b'{"action": "get_user", "user_id": 42}',
)

serialized = msg.to_bytes()
print(f"A2A message size: {len(serialized)} bytes (52-byte header + payload)")

# Deserialize on the receiving end
received = A2AMessage.from_bytes(serialized)
print(f"Received: type=0x{received.message_type:02X}, "
      f"sender={received.sender}, receiver={received.receiver}")
```

### Setting Up Trust Relationships

```python
from flux.a2a.trust import TrustEngine

trust = TrustEngine()

# Record interactions to build trust
trust.record_interaction(
    agent_a="order_service",
    agent_b="user_service",
    success=True,
    latency_ms=5.2,
    capability_match=0.95,
)

trust.record_interaction(
    agent_a="order_service",
    agent_b="user_service",
    success=True,
    latency_ms=4.8,
    capability_match=0.98,
)

# Check trust levels
score = trust.compute_trust("order_service", "user_service")
print(f"Trust score: {score:.3f}")  # Rising above neutral (0.5)

# Only delegate to agents we trust
if trust.check_trust("order_service", "user_service", threshold=0.7):
    print("Trusted — delegating task")
else:
    print("Insufficient trust — handling locally")

# Trust dimensions (INCREMENTS+2):
# T = 0.30*T_history + 0.25*T_capability + 0.20*T_latency
#   + 0.15*T_consistency + 0.05*T_determinism + 0.05*T_audit
```

### Converting a Microservice to Agent Architecture

```python
# BEFORE: Monolithic Flask app with internal services
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/process")
def process():
    data = request.json
    validated = validate_service.validate(data)       # sync call
    enriched = enrich_service.enrich(validated)        # sync call
    scored = score_service.score(enriched)             # sync call
    stored = store_service.save(scored)                # sync call
    return jsonify(stored)

# AFTER: Agent-based architecture using FLUX tiles
from flux.tiles.library import (
    tell_tile, ask_tile, barrier_tile, broadcast_tile,
)
from flux.a2a.coordinator import A2ACoordinator

coordinator = A2ACoordinator()

# Define agents
validate_agent = uuid.uuid4()
enrich_agent = uuid.uuid4()
score_agent = uuid.uuid4()
store_agent = uuid.uuid4()

# Set up trust relationships
trust.record_interaction("coordinator", "validate", True, 2.0, 0.99)
trust.record_interaction("coordinator", "enrich", True, 5.0, 0.95)
trust.record_interaction("coordinator", "score", True, 3.0, 0.97)
trust.record_interaction("coordinator", "store", True, 8.0, 0.90)

# Register delegation patterns
coordinator.register_handler(
    validate_agent,
    handler=lambda msg: validate(msg.payload),
)

coordinator.register_handler(
    enrich_agent,
    handler=lambda msg: enrich(msg.payload),
)

# Process via A2A delegation
async def process_agentified(data):
    conv = uuid.uuid4()

    # Step 1: Validate (ask = request-response)
    validation_result = await coordinator.ask(
        validate_agent, data, conv
    )

    # Step 2-3: Enrich and score in parallel (tell = fire-and-forget)
    await coordinator.tell(enrich_agent, validation_result, conv)
    await coordinator.tell(score_agent, validation_result, conv)

    # Step 4: Barrier — wait for both
    await coordinator.barrier(conv, participants=2)

    # Step 5: Store results
    await coordinator.tell(store_agent, results, conv)

    return {"status": "completed"}
```

### A2A Message Flow

```
[Coordinator]                    [Validate Agent]
     |                                  |
     |--- ASK (validate) ------------->|
     |                                  |
     |<-- REPLY (validated) -----------|
     |                                  |
     |--- TELL (enrich) --------------> [Enrich Agent]
     |--- TELL (score) ----------------> [Score Agent]
     |                                  |
     |--- BARRIER (sync) ------------->|
     |                                  |
     |--- TELL (store) ----------------> [Store Agent]
     |                                  |
     |<-- CONFIRM --------------------->|
```

---

## Phase 5: Evolve (Week 2+)

The final phase enables FLUX's **self-evolution** — the system that builds a better version of itself by continuously discovering and applying optimizations.

### Setting Up the Evolution Engine

```python
from flux.evolution.evolution import EvolutionEngine
from flux.evolution.validator import CorrectnessValidator

engine = EvolutionEngine(
    profiler=profiler,
    selector=selector,
    validator=CorrectnessValidator(),
    max_generations=50,
    convergence_threshold=0.001,
)

# Define workloads for profiling during evolution
def typical_workload():
    """Representative workload for evolution testing."""
    # Simulate real traffic patterns
    process_record({"id": 1, "name": "Alice", "email": "a@b.com"})
    process_record({"id": 2, "name": "Bob", "email": "b@c.com"})

# Define correctness validation
def validate_system(genome) -> bool:
    """Ensure mutations don't break correctness."""
    # Run test suite against mutated system
    result = process_record({"id": 1, "name": "Test", "email": "t@t.com"})
    return result.get("id") == 1
```

### Running Evolution

```python
# Run the evolution loop
report = engine.evolve(
    module_root=root,
    tile_registry=None,  # Uses default tile library
    workloads=[typical_workload],
    max_generations=10,
    validation_fn=validate_system,
)

# Print the evolution report
print("=" * 70)
print("EVOLUTION REPORT")
print("=" * 70)
print(f"Generations:        {report.generations}")
print(f"Initial fitness:    {report.initial_fitness:.4f}")
print(f"Final fitness:      {report.final_fitness:.4f}")
print(f"Improvement:        {report.fitness_improvement:.4f} "
      f"({report.fitness_improvement_pct:.1f}%)")
print(f"Total speedup:      {report.total_speedup:.2f}x")
print(f"Mutations:          {report.mutations_succeeded}/{report.mutations_proposed} "
      f"succeeded ({report.success_rate:.0%})")
print(f"Patterns found:     {report.patterns_discovered}")
print(f"Elapsed:            {report.elapsed_ns / 1e9:.2f}s")

# Show per-generation trajectory
print("\nGeneration Trajectory:")
for record in report.records:
    arrow = "+" if record.is_improvement else "="
    print(f"  Gen {record.generation:>3d} {arrow} "
          f"fitness={record.fitness_after:.4f} "
          f"(delta={record.fitness_delta:+.4f}) "
          f"mutations={record.mutations_committed}/{record.mutations_proposed}")
```

### Reviewing Proposed Mutations

The evolution engine proposes specific mutations. Here's how to inspect them:

```python
# Get the best mutations
best = engine.get_best_mutations(n=5)

print("\nTop 5 Mutations:")
for i, record in enumerate(best, 1):
    p = record.proposal
    r = record.result
    print(f"\n  {i}. {p.description}")
    print(f"     Strategy:    {p.strategy.value}")
    print(f"     Target:      {p.target}")
    print(f"     Speedup:     {r.measured_speedup:.2f}x")
    print(f"     Fitness:     {r.fitness_before:.4f} -> {r.fitness_after:.4f}")
    print(f"     Risk:        {p.estimated_risk:.2f}")
    print(f"     Committed:   {record.committed}")
```

### Fitness Score Trajectory

A typical evolution run shows a fitness trajectory like:

```
Generation  Fitness   Delta     Mutations    Patterns
──────────  ───────   ─────     ─────────    ────────
    1       0.2340   +0.0000    0/3          2
    2       0.2891   +0.0551    1/3          4
    3       0.3456   +0.0565    2/4          5
    4       0.4012   +0.0556    1/2          6
    5       0.4230   +0.0218    0/1          7
    6       0.4789   +0.0559    2/3          8
    7       0.4891   +0.0102    0/1          8
    8       0.5234   +0.0343    1/2          9
    9       0.5301   +0.0067    0/0          9  <-- converging
   10       0.5312   +0.0011    0/0          9  <-- converged
```

The engine stops when fitness improvement drops below the convergence threshold, ensuring it doesn't waste cycles on diminishing returns.

### The Self-Improving System

The evolution loop follows a precise cycle:

1. **CAPTURE** — Take a genome snapshot of the current system state
2. **PROFILE** — Run representative workloads and collect execution data
3. **MINE** — Find hot patterns in execution traces (e.g., "map→filter→reduce appears 47 times")
4. **PROPOSE** — Generate mutation proposals (recompile, fuse tiles, merge tiles)
5. **EVALUATE** — Test each proposal for correctness and speed improvement
6. **COMMIT** — Apply successful mutations via hot-reload; rollback failures
7. **MEASURE** — Compare new genome fitness to previous generation
8. **RECORD** — Save the genome, increment generation
9. **REPEAT** — Continue until convergence or max generations

This means your system literally gets faster over time, without any manual intervention.

---

## Real-World Migration Examples

### Example 1: Web API Migration (Flask/FastAPI)

**Scenario:** A Flask API with 15 route handlers, a SQLAlchemy ORM layer, and a Celery task queue. Response times average 200ms; the P99 is 2 seconds due to complex database queries.

**Day 1 — Wrap:**

```python
# Create FLUX module hierarchy
root = ModuleContainer("webapp", Granularity.TRAIN)
api = root.add_child("api", Granularity.CARRIAGE)
orm = root.add_child("orm", Granularity.CARRIAGE)
tasks = root.add_child("tasks", Granularity.CARRIAGE)

# Wrap each route handler
routes = api.add_child("routes", Granularity.LUGGAGE)
for handler_name, handler_source in discover_handlers("./app/routes"):
    routes.load_card(handler_name, handler_source, "python")

# Wrap ORM queries
queries = orm.add_child("queries", Granularity.LUGGAGE)
for query_name, query_source in discover_queries("./app/models"):
    queries.load_card(query_name, query_source, "python")

# Wrap Celery tasks
task_cards = tasks.add_child("workers", Granularity.LUGGAGE)
for task_name, task_source in discover_tasks("./app/tasks"):
    task_cards.load_card(task_name, task_source, "python")
```

**Day 2-3 — Profile:**

After wrapping, run the profiler against production-like traffic. Results typically show:
- ORM query building (complex joins): **HEAT** — recompile to C
- Response serialization: **HOT** — recompile to Rust
- Route handlers: **WARM** — keep in Python
- Celery tasks: **COOL** — keep in Python
- Auth middleware: **WARM** — consider TypeScript

**Day 3-5 — Optimize:**

Recompile the HEAT ORM queries to C, gaining ~8x on query building. Rebuild response serialization in Rust, gaining ~10x on serialization. Result: P99 drops from 2s to 300ms.

### Example 2: ML Pipeline Migration (scikit-learn)

**Scenario:** A scikit-learn pipeline with data preprocessing, feature engineering, model training, and prediction. Training takes 45 minutes; feature engineering alone takes 30 minutes.

**Day 1 — Wrap:**

```python
root = ModuleContainer("ml_pipeline", Granularity.TRAIN)
preprocess = root.add_child("preprocess", Granularity.CARRIAGE)
features = root.add_child("features", Granularity.CARRIAGE)
model = root.add_child("model", Granularity.CARRIAGE)

# Wrap each pipeline stage
preprocess.load_card("clean", cleaning_code, "python")
preprocess.load_card("normalize", normalization_code, "python")
features.load_card("extract", feature_extraction_code, "python")
features.load_card("select", feature_selection_code, "python")
model.load_card("train", training_code, "python")
model.load_card("predict", prediction_code, "python")
```

**Day 2-3 — Profile:**

The profiler reveals that feature extraction loops over millions of rows with string operations — **HEAT**. Feature selection uses statistical tests — **HOT**. Model training is I/O-bound (numpy optimized) — **WARM**.

**Day 3-5 — Optimize:**

Recompile feature extraction to C+SIMD for the text processing loops — ~16x speedup reduces the 30-minute feature step to under 2 minutes. Replace feature selection with FLUX tile composition (`map_tile → filter_tile → reduce_tile`) for cleaner code and ~3x improvement. Total training time drops from 45 minutes to 12 minutes.

### Example 3: Game Engine Migration (Game Loop)

**Scenario:** A Python game engine with a main loop running at 30 FPS. Physics simulation, collision detection, and rendering are all in Python, causing frame drops during intense scenes.

**Day 1 — Wrap:**

```python
root = ModuleContainer("game_engine", Granularity.TRAIN)
physics = root.add_child("physics", Granularity.CARRIAGE)
collision = root.add_child("collision", Granularity.CARRIAGE)
render = root.add_child("render", Granularity.CARRIAGE)
input = root.add_child("input", Granularity.CARRIAGE)

physics.load_card("integrate", physics_integration_code, "python")
physics.load_card("forces", force_calculation_code, "python")
collision.load_card("broad_phase", broad_phase_code, "python")
collision.load_card("narrow_phase", narrow_phase_code, "python")
render.load_card("draw", rendering_code, "python")
render.load_card("scene_graph", scene_graph_code, "python")
```

**Day 2-3 — Profile:**

Every frame, the profiler records:
- Narrow-phase collision detection: **HEAT** (called per-pair, thousands per frame)
- Physics integration: **HOT** (called per-object, hundreds per frame)
- Broad-phase collision: **WARM** (called once per frame)
- Rendering: **HOT** (called per-frame)
- Input handling: **COOL** (event-driven, infrequent)

**Day 3-5 — Optimize:**

Recompile narrow-phase collision to C+SIMD — ~16x speedup on the AABB overlap tests. Recompile physics integration to Rust — ~10x speedup on force accumulation. Keep rendering in Python (it delegates to a GPU API anyway). Keep input handling in Python. Result: frame rate jumps from 30 FPS to a stable 60 FPS.

---

## Troubleshooting

### Common Issues and Solutions

**Issue: `ModuleNotFoundError` when wrapping modules**

If your wrapped code imports from other local modules, you need to ensure the import paths are correct. When wrapping, FLUX modules execute in their own namespace context.

```python
# Solution: Use the ModuleNamespace for import resolution
from flux.modules.namespace import ModuleNamespace

ns = ModuleNamespace()
ns.define("my_module.utils", utils_module)
container.namespace = ns
```

**Issue: Recompilation fails with "No compiler registered"**

You need to register compilers before attempting cross-language compilation:

```python
bridge.register_compiler("python", LanguageCompiler(
    lang="python", can_compile_to_fir=True, can_emit_from_fir=True
))
bridge.register_compiler("c", LanguageCompiler(
    lang="c", can_compile_to_fir=True, can_emit_from_fir=True
))
```

**Issue: Performance regression after recompilation**

If a recompiled module is slower (due to FIR overhead or suboptimal codegen), you can rollback:

```python
# Revert a language assignment
selector.clear_override("problematic.module")
selector.apply_recommendation("problematic.module", "python")

# Or use the evolution engine's built-in rollback
engine.mutator.rollback_mutation(proposal, result)
```

**Issue: Module dependency conflicts**

When modules have circular dependencies or import-time side effects, use lazy loading:

```python
# Solution: Load modules lazily via reload_card
container.load_card("module_a", "# lazy placeholder", "python")

# Later, when dependencies are ready:
container.reload_card("module_a", actual_source_code)
```

**Issue: A2A messages not delivered**

Verify trust levels between agents:

```python
score = trust.compute_trust("sender", "receiver")
if score < 0.7:
    # Build trust first by recording successful low-risk interactions
    trust.record_interaction("sender", "receiver", True, 1.0, 1.0)
```

**Issue: Evolution engine converges too early**

Adjust the convergence threshold and max generations:

```python
engine = EvolutionEngine(
    max_generations=200,              # Allow more generations
    convergence_threshold=0.0001,     # Tighter convergence
)
```

### Performance Regression Rollback

FLUX's `ModuleCard` tracks version history. To rollback:

```python
# Each card has version and checksum tracking
card = container.cards["my_module"]
print(f"Version: {card.version}, Checksum: {card.checksum}")

# Invalidate and recompile with previous source
card.invalidate()
# The previous source can be stored in your version control system
```

### Module Dependency Conflicts

For complex dependency graphs, use the container hierarchy to express relationships:

```python
# Shared utilities at LUGGAGE level
utils = root.add_child("utils", Granularity.LUGGAGE)
utils.load_card("helpers", helpers_code, "python")

# Feature modules reference shared utils
feature_a = root.add_child("feature_a", Granularity.LUGGAGE)
feature_a.namespace.define("utils.helpers", utils.cards["helpers"])

# Hot-reload feature_a independently without touching utils
feature_a.reload_at("feature_a", Granularity.LUGGAGE)
```

---

## Quick Reference

### Migration Checklist

- [ ] **Phase 1 (Day 1):** Wrap existing modules as `ModuleCard` instances in `ModuleContainer` hierarchy
- [ ] **Phase 2 (Day 2-3):** Run `AdaptiveProfiler` on realistic workloads, identify heat levels
- [ ] **Phase 3 (Day 3-5):** Use `AdaptiveSelector` for language recommendations, `CompilerBridge` for recompilation
- [ ] **Phase 4 (Week 1):** Convert key interfaces to A2A messages, set up `TrustEngine`, implement delegation
- [ ] **Phase 5 (Week 2+):** Enable `EvolutionEngine`, review mutations, monitor fitness trajectory

### Key Classes

| Class | Purpose | Key Method |
|---|---|---|
| `ModuleCard` | Atomic code unit | `.compile()`, `.recompile()` |
| `ModuleContainer` | Module hierarchy | `.load_card()`, `.reload_card()` |
| `AdaptiveProfiler` | Execution profiling | `.get_heatmap()`, `.get_bottleneck_report()` |
| `AdaptiveSelector` | Language selection | `.recommend()`, `.select_all()` |
| `CompilerBridge` | Cross-language compilation | `.recompile()`, `.can_recompile()` |
| `FluxCompiler` | Source → bytecode | `.compile_c()`, `.compile_python()`, `.compile_md()` |
| `A2AMessage` | Agent communication | `.to_bytes()`, `.from_bytes()` |
| `TrustEngine` | Trust management | `.compute_trust()`, `.check_trust()` |
| `EvolutionEngine` | Self-evolution | `.evolve()`, `.step()` |
