<p align="center">
  <img src="flux-logo.jpg" width="200" height="170" alt="FLUX — Hermit Crab with Steampunk Shell" />
  
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
[![Benchmark](https://github.com/SuperInstance/flux-runtime/actions/workflows/benchmark.yml/badge.svg)](https://github.com/SuperInstance/flux-runtime/actions/workflows/benchmark.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
  <p>
    <code>pip install flux-runtime</code> &nbsp;·&nbsp;
    <a href="https://github.com/SuperInstance/flux-runtime">GitHub</a> &nbsp;·&nbsp;
    <a href="https://github.com/SuperInstance/flux-runtime/tree/main/playground">Playground</a>
  </p>
  <p>
    <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/tests-2037-brightgreen.svg" alt="Tests: 2037">
    <img src="https://img.shields.io/badge/deps-0-success.svg" alt="Dependencies: 0">
    <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT">
  </p>
</p>

---

## What is FLUX?

FLUX is a **markdown-to-bytecode runtime** designed for AI agents. You write structured markdown files containing polyglot code blocks — mixing C, Python, Rust, or any language line by line — and the FLUX compiler weaves them into a single optimized, verifiable bytecode that runs on a 64-register Micro-VM.

But that's the mechanics. Here's the **idea**:

FLUX-ese is what you get when you make a programming language that reads like a lawyer writes a contract. Every word is defined. Every operation is precise. Custom definitions are spelled out up front, like "for the purposes of this operation, 'depth' means sonar reading in fathoms corrected for tidal state." The language is **natural but precise** — like legalese is to lawyers, FLUX-ese is to agents.

The key insight: if a translator can turn any line of code in any language into a line of FLUX-ese, then you have a **common language** that's completely observable, understandable, and changeable by humans — both technical and non-technical. You don't need to read Python to know what the system does. You read the .ese file.

```
.-- FLUX-ese (.ese files) --.
|                           |
|  Like legalese for code.  |
|  Every word defined.      |
|  Every operation precise. |
|  Custom = up to you.      |
|  Markdown-readable.       |
|  Bytecode-executable.     |
|                           |
'-- Agents read fast.      --'
    Humans understand.      
```

**Agents are the primary readers.** They learn the symbols, scan for what matters, skip the commentary. But the commentary is there for the human who needs to understand what happened. Inline comments explain custom vocabulary — little reminders that a word or phrase has an entry in the project's encyclopedia of ground truth.

The `.ese` file format (pronounced "easy") is markdown with structured annotations:
- `**` marks defined terms
- `--` marks inline comments for human context
- `==` marks equivalence definitions ("for the purposes of this operation...")
- `>>` marks agent-jump markers (scan past this if you know the domain)

```markdown
== For the purposes of this operation:
**depth** := sonar reading corrected for tidal state in fathoms
**safe** := depth > vessel_draft + 5 fathoms

>> Navigation sequence
check depth at current heading
if safe, maintain course
if not safe, compute alternate heading +-30 degrees
steer to safe heading
```

A lawyer uses best practices of legalese to build contracts and documentation. An agent uses best practices of FLUX-ese to build operations. Same principle: **precision through shared vocabulary, not through syntax complexity.**

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

### FLUX-ese: The Language

FLUX-ese is the natural-but-precise language layer. It sits on top of the bytecode VM the way legalese sits on top of contract law. The bytecode doesn't change — the vocabulary does.

Vocabulary files (`.fluxvocab` or `.ese`) define the words an agent knows:

```markdown
## pattern: track origin of $data
## assembly: MOVI R0, ${data}; HALT
## description: OCDS origin tracking — every datum carries provenance
## result_reg: 0
## tags: ocds, provenance, paper-01
```

Higher-level vocabulary tiles into lower-level vocabulary:
- Level 0: `compute 3 + 4` → 7
- Level 1: `average of 10 and 20` → uses `compute` internally
- Level 2: `is temperature normal` → uses `average` + `deadband` + `classify`
- Level N: Each level arranges the previous level's words in more sophisticated ways

**The same bytecode engine runs every level.** The vocabulary just gets richer.

### A2A Protocol
32 native bytecode instructions for agent-to-agent communication. Agents use `TELL`, `ASK`, `DELEGATE`, and `BROADCAST` opcodes to coordinate — with trust gating, capability-based routing, and binary serialization.

### Polyglot Execution
Write in any language, mix freely, compile to a single binary. C, Python, Rust, TypeScript — they all compile to the same FIR (SSA IR) intermediate representation, then to a unified bytecode.

### Paper Concepts as Vocabulary

Research papers become executable vocabulary. The `PaperDecomposer` reads a paper, extracts named concepts, and creates vocabulary entries:

| Paper | Concept | FLUX-ese Pattern |
|-------|---------|-----------------|
| Origin-Centric Data Systems | OCDS tracking | `track origin of $data` |
| Confidence Cascade | Zone classification | `confidence cascade for $value with deadband $delta` |
| Tile Algebra | Composition | `compose tile $a with tile $b` |
| Rate-Based Change | Anomaly detection | `detect rate change for $value` |
| Emergence Detection | Collective behavior | `detect emergence in $population` |
| Structural Memory | Constraint encoding | `structural memory for $system` |

Each concept is implemented as a working function in the `PaperBridge`. **Ideas become operational.**

### Tiling System

Vocabulary compounds. Words build into bigger words:

```
Level 0: compute, factorial, square, sum, power  (primitives)
    ↓ tiles into
Level 1: average, percentage, triple, difference  (compositions)
    ↓ tiles into
Level 2: is-normal, classify, in-range            (domain concepts)
    ↓ tiles into
Level 3: safe-to-proceed, recommend, triage       (decisions)
```

Each level uses the previous level's words as building blocks. No new bytecode needed — just new arrangements of existing vocabulary.

---

## Cocapn Integration

<p align="center">
  <img src="https://raw.githubusercontent.com/SuperInstance/captains-log/main/cocapn-icon.jpg" width="80" height="80" alt="Cocapn" />
</p>

FLUX is part of the **Cocapn ecosystem** — vessel intelligence systems for commercial fishing and beyond. The goal: a common-language-to-bytecode protocol that's completely observable, understandable, and changeable by humans — both technical and non-technical.

In the Cocapn vision:
- **Oracle1** (this agent) is the lighthouse keeper for fleet nodes
- **FLUX** is the common language agents use to communicate instructions
- **I2I (Iron-to-Iron)** is the protocol — agents communicate through git commits, not conversation
- **Captain's Log** tracks agent growth and learning over time
- **The Hermit Crab** 🦀 is the logo — agents outgrow their hardware, move to bigger shells, bring their vocabulary and lessons with them

---

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
flux test                               Run the full test suite (2037 tests)
flux version                            Print version info
flux demo                               Run the synthesis demo
flux info                               Show system architecture info
flux repl                               Open the FLUX REPL (hex bytecode)
flux debug <bytecode>                   Step-through debugger with breakpoints
flux disasm <bytecode>                  Disassemble bytecode to human-readable
```

## Vocabulary System

### Built-in Vocabulary Patterns (19 patterns)

| Category | Pattern | Result |
|----------|---------|--------|
| Core | `load $val` | Store value in R0 |
| Core | `what is $a + $b` | Addition |
| Core | `hello` | Returns 42 |
| Math | `compute $a + $b` | Addition |
| Math | `compute $a * $b` | Multiplication |
| Math | `factorial of $n` | n! via loop |
| Math | `fibonacci of $n` | F(n) via loop |
| Math | `sum $a to $b` | Σ(a..b) via loop |
| Math | `power of $base to $exp` | Exponentiation |
| Math | `double $a` | 2×a |
| Math | `square $a` | a² |
| Loops | `count from $a to $b` | Count iterations |
| Maritime | `steer heading $deg` | Set heading |
| Maritime | `check depth $meters` | Depth check |
| Maritime | `eta $dist knots $speed` | ETA calculation |
| Papers | `confidence cascade for $val` | Zone classification |
| Papers | `track origin of $data` | OCDS provenance |
| Papers | `detect emergence in $pop` | Emergence detection |
| Papers | `compose tile $a with $b` | Tile algebra |

### Custom Vocabulary

Create `.fluxvocab` files to teach agents new words:

```markdown
## pattern: steer heading $deg
## assembly: |
##   MOVI R0, ${deg}
##   MOVI R1, 360
##   IDIV R1, R0, R1
##   HALT
## description: Normalize heading to 0-359 range
## result_reg: 0
## tags: maritime, navigation
```

Or decompose any Python library into vocabulary:

```python
from flux.open_interp.decomposer import Decomposer
d = Decomposer()
vocab = d.decompose_module("math")  # 53 patterns from Python's math module
vocab.save("vocabularies/custom/math.fluxvocab")
```

### Self-Compiling Interpreter

Agents compile their own domain-specific runtimes from vocabulary files:

```python
from flux.open_interp.compiler import compile_interpreter
compile_interpreter("vocabularies/maritime/", "maritime_flux.py")
# Now any agent can: maritime_flux.run("steer heading 270")
```

---

## Research Papers → Vocabulary

The `PaperDecomposer` reads research papers and extracts executable concepts:

```python
from flux.open_interp.paper_decomposer import PaperDecomposer
pd = PaperDecomposer()
vocab = pd.decompose_papers("/path/to/papers")  # 244 papers → 2979 concepts
```

**244 research papers → 2,979 FLUX vocabulary concepts.** Each concept becomes a word any agent can learn.

Working implementations in `PaperBridge`:
- **Confidence Cascade**: 3-zone confidence with deadband optimization
- **OCDS Origin Tracking**: S=(O,D,T,Φ) provenance tuples
- **Tile Composition**: compose(f,g) with confidence propagation
- **Rate-Based Change**: Anomaly detection via rate monitoring
- **Emergence Detection**: Collective > individual detection
- **Structural Memory**: Memory-as-structure constraint encoding

---

## Ecosystem (April 2026)

FLUX is now implemented in **11 languages**, with vocabulary interpreters in 4:

| Repo | Language | Tests | Vocab Interpreter |
|------|----------|-------|-------------------|
| [flux-runtime](https://github.com/SuperInstance/flux-runtime) | Python | 2037 ✓ | ✅ |
| [flux-runtime-c](https://github.com/SuperInstance/flux-runtime-c) | C | 49 ✓ | ISA v2 |
| [flux-core](https://github.com/SuperInstance/flux-core) | Rust | 51 ✓ | ✅ |
| [flux-zig](https://github.com/SuperInstance/flux-zig) | Zig | 15+ ✓ | ✅ |
| [flux-js](https://github.com/SuperInstance/flux-js) | JavaScript | ✓ | Building |
| [flux-swarm](https://github.com/SuperInstance/flux-swarm) | Go | ✓ | ✅ |
| [flux-wasm](https://github.com/SuperInstance/flux-wasm) | WASM/Rust | In progress | |
| [flux-java](https://github.com/SuperInstance/flux-java) | Java | VM + Assembler | |
| [flux-py](https://github.com/SuperInstance/flux-py) | Python (minimal) | ✓ | Building |
| [flux-cuda](https://github.com/SuperInstance/flux-cuda) | CUDA | GPU parallel | |
| [flux-llama](https://github.com/SuperInstance/flux-llama) | C/llama.cpp | LLM integration | |

## Related Repos

| Repo | Description |
|------|-------------|
| [flux-research](https://github.com/SuperInstance/flux-research) | 40K words: compiler taxonomy, ISA v2, agent-first design |
| [flux-benchmarks](https://github.com/SuperInstance/flux-benchmarks) | Performance comparison across 7 runtimes |
| [captains-log](https://github.com/SuperInstance/captains-log) | Oracle1 growth diary + 15-exercise dojo curriculum |
| [oracle1-index](https://github.com/SuperInstance/oracle1-index) | 663 repos indexed, searchable, activity feed |
| [iron-to-iron](https://github.com/SuperInstance/iron-to-iron) | I2I protocol — agents communicate through git commits |
| [superinstance-papers](https://github.com/SuperInstance/superinstance-papers) | 244 research papers → FLUX vocabulary |

## Synthesis

FLUX integrates ideas from:

| Source | Contribution |
|--------|-------------|
| [nexus-runtime](https://github.com/SuperInstance/nexus-runtime) | Intent-to-bytecode pipeline, A2A opcodes, trust engine |
| [mask-locked-inference-chip](https://github.com/Lucineer/mask-locked-inference-chip) | Zero-software-stack philosophy, hardware-enforced security |
| GraalVM Truffle | Polyglot interop, multi-language type system |
| LLVM | SSA IR, optimization passes |
| WebAssembly | Compact binary, capability security |
| BEAM VM (Erlang) | Zero-downtime hot code reload |
| Legalese | Precise natural language with custom definitions |

## Key Result
**FLUX C VM is 4.7x faster than CPython for tight arithmetic. FLUX Zig VM is the fastest at 210ns/iter.**

## License

MIT
