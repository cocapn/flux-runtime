<p align="center">
  <pre>
     ██████╗ ██████╗ ██████╗ ███████╗
     ██╔══██╗██╔═══╝ ██╔══██╗██╔════╝
     ██████╔╝██║     ██║  ██║█████╗
     ██╔═══╝ ██║     ██║  ██║██╔══╝
     ██║     ╚██████╗██████╔╝███████╗
     ╚═╝      ╚═════╝╚═════╝ ╚══════╝

     Fluid Language Universal eXecution
  </pre>
  <p><strong>A self-assembling, self-improving runtime that compiles markdown to bytecode.</strong></p>
  <p>
    <code>pip install flux-runtime</code> &nbsp;·&nbsp;
    <a href="https://github.com/SuperInstance/flux-runtime">GitHub</a> &nbsp;·&nbsp;
    <a href="https://github.com/SuperInstance/flux-runtime/tree/main/playground">Playground</a>
  </p>
  <p>
    <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/tests-1848-brightgreen.svg" alt="Tests: 1848">
    <img src="https://img.shields.io/badge/deps-0-success.svg" alt="Dependencies: 0">
    <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT">
  </p>
</p>

---

## Quick Start

```bash
pip install flux-runtime
```

```bash
flux hello                              # Run the hello world demo
flux compile examples/02_polyglot.md -o output.bin   # Compile FLUX.MD to bytecode
flux run output.bin                     # Execute in the VM
```

That's it. Three commands from zero to running bytecode.

## What is FLUX?

FLUX is a **markdown-to-bytecode runtime** designed for AI agents. You write structured markdown files containing polyglot code blocks — mixing C, Python, Rust, or any language line by line — and the FLUX compiler weaves them into a single optimized, verifiable bytecode that runs on a 64-register Micro-VM.

Unlike traditional compilers, FLUX treats **agents as first-class citizens**: the system profiles itself, discovers hot patterns, recompiles bottleneck modules to faster languages, and evolves — all while running.

> Think of it as going from orchestra (fixed score) → folk (changes nightly) → jazz (improvises) → rock (pushes limits) → **DJ/rave** (layers, adapts, self-improves in real-time).

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  TIER 8: SYNTHESIS — FluxSynthesizer (the DJ booth)    │
│  Wires ALL subsystems together                          │
├─────────────────────────────────────────────────────────┤
│  TIER 7: MODULES — 8-Level Fractal Hot-Reload          │
│  TRAIN → CARRIAGE → LUGGAGE → BAG → ... → CARD        │
├─────────────────────┬───────────────────────────────────┤
│  TIER 6A: ADAPTIVE  │  TIER 6B: EVOLUTION             │
│  Profiler + Selector│  Genome + Mutator + Validator     │
├─────────────────────┴───────────────────────────────────┤
│  TIER 5: TILES — 35 composable computation patterns    │
├─────────────────────────────────────────────────────────┤
│  TIER 4: AGENT RUNTIME — Trust, scheduling, resources  │
├─────────────────────────────────────────────────────────┤
│  TIER 3: A2A PROTOCOL — TELL, ASK, DELEGATE, BROADCAST│
├─────────────────────────────────────────────────────────┤
│  TIER 2: SUPPORT — Optimizer, JIT, Types, Stdlib, Sec  │
├─────────────────────────────────────────────────────────┤
│  TIER 1: CORE — FLUX.MD → FIR (SSA) → Bytecode → VM   │
└─────────────────────────────────────────────────────────┘
```

**Zero external dependencies** — runs on Python 3.10+ stdlib alone.

## Key Concepts

### A2A Protocol
32 native bytecode instructions for agent-to-agent communication. Agents use `TELL`, `ASK`, `DELEGATE`, and `BROADCAST` opcodes to coordinate — with trust gating, capability-based routing, and binary serialization.

### Polyglot Execution
Write in any language, mix freely, compile to a single binary. C, Python, Rust, TypeScript — they all compile to the same FIR (SSA IR) intermediate representation, then to a unified bytecode.

### FIR — SSA IR
The universal pivot point. All frontends produce FIR; all backends consume it. 15 types, 42 instructions, SSA form with proper dominators and terminators.

### Tile System
35 reusable, composable computation patterns across 6 categories: COMPUTE, MEMORY, CONTROL, A2A, EFFECT, TRANSFORM. Chain, parallel, and nest tiles to build complex programs from simple pieces.

## Examples

| # | Example | Description |
|---|---------|-------------|
| 1 | [`01_hello_world.py`](examples/01_hello_world.py) | 3 ways to run FLUX: raw bytecode, FIR builder, full pipeline |
| 2 | [`02_polyglot.py`](examples/02_polyglot.py) | Mix C + Python in one file |
| 3 | [`03_a2a_agents.py`](examples/03_a2a_agents.py) | Agent-to-agent communication |
| 4 | [`04_adaptive_profiling.py`](examples/04_adaptive_profiling.py) | Heat maps & language selection |
| 5 | [`05_tile_composition.py`](examples/05_tile_composition.py) | Composable computation patterns |
| 6 | [`06_evolution.py`](examples/06_evolution.py) | Self-improvement engine |
| 7 | [`07_full_synthesis.py`](examples/07_full_synthesis.py) | The grand tour — everything wired together |

## CLI Reference

```
flux hello                              Run the hello world demo
flux compile <input> -o <output>        Compile source to FLUX bytecode
flux run <bytecode> [--cycles N]        Execute bytecode in the VM
flux test                               Run the full test suite (1848 tests)
flux version                            Print version info
flux demo                               Run the synthesis demo
flux info                               Show system architecture info
flux replay <bytecode> [--verbose]      Replay a bytecode trace
flux migrate <path> [--output-dir DIR]  Migrate source to FLUX.MD format
flux playground                         Open the HTML playground
```

### Usage Examples

```bash
# Compile a C file
flux compile math.c -o math.bin

# Compile a FLUX.MD document
flux compile pipeline.md -o pipeline.bin --verbose

# Run bytecode with a cycle budget
flux run pipeline.bin --cycles 500000

# Migrate an existing Python project
flux migrate src/ --output-dir ./flux_output --verbose

# Migrate a single file
flux migrate calculator.py --lang python
```

## Migration Guide

Bring your existing code to FLUX in one command:

```bash
# Migrate a Python project
flux migrate my_project/ --output-dir ./flux_output

# Migrate a single C file
flux migrate renderer.c --lang c

# Migrate a directory with verbose output
flux migrate src/ --lang auto --verbose
```

The migrator produces structured `FLUX.MD` files with:
- `## module:` header with filename
- `## lang:` language identifier
- `### Function:` / `### Class:` / `### Struct:` sections for each discovered symbol
- Original source preserved in code blocks
- FIR IR mapping comments showing how constructs map to FLUX instructions

See [`tools/flux_migrate.py`](tools/flux_migrate.py) for the full migration tool with complexity analysis, tile recommendations, and hierarchy mapping.

## Full Pipeline

```python
from flux.pipeline import FluxPipeline

pipeline = FluxPipeline(optimize=True)
result = pipeline.run("""
---
title: My Module
---

## fn: main

```c
int add(int a, int b) {
    return a + b;
}
```
""", lang="md")

print(f"Success: {result.success}")
print(f"Bytecode: {len(result.bytecode)} bytes")
```

## For Contributors

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Write code + tests (`pytest tests/ -v`)
4. Ensure all 1848 tests pass
5. Commit with descriptive message
6. Open a pull request

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

## Synthesis

FLUX integrates the best ideas from:

| Source | Contribution |
|--------|-------------|
| [nexus-runtime](https://github.com/SuperInstance/nexus-runtime) | Intent-to-bytecode pipeline, A2A opcodes, trust engine |
| [mask-locked-inference-chip](https://github.com/Lucineer/mask-locked-inference-chip) | Zero-software-stack philosophy, hardware-enforced security |
| GraalVM Truffle | Polyglot interop, multi-language type system |
| LLVM | SSA IR, optimization passes |
| WebAssembly | Compact binary, capability security |
| BEAM VM (Erlang) | Zero-downtime hot code reload |

## License

MIT

## Ecosystem (April 2026)

FLUX is now implemented in 11 languages:

| Repo | Language | Status |
|------|----------|--------|
| [flux-runtime](https://github.com/SuperInstance/flux-runtime) | Python | 1944 tests ✓ |
| [flux-runtime-c](https://github.com/SuperInstance/flux-runtime-c) | C | 39 tests ✓ |
| [flux-core](https://github.com/SuperInstance/flux-core) | Rust | 13 tests ✓ |
| [flux-zig](https://github.com/SuperInstance/flux-zig) | Zig | ⚡ 210ns/iter |
| [flux-js](https://github.com/SuperInstance/flux-js) | JavaScript | 373ns/iter |
| [flux-swarm](https://github.com/SuperInstance/flux-swarm) | Go | 5/5 tests ✓ |
| [flux-wasm](https://github.com/SuperInstance/flux-wasm) | WASM/Rust | In progress |
| [flux-java](https://github.com/SuperInstance/flux-java) | Java | VM + Assembler |
| [flux-py](https://github.com/SuperInstance/flux-py) | Python (minimal) | 64 lines |
| [flux-cuda](https://github.com/SuperInstance/flux-cuda) | CUDA | GPU parallel |
| [flux-llama](https://github.com/SuperInstance/flux-llama) | C/llama.cpp | LLM integration |

## Research
- [flux-research](https://github.com/SuperInstance/flux-research) — 40K words: compiler taxonomy, ISA v2, agent-first design
- [flux-benchmarks](https://github.com/SuperInstance/flux-benchmarks) — Performance comparison across 7 runtimes
- [captains-log](https://github.com/SuperInstance/captains-log) — Oracle1 growth diary + dojo curriculum
- [oracle1-index](https://github.com/SuperInstance/oracle1-index) — 663 repos indexed, status feed

## Key Result
**FLUX C VM is 4.7x faster than CPython for tight arithmetic.**
