# FLUX Examples — Practical, Runnable Demos

Welcome to the FLUX example gallery. Each example is a self-contained Python
script that demonstrates a key FLUX concept with beautiful terminal output.

## Quick Start

```bash
cd /home/z/my-project/flux-repo
PYTHONPATH=src python3 examples/01_hello_world.py
```

---

## Examples

### 01 — Hello World
**`examples/01_hello_world.py`**

The simplest possible FLUX programs — three approaches:
- **Raw bytecode**: Hand-encode MOVI + IADD + HALT bytes, run on the VM
- **FIR builder**: Use FIRBuilder to build SSA IR, encode, run
- **Pipeline**: Compile C source through FluxPipeline, execute on VM
- **Bonus**: A bytecode loop computing Sum(1..5)

```bash
PYTHONPATH=src python3 examples/01_hello_world.py
```

**Expected output**: Register dumps, cycle counts, and disassembly for each approach.

---

### 02 — Polyglot
**`examples/02_polyglot.md`** + **`examples/02_polyglot.py`**

FLUX.MD lets you mix C and Python in a single Markdown document. The Python
script parses the `.md` file, extracts code blocks, and compiles each through
the appropriate frontend.

```bash
PYTHONPATH=src python3 examples/02_polyglot.py
```

**Expected output**: Parsed code blocks, compilation results, pipeline execution.

---

### 03 — A2A Agents
**`examples/03_a2a_agents.py`**

Demonstrates agent-to-agent communication using FLUX's binary A2A message
format with 52-byte headers, trust tokens, capabilities, and priority levels.

- Creates 3 agents (Producer → Transformer → Consumer)
- Serializes/deserializes messages
- Shows trust score evolution over exchanges
- Lists all A2A protocol opcodes (0x60–0x7B)

```bash
PYTHONPATH=src python3 examples/03_a2a_agents.py
```

**Expected output**: Message anatomy, binary round-trip verification, trust growth chart.

---

### 04 — Adaptive Profiling
**`examples/04_adaptive_profiling.py`**

Shows the adaptive subsystem that drives language selection:
- Creates a profiler and records calls for a simulated audio pipeline
- Classifies modules by heat level (FROZEN → COOL → WARM → HOT → HEAT)
- Generates language recommendations (Python → C + SIMD)
- Displays a beautiful heatmap table with colored bars

```bash
PYTHONPATH=src python3 examples/04_adaptive_profiling.py
```

**Expected output**: Colored heatmap, heat distribution, language recommendations,
top bottlenecks, speedup estimates, system metrics.

---

### 05 — Tile Composition
**`examples/05_tile_composition.py`**

The tile system is FLUX's reusable computation pattern library:
- Explores the 34 built-in tiles across 6 categories
- Creates a custom `audio_filter` tile with FIR blueprint
- Composes tiles: chain (map → filter), parallel (4× loop)
- Searches the registry, finds alternatives, analyzes costs

```bash
PYTHONPATH=src python3 examples/05_tile_composition.py
```

**Expected output**: Tile library overview, composition examples, cost analysis,
tile type distribution chart.

---

### 06 — Self-Evolution
**`examples/06_evolution.py`**

Demonstrates the evolution engine that makes FLUX self-improving:
- Creates a genome from a system snapshot
- Mines execution traces for hot patterns
- Proposes mutations (language recompilation, tile fusion)
- Validates correctness and commits successful mutations
- Shows fitness progress over generations with colored bars

```bash
PYTHONPATH=src python3 examples/06_evolution.py
```

**Expected output**: Heat classification, discovered patterns, mutation proposals,
fitness progress chart, evolution summary with success rates.

---

### 07 — Full Synthesis (Grand Tour)
**`examples/07_full_synthesis.py`**

The "wow" demo — wires every FLUX subsystem together:
1. Boots a FluxSynthesizer with 12 audio processing modules
2. Profiles a realistic workload
3. Classifies all modules by heat
4. Gets language recommendations per module
5. Hot-reloads a module (zero downtime)
6. Runs 3 generations of self-evolution
7. Identifies top bottlenecks
8. Produces a full system report

```bash
PYTHONPATH=src python3 examples/07_full_synthesis.py
```

**Expected output**: A complete system lifecycle from boot to self-improvement,
with boxes, tables, and colored output at every step.

---

## Architecture Overview

```
FLUX.MD ──→ Parser ──→ FIR Builder ──→ Optimizer ──→ Bytecode ──→ VM
                                    ↓
                              Tile Registry
                                    ↓
                              Evolution Engine
                                    ↓
                              Adaptive Selector
                              (heat → language)
```

## Source Layout

```
src/flux/
├── a2a/messages.py        # Binary A2A message protocol
├── adaptive/
│   ├── profiler.py        # Runtime profiling & heat classification
│   └── selector.py        # Language recommendation engine
├── bytecode/
│   ├── encoder.py         # FIR → bytecode encoder
│   └── opcodes.py         # 100+ opcode definitions
├── compiler/pipeline.py   # Multi-language compilation (C, Python, MD)
├── evolution/             # Self-evolution engine
│   ├── genome.py          # System DNA (snapshots, diff, fitness)
│   ├── mutator.py         # Mutation proposals & application
│   ├── pattern_mining.py  # Hot pattern discovery
│   └── validator.py       # Correctness validation
├── fir/builder.py         # SSA IR builder
├── modules/
│   ├── container.py       # Fractal module hierarchy
│   └── granularity.py     # TRAIN → CARRIAGE → ... → CARD
├── pipeline/e2e.py        # End-to-end compilation pipeline
├── synthesis/synthesizer.py  # The complete FLUX system (the DJ)
├── tiles/
│   ├── library.py         # 34 built-in tiles
│   ├── registry.py        # Tile search & discovery
│   └── tile.py            # Tile, CompositeTile, ParallelTile
└── vm/
    ├── interpreter.py     # Fetch-decode-execute VM
    ├── memory.py          # Memory regions
    └── registers.py       # 64-register file (GP + FP + VEC)
```
