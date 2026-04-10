# FLUX Research Roadmap

**Version 1.0 | July 2025**

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [What We Built](#3-what-we-built)
4. [Open Research Questions](#4-open-research-questions)
5. [Suggested Research Projects](#5-suggested-research-projects)
6. [How to Extend FLUX](#6-how-to-extend-flux)
7. [Performance Characteristics](#7-performance-characteristics)
8. [Lessons Learned](#8-lessons-learned)

---

## 1. Executive Summary

**FLUX (Fluid Language Universal eXecution)** is a self-assembling, self-improving runtime that treats agents as first-class citizens. It compiles structured markdown containing polyglot code blocks (C, Python, Rust, and more) into a single optimized bytecode, executes it on a custom micro-VM, and then *improves itself* — profiling its own execution, discovering hot patterns, recompiling bottleneck modules to faster languages, generating new computation tiles, and validating correctness — all while the music never stops.

FLUX sits at the convergence of three traditionally separate disciplines:

- **Compilation** — A full pipeline from markdown source through SSA-form IR to binary bytecode with 104 opcodes
- **Artificial Intelligence** — Self-evolution via pattern mining, genetic mutation, fitness evaluation, and correctness validation
- **Art** — 8-level fractal hot-reload, composable tiles, and a design philosophy inspired by live music performance

The system currently comprises **106 source modules**, **1848 passing tests** across **30 test files**, and **15+ subsystems** covering everything from a 64-register micro-VM to an adaptive language selector to a multi-agent orchestration protocol.

### Where We're Going

The immediate research frontier is **self-hosting** — writing the FLUX compiler in FLUX itself. Beyond that lies the deeper question of whether self-improving systems can reach a fixed point of optimization, whether multi-agent topologies can exhibit emergent collective intelligence, and whether the tension between creative exploration and convergent optimization can be resolved. This roadmap lays out the concrete steps to investigate these questions.

---

## 2. Architecture Overview

FLUX is a **27-layer system** organized into 8 logical tiers, with data flowing bottom-up (compilation) and top-down (evolution):

```
┌─────────────────────────────────────────────────────────────────────┐
│  TIER 8: SYNTHESIS — FluxSynthesizer (the DJ booth)                │
│  Orchestrates all subsystems: modules, profiler, selector, tiles,   │
│  evolution, hot-reload, system reports, demo runner                 │
├─────────────────────────────────────────────────────────────────────┤
│  TIER 7: MODULES — 8-Level Fractal Hierarchy                        │
│  TRAIN → CARRIAGE → LUGGAGE → BAG → POCKET → WALLET → SLOT → CARD │
│  Containers, cards, namespace isolation, SHA-256 checksum trees     │
│  FractalReloader with cascade, strategy, history                    │
├──────────────────────────┬──────────────────────────────────────────┤
│  TIER 6A: ADAPTIVE       │  TIER 6B: EVOLUTION                     │
│  AdaptiveProfiler        │  Genome (system DNA snapshots)            │
│  AdaptiveSelector        │  PatternMiner (modified Apriori)         │
│  CompilerBridge          │  SystemMutator (7 strategies)            │
│                          │  CorrectnessValidator (regression)       │
│                          │  EvolutionEngine (main loop)             │
├──────────────────────────┴──────────────────────────────────────────┤
│  TIER 5: TILES — 35 built-in composable computation patterns        │
│  COMPUTE (8) · MEMORY (6) · CONTROL (6) · A2A (6)                  │
│  EFFECT (3) · TRANSFORM (6)                                        │
│  TileGraph (DAG), TileRegistry (search/alternatives)                │
├─────────────────────────────────────────────────────────────────────┤
│  TIER 4: AGENT RUNTIME                                             │
│  Agent (wraps Interpreter) · AgentRuntime (orchestrator)            │
│  CLI (compile/run/test)                                             │
├─────────────────────────────────────────────────────────────────────┤
│  TIER 3: A2A PROTOCOL                                              │
│  Messages (4 kinds) · Channels (3 types) · Registry (capability)    │
│  Negotiation (4-step trust handshake) · Serialization (binary)      │
├─────────────────────────────────────────────────────────────────────┤
│  TIER 2: SUPPORTING SUBSYSTEMS                                      │
│  Optimizer (CF, DCE, Inline) · JIT (cache, tracing, IR opts)      │
│  Type System (unify, generics, compat) · Stdlib (26 functions)      │
│  Security (capabilities, sandbox) · Hot Reload (BEAM-inspired)      │
├─────────────────────────────────────────────────────────────────────┤
│  TIER 1: CORE COMPILATION PIPELINE                                  │
│  L0: FLUX.MD Parser (markdown → AST)                               │
│  L1: Frontends (C, Python → FIR)                                   │
│  L2: FIR — Flux IR (SSA form, 15 types, 42 instructions)           │
│  L3: Bytecode (104 opcodes, 6 encoding formats, binary format)     │
│  L4: Micro-VM (64 registers, fetch-decode-execute)                  │
└─────────────────────────────────────────────────────────────────────┘
```

### Data Flow (Compilation Path)

```
FLUX.MD ──→ Parser (L0) ──→ Frontend (L1) ──→ FIRBuilder (L2)
                                                    │
                                                    ▼
                         VM Interpreter (L4) ←── BytecodeEncoder (L3)
```

### Data Flow (Evolution Path)

```
Execution Traces ──→ PatternMiner ──→ SystemMutator ──→ CorrectnessValidator
                        │                   │                   │
                        ▼                   ▼                   ▼
                   Hot Patterns      Mutation Proposals    Pass/Fail
                        │                   │                   │
                        └───────────────────┼───────────────────┘
                                            ▼
                                    EvolutionEngine.step()
                                            │
                                            ▼
                                    Genome Updated → Next Generation
```

---

## 3. What We Built

### By the Numbers

| Metric | Value |
|--------|-------|
| Source modules (non-init .py) | 106 |
| Total .py files (including init) | 137 |
| Test files | 30 |
| Total passing tests | 1,848 |
| Subsystems | 15+ |
| Bytecode opcodes | 104 |
| FIR instruction types | 42 |
| FIR types | 15 |
| Built-in tiles | 35 |
| Module granularity levels | 8 |
| Mutation strategies | 7 |
| Language profiles | 6 |
| A2A message types | 4 |
| Channel types | 3 |
| Trust dimensions | 6 |

### Subsystem Summary

| # | Subsystem | Path | Source Files | Tests | Description |
|---|-----------|------|:---:|:---:|-------------|
| 1 | FIR Core | `src/flux/fir/` | 7 | 13 | Universal SSA IR with types, instructions, blocks, builder, validator, printer |
| 2 | FLUX.MD Parser | `src/flux/parser/` | 2 | 11 | Structured markdown parser with YAML frontmatter, code blocks, agent directives |
| 3 | Bytecode | `src/flux/bytecode/` | 4 | 12 | 104-opcode binary format with encoder, decoder, validator |
| 4 | Micro-VM | `src/flux/vm/` | 3 | 25 | 64-register fetch-decode-execute interpreter with memory management |
| 5 | Frontends | `src/flux/frontend/` | 2 | 8 | C and Python → FIR compilers |
| 6 | Optimizer | `src/flux/optimizer/` | 2 | 4 | Constant folding, dead code elimination, inlining |
| 7 | JIT Compiler | `src/flux/jit/` | 5 | 43 | Function inlining, LRU cache, execution tracing, IR optimization |
| 8 | Type System | `src/flux/types/` | 4 | 76 | Polyglot type unification (C/Python/Rust), generics, compatibility |
| 9 | Standard Library | `src/flux/stdlib/` | 5 | 66 | Intrinsics, collections, math, strings, agent utilities |
| 10 | A2A Protocol | `src/flux/protocol/` | 5 | 85 | Messages, channels, registry, negotiation, binary serialization |
| 11 | Agent Runtime | `src/flux/runtime/` | 3 | 6 | Agent wrapper, runtime orchestrator, CLI |
| 12 | Security | `src/flux/security/` | 3 | 6 | Capability tokens, resource limits, sandbox |
| 13 | Hot Reload | `src/flux/reload/` | 1 | 3 | BEAM-inspired dual-version loading with rollback |
| 14 | Module System | `src/flux/modules/` | 6 | 72 | 8-level fractal hierarchy, checksum trees, namespace isolation |
| 15 | Adaptive Subsystem | `src/flux/adaptive/` | 4 | 99 | Runtime profiler, language selector, compiler bridge |
| 16 | Tile System | `src/flux/tiles/` | 6 | 145 | 35 composable tiles across 6 categories, DAG graphs, registry |
| 17 | Evolution Engine | `src/flux/evolution/` | 6 | 154 | Genome, pattern mining, mutation, validation, evolution loop |
| 18 | Synthesis | `src/flux/synthesis/` | 4 | 54 | Top-level orchestrator wiring all subsystems, reports, demo |
| 19 | E2E Pipeline | `src/flux/pipeline/` | 3 | 14 | Full pipeline, polyglot compiler, debugger |
| 20 | A2A Primitives | `src/flux/a2a/` | 4 | 10 | Message types, transport, coordinator, trust engine |

---

## 4. Open Research Questions

Consolidated from all five research documents (`bootstrap_and_meta.md`, `simulation_and_prediction.md`, `memory_and_learning.md`, `agent_orchestration.md`, `creative_use_cases.md`) plus the builder schema analysis.

### Tier 1: Critical (Required for Self-Hosting)

**Q1: Self-Hosting Bootstrap — Can FLUX compile itself?**
The FIR already has struct, array, and string types, but the VM lacks handlers for `GETFIELD`, `SETFIELD`, `GETELEM`, `SETELEM`, `MEMCPY`, `MEMSET`, and string primitives. These must be implemented before the compiler can be expressed as FLUX bytecode. Estimate: ~500-800 lines of interpreter code. *Source: bootstrap_and_meta.md §1.3*

**Q2: Fixed-Point Optimization — Does the bootstrap converge?**
Compile the compiler with itself N times and verify `bytecode(N) == bytecode(N+1)`. This requires deterministic FIR construction (eliminate dict iteration order dependence), deterministic register allocation, and deterministic encoding. The current codebase has some non-determinism in `FIRBuilder`. *Source: bootstrap_and_meta.md §1.5*

**Q3: Behavioral Equivalence Verification — Can we prove evolved bytecode is correct?**
The `CorrectnessValidator` uses behavioral testing (baseline capture + regression detection), which is sound but incomplete — it misses edge cases not covered by the test suite. Godel's incompleteness theorems imply that no sufficiently powerful system can prove all true statements about itself. Formal verification of optimized bytecode against the FIR specification remains open. *Source: bootstrap_and_meta.md §5.6, agent_orchestration.md §6.3*

### Tier 2: Important (Key Capabilities)

**Q4: Multi-Agent Culture — Can agent populations develop persistent optimization norms?**
When multiple FLUX agents evolve independently, can they develop shared "culture" through the tile registry (meme propagation), trust dynamics (norm emergence), and genome inheritance (cross-agent recombination)? The trust engine may create monopolies that lock out new agents. *Source: agent_orchestration.md §3-6*

**Q5: Transfer Learning for Code — Can optimization knowledge transfer across workload domains?**
The `PatternMiner` discovers concrete patterns (specific module paths). Generalization rules (abstracted pattern signatures) could enable transferring optimization knowledge from one domain to another — e.g., fusing map+filter works for numerical pipelines, so try it for string pipelines too. *Source: memory_and_learning.md §3*

**Q6: Creative vs. Efficiency Tension — Can a system be both maximally creative and maximally efficient?**
The fitness function weights speed (0.4), modularity (0.3), correctness (0.3). But creativity requires diversity of reachable states, which converges away from efficiency. Introducing a "creative potential" metric as a fourth fitness component may resolve this. *Source: creative_use_cases.md §7, Q1*

**Q7: Predictive Profiling — Can we predict heat levels before execution?**
Currently modules start as FROZEN until profiled. Abstract interpretation over FIR (interval arithmetic), structural heuristics (call site count, loop nesting), and pre-execution simulation could predict heat levels at load time, eliminating the warm-up period. *Source: simulation_and_prediction.md §1*

**Q8: Incremental Compilation with Dependency Tracking — How fine-grained can hot-reload be?**
Currently, card reload invalidates the entire subtree. A symbol-level dependency graph would enable fine-grained recompilation: only recompile cards that import changed symbols. The `HotLoader` already supports dual-version loading; combined with dependency tracking, this gives incremental hot-reload with zero downtime. *Source: bootstrap_and_meta.md §3*

**Q9: Persistent Cross-Session Memory — Can FLUX accumulate wisdom across sessions?**
All evolution state is currently ephemeral. A four-tier persistence model (Hot/Warm/Cold/Frozen) with SQLite for warm data and versioned files for frozen data would enable the system to learn from past sessions. *Source: memory_and_learning.md §2*

**Q10: Emergent Hierarchy — Can agent topologies self-organize?**
The five canonical topologies (hierarchical, mesh, star, ring, blackboard) are currently programmer-imposed. Can natural hierarchies emerge from flat initial conditions through trust dynamics alone? Preliminary analysis suggests agents with high outgoing trust become hubs, high incoming trust become authorities. *Source: agent_orchestration.md §1, §6.6*

### Tier 3: Exploratory (Deep Research)

**Q11: Digital Twin Accuracy Limits — Can a shadow system predict real evolution accurately?**
A Digital Twin runs ahead of the real system, predicting evolution outcomes. Drift between predicted and actual fitness indicates the limits of the cost model. At what complexity level does the twin become less accurate than simply running the real system? *Source: simulation_and_prediction.md §5*

**Q12: Energy-Carbon Optimization — Can the fitness function incorporate energy consumption?**
Per-instruction energy costs are known (Horowitz et al. 2014). Extending the fitness function with an energy dimension enables carbon-budgeted deployment. But energy-optimal code may differ from speed-optimal code (e.g., branch mispredictions cost 20x more energy). *Source: simulation_and_prediction.md §6*

**Q13: Computational Irreducibility — Is there a limit to predictive optimization?**
Some systems may be computationally irreducible — no shortcut exists to predict their behavior except running them. When the ratio of successful to failed mutations drops below a threshold (flat fitness landscape), should the system switch from exploitation to exploration? *Source: creative_use_cases.md §7, Q5*

**Q14: Meta-Optimization — Can the evolution engine safely modify its own optimization passes?**
This is related to the superoptimization problem (Schkufza et al., 2013). If the engine proposes a new optimization pass, how do we verify it always preserves semantics, never makes programs slower, and terminates? *Source: bootstrap_and_meta.md §5.5*

**Q15: FIR Self-Representation — Can the FIR represent its own instruction set?**
The FIR has `StructType` and `EnumType`, so the instruction set could be represented as FIR data. But interpreting that data to drive compilation requires metaprogramming (type-level computation, macros, dependent types) that the current FIR does not support. *Source: bootstrap_and_meta.md §5.8*

---

## 5. Suggested Research Projects

### Project 1: Complete the VM for Self-Hosting
- **Description:** Implement missing VM opcode handlers for struct field access (`GETFIELD`/`SETFIELD`), array element access (`GETELEM`/`SETELEM`), bulk memory operations (`MEMCPY`/`MEMSET`), string primitives (concat, compare, slice), and A2A opcodes (`TELL`, `ASK`, `DELEGATE`, etc.). This is the single most important engineering task.
- **Difficulty:** 3/5
- **Dependencies:** `src/flux/vm/interpreter.py`, `src/flux/bytecode/opcodes.py`
- **Expected Outcome:** ~500-800 lines of interpreter code; all 104 opcodes functional in the VM; FIR round-trip tests pass
- **Suggested Approach:** Start with `GETFIELD`/`SETFIELD` (needed for all struct operations), then `GETELEM`/`SETELEM` (arrays), then string primitives. Use the existing `MemoryRegion` for all memory access. Add bounds checking for every load/store.

### Project 2: Bootstrap Stage 1 — FIR Builder as FLUX.MD
- **Description:** Write the FIR builder (currently `src/flux/fir/builder.py`) as a FLUX.MD document with embedded C code. Compile it through the pipeline to produce bytecode that can construct FIRModule objects in-memory.
- **Difficulty:** 4/5
- **Dependencies:** Project 1 (VM completeness), `src/flux/fir/`, `src/flux/parser/`
- **Expected Outcome:** A FLUX.MD file that, when compiled and executed, produces the same FIR output as the Python `FIRBuilder`
- **Suggested Approach:** Write C functions that allocate memory for FIR structs, populate fields, and return pointers. Use `ALLOCA` + `STORE` for struct layout. Test by comparing the Python-built FIR against the self-compiled FIR.

### Project 3: Predictive Profiler with Abstract Interpretation
- **Description:** Implement an abstract interpreter over FIR that predicts execution cost without running code. Use interval arithmetic for value ranges and induction variable analysis for loop bounds.
- **Difficulty:** 4/5
- **Dependencies:** `src/flux/fir/`, `src/flux/adaptive/profiler.py`
- **Expected Outcome:** Heat level predictions for FROZEN modules at load time; ~100x faster than real profiling; 80%+ prediction accuracy on representative workloads
- **Suggested Approach:** Define an `AbstractValue` type (interval + constness). Implement abstract evaluation for each FIR instruction type. Track loop trip counts via induction variable detection. Integrate with `AdaptiveProfiler.get_heatmap()` to fill in FROZEN modules.

### Project 4: Persistent Memory Store
- **Description:** Implement the four-tier memory architecture (Hot/Warm/Cold/Frozen) using SQLite for warm data (genomes, patterns, mutation records) and the filesystem for frozen data (versioned tile libraries, generalization rules).
- **Difficulty:** 3/5
- **Dependencies:** `src/flux/evolution/genome.py`, `src/flux/evolution/pattern_mining.py`
- **Expected Outcome:** FLUX sessions can resume from where they left off; learned tiles persist across restarts; evolution history is queryable
- **Suggested Approach:** Implement `MemoryStore` class with `save_genome()`, `load_latest_genome()`, `save_patterns()`, `save_learned_tile()`. Use WAL (write-ahead log) for crash safety. Add `recover_session()` to `FluxSynthesizer.__init__()`.

### Project 5: Multi-Agent PSO (Particle Swarm Optimization)
- **Description:** Use FLUX agents as particles in a swarm optimization algorithm. Each agent has a position (genome) and velocity (mutation rate). Global best is maintained through `REDUCE` operations.
- **Difficulty:** 3/5
- **Dependencies:** `src/flux/evolution/`, `src/flux/a2a/`, `src/flux/runtime/`
- **Expected Outcome:** Demonstrate that a swarm of FLUX agents collectively finds better optimizations than a single agent; measure convergence speedup vs. single-agent evolution
- **Suggested Approach:** Implement the PSO bytecode pattern (see `agent_orchestration.md §5.1`). Each agent runs the PSO loop in its VM. Use `REDUCE` to find global best. Compare fitness trajectories of single-agent vs. swarm evolution.

### Project 6: Digital Twin with Chaos Engineering
- **Description:** Build a shadow copy of the FLUX runtime that predicts evolution outcomes before committing them. Add chaos engineering (faulty mutations, conflicting proposals, memory pressure) to test robustness.
- **Difficulty:** 4/5
- **Dependencies:** `src/flux/evolution/evolution.py`, `src/flux/simulation_and_prediction.md` designs
- **Expected Outcome:** A `DigitalTwin` class that runs ahead of the real system; drift rate measurement; chaos injector that verifies rollback safety
- **Suggested Approach:** Implement `DigitalTwin.simulate_next_generation()` using cost model estimates instead of real execution. Track prediction accuracy with `measure_drift()`. Implement `ChaosInjector` with fault patterns (faulty mutations, conflicting targets, memory pressure).

### Project 7: Experience Generalization Engine
- **Description:** Move from concrete pattern matching to abstract pattern matching. Extract structural signatures from discovered patterns and store generalization rules that can be applied across workloads.
- **Difficulty:** 4/5
- **Dependencies:** `src/flux/evolution/pattern_mining.py`, `src/flux/tiles/registry.py`
- **Expected Outcome:** Abstract pattern signatures; case-based reasoning for new workloads; transfer learning between domains
- **Suggested Approach:** Implement `AbstractPatternSignature` extraction (replace module paths with tile type categories). Build `GeneralizationRule` with Bayesian confidence updates. Implement `CaseMemory.find_similar_cases()` using structural edit distance.

### Project 8: Live Coding Performance System
- **Description:** Build a performance interface for FLUX that allows real-time hot-reload with visual feedback. Project TileGraph DOT output, heatmap colors, and fitness trends in real time.
- **Difficulty:** 3/5
- **Dependencies:** `src/flux/synthesis/`, `src/flux/modules/reloader.py`, `src/flux/tiles/graph.py`
- **Expected Outcome:** A web-based dashboard showing live system state; performer can edit FLUX.MD and see changes in <100ms; audience sees real-time visualizations
- **Suggested Approach:** Use WebSocket for real-time updates. Render `TileGraph.to_dot()` with Graphviz. Color-code modules by heat level. Add a code editor that triggers `hot_swap()` on save.

### Project 9: Adaptive Storytelling Engine
- **Description:** Use FLUX's tile composition and evolution engine to create an interactive narrative system where story beats are tiles, chapters are modules, and the "creative director" agent optimizes narrative quality.
- **Difficulty:** 3/5
- **Dependencies:** `src/flux/synthesis/`, `src/flux/tiles/`, `src/flux/a2a/`
- **Expected Outcome:** A working demo of emergent narrative; the PatternMiner discovers which story beats co-occur and proposes fused narrative tiles
- **Suggested Approach:** Map narrative structure to the 8-level module hierarchy (Story → Act → Chapter → Scene → Beat → Action → Detail → Word). Implement a custom fitness function for narrative quality. Use `PatternMiner` to discover player behavior patterns.

### Project 10: Energy-Aware Evolution
- **Description:** Extend the fitness function with an energy dimension. Implement per-instruction energy costs (from Horowitz et al. 2014) and optimize for energy efficiency instead of (or in addition to) speed.
- **Difficulty:** 2/5
- **Dependencies:** `src/flux/evolution/genome.py`, `src/flux/bytecode/opcodes.py`
- **Expected Outcome:** Energy-cost model for FIR functions; modified fitness function with energy weight; demo showing energy-optimized code differs from speed-optimized code
- **Suggested Approach:** Implement `EnergyCostModel` as an extension of `FIRCostModel`. Add `energy_score` to `Genome.evaluate_fitness()`. Compare language recommendations: for speed, C+SIMD wins; for energy, Python may win on I/O-bound code due to lower per-instruction energy cost.

---

## 6. How to Extend FLUX

### 6.1 Adding a New Opcode

1. **Define the opcode** in `src/flux/bytecode/opcodes.py`:
   ```python
   class Op(IntEnum):
       # ... existing opcodes ...
       MY_NEW_OP = 0xA0  # Pick an unused slot in 0xA0-0xFF
   ```

2. **Classify its format** by adding to the appropriate frozenset (`FORMAT_A`, `FORMAT_B`, etc.) or defining a new format.

3. **Add FIR instruction** in `src/flux/fir/instructions.py` (if it maps to a FIR-level operation).

4. **Implement VM handler** in `src/flux/vm/interpreter.py`:
   ```python
   elif opcode == Op.MY_NEW_OP:
       # Decode operands based on format
       # Execute semantics
       # Update registers/memory as needed
   ```

5. **Add encoder mapping** in `src/flux/bytecode/encoder.py` and **decoder mapping** in `src/flux/bytecode/decoder.py`.

6. **Write tests** — at minimum: encode/decode roundtrip, VM execution, FIR-to-bytecode mapping.

### 6.2 Adding a New Tile

```python
from flux.tiles import Tile, TileType, TilePort, PortDirection
from flux.fir.types import TypeContext

ctx = TypeContext()

my_tile = Tile(
    name="my_fft",
    tile_type=TileType.COMPUTE,
    inputs=[TilePort("signal", PortDirection.INPUT, ctx.f32)],
    outputs=[TilePort("spectrum", PortDirection.OUTPUT, ctx.f32)],
    params={"window_size": 1024},
    cost_estimate=5.0,
    abstraction_level=4,
    tags={"signal_processing", "transform"},
    fir_blueprint=my_fft_blueprint,  # callable(builder, inputs, params) -> {"output_name": value}
)

synth.register_tile(my_tile)
```

### 6.3 Adding a New Language Frontend

1. Create `src/flux/frontend/<lang>_frontend.py` implementing a parser that produces `FIRModule`.
2. Register it in `src/flux/compiler/pipeline.py` so the `FluxCompiler` can dispatch to it.
3. Add language profile to `src/flux/adaptive/selector.py`:
   ```python
   LANGUAGES["go"] = LanguageProfile(
       name="go", speed_tier=7, expressiveness_tier=7,
       modularity_tier=8, compile_time_tier=3,
       hot_reload_support=False, simd_support=False, memory_safety=True,
   )
   ```
4. Add type mappings to `src/flux/types/unify.py`.
5. Write tests in `tests/test_frontends.py`.

### 6.4 Adding a New Evolution Strategy

1. Add to the `MutationStrategy` enum in `src/flux/evolution/genome.py`:
   ```python
   MutationStrategy.MY_STRATEGY = "my_strategy"
   ```

2. Implement proposal logic in `SystemMutator.propose_mutations()` in `src/flux/evolution/mutator.py`.

3. Implement apply logic in `SystemMutator.apply_mutation()`.

4. Add tests in `tests/test_evolution.py`.

### 6.5 Adding a New Module Granularity Level

1. Extend the `Granularity` enum in `src/flux/modules/granularity.py`.
2. Update `GranularityMeta` with reload cost, isolation level, and typical size.
3. Update `should_reload_to()` for boundary checking.
4. The `ModuleContainer` hierarchy automatically supports arbitrary nesting depth.

### 6.6 Adding a New Agent Topology

1. Define the topology as a `TileGraph` connecting A2A tiles.
2. Use `tell_tile`, `ask_tile`, `broadcast_tile`, `barrier_tile` as building blocks.
3. Register agents with the `AgentCoordinator`.
4. Implement any topology-specific logic (e.g., deadlock detection for rings, leader election for hierarchies) as coordination tiles.

---

## 7. Performance Characteristics

### Current Benchmark Data

| Operation | Time | Notes |
|-----------|------|-------|
| Full test suite (1848 tests) | ~13s | pytest on single core |
| Single FIR build (small function) | <0.1ms | FIRBuilder.create_function() |
| Bytecode encode (small module) | <0.5ms | BytecodeEncoder.encode() |
| Bytecode decode (small module) | <0.5ms | BytecodeDecoder.decode() |
| VM execution (1M cycles) | ~50ms | Simple arithmetic loop |
| Evolution step (single generation) | ~10ms | Capture + mine + propose + evaluate |
| Multi-generation evolution (100 gen) | ~1s | Convergence typically at ~20 generations |
| Hot-swap (CARD level) | <1ms | Memory only, no compilation |
| Full pipeline (MD → bytecode) | ~5ms | Small FLUX.MD with one function |
| TileGraph compilation (35 tiles) | ~2ms | Topological sort + FIR emission |

### Known Bottlenecks

1. **VM Interpreter is single-threaded Python.** The fetch-decode-execute loop has no SIMD vectorization and no pipelining. Real workloads will be 100-1000x slower than native C.
2. **No native code generation.** The JIT compiler plans exist but only produce FIR-level optimizations, not native machine code. True performance requires a backend (LLVM, Cranelift, or hand-written x86-64).
3. **Pattern mining scales quadratically.** The modified Apriori algorithm has O(n^2 * k) complexity for n traces and k pattern length. Large execution traces (>1000 entries) may be slow.
4. **Genome deep copy on every mutation.** `Genome.mutate()` uses `deepcopy`, which is O(module_count + tile_count). For genomes with >1000 modules, this becomes noticeable.
5. **No incremental bytecode encoding.** The `BytecodeEncoder` re-encodes the entire module on every change. For large modules, this wastes time re-encoding unchanged functions.
6. **Trust engine pairwise scaling.** N agents create O(N^2) pairwise trust profiles. Large swarms (>100 agents) need pruning strategies.

---

## 8. Lessons Learned

### What Worked

1. **FIR as the universal pivot.** Having a single intermediate representation that all frontends produce and all backends consume was the single most important architectural decision. It enabled polyglot compilation, cross-language type unification, and the tile system's FIR emission without any special cases.

2. **Frozen dataclasses for types.** Using `@dataclass(frozen=True)` for FIR types made them hashable, which enabled interning, equality comparison, and use as dictionary keys — all essential for the builder, validator, and optimizer.

3. **Test-driven development at scale.** Writing 1848 tests provided a safety net that made aggressive refactoring possible. Every subsystem was built with comprehensive tests before integration, which caught bugs early and provided the `CorrectnessValidator` with a rich baseline.

4. **The music metaphor as design guidance.** Thinking of the system as a DJ booth (layering, reading the room, swapping tracks) led to design decisions that a purely technical framing would have missed — particularly the 8-level granularity hierarchy (from TRAIN to CARD) and the emphasis on zero-downtime hot-reload.

5. **Evolution as a separate subsystem.** Keeping the evolution engine decoupled from the compilation pipeline meant we could evolve language assignments, tile compositions, and optimization settings without modifying the core compiler. The `Genome` abstraction made this possible.

### What Didn't Work

1. **Dict iteration order non-determinism.** Several modules use `dict` iteration (Python 3.7+ preserves insertion order, but `defaultdict` and set operations can still vary). This will be a problem for deterministic bootstrap and needs to be addressed before self-hosting.

2. **Over-conservative invalidation.** The module system invalidates the entire subtree on reload, which is correct but wasteful. Fine-grained dependency tracking (planned for a future iteration) would significantly reduce unnecessary recompilation.

3. **No persistence.** All evolution state is lost between sessions. This was a conscious decision to keep the initial implementation simple, but it means the system starts from zero every time — wasting accumulated optimization knowledge.

4. **VM opcode gap.** Defining 104 opcodes in the encoding layer but only implementing ~40 in the VM created a false sense of completeness. Future work should either implement all opcodes or clearly mark unimplemented ones.

### Surprising Discoveries

1. **Tiles as memes.** The tile system turned out to be more than a performance optimization framework. Tiles are the unit of cultural transmission in multi-agent systems — they propagate through the registry, evolve through pattern mining, and compete for adoption based on their cost/benefit ratio. This was not planned but emerged naturally from the architecture.

2. **The fitness function is a design statement.** The weights (speed 0.4, modularity 0.3, correctness 0.3) encode a specific set of values. Changing these weights produces dramatically different system behaviors: heavy speed weighting converges to all-C+SIMD; heavy modularity weighting keeps everything in Python. The fitness function is arguably the most important "code" in the system.

3. **Heat classification is remarkably effective.** The simple percentile-based heat classification (FROZEN/COOL/WARM/HOT/HEAT) provides a good enough signal for language selection that the system makes reasonable decisions even without any machine learning. Sometimes simple heuristics beat complex models.

4. **Trust dynamics create emergent topology.** Even without explicit topology configuration, the trust engine's pairwise scoring creates natural hubs (highly trusted agents) and periphery (low-trust agents). This suggests that FLUX could support topology-free agent deployment where structure emerges from behavior.

5. **The DJ metaphor broke down exactly where we expected.** The DJ metaphor works beautifully for explaining hot-reload, layering, and adaptation. It breaks down at self-modification — a DJ doesn't rewrite the turntable while spinning. This is where FLUX goes beyond the metaphor into genuinely novel territory.

---

## Appendix: Research Document Index

| Document | Path | Key Topics |
|----------|------|------------|
| Bootstrap & Meta-Compilation | `docs/research/bootstrap_and_meta.md` | Self-hosting, polyglot runtime, incremental compilation, self-optimizing bytecode |
| Simulation & Prediction | `docs/research/simulation_and_prediction.md` | Pre-execution simulation, speculative evolution, performance modeling, digital twin, energy optimization |
| Memory & Learning | `docs/research/memory_and_learning.md` | Cross-session memory, experience generalization, learned tiles, meta-learning, strategic forgetting |
| Agent Orchestration | `docs/research/agent_orchestration.md` | Topologies, emergent behavior, specialization, deadlock detection, collective intelligence |
| Creative Use Cases | `docs/research/creative_use_cases.md` | Live coding, generative art, collaborative creation, adaptive storytelling, simulation |

---

*This roadmap is a living document. As research progresses, questions should be refined, projects completed or deprioritized, and new questions added. The FLUX system itself is the primary research instrument — every improvement to the system improves our ability to study it.*
