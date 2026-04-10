# FLUX: Fluid Language Universal eXecution

[![CI](https://github.com/SuperInstance/flux-runtime/actions/workflows/ci.yml/badge.svg)](https://github.com/SuperInstance/flux-runtime/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests: 1848](https://img.shields.io/badge/tests-1848-brightgreen.svg)](https://github.com/SuperInstance/flux-runtime)
[![Dependencies: 0](https://img.shields.io/badge/deps-0-success.svg)](https://github.com/SuperInstance/flux-runtime)
[![Playground](https://img.shields.io/badge/try-playground-ff69b4.svg)](https://github.com/SuperInstance/flux-runtime/tree/main/playground)

**A Self-Assembling, Self-Improving Runtime — The DJ Booth for Agent Code**

```
     ╔═══════════════════════════════════════════╗
     ║                                           ║
     ║   ██████╗ ██████╗ ██████╗ ███████╗         ║
     ║   ██╔══██╗██╔═══╝ ██╔══██╗██╔════╝         ║
     ║   ██████╔╝██║     ██║  ██║█████╗           ║
     ║   ██╔═══╝ ██║     ██║  ██║██╔══╝           ║
     ║   ██║     ╚██████╗██████╔╝███████╗         ║
     ║   ╚═╝      ╚═════╝╚═════╝ ╚══════╝         ║
     ║                                           ║
     ║   Fluid Language Universal eXecution      ║
     ║   v0.1.0 · 1848 tests · 106 modules       ║
     ║                                           ║
     ╚═══════════════════════════════════════════╝
```

FLUX is not just a compiler or a VM. It's a living system that writes, optimizes, recompiles, and improves its own code — all while running. Think of it as the evolution from orchestra (rigid, top-down) through folk (expressive), jazz (improvisational), rock (powerful), to DJ/rave (layered, adaptive, self-evolving).

## The Philosophy

> **An orchestra** plays from a fixed score — that's a traditional compiler.
> **Folk musicians** change the arrangement every night — that's hot reload.
> **Jazz ensembles** improvise based on what they hear — that's adaptive optimization.
> **Rock bands** push the speakers to the limit — that's the profiler finding bottlenecks.
> **A DJ at a rave** layers samples, reads the room, swaps tracks mid-set, and the system gets better every minute — that's FLUX.

FLUX treats agents as first-class citizens. Agents write structured markdown containing polyglot code blocks — mixing C, Rust, Python, or any language line by line — and the FLUX compiler weaves them into a single optimized, verifiable bytecode. Then the system profiles itself, discovers hot patterns, recompiles bottleneck modules to faster languages, and evolves — all while the music never stops.

## Architecture — The Full Stack

```
┌─────────────────────────────────────────────────────────────────────┐
│  TIER 8: SYNTHESIS — FluxSynthesizer (the DJ booth)                │
│  Wires ALL subsystems: modules, profiler, selector, tiles,         │
│  evolution, hot-reload, system reports                              │
├─────────────────────────────────────────────────────────────────────┤
│  TIER 7: MODULES — 8-Level Fractal Hierarchy                        │
│  TRAIN → CARRIAGE → LUGGAGE → BAG → POCKET → WALLET → SLOT → CARD │
│  Nested containers, atomic hot-reload, namespace isolation          │
├──────────────────────────┬──────────────────────────────────────────┤
│  TIER 6A: ADAPTIVE       │  TIER 6B: EVOLUTION                     │
│  Profiler (heat map)     │  Genome (system DNA snapshots)           │
│  Selector (lang rec)     │  PatternMiner (hot sequence mining)      │
│  CompilerBridge (recomp) │  SystemMutator (7 strategies)           │
│                          │  CorrectnessValidator (no regressions)   │
│                          │  EvolutionEngine (the main loop)        │
├──────────────────────────┴──────────────────────────────────────────┤
│  TIER 5: TILES — 35 built-in composable computation patterns       │
│  COMPUTE(8) MEMORY(6) CONTROL(6) A2A(6) EFFECT(3) TRANSFORM(6)     │
├─────────────────────────────────────────────────────────────────────┤
│  TIER 4: AGENT RUNTIME (trust, scheduling, resources)              │
├─────────────────────────────────────────────────────────────────────┤
│  TIER 3: A2A PROTOCOL (SEND, ASK, TELL, DELEGATE...)               │
├─────────────────────────────────────────────────────────────────────┤
│  TIER 2: SUPPORTING — Optimizer · JIT · Types · Stdlib · Security  │
├─────────────────────────────────────────────────────────────────────┤
│  TIER 1: CORE PIPELINE                                              │
│  L0: FLUX.MD Parser  →  L1: Frontends (C/Python/Rust)              │
│  →  L2: FIR (SSA IR, 15 types, 42 instructions)                    │
│  →  L3: Bytecode (104 opcodes, 6 formats)                          │
│  →  L4: Micro-VM (64 registers, fetch-decode-execute)              │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Features

- **Polyglot compilation** — Write in any language, mix freely, compile to a single binary
- **Zero-overhead cross-language calls** — Polyglot ABI with region-qualified pointers
- **Native A2A opcodes** — 32 bytecode instructions for agent-to-agent communication
- **5-tier execution** — Interpreter → Baseline JIT → Optimizing JIT → AOT → Silicon
- **8-level fractal hot-reload** — Swap code at any granularity without stopping (TRAIN to CARD)
- **Adaptive language selection** — COOL→Python, WARM→TypeScript, HOT→Rust, HEAT→C+SIMD
- **35 composable tiles** — Reusable computation patterns: chain, nest, parallel, hot-swap
- **Self-evolution engine** — Profile → Discover → Propose → Validate → Commit → Improve
- **6-dimension trust engine** — History, capability, latency, consistency, determinism, audit
- **Capability-based security** — Hierarchical tokens, resource limits, hardware sandbox mode
- **Linear region memory** — Ownership-based, zero-GC, zero-fragmentation

## Quick Start

### Install

```bash
# Clone and install (editable dev mode)
git clone https://github.com/SuperInstance/flux-runtime.git
cd flux-runtime
pip install -e ".[dev]"

# Or just install with zero setup
pip install flux-runtime
```

> **Zero external dependencies** — FLUX runs on Python 3.10+ stdlib alone. The `[dev]` extras add testing/linting tools.

### 🚀 Hello World (start here)

```bash
PYTHONPATH=src python3 examples/01_hello_world.py
```

Three approaches to run FLUX: raw bytecode, FIR builder, and the full C→bytecode pipeline. Produces beautiful terminal output.

### The Self-Improving Demo (recommended)

```bash
flux demo
# or: python -m flux.synthesis.demo
```

This demonstrates the entire system: loading nested modules, profiling execution, classifying heat levels, running the evolution engine, showing language upgrades, and hot-reloading a card mid-set.

### All Examples

```bash
PYTHONPATH=src python3 examples/01_hello_world.py    # 3 ways to run FLUX
PYTHONPATH=src python3 examples/02_polyglot.py        # Mix C + Python in one file
PYTHONPATH=src python3 examples/03_a2a_agents.py      # Agent-to-agent communication
PYTHONPATH=src python3 examples/04_adaptive_profiling.py  # Heat maps & language selection
PYTHONPATH=src python3 examples/05_tile_composition.py    # Composable computation patterns
PYTHONPATH=src python3 examples/06_evolution.py        # Self-improvement engine
PYTHONPATH=src python3 examples/07_full_synthesis.py   # The grand tour — everything wired together
```

### Migrate Your Existing Project

```bash
# Analyze a Python file — see functions, complexity, tile recommendations
PYTHONPATH=src python3 tools/flux_analyze.py my_project/main.py

# Generate FLUX.MD wrappers for an entire project
PYTHONPATH=src python3 tools/flux_migrate.py my_project/ --output flux_output/

# Dry-run to see the migration plan without writing files
PYTHONPATH=src python3 tools/flux_migrate.py my_project/ --dry-run
```

See [Migration Guide](docs/MIGRATION_GUIDE.md) and [Reverse Engineering](docs/REVERSE_ENGINEERING.md) for details.

### Run the Tests

```bash
pytest tests/ -v
# 1848 passed in ~13s
```

### The Synthesizer API

```python
from flux.synthesis import FluxSynthesizer

synth = FluxSynthesizer("my_app")

# Load modules at different nesting levels
synth.load_module("audio/input", source, language="python")
synth.load_module("audio/dsp/filter", source, language="python")

# Profile a workload
synth.record_call("my_app.audio.dsp.filter", duration_ns=50000, calls=100)

# See the heat map
print(synth.get_heatmap())
# {'my_app.audio.dsp.filter': 'HEAT', ...}

# Get language recommendations
for path, rec in synth.get_recommendations().items():
    if rec.should_change:
        print(f"  {path}: {rec.current_language} → {rec.recommended_language}")

# Run self-evolution for 5 generations
report = synth.evolve(generations=5)
print(f"Fitness: {report.initial_fitness:.4f} → {report.final_fitness:.4f}")

# Hot-reload a single card without stopping
synth.hot_swap("audio/dsp/filter", "def improved_filter(s): return [x*2 for x in s]")

# Generate full system report
print(synth.get_system_report().to_text())
```

### Full Pipeline (FLUX.MD → VM)

```python
from flux.pipeline import FluxPipeline

pipeline = FluxPipeline(optimize=True, execute=False)
result = pipeline.run("""
---
title: My Module
---

```c
int add(int a, int b) {
    return a + b;
}
```
""", lang="md")

print(f"Success: {result.success}")
print(f"Functions: {list(result.module.functions.keys())}")
print(f"Bytecode: {len(result.bytecode)} bytes")
```

### Polyglot Compilation (C + Python)

```python
from flux.pipeline import PolyglotCompiler, PolyglotSource

compiler = PolyglotCompiler()
result = compiler.compile([
    PolyglotSource(lang="c", source="int mul(int a, int b) { return a * b; }"),
    PolyglotSource(lang="python", source="def add(a, b):\n    return a + b\n"),
])
print(f"Functions: {list(result.module.functions.keys())}")
```

### VM Execution

```python
from flux.vm.interpreter import Interpreter
from flux.bytecode.opcodes import Op

bytecode = bytes([
    Op.MOVI, 0x01, 10, 0x00,   # MOV R1, 10
    Op.MOVI, 0x02, 20, 0x00,   # MOV R2, 20
    Op.IADD, 0x00, 0x01, 0x02, # R0 = R1 + R2
    Op.HALT,
])
interp = Interpreter(bytecode)
interp.execute()
print(f"R0 = {interp.regs.read_gp(0)}")  # 30
```

## Subsystem Overview

| # | Subsystem | Path | Tests | Description |
|---|-----------|------|:---:|-------------|
| 1 | FIR Core | `src/flux/fir/` | 13 | Universal SSA IR: 15 types, 42 instructions, builder, validator, printer |
| 2 | FLUX.MD Parser | `src/flux/parser/` | 11 | Structured markdown: frontmatter, code blocks, agent directives |
| 3 | Bytecode | `src/flux/bytecode/` | 12 | 104 opcodes, binary encoder/decoder/validator |
| 4 | Micro-VM | `src/flux/vm/` | 25 | 64-register interpreter with memory management |
| 5 | Frontends | `src/flux/frontend/` | 8 | C and Python → FIR compilers |
| 6 | Optimizer | `src/flux/optimizer/` | 4 | Constant folding, DCE, function inlining |
| 7 | JIT Compiler | `src/flux/jit/` | 43 | Inlining, LRU cache, execution tracing, IR opts |
| 8 | Type System | `src/flux/types/` | 76 | Polyglot unification (C/Python/Rust), generics |
| 9 | Standard Library | `src/flux/stdlib/` | 66 | Intrinsics, collections, math, strings, agents |
| 10 | A2A Protocol | `src/flux/protocol/` | 85 | Messages, channels, registry, negotiation, serialization |
| 11 | Agent Runtime | `src/flux/runtime/` | 6 | Agent wrapper, orchestrator, CLI |
| 12 | Security | `src/flux/security/` | 6 | Capability tokens, resource limits, sandbox |
| 13 | Hot Reload | `src/flux/reload/` | 3 | BEAM-inspired dual-version loading with rollback |
| 14 | Module System | `src/flux/modules/` | 72 | 8-level fractal hierarchy, checksum trees, namespaces |
| 15 | Adaptive Subsystem | `src/flux/adaptive/` | 99 | Profiler, language selector, compiler bridge |
| 16 | Tile System | `src/flux/tiles/` | 145 | 35 tiles, DAG graphs, registry, pattern matching |
| 17 | Evolution Engine | `src/flux/evolution/` | 154 | Genome, pattern mining, mutation, validation, loop |
| 18 | Synthesis | `src/flux/synthesis/` | 54 | Top-level orchestrator, reports, demo |
| 19 | E2E Pipeline | `src/flux/pipeline/` | 14 | Full pipeline, polyglot compiler, debugger |
| 20 | A2A Primitives | `src/flux/a2a/` | 10 | Message types, transport, coordinator, trust |
| | **TOTAL** | | **1848** | **106 source modules, 30 test files** |

## File Structure

```
flux-repo/
├── src/flux/
│   ├── __init__.py                     # Package root (v0.1.0)
│   ├── cli.py                         # CLI entry point (compile/run/test)
│   ├── synthesis/                     # TIER 8: Top-level integration
│   │   ├── synthesizer.py            # FluxSynthesizer — the DJ booth
│   │   ├── report.py                 # SystemReport — 7-section reports
│   │   └── demo.py                   # Runnable demo
│   ├── modules/                       # TIER 7: 8-level fractal hierarchy
│   │   ├── granularity.py            # Granularity enum (TRAIN→CARD)
│   │   ├── card.py                   # ModuleCard — atomic hot-reload unit
│   │   ├── container.py              # ModuleContainer — nestable tree
│   │   ├── reloader.py               # FractalReloader — cascade + strategy
│   │   └── namespace.py              # ModuleNamespace — scope isolation
│   ├── adaptive/                      # TIER 6A: Profiling + language selection
│   │   ├── profiler.py               # AdaptiveProfiler (FROZEN→HEAT)
│   │   ├── selector.py               # AdaptiveSelector (heat → language)
│   │   └── compiler_bridge.py        # CompilerBridge (cross-language)
│   ├── evolution/                     # TIER 6B: Self-improvement engine
│   │   ├── genome.py                 # Genome — system DNA snapshots
│   │   ├── pattern_mining.py         # PatternMiner — hot sequence discovery
│   │   ├── mutator.py                # SystemMutator — 7 mutation strategies
│   │   ├── validator.py              # CorrectnessValidator — regression guard
│   │   └── evolution.py              # EvolutionEngine — the main loop
│   ├── tiles/                         # TIER 5: 35 composable patterns
│   │   ├── tile.py                   # Tile, CompositeTile, ParallelTile
│   │   ├── ports.py                  # TilePort, PortDirection
│   │   ├── library.py                # 35 built-in tiles across 6 categories
│   │   ├── graph.py                  # TileGraph — DAG + FIR compilation
│   │   └── registry.py               # TileRegistry — search + alternatives
│   ├── runtime/                       # TIER 4: Agent Runtime
│   │   ├── agent.py                  # Agent (wraps Interpreter)
│   │   └── agent_runtime.py          # AgentRuntime orchestrator
│   ├── protocol/                      # TIER 3: A2A Protocol
│   │   ├── message.py                # Typed message envelopes
│   │   ├── channel.py                # Direct/Broadcast/Topic channels
│   │   ├── registry.py               # Capability-based routing
│   │   ├── negotiation.py            # 4-step trust handshake
│   │   └── serialization.py          # BinaryMessageCodec
│   ├── a2a/                           # A2A primitives
│   │   ├── messages.py               # A2A message types
│   │   ├── transport.py              # Agent transport
│   │   ├── coordinator.py            # Agent coordination
│   │   └── trust.py                  # Trust engine
│   ├── optimizer/                     # TIER 2: Optimization passes
│   │   ├── passes.py                 # CF, DCE, Inline
│   │   └── pipeline.py               # OptimizationPipeline
│   ├── jit/                           # TIER 2: JIT compiler
│   │   ├── compiler.py               # JITCompiler
│   │   ├── cache.py                  # JITCache (LRU, SHA-256)
│   │   ├── tracing.py                # ExecutionTracer
│   │   └── ir_optimize.py            # IR-level optimizations
│   ├── types/                         # TIER 2: Type system
│   │   ├── unify.py                  # TypeUnifier (C/Python/Rust → FIR)
│   │   ├── compat.py                 # Type compatibility
│   │   └── generic.py                # GenericType, TypeVar, TypeScheme
│   ├── stdlib/                        # TIER 2: Standard library
│   │   ├── intrinsics.py             # print, assert, panic, sizeof, etc.
│   │   ├── collections.py            # List, Map, Set, Queue, Stack
│   │   ├── math.py                   # min, max, abs, clamp, lerp, sqrt
│   │   ├── strings.py                # concat, substring, split, etc.
│   │   └── agents.py                 # AgentRegistry, MessageQueue, Scheduler
│   ├── security/                      # TIER 2: Security
│   │   ├── capabilities.py           # Capability tokens
│   │   ├── resource_limits.py        # Resource monitoring
│   │   └── sandbox.py                # Sandbox lifecycle
│   ├── reload/                        # TIER 2: Hot code reload
│   │   └── hot_loader.py             # BEAM-inspired HotLoader
│   ├── parser/                        # TIER 1: L0 Parser
│   │   ├── nodes.py                  # 12 AST node dataclasses
│   │   └── parser.py                 # FluxMDParser class
│   ├── frontend/                      # TIER 1: L1 Frontends
│   │   ├── c_frontend.py             # C → FIR compiler
│   │   └── python_frontend.py        # Python → FIR compiler
│   ├── fir/                           # TIER 1: L2 FIR
│   │   ├── types.py                  # 15 type classes + TypeContext
│   │   ├── values.py                 # SSA Value
│   │   ├── instructions.py           # 42 instruction classes
│   │   ├── blocks.py                 # FIRBlock, FIRFunction, FIRModule
│   │   ├── builder.py                # FIRBuilder
│   │   ├── validator.py              # FIRValidator
│   │   └── printer.py                # print_fir()
│   ├── bytecode/                      # TIER 1: L3 Bytecode
│   │   ├── opcodes.py                # 104-opcode IntEnum
│   │   ├── encoder.py                # FIRModule → bytes
│   │   ├── decoder.py                # bytes → DecodedModule
│   │   └── validator.py              # BytecodeValidator
│   ├── vm/                            # TIER 1: L4 Micro-VM
│   │   ├── registers.py              # 64-register file (GP/FP/VEC)
│   │   ├── memory.py                 # MemoryRegion + MemoryManager
│   │   └── interpreter.py            # Fetch-decode-execute loop
│   ├── compiler/                      # Unified compiler pipeline
│   │   └── pipeline.py               # FluxCompiler (C/Python/MD → bytecode)
│   └── pipeline/                      # E2E pipeline
│       ├── e2e.py                    # FluxPipeline + PipelineResult
│       ├── polyglot.py               # PolyglotCompiler + PolyglotSource
│       └── debug.py                  # PipelineDebugger + disassembler
├── tests/
│   ├── test_synthesis.py             # 54 tests — Integration layer
│   ├── test_evolution.py             # 154 tests — Evolution engine
│   ├── test_tiles.py                 # 145 tests — Tile system
│   ├── test_adaptive.py              # 99 tests — Adaptive subsystem
│   ├── test_protocol.py              # 85 tests — A2A protocol
│   ├── test_type_unify.py            # 76 tests — Type system
│   ├── test_modules.py               # 72 tests — Module system
│   ├── test_stdlib.py                # 66 tests — Standard library
│   ├── test_jit.py                   # 43 tests — JIT compiler
│   ├── test_integration.py           # 14 tests — E2E pipeline
│   ├── test_vm.py                    # 25 tests — VM interpreter
│   ├── test_bytecode.py              # 12 tests — Bytecode
│   ├── test_parser.py                # 11 tests — Parser
│   ├── test_a2a.py                   # 10 tests — A2A primitives
│   ├── test_security.py              # 6 tests — Security
│   ├── test_runtime.py               # 6 tests — Agent runtime
│   ├── test_fir.py                   # 13 tests — FIR
│   ├── test_frontends.py             # 8 tests — Frontends
│   ├── test_optimizer.py             # 4 tests — Optimizer
│   └── test_reload.py                # 3 tests — Hot reload
├── docs/
│   ├── research/                     # 5 research documents
│   │   ├── bootstrap_and_meta.md     # Self-hosting, polyglot runtime
│   │   ├── simulation_and_prediction.md # Predictive optimization
│   │   ├── memory_and_learning.md    # Persistent memory, generalization
│   │   ├── agent_orchestration.md    # Multi-agent topologies, emergence
│   │   └── creative_use_cases.md     # Live coding, art, storytelling
│   ├── RESEARCH_ROADMAP.md           # Comprehensive research roadmap
│   ├── GRADUATION.md                # Vision + design principles
│   └── FLUX_Design_Specification.pdf # 24-page technical spec
├── benchmarks/
│   └── benchmarks.py                 # Performance benchmarks
├── worklog.md                        # Complete development history
├── README.md                         # This file
└── LICENSE                           # MIT License
```

## How to Extend

### Adding a New Tile

```python
from flux.tiles import Tile, TileType, TilePort, PortDirection
from flux.fir.types import TypeContext

ctx = TypeContext()

my_tile = Tile(
    name="my_custom_fft",
    tile_type=TileType.COMPUTE,
    inputs=[TilePort("signal", PortDirection.INPUT, ctx.f32)],
    outputs=[TilePort("spectrum", PortDirection.OUTPUT, ctx.f32)],
    params={"window_size": 1024},
    cost_estimate=5.0,
    abstraction_level=4,
)
synth.register_tile(my_tile)
```

### Adding a New Language Frontend

1. Create `src/flux/frontend/<lang>_frontend.py` that produces `FIRModule`
2. Register in `src/flux/compiler/pipeline.py`
3. Add `LanguageProfile` in `src/flux/adaptive/selector.py`
4. Add type mappings in `src/flux/types/unify.py`

### Adding a New Mutation Strategy

```python
from flux.evolution.genome import MutationStrategy
MutationStrategy.CUSTOM = "custom"
# Then implement handler in SystemMutator.propose_mutations()
```

## Research

FLUX is a research project exploring the convergence of compilation, AI, and art. See:

- **[Research Roadmap](docs/RESEARCH_ROADMAP.md)** — 15 open research questions, 10 suggested projects, extension guides
- **[Graduation Document](docs/GRADUATION.md)** — Vision, design principles, the road ahead
- **[Research Documents](docs/research/)** — 5 deep-dive research memos covering self-hosting, prediction, memory, orchestration, and creative applications

## Synthesis

FLUX integrates the best ideas from:

| Source | Contribution |
|--------|-------------|
| [nexus-runtime](https://github.com/SuperInstance/nexus-runtime) | Intent-to-bytecode pipeline, A2A opcodes, trust engine, cycle-deterministic VM |
| [mask-locked-inference-chip](https://github.com/Lucineer/mask-locked-inference-chip) | Zero-software-stack philosophy, hardware-enforced security |
| GraalVM Truffle | Polyglot interop, multi-language type system |
| LLVM | SSA IR, optimization passes, JIT/AOT |
| WebAssembly | Compact binary, capability security, streaming compilation |
| BEAM VM (Erlang) | Zero-downtime hot code reload |
| Apache Arrow | Zero-copy cross-language data passing |

## Contributing

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Write code + tests (`pytest tests/ -v`)
4. Ensure all 1848 tests pass
5. Commit with descriptive message
6. Open a pull request

### Development Principles

- Every module has comprehensive tests (aim for >90% coverage)
- Use `frozen=True` dataclasses for shared types
- No external dependencies — stdlib only
- The FIR is the universal pivot — all frontends produce it, all backends consume it
- Hot-reload at any granularity must never drop in-flight requests

### Try it Online

Open [`playground/index.html`](playground/index.html) in your browser for an interactive tour of the architecture, live pipeline demo, tile gallery, and evolution visualizer.

## License

MIT
