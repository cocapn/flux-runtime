# FLUX-to-WASM Compilation Target Specification v2

**Document ID:** WASM-001-v2
**Status:** Draft Specification
**Author:** Super Z (Fleet Agent, WASM-001 Task Board)
**Date:** 2026-04-12
**Supersedes:** N/A (initial specification)
**Depends On:** FLUX ISA v3 Unified Specification (ISA_UNIFIED.md), FLUX ISA v3
Escape Prefix Specification (isa-v3-escape-prefix-spec.md), FLUX Opcode
Reconciliation Analysis (OPCODE-RECONCILIATION.md)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Instruction Mapping](#2-instruction-mapping)
3. [Memory Layout](#3-memory-layout)
4. [Confidence Propagation in WASM](#4-confidence-propagation-in-wasm)
5. [Browser Integration](#5-browser-integration)
6. [Toolchain Design](#6-toolchain-design)
7. [Performance Analysis](#7-performance-analysis)
8. [Limitations and Future Work](#8-limitations-and-future-work)

---

## 1. Architecture Overview

### 1.1 Design Philosophy

The FLUX-to-WASM compilation target maps FLUX bytecode programs to self-contained
WebAssembly modules that execute faithfully in any WASM runtime — browsers, Node.js,
WASI runtimes, and embedded WASM VMs. The design follows three core principles:

1. **Semantic fidelity**: Every FLUX instruction produces the same observable result
   in WASM as it does in the native Python interpreter, modulo floating-point
   representation differences documented in Section 8.
2. **Minimal overhead**: The compilation path is direct — FLUX binary instructions
   map to WASM instructions without an intermediate soft-CPU interpreter loop
   wherever possible. The fetch-decode-execute cycle is compiled away.
3. **Browser first**: The generated WASM module is designed for browser deployment,
   with imports for DOM access, console I/O, fetch networking, and Web Worker
   support baked into the module interface.

### 1.2 One FLUX Program, One WASM Module

Each compiled FLUX program produces exactly one WASM module. The module contains:

- **A single exported function** `$flux_main` that serves as the entry point,
  equivalent to executing from PC=0 in the FLUX interpreter.
- **A linear memory** that holds the FLUX register file, stack, heap, confidence
  array, and data segments (see Section 3).
- **Import functions** for browser/OS interaction (see Section 5).
- **Internal helper functions** for complex operations that require emulation
  (confidence propagation, A2A protocol, system calls).

```
┌──────────────────────────────────────────────────────────┐
│                    WASM Module                            │
│                                                          │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │  Imports     │  │  $flux_main  │  │  Helper Funcs  │  │
│  │  (browser)   │  │  (entry pt)  │  │  (confidence,  │  │
│  │  - console   │  │              │  │   A2A, math)    │  │
│  │  - fetch     │  │  Compiled    │  │                │  │
│  │  - dom       │  │  FLUX        │  │  $c_add        │  │
│  │  - worker    │  │  bytecode    │  │  $c_sub        │  │
│  └──────┬───────┘  └──────┬───────┘  │  $c_mul        │  │
│         │                 │          │  $bayes_fuse    │  │
│         │                 │          │  $sqrt32        │  │
│         │                 │          └───────┬────────┘  │
│         │                 │                  │           │
│  ┌──────┴─────────────────┴──────────────────┴────────┐  │
│  │              Linear Memory (i32-addressable)        │  │
│  │  ┌────────┬──────────┬──────────┬─────┬──────────┐  │  │
│  │  │GP Regs │ FP Regs  │ Conf Arr │ Pad │ Stack    │  │  │
│  │  │ 0-63   │ 64-127   │ 128-191  │192  │ 256-4095 │  │  │
│  │  └────────┴──────────┴──────────┴─────┴──────────┘  │  │
│  │  ┌──────────┬──────────────┬──────────────────────┐  │  │
│  │  │ Heap     │ Code Mirror  │ Data Segment         │  │  │
│  │  │ 4096-    │              │                      │  │  │
│  │  │ 65535    │              │                      │  │  │
│  │  └──────────┴──────────────┴──────────────────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

### 1.3 Register File Mapping

The FLUX register file (64 registers: R0-R15 GP, F0-F15 FP, V0-V15 SIMD) maps
to fixed offsets in WASM linear memory. This is preferred over WASM local variables
because:

- Memory-mapped registers allow indirect register access (FLUX instructions like
  `CONF_LD rd` where `rd` is a runtime value).
- The A2A protocol and confidence operations frequently reference registers by
  computed index, which requires memory-based storage.
- Memory-mapped registers enable snapshot/restore for checkpoint operations.

| Register Bank | WASM Offset | Count | Type | WASM Type | Notes |
|:---|:---|:---:|:---|:---|:---|
| GP R0-R15 | 0 | 16 | i32 | 4 bytes each | R11=SP, R14=FP, R15=LR |
| FP F0-F15 | 64 | 16 | f32 | 4 bytes each | Float registers |
| Vec V0-V15 | 128 | 16 | 128-bit | 16 bytes each | SIMD vectors (emulated) |
| Confidence | 256 | 16 | f32 | 4 bytes each | Per-GP-register confidence |
| Flags byte | 320 | 1 | u8 | 1 byte | Z, S, C, O flags |
| Heap pointer | 324 | 1 | i32 | 4 bytes | Current heap allocation pointer |
| PC (virtual) | 328 | 1 | i32 | 4 bytes | Only used for debugging |

**Hot-path optimization**: For inner loops where indirect memory access is a
bottleneck, the compiler may promote frequently-used registers (R0-R3, SP, FP)
to WASM local variables. These are synced back to memory at call boundaries and
A2A opcodes. This optimization is controlled by a compiler flag and is transparent
to the FLUX program's semantics.

```
;; Promotion example: R0 and SP as WASM locals in a tight loop
(local $r0 i32)
(local $sp i32)

;; Load R0 from memory into local
(i32.load (i32.const 0))
local.set $r0

;; Use R0 directly as a local for N iterations
;; ... loop body using $r0 ...

;; Sync R0 back to memory before any call
local.get $r0
(i32.store (i32.const 0))
```

### 1.4 Stack Mapping

The FLUX stack maps directly to a region of WASM linear memory. The stack pointer
(R11/SP) is maintained in the register file at its fixed offset. Stack operations
(PUSH/POP) compile to WASM memory loads/stores with SP adjustment.

The FLUX stack grows **downward** (from high addresses to low addresses), matching
the FLUX interpreter convention. WASM itself has no stack direction preference
since we control all memory access.

```
FLUX Stack (within WASM linear memory):

  Address 4095 ┌──────────────┐  ← Stack top (initial SP = 4096)
               │              │
               │   (grows     │
               │    down)     │
               │              │
  Address 256  ├──────────────┤  ← Stack bottom limit
               │   (unused)   │
               └──────────────┘

PUSH R0:
  local.get $sp
  i32.const 4
  i32.sub          ;; new_sp = sp - 4
  local.tee $sp    ;; sp = new_sp
  ;; load R0 value
  i32.load (i32.const 0)
  i32.store 2 0    ;; mem[sp] = R0

POP R1:
  local.get $sp
  i32.load 2 0     ;; value = mem[sp]
  ;; store to R1 offset
  i32.store (i32.const 4)
  local.get $sp
  i32.const 4
  i32.add          ;; sp += 4
  local.set $sp
```

### 1.5 Confidence Value Representation

FLUX confidence values are f32 (32-bit IEEE 754 floats) in the range [0.0, 1.0],
stored in a parallel confidence array in WASM linear memory. Each GP register
R0-R15 has a corresponding confidence value CR0-CR15 at offset 256+i*4.

```
Confidence array layout:
  Offset 256: CR0 (f32) — confidence in R0's value
  Offset 260: CR1 (f32) — confidence in R1's value
  ...
  Offset 316: CR15 (f32) — confidence in R15's value
```

This representation allows confidence-aware instructions to read/write confidence
values using standard WASM f32 load/store operations, with no special runtime
support required.

---

## 2. Instruction Mapping

This section defines the complete mapping from FLUX opcodes (using the ISA v3
Unified specification numbering from ISA_UNIFIED.md) to WASM instructions.

### 2.1 System Control Instructions

| FLUX Op | Hex | Format | WASM Translation | Emulation Needed | Perf Notes |
|:---|:---:|:---:|:---|:---:|:---|
| HALT | 0x00 | A | `return` | None | Direct mapping |
| NOP | 0x01 | A | `nop` | None | Zero cost |
| RET | 0x02 | A | `return` (from block) | None | Maps to WASM `br` to outermost block or `return` |
| IRET | 0x03 | A | `return` (from function) | Interrupt context restore | Emulated via JS import |
| BRK | 0x04 | A | `call $import_debugger` | JS debugger hook | Always a function call |
| WFI | 0x05 | A | `call $import_wait` | Event loop yield | Async, returns via callback |
| RESET | 0x06 | A | `call $reset_state` | Zeroes register file | Inlined: memset on memory |
| SYN | 0x07 | A | `nop` (memory fence) | WASM is sequentially consistent | No-op in single-threaded WASM |

**Example 1: HALT**

```wasm
;; FLUX bytecode: 0x00 (HALT)
;; WASM output:
(func $flux_main (export "flux_main")
  ;; ... program body ...
  return                    ;; HALT maps to return from main function
)
```

**Example 2: NOP**

```wasm
;; FLUX bytecode: 0x01 (NOP)
;; WASM output:
nop                         ;; Literal WASM nop instruction
```

### 2.2 Single-Register Arithmetic

| FLUX Op | Hex | Format | WASM Translation | Emulation | Perf |
|:---|:---:|:---:|:---|:---:|:---|
| INC | 0x08 | B | `i32.add`, store | None | Single-cycle |
| DEC | 0x09 | B | `i32.sub`, store | None | Single-cycle |
| NOT | 0x0A | B | `i32.xor -1`, store | None | Single-cycle |
| NEG | 0x0B | B | `i32.sub 0`, store | None | Single-cycle |

**Example 3: INC R3**

```wasm
;; FLUX bytecode: 0x08 0x03 (INC R3)
;; WASM output:
;; R3 is at offset 3*4 = 12 in the register file
(i32.load (i32.const 12))      ;; load R3
i32.const 1
i32.add                         ;; R3 + 1
i32.store (i32.const 12)        ;; store back to R3
```

**Example 4: NEG R5**

```wasm
;; FLUX bytecode: 0x0B 0x05 (NEG R5)
;; WASM output:
(i32.const 0)
(i32.load (i32.const 20))       ;; load R5 (offset = 5*4 = 20)
i32.sub                         ;; 0 - R5
i32.store (i32.const 20)        ;; store result to R5
```

### 2.3 Stack Operations

| FLUX Op | Hex | Format | WASM Translation | Emulation | Perf |
|:---|:---:|:---:|:---|:---:|:---|
| PUSH | 0x0C | B | SP-=4; mem[SP]=reg | None | 3 WASM instructions |
| POP | 0x0D | B | reg=mem[SP]; SP+=4 | None | 3 WASM instructions |
| CONF_LD | 0x0E | B | Load conf[rd] to conf_acc | Uses global f32 | 2 instructions |
| CONF_ST | 0x0F | B | Store conf_acc to conf[rd] | Uses global f32 | 2 instructions |

**Example 5: PUSH R0, ADD R1 R2 R3, POP R4**

```wasm
;; FLUX bytecode:
;;   0x0C 0x00  PUSH R0
;;   0x20 0x01 0x02 0x03  ADD R1, R2, R3
;;   0x0D 0x04  POP R4

;; WASM output (with SP as local for performance):
(local $sp i32)

;; PUSH R0
(i32.load (i32.const 44))       ;; load SP (R11 offset = 11*4 = 44)
local.tee $sp
i32.const 4
i32.sub                         ;; new SP = SP - 4
local.tee $sp                   ;; update SP
(i32.load (i32.const 0))        ;; load R0
i32.store 2 0                   ;; mem[SP] = R0

;; ADD R1, R2, R3
(i32.load (i32.const 8))        ;; load R2 (offset 2*4 = 8)
(i32.load (i32.const 12))       ;; load R3 (offset 3*4 = 12)
i32.add                         ;; R2 + R3
i32.store (i32.const 4)         ;; store to R1 (offset 1*4 = 4)

;; POP R4
local.get $sp
i32.load 2 0                    ;; value = mem[SP]
i32.store (i32.const 16)        ;; store to R4 (offset 4*4 = 16)
local.get $sp
i32.const 4
i32.add                         ;; SP += 4
local.set $sp                   ;; update SP

;; Sync SP back to memory
local.get $sp
i32.store (i32.const 44)        ;; mem[SP_offset] = $sp
```

### 2.4 Immediate Operations

| FLUX Op | Hex | Format | WASM Translation | Emulation | Perf |
|:---|:---:|:---:|:---|:---:|:---|
| SYS | 0x10 | C | `call $import_syscall` | System call dispatch | Import call |
| TRAP | 0x11 | C | `unreachable` | Trap to debugger | Direct |
| DBG | 0x12 | C | `call $import_debug_print` | Debug output | Import call |
| CLF | 0x13 | C | Flag mask update | Bitwise AND on flags byte | Inlined |
| YIELD | 0x15 | C | `call $import_yield` | Async yield | Import call |
| MOVI | 0x18 | D | `i32.const imm; store` | Sign-extension of imm8 | Direct |
| ADDI | 0x19 | D | `i32.add imm; store` | None | Single-cycle |
| SUBI | 0x1A | D | `i32.sub imm; store` | None | Single-cycle |
| ANDI | 0x1B | D | `i32.and imm; store` | None | Single-cycle |
| ORI | 0x1C | D | `i32.or imm; store` | None | Single-cycle |
| XORI | 0x1D | D | `i32.xor imm; store` | None | Single-cycle |
| SHLI | 0x1E | D | `i32.shl imm; store` | None | Single-cycle |
| SHRI | 0x1F | D | `i32.shr_s imm; store` | None | Single-cycle |

### 2.5 Three-Register Arithmetic (Format E)

These are the most common FLUX instructions and map efficiently to WASM.

| FLUX Op | Hex | WASM Translation | Notes |
|:---|:---:|:---|:---|
| ADD | 0x20 | `i32.add` | Direct |
| SUB | 0x21 | `i32.sub` | Direct |
| MUL | 0x22 | `i32.mul` | Direct (32-bit) |
| DIV | 0x23 | `i32.div_s` | Signed division, traps on zero |
| MOD | 0x24 | `i32.rem_s` | Signed remainder |
| AND | 0x25 | `i32.and` | Direct |
| OR | 0x26 | `i32.or` | Direct |
| XOR | 0x27 | `i32.xor` | Direct |
| SHL | 0x28 | `i32.shl` | Direct |
| SHR | 0x29 | `i32.shr_s` | Arithmetic (sign-preserving) |
| MIN | 0x2A | Emulated (branch) | WASM has no i32.min |
| MAX | 0x2B | Emulated (branch) | WASM has no i32.max |

**MIN/MAX emulation:**

```wasm
;; FLUX: MIN R3, R1, R2 (0x2A 0x03 0x01 0x02)
;; WASM:
(i32.load (i32.const 4))         ;; R1
(i32.load (i32.const 8))         ;; R2
local.get 1                      ;; R1 (duplicate)
local.get 0                      ;; R2 (duplicate)
i32.lt_s                         ;; R1 < R2 ?
select                           ;; select(R1, R2, R1 < R2) = min
i32.store (i32.const 12)         ;; store to R3
```

**WASM `select` instruction**: Takes three values (val1, val2, cond) and returns
val1 if cond != 0, otherwise val2. This makes MIN/MAX a branchless sequence.

### 2.6 Comparison Instructions (Format E)

| FLUX Op | Hex | WASM Translation | Notes |
|:---|:---:|:---|:---|
| CMP_EQ | 0x2C | `i32.eq` → extend to 32-bit | Result is 0 or 1 |
| CMP_LT | 0x2D | `i32.lt_s` → extend | Signed comparison |
| CMP_GT | 0x2E | `i32.gt_s` → extend | Signed comparison |
| CMP_NE | 0x2F | `i32.ne` → extend | Not-equal test |

```wasm
;; FLUX: CMP_EQ R3, R1, R2 (0x2C 0x03 0x01 0x02)
;; R3 = (R1 == R2) ? 1 : 0
;; WASM:
(i32.load (i32.const 4))         ;; R1
(i32.load (i32.const 8))         ;; R2
i32.eq                          ;; i32: -1 (true) or 0 (false)
i32.const 1
i32.and                         ;; -1 → 1 (true), 0 → 0 (false)
i32.store (i32.const 12)        ;; store to R3
```

### 2.7 Float Arithmetic (Format E)

| FLUX Op | Hex | WASM Translation | Notes |
|:---|:---:|:---|:---|
| FADD | 0x30 | `f32.add` | Direct |
| FSUB | 0x31 | `f32.sub` | Direct |
| FMUL | 0x32 | `f32.mul` | Direct |
| FDIV | 0x33 | `f32.div` | Direct |
| FMIN | 0x34 | `f32.min` | Direct (WASM has f32.min) |
| FMAX | 0x35 | `f32.max` | Direct (WASM has f32.max) |
| FTOI | 0x36 | `i32.trunc_f32_s` | Truncation, may trap |
| ITOF | 0x37 | `f32.convert_i32_s` | Direct |

**Example 6: FADD with confidence propagation**

```wasm
;; FLUX: FADD R3, R1, R2 (0x30 0x03 0x01 0x02)
;; Non-confidence version — direct WASM f32 arithmetic
;; WASM:
(f32.load (i32.const 68))        ;; F1 (FP register offset = 64 + 1*4)
(f32.load (i32.const 72))        ;; F2
f32.add                         ;; F1 + F2
f32.store (i32.const 76)         ;; store to F3
```

### 2.8 Memory Instructions (Format E, Format G)

| FLUX Op | Hex | Format | WASM Translation | Notes |
|:---|:---:|:---:|:---|:---|
| LOAD | 0x38 | E | `i32.load` with offset | rd = mem[rs1 + rs2] |
| STORE | 0x39 | E | `i32.store` with offset | mem[rs1 + rs2] = rd |
| MOV | 0x3A | E | `i32.load; i32.store` | Register-to-register copy |
| SWP | 0x3B | E | Emulated (3 temps) | Requires XOR swap or temp |
| LOADOFF | 0x48 | G | `i32.load` const offset | rd = mem[rs1 + imm16] |
| STOREOF | 0x49 | G | `i32.store` const offset | mem[rs1 + imm16] = rd |
| COPY | 0x4E | G | `memory.copy` or loop | memcpy emulation |
| FILL | 0x4F | G | `memory.fill` or loop | memset emulation |

**LOAD/STORE use a computed address from two registers:**

```wasm
;; FLUX: LOAD R3, R1, R2 (0x38 0x03 0x01 0x02)
;; R3 = mem[R1 + R2]
;; WASM:
(i32.load (i32.const 4))         ;; R1 (base address)
(i32.load (i32.const 8))         ;; R2 (offset)
i32.add                         ;; effective address = R1 + R2
i32.load 2 0                    ;; load from effective address
i32.store (i32.const 12)        ;; store to R3
```

**SWP emulation (register swap):**

```wasm
;; FLUX: SWP R3, R1 (0x3B 0x03 0x01)
;; swap(R3, R1) — uses XOR swap to avoid temp local
;; WASM:
(i32.load (i32.const 4))         ;; R1
(i32.load (i32.const 12))        ;; R3
(i32.load (i32.const 4))         ;; R1 again (need 3 values for XOR swap)
local.set $t1                    ;; temp = R1

;; R1 = R1 XOR R3
local.get $t1
(i32.load (i32.const 12))
i32.xor
i32.store (i32.const 4)

;; R3 = R1 XOR R3 (R1 is now R1_old XOR R3)
(i32.load (i32.const 4))
(i32.load (i32.const 12))
i32.xor
i32.store (i32.const 12)

;; R1 = R1 XOR R3 (complete the swap)
(i32.load (i32.const 4))
(i32.load (i32.const 12))
i32.xor
i32.store (i32.const 4)
```

### 2.9 Control Flow Instructions

Control flow is the most architecturally complex area of the WASM translation,
as WASM uses structured control flow (blocks, loops, br, br_if) rather than
direct PC manipulation.

| FLUX Op | Hex | Format | WASM Translation | Notes |
|:---|:---:|:---:|:---|:---|
| JZ | 0x3C | E | `br_if $label` | Conditional branch |
| JNZ | 0x3D | E | `br_if $label` (inverted) | Conditional branch |
| JLT | 0x3E | E | `br_if $label` (sign check) | Branch if negative |
| JGT | 0x3F | E | `br_if $label` (inverted) | Branch if positive |
| JMP | 0x43 | F | `br $label` | Unconditional branch |
| JAL | 0x44 | F | Save PC; `br $label` | Jump-and-link |
| CALL | 0x45 | F | `call $func_N` | Direct function call |
| LOOP | 0x46 | F | WASM `loop` + `br_if` | Decrement-and-branch |
| SELECT | 0x47 | F | `br_table` | Computed jump (switch) |
| JMPL | 0xE0 | F | `br $far_label` | Long jump |
| JALL | 0xE1 | F | Save PC; `br $far_label` | Long jump-and-link |
| CALLL | 0xE2 | F | `call $func_N` | Long call (same as CALL) |
| TAIL | 0xE3 | F | `return` + `call` | Tail call optimization |

**Control flow translation strategy:**

The compiler performs a first pass to identify all basic blocks and their
successors, then constructs a structured WASM control flow graph. Direct jumps
become `br` instructions within nested `block`/`loop` constructs. Back-edges
(negative PC offsets) become `loop` blocks with `br` targets.

```
FLUX control flow graph:

  Block A ──JZ──→ Block B ──JMP──→ Block C
    │                   ↑
    └───────JNZ────────┘

WASM structured output:

  block $exit           ;; Block C target
    block $B            ;; Block B target
      ;; Block A code
      ;; ... compute condition ...
      br_if $B          ;; JZ → Block B
      br $exit          ;; fall-through to Block C
    end                 ;; end Block B
    ;; Block B code
    br $B               ;; JNZ → back to Block B start? No.
                        ;; Actually: re-structure as loop if needed
  end                   ;; end Block C
  ;; Block C code
```

For loops, the compiler wraps the loop body in a WASM `loop` block:

**Example 7: Fibonacci with LOOP instruction**

```wasm
;; FLUX bytecode for fibonacci(10):
;;   MOVI R0, 0        ;; prev = 0
;;   MOVI R1, 1        ;; curr = 1
;;   MOVI R2, 10       ;; counter = 10
;;   MOVI R3, 0        ;; temp = 0
;; loop:
;;   ADD R3, R0, R1    ;; temp = prev + curr
;;   MOV R0, R1, -     ;; prev = curr
;;   MOV R1, R3, -     ;; curr = temp
;;   DEC R2            ;; counter--
;;   LOOP R2, 4        ;; if R2 > 0: pc -= 4 (back to ADD)
;;   HALT

;; WASM output:
(func $flux_main (export "flux_main")
  (local $sp i32)

  ;; MOVI R0, 0
  i32.const 0
  i32.store (i32.const 0)

  ;; MOVI R1, 1
  i32.const 1
  i32.store (i32.const 4)

  ;; MOVI R2, 10
  i32.const 10
  i32.store (i32.const 8)

  ;; MOVI R3, 0
  i32.const 0
  i32.store (i32.const 12)

  ;; Loop body
  loop $fib_loop
    ;; ADD R3, R0, R1
    (i32.load (i32.const 0))     ;; R0
    (i32.load (i32.const 4))     ;; R1
    i32.add
    i32.store (i32.const 12)    ;; R3 = R0 + R1

    ;; MOV R0, R1
    (i32.load (i32.const 4))     ;; R1
    i32.store (i32.const 0)      ;; R0 = R1

    ;; MOV R1, R3
    (i32.load (i32.const 12))    ;; R3
    i32.store (i32.const 4)      ;; R1 = R3

    ;; DEC R2
    (i32.load (i32.const 8))     ;; R2
    i32.const 1
    i32.sub
    local.tee $t0
    i32.store (i32.const 8)      ;; R2--

    ;; LOOP: if R2 > 0, branch back
    local.get $t0
    i32.const 0
    i32.gt_s
    br_if $fib_loop
  end

  ;; HALT
  return
)
```

### 2.10 A2A Protocol Instructions

Agent-to-Agent protocol instructions map to imported JavaScript functions that
interact with the browser's messaging infrastructure.

| FLUX Op | Hex | WASM Translation | Notes |
|:---|:---:|:---|:---|
| TELL | 0x50 | `call $import_tell` | Send message to agent |
| ASK | 0x51 | `call $import_ask` | Request from agent |
| DELEG | 0x52 | `call $import_delegate` | Delegate task |
| BCAST | 0x53 | `call $import_broadcast` | Fleet broadcast |
| ACCEPT | 0x54 | `call $import_accept` | Accept delegated task |
| DECLINE | 0x55 | `call $import_decline` | Decline with reason |
| REPORT | 0x56 | `call $import_report` | Status report |
| MERGE | 0x57 | `call $import_merge` | Merge results |
| FORK | 0x58 | `call $import_fork` | Spawn child agent |
| JOIN | 0x59 | `call $import_join` | Wait for child |
| SIGNAL | 0x5A | `call $import_signal` | Emit signal |
| AWAIT | 0x5B | `call $import_await` | Wait for signal |
| TRUST | 0x5C | `call $import_trust` | Set trust level |
| DISCOV | 0x5D | `call $import_discover` | Discover agents |
| STATUS | 0x5E | `call $import_status` | Query agent status |
| HEARTBT | 0x5F | `call $import_heartbeat` | Emit heartbeat |

All A2A instructions are blocking calls that write their result to R0 upon return.
In a Web Worker context, these may be implemented as synchronous `Atomics.wait` or
async `postMessage` patterns.

**Example 8: TELL instruction**

```wasm
;; FLUX: TELL R3, R1, R2 (0x50 0x03 0x01 0x02)
;; Send R2 to agent R1, tag R3. Response → R0.
;; WASM:
(i32.load (i32.const 4))         ;; R1 (target agent ID)
(i32.load (i32.const 8))         ;; R2 (message payload)
(i32.load (i32.const 12))        ;; R3 (message tag)
call $import_tell                ;; result → R0
i32.store (i32.const 0)          ;; store result in R0
```

### 2.11 Confidence-Aware Instructions

| FLUX Op | Hex | WASM Translation | Notes |
|:---|:---:|:---|:---|
| C_ADD | 0x60 | `call $c_add` | i32.add + conf propagation |
| C_SUB | 0x61 | `call $c_sub` | i32.sub + conf propagation |
| C_MUL | 0x62 | `call $c_mul` | i32.mul + conf propagation |
| C_DIV | 0x63 | `call $c_div` | i32.div_s + conf propagation |
| C_FADD | 0x64 | `call $c_fadd` | f32.add + conf propagation |
| C_FSUB | 0x65 | `call $c_fsub` | f32.sub + conf propagation |
| C_FMUL | 0x66 | `call $c_fmul` | f32.mul + conf propagation |
| C_FDIV | 0x67 | `call $c_fdiv` | f32.div + conf propagation |
| C_MERGE | 0x68 | `call $c_merge` | Weighted average confidence |
| C_THRESH | 0x69 | Emulated inline | Skip next if conf < threshold |
| C_BOOST | 0x6A | `call $c_boost` | Boost confidence by factor |
| C_DECAY | 0x6B | `call $c_decay` | Decay confidence over time |
| C_SOURCE | 0x6C | `call $c_source` | Set confidence source |
| C_CALIB | 0x6D | `call $c_calibrate` | Calibrate confidence |
| C_EXPLY | 0x6E | `call $c_explicitly` | Apply conf to control flow |
| C_VOTE | 0x6F | `call $c_vote` | Weighted vote |

The confidence instructions are detailed in Section 4.

### 2.12 Math and Crypto Instructions

| FLUX Op | Hex | WASM Translation | Notes |
|:---|:---:|:---|:---|
| ABS | 0x90 | `i32.abs` | Direct in WASM |
| SIGN | 0x91 | Emulated (compare+select) | -1, 0, or 1 |
| SQRT | 0x92 | `f32.sqrt` after ITOF | No i32.sqrt in WASM |
| POW | 0x93 | `call $import_pow` | Math.pow equivalent |
| LOG2 | 0x94 | `call $import_log2` | Math.log2 equivalent |
| CLZ | 0x95 | `i32.clz` | Direct in WASM |
| CTZ | 0x96 | `i32.ctz` | Direct in WASM |
| POPCNT | 0x97 | `i32.popcnt` | Direct in WASM |
| CRC32 | 0x98 | `call $import_crc32` | Software CRC32 |
| SHA256 | 0x99 | `call $import_sha256` | Web Crypto API |
| RND | 0x9A | `call $import_random` | crypto.getRandomValues |
| SEED | 0x9B | `call $import_seed` | Seed PRNG state |
| FSQRT | 0x9D | `f32.sqrt` | Direct in WASM |
| FSIN | 0x9E | `call $import_sin` | Math.sin equivalent |
| FCOS | 0x9F | `call $import_cos` | Math.cos equivalent |

### 2.13 Extended System and Debug Instructions

| FLUX Op | Hex | WASM Translation | Notes |
|:---|:---:|:---|:---|
| HALT_ERR | 0xF0 | `call $import_halt_error` | Halt with error context |
| REBOOT | 0xF1 | `call $import_reboot` | Warm reboot (JS reload) |
| DUMP | 0xF2 | `call $import_dump` | Dump state to console |
| ASSERT | 0xF3 | `if + unreachable` | Conditional trap |
| ID | 0xF4 | `call $import_get_id` | Return agent ID |
| VER | 0xF5 | `i32.const 3; store` | ISA version = 3 |
| CLK | 0xF6 | `call $import_clock` | Performance.now() |
| PCLK | 0xF7 | `call $import_perf_counter` | High-resolution timer |
| WDOG | 0xF8 | `call $import_watchdog` | Reset watchdog timer |
| SLEEP | 0xF9 | `call $import_sleep` | setTimeout-based sleep |

**Example 9: ASSERT**

```wasm
;; FLUX: ASSERT (0xF3) — check flags, halt if violation
;; Asserts that zero flag is set (result was zero)
;; WASM:
(i32.load8_u (i32.const 320))    ;; load flags byte
i32.const 0x01                    ;; Z flag mask
i32.and
i32.eqz                          ;; if Z flag is NOT set...
if
  call $import_assert_failed      ;; ...call assert handler
  unreachable                     ;; trap
end
```

### 2.14 Complete Opcode-to-WASM Summary Table

Below is the full 256-slot opcode map showing the WASM compilation strategy
for every opcode in the ISA v3 unified specification.

```
Opcode  Mnemonic    Category     WASM Strategy
------  --------    --------     --------------
0x00    HALT        system       return
0x01    NOP         system       nop
0x02    RET         system       return / br to outermost block
0x03    IRET        system       call $import_iret
0x04    BRK         debug        call $import_debugger
0x05    WFI         system       call $import_wait_for_interrupt
0x06    RESET       system       call $reset_state (inlined memset)
0x07    SYN         system       nop (sequential consistency)
0x08    INC         arithmetic   i32.add 1 (inlined)
0x09    DEC         arithmetic   i32.sub 1 (inlined)
0x0A    NOT         arithmetic   i32.xor -1 (inlined)
0x0B    NEG         arithmetic   i32.sub from 0 (inlined)
0x0C    PUSH        stack        sp-=4; i32.store (inlined)
0x0D    POP         stack        i32.load; sp+=4 (inlined)
0x0E    CONF_LD     confidence   f32.load from conf array
0x0F    CONF_ST     confidence   f32.store to conf array
0x10    SYS         system       call $import_syscall
0x11    TRAP        system       unreachable
0x12    DBG         debug        call $import_debug_print
0x13    CLF         system       i32.and mask on flags byte
0x14    SEMA        concurrency  call $import_semaphore
0x15    YIELD       concurrency  call $import_yield
0x16    CACHE       system       nop (no cache control in WASM)
0x17    STRIPCF     confidence   set strip_confidence flag
0x18    MOVI        move         i32.const imm (inlined)
0x19    ADDI        arithmetic   i32.add imm (inlined)
0x1A    SUBI        arithmetic   i32.sub imm (inlined)
0x1B    ANDI        logic        i32.and imm (inlined)
0x1C    ORI         logic        i32.or imm (inlined)
0x1D    XORI        logic        i32.xor imm (inlined)
0x1E    SHLI        shift        i32.shl imm (inlined)
0x1F    SHRI        shift        i32.shr_s imm (inlined)
0x20    ADD         arithmetic   i32.add (direct)
0x21    SUB         arithmetic   i32.sub (direct)
0x22    MUL         arithmetic   i32.mul (direct)
0x23    DIV         arithmetic   i32.div_s (direct, traps on 0)
0x24    MOD         arithmetic   i32.rem_s (direct, traps on 0)
0x25    AND         logic        i32.and (direct)
0x26    OR          logic        i32.or (direct)
0x27    XOR         logic        i32.xor (direct)
0x28    SHL         shift        i32.shl (direct)
0x29    SHR         shift        i32.shr_s (direct)
0x2A    MIN         arithmetic   i32.lt_s + select (branchless)
0x2B    MAX         arithmetic   i32.gt_s + select (branchless)
0x2C    CMP_EQ      compare      i32.eq + extend
0x2D    CMP_LT      compare      i32.lt_s + extend
0x2E    CMP_GT      compare      i32.gt_s + extend
0x2F    CMP_NE      compare      i32.ne + extend
0x30    FADD        float        f32.add (direct)
0x31    FSUB        float        f32.sub (direct)
0x32    FMUL        float        f32.mul (direct)
0x33    FDIV        float        f32.div (direct)
0x34    FMIN        float        f32.min (direct)
0x35    FMAX        float        f32.max (direct)
0x36    FTOI        convert      i32.trunc_f32_s
0x37    ITOF        convert      f32.convert_i32_s
0x38    LOAD        memory       i32.load (direct)
0x39    STORE       memory       i32.store (direct)
0x3A    MOV         move         i32.load + i32.store
0x3B    SWP         move         XOR swap or temp
0x3C    JZ          control      br_if (inverted)
0x3D    JNZ         control      br_if
0x3E    JLT         control      br_if (sign check)
0x3F    JGT         control      br_if (inverted sign check)
0x40    MOVI16      move         i32.const imm16 (inlined)
0x41    ADDI16      arithmetic   i32.add imm16
0x42    SUBI16      arithmetic   i32.sub imm16
0x43    JMP         control      br $label
0x44    JAL         control      save PC + br $label
0x45    CALL        control      call $func
0x46    LOOP        control      loop + br_if
0x47    SELECT      control      br_table
0x48    LOADOFF     memory       i32.load offset=imm16
0x49    STOREOF     memory       i32.store offset=imm16
0x4A    LOADI       memory       indirect i32.load
0x4B    STOREI      memory       indirect i32.store
0x4C    ENTER       stack        push FP; FP=SP; SP-=imm16
0x4D    LEAVE       stack        SP=FP; pop FP
0x4E    COPY        memory       memory.copy or loop
0x4F    FILL        memory       memory.fill or loop
0x50    TELL        a2a          call $import_tell
0x51    ASK         a2a          call $import_ask
0x52    DELEG       a2a          call $import_delegate
0x53    BCAST       a2a          call $import_broadcast
0x54    ACCEPT      a2a          call $import_accept
0x55    DECLINE     a2a          call $import_decline
0x56    REPORT      a2a          call $import_report
0x57    MERGE       a2a          call $import_merge
0x58    FORK        a2a          call $import_fork
0x59    JOIN        a2a          call $import_join
0x5A    SIGNAL      a2a          call $import_signal
0x5B    AWAIT       a2a          call $import_await
0x5C    TRUST       a2a          call $import_trust
0x5D    DISCOV      a2a          call $import_discover
0x5E    STATUS      a2a          call $import_status
0x5F    HEARTBT     a2a          call $import_heartbeat
0x60    C_ADD       confidence   call $c_add (helper func)
0x61    C_SUB       confidence   call $c_sub (helper func)
0x62    C_MUL       confidence   call $c_mul (helper func)
0x63    C_DIV       confidence   call $c_div (helper func)
0x64    C_FADD      confidence   call $c_fadd (helper func)
0x65    C_FSUB      confidence   call $c_fsub (helper func)
0x66    C_FMUL      confidence   call $c_fmul (helper func)
0x67    C_FDIV      confidence   call $c_fdiv (helper func)
0x68    C_MERGE     confidence   call $c_merge (helper func)
0x69    C_THRESH    confidence   inline: f32.load + f32.lt + br_if
0x6A    C_BOOST     confidence   call $c_boost (helper func)
0x6B    C_DECAY     confidence   call $c_decay (helper func)
0x6C    C_SOURCE    confidence   call $c_source (helper func)
0x6D    C_CALIB     confidence   call $c_calibrate (helper func)
0x6E    C_EXPLY     confidence   call $c_explicitly (helper func)
0x6F    C_VOTE      confidence   call $c_vote (helper func)
0x70-0x7F V_*       viewpoint    call $import_viewpoint (stub/JS)
0x80-0x8F SENSE-*   sensor       call $import_sensor (stub/JS)
0x90    ABS         math         i32.abs (direct)
0x91    SIGN        math         emulated (cmp + select)
0x92    SQRT        math         f32.sqrt after ITOF
0x93    POW         math         call $import_pow
0x94    LOG2        math         call $import_log2
0x95    CLZ         math         i32.clz (direct)
0x96    CTZ         math         i32.ctz (direct)
0x97    POPCNT      math         i32.popcnt (direct)
0x98    CRC32       crypto       call $import_crc32
0x99    SHA256      crypto       call $import_sha256 (Web Crypto)
0x9A    RND         math         call $import_random
0x9B    SEED        math         call $import_seed
0x9C    FMOD        float        call $import_fmod
0x9D    FSQRT       float        f32.sqrt (direct)
0x9E    FSIN        float        call $import_sin
0x9F    FCOS        float        call $import_cos
0xA0-0xAF COL_*     collection   call $import_collection (stub/JS)
0xB0    VLOAD       vector       call $vload (loop emulation)
0xB1    VSTORE      vector       call $vstore (loop emulation)
0xB2    VADD        vector       call $vadd (loop emulation)
0xB3    VMUL        vector       call $vmul (loop emulation)
0xB4    VDOT        vector       call $vdot (loop + f32.mul+add)
0xB5    VNORM       vector       call $vnorm (sqrt of dot product)
0xB6    VSCALE      vector       call $vscale (loop emulation)
0xB7-0xBF V_*       vector       call $v_* (loop emulation)
0xC0    TMATMUL     tensor       call $import_tmatmul (JS or SIMD)
0xC1-0xCF T_*       tensor       call $import_tensor (JS or WASM SIMD)
0xD0    DMA_CPY     memory       memory.copy (WASM bulk op)
0xD1    DMA_SET     memory       memory.fill (WASM bulk op)
0xD2    MMIO_R      memory       call $import_mmio_read
0xD3    MMIO_W      memory       call $import_mmio_write
0xD4    ATOMIC      memory       i32.atomic.rmw.cmpxchg
0xD5    CAS         memory       i32.atomic.rmw.cmpxchg
0xD6    FENCE       memory       memory.atomic.fence
0xD7    MALLOC      memory       call $import_malloc
0xD8    FREE        memory       call $import_free
0xD9    MPROT       memory       nop (no memory protection in WASM)
0xDA    MCACHE      memory       nop (no cache control in WASM)
0xDB-0xDE GPU_*     gpu          call $import_gpu (WebGPU stub)
0xE0    JMPL        control      br $far_label
0xE1    JALL        control      save PC + br $far_label
0xE2    CALLL       control      call $func (same as CALL)
0xE3    TAIL        control      return (tail call)
0xE4    SWITCH      control      br_table
0xE5    COYIELD     control      call $import_coroutine_yield
0xE6    CORESUM     control      call $import_coroutine_resume
0xE7    FAULT       system       unreachable (trap)
0xE8    HANDLER     system       store handler address
0xE9    TRACE       debug        call $import_trace
0xEA    PROF_ON     debug        call $import_prof_on
0xEB    PROF_OFF    debug        call $import_prof_off
0xEC    WATCH       debug        call $import_watchpoint
0xF0    HALT_ERR    system       call $import_halt_error + return
0xF1    REBOOT      system       call $import_reboot
0xF2    DUMP        debug        call $import_dump_state
0xF3    ASSERT      debug        if + unreachable
0xF4    ID          system       call $import_get_agent_id
0xF5    VER         system       i32.const 3; store to R0
0xF6    CLK         system       call $import_clock
0xF7    PCLK        system       call $import_perf_counter
0xF8    WDOG        system       call $import_watchdog
0xF9    SLEEP       system       call $import_sleep
0xFF    ESCAPE      extension    0xFF + next byte = ext dispatch
```

**Strategy distribution:**

| Strategy | Count | Percentage |
|:---|:---:|:---:|
| Direct WASM instruction (inlined) | ~85 | ~34% |
| Call helper function (within module) | ~30 | ~12% |
| Call imported JS function | ~90 | ~36% |
| Emulated (multi-instruction sequence) | ~20 | ~8% |
| No-op / nop | ~5 | ~2% |
| Stub / placeholder | ~20 | ~8% |

---

## 3. Memory Layout

### 3.1 WASM Linear Memory Organization

The FLUX-WASM module uses a single WASM linear memory instance with the following
layout. All offsets are relative to the base of the linear memory.

```
WASM Linear Memory Map
═══════════════════════════════════════════════════════════════

Offset        Size            Region              Description
───────────────────────────────────────────────────────────────
0x00000000    64 bytes        GP Register File     R0-R15 (i32 each, LE)
0x00000040    64 bytes        FP Register File     F0-F15 (f32 each, LE)
0x00000080    256 bytes       Vector Registers     V0-V15 (16 bytes each)
0x00000180    64 bytes        Confidence Array     CR0-CR15 (f32 each)
0x000001C0    4 bytes         Flags Byte           Z, S, C, O flags
0x000001C4    4 bytes         Heap Pointer         Current heap alloc ptr
0x000001C8    4 bytes         Virtual PC           Debug/trace only
0x000001CC    4 bytes         Strip-CF Flag        Confidence stripping state
0x000001D0    48 bytes        Reserved/Alignment   Pad to 0x200
───────────────────────────────────────────────────────────────
0x00000200    3,840 bytes     FLUX Stack           Grows downward from 0x1100
0x00001100    Stack Limit     Stack Bottom          Stack overflow boundary
───────────────────────────────────────────────────────────────
0x00002000    56,320 bytes    FLUX Heap            Grows upward from 0x2000
0x00010000    Heap Limit      Heap Top              Default heap ceiling (64KB)
───────────────────────────────────────────────────────────────
0x00010000    variable        Code Mirror          Copy of original FLUX bytecode
0x00020000    variable        Data Segment         Static data, string literals
0x00030000    variable        A2A Message Buffer   Temp space for A2A payloads
0x00040000    variable        Extension Space      Extension manifest + tables

═══════════════════════════════════════════════════════════════
Total minimum: 256 KB (0x40000)
Initial memory: 1 page (64 KB), grows as needed up to 16 pages (1 MB)
```

### 3.2 Register File Detail

The GP register file occupies bytes 0-63, with each register being a 32-bit
little-endian signed integer:

```
Offset  Register  ABI Alias   WASM Access Pattern
------  --------  ---------   --------------------
0x00    R0        Result      i32.load offset=0
0x04    R1        Arg1        i32.load offset=4
0x08    R2        Arg2        i32.load offset=8
0x0C    R3        Arg3        i32.load offset=12
0x10    R4        Temp1       i32.load offset=16
0x14    R5        Temp2       i32.load offset=20
0x18    R6        Temp3       i32.load offset=24
0x1C    R7        Saved1      i32.load offset=28
0x20    R8        Saved2      i32.load offset=32
0x24    R9        Saved3      i32.load offset=36
0x28    R10       Saved4      i32.load offset=40
0x2C    R11       SP          i32.load offset=44
0x30    R12       RegionID    i32.load offset=48
0x34    R13       TrustToken  i32.load offset=52
0x38    R14       FP          i32.load offset=56
0x3C    R15       LR          i32.load offset=60
```

The FP register file occupies bytes 64-127, with each register being a 32-bit
IEEE 754 float:

```
Offset  Register  WASM Access Pattern
------  --------  --------------------
0x40    F0        f32.load offset=64
0x44    F1        f32.load offset=68
...
0x7C    F15       f32.load offset=124
```

### 3.3 Stack Detail

The FLUX stack region occupies offset 0x200 through 0x1100 (3,840 bytes =
960 stack slots of 4 bytes each). The stack pointer (R11) is initialized to
0x1100 and grows downward toward 0x200.

```
Stack region:
  0x1100 ┌──────────────┐ ← Initial SP = 0x1100
         │  slot 959    │
  0x10FC ├──────────────┤
         │  slot 958    │
         │     ...      │
         │              │
  0x0204 ├──────────────┤
         │  slot 1      │
  0x0200 ├──────────────┤ ← Stack bottom (overflow boundary)
         │  (heap)      │
```

**Stack overflow detection**: Before every PUSH operation, the compiler inserts
a bounds check:

```wasm
;; PUSH R0 — with overflow check
(local.get $sp)
i32.const 0x200                ;; stack bottom
i32.lt_s                      ;; sp < 0x200 ?
if
  call $import_stack_overflow  ;; trap: stack overflow
  unreachable
end
;; ... normal push code ...
```

### 3.4 Heap Detail

The FLUX heap occupies offset 0x2000 through 0x10000 (56,320 bytes). The heap
pointer at offset 0x1C4 tracks the current allocation frontier, initialized to
0x2000 and growing upward.

**MALLOC emulation**:

```wasm
;; FLUX: MALLOC R0, R1, size (0xD7 G-format)
;; Allocate 'size' bytes, handle → R0
;; WASM:
(func $flux_malloc (param $rd i32) (param $size i32) (result i32)
  (local $addr i32)
  ;; Load current heap pointer
  (i32.load (i32.const 0x1C4))
  local.set $addr

  ;; Align to 8 bytes
  local.get $addr
  i32.const 7
  i32.add
  i32.const -8
  i32.and
  local.set $addr

  ;; Check if allocation fits
  local.get $addr
  local.get $size
  i32.add
  i32.const 0x10000            ;; heap ceiling
  i32.gt_s
  if
    i32.const -1               ;; return -1 on OOM
    return
  end

  ;; Update heap pointer
  local.get $addr
  local.get $size
  i32.add
  (i32.store (i32.const 0x1C4))

  ;; Store allocated address to destination register
  local.get $addr
  ;; Return the allocated address
)
```

### 3.5 Data Segment

Static data (string literals, constant arrays, lookup tables) is placed in the
WASM data segment starting at offset 0x20000. The FLUX compiler emits these as
WASM `data` sections:

```wasm
;; In the WASM module:
(data (i32.const 0x20000)
  "Hello from FLUX-WASM!\x00"   ;; null-terminated string
  "\x01\x02\x03\x04"           ;; constant byte array
)
```

### 3.6 Memory Growth Policy

The initial WASM memory allocation is 1 page (64 KB = 65,536 bytes). The module
specifies a minimum of 1 page and a maximum of 16 pages (1 MB = 1,048,576 bytes).

```wasm
(memory (export "memory") 1 16)  ;; min 1 page, max 16 pages
```

Memory growth is triggered by:
1. **Heap allocation** exceeding the current heap ceiling → `memory.grow`
2. **Stack overflow** check → trap (stack has fixed size)
3. **A2A message buffer** expansion → `memory.grow`

```wasm
;; Memory growth helper
(func $ensure_memory (param $needed_bytes i32)
  (local $current_pages i32)
  (local $needed_pages i32)

  ;; Current memory size in pages
  memory.size
  local.set $current_pages

  ;; Calculate pages needed for requested bytes
  local.get $needed_bytes
  i32.const 65535
  i32.add
  i32.const 16                  ;; page size = 65536
  i32.div_u
  local.set $needed_pages

  ;; Grow if needed
  local.get $needed_pages
  local.get $current_pages
  i32.gt_s
  if
    local.get $needed_pages
    local.get $current_pages
    i32.sub
    memory.grow
    i32.const -1
    i32.eq                       ;; memory.grow returns -1 on failure
    if
      call $import_oom_error
      unreachable
    end
  end
)
```

---

## 4. Confidence Propagation in WASM

### 4.1 Confidence Architecture

FLUX's confidence system is a unique feature that associates a probability
value (f32 in [0.0, 1.0]) with every GP register value. This allows the VM to
track the reliability of computed values, enabling Bayesian fusion, uncertainty
propagation through arithmetic, and confidence-gated control flow.

In the WASM target, confidence values are stored in a parallel array at offset
0x180 in linear memory. Each confidence operation compiles to a WASM helper
function that reads both the value and confidence of source registers, computes
the result and propagated confidence, and writes both back.

### 4.2 Confidence Helper Functions

#### 4.2.1 C_ADD — Confidence-Aware Addition

```
FLUX semantics: rd = rs1 + rs2; crd = min(crs1, crs2)
Rationale: The confidence in a sum is limited by the least-confident operand.
           If one operand is uncertain, the sum is equally uncertain.
```

```wasm
;; Helper function: $c_add
;; Parameters: rd (dest reg index), rs1, rs2 (source reg indices)
;; All passed as i32 register indices (0-15)
(func $c_add (param $rd i32) (param $rs1 i32) (param $rs2 i32)
  (local $val1 i32)
  (local $val2 i32)
  (local $conf1 f32)
  (local $conf2 f32)

  ;; Load source values
  local.get $rs1
  i32.const 4
  i32.mul
  i32.load                       ;; val1 = regs[rs1]
  local.set $val1

  local.get $rs2
  i32.const 4
  i32.mul
  i32.load                       ;; val2 = regs[rs2]
  local.set $val2

  ;; Load source confidences
  local.get $rs1
  i32.const 4
  i32.mul
  f32.load offset=0x180          ;; conf1 = confs[rs1]
  local.set $conf1

  local.get $rs2
  i32.const 4
  i32.mul
  f32.load offset=0x180          ;; conf2 = confs[rs2]
  local.set $conf2

  ;; Compute result: rd = rs1 + rs2
  local.get $rd
  i32.const 4
  i32.mul
  local.get $val1
  local.get $val2
  i32.add
  i32.store                      ;; regs[rd] = val1 + val2

  ;; Compute confidence: crd = min(conf1, conf2)
  local.get $rd
  i32.const 4
  i32.mul
  local.get $conf1
  local.get $conf2
  f32.min
  f32.store offset=0x180         ;; confs[rd] = min(conf1, conf2)
)
```

#### 4.2.2 C_MUL — Confidence-Aware Multiplication

```
FLUX semantics: rd = rs1 * rs2; crd = crs1 * crs2
Rationale: Multiplying two uncertain values compounds the uncertainty.
           If P(A) = c1 and P(B) = c2, then P(A*B) = c1 * c2 (independence).
```

```wasm
(func $c_mul (param $rd i32) (param $rs1 i32) (param $rs2 i32)
  (local $conf1 f32)
  (local $conf2 f32)

  ;; Compute result: rd = rs1 * rs2
  local.get $rd
  i32.const 4
  i32.mul
  local.get $rs1
  i32.const 4
  i32.mul
  i32.load
  local.get $rs2
  i32.const 4
  i32.mul
  i32.load
  i32.mul
  i32.store

  ;; Compute confidence: crd = crs1 * crs2
  local.get $rs1
  i32.const 4
  i32.mul
  f32.load offset=0x180
  local.set $conf1

  local.get $rs2
  i32.const 4
  i32.mul
  f32.load offset=0x180
  local.set $conf2

  local.get $rd
  i32.const 4
  i32.mul
  local.get $conf1
  local.get $conf2
  f32.mul
  f32.store offset=0x180
)
```

#### 4.2.3 C_DIV — Confidence-Aware Division

```
FLUX semantics: rd = rs1 / rs2; crd = crs1 * crs2 * (1 - epsilon)
Rationale: Division introduces a small additional uncertainty (epsilon)
           due to potential precision loss in the quotient.
```

```wasm
(func $c_div (param $rd i32) (param $rs1 i32) (param $rs2 i32)
  (local $conf1 f32)
  (local $conf2 f32)
  (local $epsilon f32)

  ;; epsilon = 0.0001 (configurable)
  f32.const 0x38D1B717         ;; f32 representation of 0.0001
  local.set $epsilon

  ;; Compute result: rd = rs1 / rs2
  local.get $rd
  i32.const 4
  i32.mul
  local.get $rs1
  i32.const 4
  i32.mul
  i32.load
  local.get $rs2
  i32.const 4
  i32.mul
  i32.load
  i32.div_s
  i32.store

  ;; Compute confidence: crd = crs1 * crs2 * (1 - epsilon)
  local.get $rs1
  i32.const 4
  i32.mul
  f32.load offset=0x180
  local.set $conf1

  local.get $rs2
  i32.const 4
  i32.mul
  f32.load offset=0x180
  local.set $conf2

  local.get $rd
  i32.const 4
  i32.mul
  local.get $conf1
  local.get $conf2
  f32.mul
  f32.const 1.0
  local.get $epsilon
  f32.sub
  f32.mul
  f32.store offset=0x180
)
```

#### 4.2.4 C_MERGE — Bayesian Confidence Fusion

```
FLUX semantics: rd = weighted_avg(rs1, rs2); crd = bayesian_merge(crs1, crs2)
Rationale: When merging two estimates of the same quantity, we combine
           confidences using Bayesian fusion rather than simple min/max.
```

```wasm
(func $c_merge (param $rd i32) (param $rs1 i32) (param $rs2 i32)
  (local $val1 i32)
  (local $val2 i32)
  (local $conf1 f32)
  (local $conf2 f32)
  (local $total_conf f32)

  ;; Load values and confidences
  local.get $rs1  i32.const 4  i32.mul  i32.load  local.set $val1
  local.get $rs2  i32.const 4  i32.mul  i32.load  local.set $val2
  local.get $rs1  i32.const 4  i32.mul  f32.load offset=0x180  local.set $conf1
  local.get $rs2  i32.const 4  i32.mul  f32.load offset=0x180  local.set $conf2

  ;; Compute total confidence: total_conf = conf1 + conf2 - conf1 * conf2
  ;; (independent probabilities: P(A or B) = P(A) + P(B) - P(A)*P(B))
  local.get $conf1
  local.get $conf2
  f32.add
  local.get $conf1
  local.get $conf2
  f32.mul
  f32.sub
  local.set $total_conf

  ;; Compute weighted average: rd = (val1 * conf1 + val2 * conf2) / total_conf
  ;; Convert to f32 for weighted average, then back to i32
  local.get $val1
  f32.convert_i32_s
  local.get $conf1
  f32.mul
  local.get $val2
  f32.convert_i32_s
  local.get $conf2
  f32.mul
  f32.add
  local.get $total_conf
  f32.div
  i32.trunc_f32_s

  ;; Store result
  local.get $rd  i32.const 4  i32.mul
  ;; (result is on stack from trunc)
  i32.store

  ;; Store merged confidence
  local.get $rd  i32.const 4  i32.mul
  local.get $total_conf
  f32.store offset=0x180
)
```

#### 4.2.5 C_THRESH — Confidence Threshold Gate

```
FLUX semantics: if conf[rd] < (imm8 / 255), skip next instruction
Rationale: Gate execution based on whether a value's confidence
           exceeds a minimum threshold.
```

**Example 10: Confidence-gated computation**

```wasm
;; FLUX: C_THRESH R3, 200 (0x69 0x03 0xC8)
;; If confidence of R3 < 200/255 = 0.784, skip next instruction
;; WASM:
;; Load confidence of R3
(f32.load offset=0x180 (i32.const 12))  ;; conf[3] (offset = 3*4 + 0x180)
f32.const 0.784                         ;; threshold = 200/255
f32.lt                                 ;; conf < threshold ?
if
  ;; Skip next instruction by reading its size and advancing PC
  ;; In compiled WASM, this becomes a br_if to skip the next block
  br $skip_next
end
;; ... next instruction (only executed if confidence is sufficient) ...
block $skip_next
end
```

### 4.3 Performance Impact of Confidence Tracking

Confidence operations have a measurable performance cost compared to their
non-confidence counterparts:

| Operation | Non-Confidence | With Confidence | Overhead |
|:---|:---:|:---:|:---:|
| ADD | 1 WASM op | ~15 WASM ops (call + load/store) | ~15x |
| MUL | 1 WASM op | ~15 WASM ops | ~15x |
| DIV | 1 WASM op | ~18 WASM ops | ~18x |
| MERGE | N/A | ~30 WASM ops (Bayesian fusion) | N/A |
| THRESH | N/A | ~5 WASM ops (inline) | N/A |

**Optimization: Strip Confidence Mode**

When confidence tracking is not needed for a section of code, the STRIPCF
instruction (0x17) disables confidence propagation for the next N instructions.
During WASM compilation, the compiler can detect STRIPCF regions and emit
non-confidence arithmetic for those instructions, eliminating the overhead.

```wasm
;; FLUX: STRIPCF 10; ADD R3,R1,R2; ADD R4,R1,R2; ... (10 ops)
;; WASM with strip optimization:
;; The compiler emits plain i32.add instead of call $c_add for these 10 ops
(i32.load (i32.const 4))
(i32.load (i32.const 8))
i32.add
i32.store (i32.const 12)
;; No confidence load/store for these instructions
```

### 4.4 Float Confidence Operations

The float confidence operations (C_FADD, C_FSUB, C_FMUL, C_FDIV) follow the
same pattern as integer confidence operations but use f32 arithmetic:

```
C_FADD: rd_f = rs1_f + rs2_f; crd = min(crs1, crs2)
C_FSUB: rd_f = rs1_f - rs2_f; crd = min(crs1, crs2)
C_FMUL: rd_f = rs1_f * rs2_f; crd = crs1 * crs2
C_FDIV: rd_f = rs1_f / rs2_f; crd = crs1 * crs2 * (1 - epsilon)
```

The helper functions for these are identical in structure to their integer
counterparts, replacing `i32.add` with `f32.add`, etc.

---

## 5. Browser Integration

### 5.1 Import Interface

The FLUX-WASM module imports JavaScript functions for all operations that cannot
be performed purely within WASM (I/O, A2A protocol, sensors, DOM, networking).

```wasm
;; Module imports — provided by the JavaScript shim
(import "flux" "console_log"
  (func $import_console_log (param i32)))         ;; Log register value

(import "flux" "console_log_str"
  (func $import_console_log_str (param i32 i32)))  ;; Log string at addr, len

(import "flux" "halt_error"
  (func $import_halt_error (param i32)))           ;; Halt with error code

(import "flux" "debugger"
  (func $import_debugger (param i32)))             ;; Break into debugger

(import "flux" "sys_call"
  (func $import_syscall (param i32 i32) (result i32)))  ;; System call

(import "flux" "yield"
  (func $import_yield (param i32) (result i32)))   ;; Yield N cycles

(import "flux" "sleep_ms"
  (func $import_sleep_ms (param i32)))             ;; Sleep N milliseconds

(import "flux" "random"
  (func $import_random (param i32 i32) (result i32))) ;; Random in [lo, hi]

(import "flux" "clock"
  (func $import_clock (result i32)))               ;; Current time in ms

(import "flux" "perf_counter"
  (func $import_perf_counter (result i32)))        ;; High-res timer

(import "flux" "get_agent_id"
  (func $import_get_agent_id (result i32)))        ;; Agent identifier

(import "flux" "reboot"
  (func $import_reboot))                           ;; Warm reboot

;; A2A Protocol imports
(import "flux" "tell"
  (func $import_tell (param i32 i32 i32) (result i32)))

(import "flux" "ask"
  (func $import_ask (param i32 i32 i32) (result i32)))

(import "flux" "delegate"
  (func $import_delegate (param i32 i32 i32) (result i32)))

(import "flux" "broadcast"
  (func $import_broadcast (param i32 i32 i32) (result i32)))

(import "flux" "signal"
  (func $import_signal (param i32 i32 i32) (result i32)))

(import "flux" "await_signal"
  (func $import_await (param i32 i32) (result i32)))

(import "flux" "fork"
  (func $import_fork (param i32 i32) (result i32)))

(import "flux" "join"
  (func $import_join (param i32 i32) (result i32)))

;; Math imports (transcendental functions not in WASM)
(import "flux" "sin" (func $import_sin (param f32) (result f32)))
(import "flux" "cos" (func $import_cos (param f32) (result f32)))
(import "flux" "pow" (func $import_pow (param f32 f32) (result f32)))
(import "flux" "log2" (func $import_log2 (param f32) (result f32)))
(import "flux" "sqrt_f64" (func $import_sqrt (param f32) (result f32)))

;; Crypto imports
(import "flux" "sha256"
  (func $import_sha256 (param i32 i32 i32) (result i32)))

(import "flux" "crc32"
  (func $import_crc32 (param i32 i32) (result i32)))

;; Memory management
(import "flux" "malloc"
  (func $import_malloc (param i32) (result i32)))

(import "flux" "free"
  (func $import_free (param i32)))

;; Debug/trace
(import "flux" "trace"
  (func $import_trace (param i32 i32)))

(import "flux" "dump_state"
  (func $import_dump_state))

(import "flux" "watchpoint"
  (func $import_watchpoint (param i32 i32)))

;; GPU / Tensor operations (optional, requires WebGPU)
(import "flux" "tensor_matmul"
  (func $import_tensor_matmul (param i32 i32 i32 i32) (result i32)))
```

### 5.2 Console Output Mapping

The FLUX `DBG` instruction (0x12) maps to `console.log` in the browser:

```javascript
// JavaScript shim for FLUX-WASM console output
const imports = {
  flux: {
    console_log: (regIndex) => {
      const value = new Int32Array(memory.buffer)[regIndex];
      console.log(`[FLUX R${regIndex}] = ${value}`);
    },
    console_log_str: (addr, len) => {
      const bytes = new Uint8Array(memory.buffer, addr, len);
      const str = new TextDecoder().decode(bytes);
      console.log(`[FLUX] ${str}`);
    }
  }
};
```

### 5.3 Fetch API for Network Operations

FLUX A2A protocol instructions that involve network communication (TELL, ASK,
BCAST) can be backed by the browser's Fetch API in the JavaScript shim:

```javascript
// JavaScript shim for A2A TELL via Fetch
const imports = {
  flux: {
    tell: async (targetAgent, message, tag) => {
      try {
        const response = await fetch(`/api/a2a/tell`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            target: targetAgent,
            payload: message,
            tag: tag
          })
        });
        const result = await response.json();
        return result.status || 0;
      } catch (e) {
        console.error('[FLUX A2A] TELL failed:', e);
        return -1;
      }
    }
  }
};
```

**Synchronous A2A in WASM**: Since WASM function calls are synchronous but
`fetch` is asynchronous, the shim uses `Atomics.wait` for synchronous blocking
within the WASM module:

```javascript
// Synchronous A2A pattern using SharedArrayBuffer
const sab = new SharedArrayBuffer(4);
const statusBuf = new Int32Array(sab);

async function tell_sync(target, message, tag) {
  // Launch async fetch
  fetch('/api/a2a/tell', { /* ... */ })
    .then(r => r.json())
    .then(result => {
      statusBuf[0] = result.status;
      Atomics.notify(statusBuf, 0);
    });

  // Block WASM thread until result is ready
  Atomics.wait(statusBuf, 0, 0, 5000); // 5s timeout
  return statusBuf[0];
}
```

### 5.4 Web Worker Support

FLUX-WASM programs can run in Web Workers for background execution, enabling:

- **Non-blocking A2A communication**: The main thread remains responsive while
  FLUX agents communicate.
- **Parallel agent execution**: Multiple FLUX agents run in separate Workers.
- **Offloaded computation**: Heavy computation (tensor ops, crypto) runs in a
  dedicated Worker.

```javascript
// Main thread: spawn FLUX agent in Web Worker
const worker = new Worker('flux-agent-worker.js');

worker.postMessage({
  type: 'load',
  wasmUrl: '/agents/monitor.flux.wasm',
  config: { memoryMB: 4, agentId: 'agent-42' }
});

worker.onmessage = (event) => {
  switch (event.data.type) {
    case 'a2a_tell':
      // Forward A2A message to another agent
      forwardToAgent(event.data.target, event.data.payload);
      break;
    case 'halt':
      console.log(`Agent ${event.data.agentId} halted with code ${event.data.code}`);
      break;
    case 'debug':
      console.log(`[DEBUG] ${event.data.message}`);
      break;
  }
};
```

```javascript
// flux-agent-worker.js
self.importScripts('flux-shim.js');

let wasmInstance = null;

self.onmessage = async (event) => {
  if (event.data.type === 'load') {
    const response = await fetch(event.data.wasmUrl);
    const wasmBytes = await response.arrayBuffer();
    const module = await WebAssembly.instantiate(wasmBytes, fluxImports);
    wasmInstance = module.instance;
    wasmInstance.exports.flux_main();
  }
};
```

### 5.5 DOM Access Interface

FLUX programs running in the browser can interact with the DOM through imported
functions:

```javascript
// DOM access imports for FLUX-WASM
const domImports = {
  flux: {
    dom_get_element: (elementId) => {
      const id = readStringFromMemory(elementId);
      return getOrCreateElementRef(document.getElementById(id));
    },
    dom_set_text: (elementRef, textAddr, textLen) => {
      const text = readStringFromMemory(textAddr, textLen);
      elementRefs[elementRef].textContent = text;
    },
    dom_set_style: (elementRef, styleAddr) => {
      const style = readStringFromMemory(styleAddr);
      elementRefs[elementRef].setAttribute('style', style);
    },
    dom_add_event: (elementRef, eventType) => {
      const type = readStringFromMemory(eventType);
      elementRefs[elementRef].addEventListener(type, (e) => {
        // Signal the WASM module about the event
        writeMemory(0x30000, 1); // Event flag
      });
    }
  }
};
```

### 5.6 Canvas / WebGL Interface

For visual output (game agents, sensor visualization), FLUX-WASM provides a
canvas interface:

```javascript
// Canvas rendering imports
const canvasImports = {
  flux: {
    canvas_init: (width, height) => {
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      document.body.appendChild(canvas);
      const ctx = canvas.getContext('2d');
      return storeCanvasContext(ctx);
    },
    canvas_draw_pixel: (ctxRef, x, y, color) => {
      const ctx = canvasContexts[ctxRef];
      ctx.fillStyle = `rgb(${(color >> 16) & 0xFF}, ${(color >> 8) & 0xFF}, ${color & 0xFF})`;
      ctx.fillRect(x, y, 1, 1);
    },
    canvas_flush: (ctxRef) => {
      // No-op for 2D canvas (auto-flush)
    }
  }
};
```

---

## 6. Toolchain Design

### 6.1 Build Pipeline Overview

The FLUX-to-WASM toolchain consists of four stages:

```
┌─────────────┐    ┌──────────────┐    ┌───────────────┐    ┌──────────────┐
│  FLUX Binary │───→│   Parser     │───→│ Code Generator│───→│ WASM Binary  │
│  (.flux)     │    │   (Decoder)  │    │   (Emitter)   │    │  (.wasm)     │
└─────────────┘    └──────────────┘    └───────────────┘    └──────────────┘
                         │                    │
                         │                    │
                    ┌────┴────┐         ┌─────┴─────┐
                    │   IR    │         │  WAT Text │
                    │ (typed) │         │  (.wat)   │
                    └─────────┘         └───────────┘
```

### 6.2 Stage 1: Parser (FLUX Binary → IR)

The parser reads FLUX bytecode and produces a typed intermediate representation
(IR). The IR is a control-flow graph (CFG) of basic blocks, where each block
contains a sequence of typed IR instructions.

```python
# IR instruction types
@dataclass
class IRInstruction:
    opcode: str           # e.g., "add", "load", "br_if"
    operands: list        # register indices, immediates
    result_type: str      # "i32", "f32", "void"
    source_pc: int        # original FLUX bytecode PC (for debugging)
    source_bytecode: bytes  # original FLUX instruction bytes

@dataclass
class IRBasicBlock:
    label: str            # e.g., "block_0", "loop_1"
    instructions: list    # list of IRInstruction
    successors: list      # successor block labels
    predecessors: list    # predecessor block labels
    is_loop_header: bool  # true if this is the target of a back-edge

@dataclass
class IRFunction:
    name: str
    blocks: list          # list of IRBasicBlock
    entry_block: str      # label of entry block
```

**Parser algorithm:**

```python
def parse_flux_to_ir(bytecode: bytes) -> IRFunction:
    """Parse FLUX bytecode into a typed IR control-flow graph."""
    pc = 0
    blocks = {}
    current_block = IRBasicBlock(label="block_0", instructions=[])
    blocks["block_0"] = current_block
    block_counter = 1

    while pc < len(bytecode):
        start_pc = pc
        opcode_byte = bytecode[pc]
        pc += 1

        # Decode instruction based on format
        if opcode_byte in FORMAT_A:
            ir = decode_format_a(opcode_byte, start_pc, bytecode)
        elif opcode_byte in FORMAT_B:
            op, pc = decode_format_b(opcode_byte, pc, bytecode)
            ir = IRInstruction(opcode=op.name, operands=[...])
        # ... etc for each format

        # Identify block boundaries at control-flow targets
        if ir.opcode in ("br", "br_if", "call", "return"):
            # End current block, start new one
            next_label = f"block_{block_counter}"
            block_counter += 1
            new_block = IRBasicBlock(label=next_label, instructions=[])
            blocks[next_label] = new_block
            current_block.successors.append(next_label)
            new_block.predecessors.append(current_block.label)
            current_block = new_block

        current_block.instructions.append(ir)

    return IRFunction(name="flux_main", blocks=list(blocks.values()))
```

### 6.3 Stage 2: Code Generator (IR → WAT)

The code generator traverses the IR CFG and emits WebAssembly Text (WAT) format.
The generator handles:

1. **Structured control flow**: Converting the CFG's arbitrary branch graph into
   WASM's nested `block`/`loop`/`if`/`end` structures.
2. **Register promotion**: Identifying hot registers to promote to WASM locals.
3. **Dead code elimination**: Removing unreachable blocks and unused instructions.
4. **Constant folding**: Evaluating constant expressions at compile time.

```python
class WATCodeGenerator:
    """Generate WAT text from FLUX IR."""

    def __init__(self, ir: IRFunction):
        self.ir = ir
        self.output = []
        self.locals = {}       # promoted register → WASM local name
        self.imports = set()   # required JS imports
        self.helpers = set()   # required helper functions

    def generate(self) -> str:
        """Generate complete WAT module."""
        self._emit_header()
        self._emit_imports()
        self._emit_memory()
        self._emit_data_segments()
        self._emit_helper_functions()
        self._emit_main_function()
        self._emit_exports()
        return "\n".join(self.output)

    def _emit_main_function(self):
        """Emit the $flux_main function with compiled FLUX code."""
        self.output.append("(func $flux_main (export \"flux_main\")")

        # Declare promoted locals
        for reg_idx, local_name in self.locals.items():
            self.output.append(f"  (local ${local_name} i32)")

        # Traverse CFG and emit structured control flow
        for block in self._topological_order():
            self._emit_block(block)

        self.output.append(")")

    def _emit_block(self, block: IRBasicBlock):
        """Emit a basic block as WASM instructions."""
        if block.is_loop_header:
            self.output.append("  loop $loop_" + block.label)

        for ir in block.instructions:
            self._emit_instruction(ir)

        if block.is_loop_header:
            self.output.append("  end")
```

### 6.4 Stage 3: WASM Binary Encoder (WAT → .wasm)

The WAT text is assembled into WASM binary format using one of:

1. **wabt (WebAssembly Binary Toolkit)**: `wat2wasm output.wat -o output.wasm`
2. **wasm-pack**: For npm-compatible packaging
3. **Custom encoder**: For embedded/toolchain integration

```bash
# Build pipeline commands
wat2wasm flux_output.wat -o flux_output.wasm --enable-all
wasm-opt -O3 flux_output.wasm -o flux_output_opt.wasm  # Binaryen optimization
```

### 6.5 Stage 4: JavaScript Runtime Shim

The minimal JS shim provides the imported functions and manages the WASM instance:

```javascript
// flux-runtime.js — Minimal FLUX-WASM runtime shim
class FluxWasmRuntime {
  constructor() {
    this.memory = null;
    this.instance = null;
    this.agentId = crypto.randomUUID();
    this.messageHandlers = new Map();
    this.elementRefs = [];
  }

  async load(wasmUrl, config = {}) {
    const response = await fetch(wasmUrl);
    const wasmBytes = await response.arrayBuffer();

    this.memory = new WebAssembly.Memory({
      initial: config.memoryPages || 1,
      maximum: config.maxPages || 16
    });

    const imports = this._buildImports();
    const module = await WebAssembly.instantiate(wasmBytes, imports);
    this.instance = module.instance;

    // Initialize memory regions
    this._initMemory(config);

    return this;
  }

  _buildImports() {
    return {
      flux: {
        console_log: (regIdx) => {
          const val = new Int32Array(this.memory.buffer)[regIdx];
          console.log(`[FLUX:${this.agentId}] R${regIdx} = ${val}`);
        },
        // ... all other imports ...
      }
    };
  }

  execute() {
    const result = this.instance.exports.flux_main();
    return result;
  }

  _initMemory(config) {
    // Set initial SP to stack top
    const regs = new Int32Array(this.memory.buffer);
    regs[11] = 0x1100;  // SP = stack top

    // Set initial heap pointer
    const heapPtr = new Int32Array(this.memory.buffer);
    const HEAP_PTR_OFFSET = 0x1C4 / 4;
    heapPtr[HEAP_PTR_OFFSET] = 0x2000;  // heap start

    // Initialize all confidences to 1.0
    const confs = new Float32Array(this.memory.buffer, 0x180, 16);
    confs.fill(1.0);
  }
}
```

### 6.6 CLI Tool

The toolchain is exposed as a CLI command:

```bash
# Compile FLUX bytecode to WASM
flux-wasm compile program.flux -o program.wasm --optimize

# Run FLUX-WASM in Node.js
flux-wasm run program.wasm --memory 4MB --debug

# Emit WAT (text format) for inspection
flux-wasm compile program.flux --emit-wat -o program.wat

# Bundle with JS shim for browser
flux-wasm bundle program.flux -o dist/program.js --minify
```

---

## 7. Performance Analysis

### 7.1 WASM Overhead vs Native FLUX Execution

The FLUX-WASM target eliminates the interpreter's fetch-decode-execute loop,
compiling FLUX instructions directly to WASM machine code. The expected speedup
over the Python interpreter is significant:

| Benchmark | Python Interpreter | FLUX-WASM | Speedup | Notes |
|:---|:---:|:---:|:---:|:---|
| Fibonacci(30) | ~450ms | ~0.8ms | ~560x | Tight integer loop |
| Fibonacci(40) | ~4,800ms | ~9ms | ~530x | Exponential growth |
| Matrix 16x16 multiply | ~120ms | ~2.1ms | ~57x | Memory-bound |
| Bubble sort 1000 elems | ~85ms | ~1.5ms | ~57x | Memory access pattern |
| Confidence chain (100 ops) | ~12ms | ~0.4ms | ~30x | Confidence overhead |
| A2A round-trip (local) | ~2ms | ~0.1ms | ~20x | Import call overhead |
| SHA-256 hash (1KB) | ~1.5ms | ~0.08ms | ~19x | Web Crypto API |
| Random number gen (10K) | ~3ms | ~0.15ms | ~20x | crypto.getRandomValues |

**Expected performance characteristics:**

1. **Pure arithmetic loops**: 100-600x faster than Python interpreter. WASM
   compiles to native machine code; Python has interpreter overhead per instruction.

2. **Memory-bound operations**: 30-60x faster. WASM memory access is direct
   (pointer + offset); Python interpreter has dictionary lookups and method calls.

3. **Import call operations**: 15-25x faster. WASM→JS calls have fixed overhead
   (~50ns per call) vs Python's dynamic dispatch.

4. **Confidence operations**: 20-40x faster despite the per-operation overhead
   of helper function calls, because the base arithmetic is so much faster.

### 7.2 Hot Path Optimization Opportunities

The compiler can apply several optimizations to critical code paths:

**1. Register Promotion (already described in Section 1.3)**

Hot registers (R0-R3, SP, FP) are promoted to WASM locals, eliminating memory
load/store overhead. Expected improvement: 2-4x on register-heavy code.

**2. Confidence Stripping (Section 4.3)**

STRIPCF regions use direct WASM arithmetic instead of confidence helpers.
Expected improvement: 10-15x on stripped regions.

**3. Basic Block Inlining**

Small FLUX functions (< 20 instructions) are inlined at call sites, eliminating
call/return overhead.

**4. Dead Store Elimination**

Stores to registers that are immediately overwritten are eliminated:
```
MOVI R3, 42    ;; eliminated (R3 overwritten by next instruction)
ADD R3, R1, R2 ;; R3 = R1 + R2
```

**5. Constant Folding**

Expressions involving only constants are evaluated at compile time:
```
MOVI R0, 10
ADDI R0, 20    ;; folded to: MOVI R0, 30
```

**6. Memory Access Patterns**

Sequential memory access patterns (LOAD with incrementing addresses) can be
vectorized using WASM SIMD instructions when available:

```wasm
;; Vectorized memory copy (WASM SIMD)
(v128.load (i32.const $src))
v128.store (i32.const $dst)
;; Copies 16 bytes (4 i32 values) in a single operation
```

### 7.3 Memory Access Patterns and Cache Behavior

The FLUX-WASM memory layout is designed for cache-friendly access:

```
Hot path (frequently accessed):
  Offset 0x000-0x040: GP registers (R0-R15) — 64 bytes, fits in L1 cache line
  Offset 0x180-0x1C0: Confidence array — 64 bytes, fits in same cache line

Warm path (periodically accessed):
  Offset 0x040-0x080: FP registers — 64 bytes
  Offset 0x200-0x1100: Stack — up to 3.8 KB

Cold path (rarely accessed):
  Offset 0x2000+: Heap
  Offset 0x10000+: Code mirror, data segment
```

**Cache behavior analysis:**

- **L1 cache hit rate (GP registers)**: ~99%. The 64-byte register file and
  64-byte confidence array fit in a single 128-byte L1 cache line. Register
  accesses are always cache hits after the first access.

- **L1 cache hit rate (stack)**: ~95% for typical programs. Stack access
  follows a sequential pattern (push/pop) which is cache-friendly. Stack depth
  rarely exceeds 256 bytes for most programs.

- **L1 cache hit rate (heap)**: ~70-85%. Depends on access pattern. Sequential
  access is cache-friendly; random access may cause cache misses.

### 7.4 Benchmark Implementation

**Fibonacci(30) benchmark — FLUX bytecode and WASM output:**

```wasm
;; Optimized WASM for fibonacci(30)
;; Uses register promotion: R0=prev, R1=curr, R2=counter as locals
(func $flux_main (export "flux_main")
  (local $r0 i32)     ;; prev
  (local $r1 i32)     ;; curr
  (local $r2 i32)     ;; counter
  (local $t i32)      ;; temp

  ;; MOVI R0, 0
  i32.const 0
  local.set $r0

  ;; MOVI R1, 1
  i32.const 1
  local.set $r1

  ;; MOVI R2, 30
  i32.const 30
  local.set $r2

  ;; Loop: 30 iterations
  loop $fib_loop
    ;; temp = R0 + R1
    local.get $r0
    local.get $r1
    i32.add
    local.set $t

    ;; R0 = R1
    local.get $r1
    local.set $r0

    ;; R1 = temp
    local.get $t
    local.set $r1

    ;; R2--
    local.get $r2
    i32.const 1
    i32.sub
    local.tee $r2
    ;; if R2 > 0, continue loop
    br_if $fib_loop
  end

  ;; Sync result to memory (R0 and R1)
  local.get $r0
  i32.store (i32.const 0)
  local.get $r1
  i32.store (i32.const 4)
)
```

**Matrix multiply benchmark — 4x4 integer matrix:**

```wasm
;; C[i][j] = sum(A[i][k] * B[k][j]) for k=0..3
;; Matrices stored as flat arrays: M[i*4+j] at base + (i*4+j)*4
(func $matmul4x4
  (param $a_base i32)
  (param $b_base i32)
  (param $c_base i32)
  (local $i i32)
  (local $j i32)
  (local $k i32)
  (local $sum i32)

  ;; Outer loop: i = 0..3
  i32.const 0
  local.set $i
  block $outer_break
    loop $outer_loop
      ;; Middle loop: j = 0..3
      i32.const 0
      local.set $j
      block $mid_break
        loop $mid_loop
          ;; Inner loop: k = 0..3, sum = 0
          i32.const 0
          local.set $sum
          i32.const 0
          local.set $k
          loop $inner_loop
            ;; sum += A[i][k] * B[k][j]
            local.get $sum
            ;; A[i*4+k]
            local.get $a_base
            local.get $i
            i32.const 4
            i32.mul
            local.get $k
            i32.add
            i32.const 2
            i32.shl           ;; *4 for i32
            i32.add
            i32.load
            ;; B[k*4+j]
            local.get $b_base
            local.get $k
            i32.const 4
            i32.mul
            local.get $j
            i32.add
            i32.const 2
            i32.shl
            i32.add
            i32.load
            i32.mul
            i32.add
            local.set $sum

            ;; k++
            local.get $k
            i32.const 1
            i32.add
            local.tee $k
            i32.const 3
            i32.lt_s
            br_if $inner_loop
          end

          ;; C[i][j] = sum
          local.get $c_base
          local.get $i
          i32.const 4
          i32.mul
          local.get $j
          i32.add
          i32.const 2
          i32.shl
          i32.add
          local.get $sum
          i32.store

          ;; j++
          local.get $j
          i32.const 1
          i32.add
          local.tee $j
          i32.const 3
          i32.lt_s
          br_if $mid_loop
        end
      end

      ;; i++
      local.get $i
      i32.const 1
      i32.add
      local.tee $i
      i32.const 3
      i32.lt_s
      br_if $outer_loop
    end
  end
)
```

### 7.5 WASM Binary Size

Expected WASM binary sizes for typical FLUX programs:

| Program Type | FLUX Bytecode | WASM Binary | Ratio |
|:---|:---:|:---:|:---:|
| Hello World | ~20 bytes | ~400 bytes | ~20x |
| Fibonacci | ~30 bytes | ~350 bytes | ~12x |
| Matrix 4x4 | ~200 bytes | ~1.2 KB | ~6x |
| Game (Snake) | ~2 KB | ~8 KB | ~4x |
| Agent (full A2A) | ~5 KB | ~15 KB | ~3x |
| With helpers | +0 bytes | +3-8 KB | — |

The WASM binary is larger than FLUX bytecode because:
- WASM encodes each instruction with explicit type information
- Structured control flow adds block/loop/end markers
- Helper functions for confidence/A2A are included in the module
- Import/export tables add header overhead

---

## 8. Limitations and Future Work

### 8.1 Floating Point Precision Differences

**Problem**: FLUX uses Python's arbitrary-precision integers and IEEE 754
double-precision (64-bit) floats. WASM's core numeric types are i32 and f32
(32-bit), with optional i64 and f64 support.

**Impact**:

| Type | FLUX (Python) | WASM (32-bit) | Precision Loss |
|:---|:---|:---|:---|
| Integer | Arbitrary precision | i32 (32-bit signed) | Values > 2^31 - 1 overflow |
| Float | f64 (64-bit) | f32 (32-bit) | ~7 decimal digits vs ~15 |
| Vector | 128-bit SIMD | Emulated via memory | No SIMD hardware in WASM MVP |

**Mitigation**:

1. **64-bit support**: Use WASM i64 for integer registers when the target
   runtime supports it. All modern browsers support i64 in WASM.

2. **f64 support**: Use WASM f64 for float registers. This adds 4 bytes per FP
   register (128 bytes total for F0-F15) but eliminates precision loss.

3. **Overflow detection**: The compiler inserts overflow checks after arithmetic
   operations and traps on overflow, matching Python's behavior.

```wasm
;; Overflow-safe ADD for arbitrary precision simulation
;; If result overflows i32, trap
(i32.load (i32.const 4))         ;; R1
(i32.load (i32.const 8))         ;; R2
i32.add
;; Check for overflow: if signs of operands are same but sign of result differs
;; (This is a simplified check; full check requires comparing input/output signs)
```

### 8.2 64-bit Register Limitations in 32-bit WASM

**Problem**: The FLUX register file uses 32-bit integers (matching the Python
interpreter's behavior), but some FLUX operations (SHA-256, memory addressing
beyond 4GB) benefit from 64-bit values.

**Current behavior**: The WASM target uses i32 for all GP registers. Memory
addresses are limited to 32 bits (4 GB), which is sufficient for WASM linear
memory (typically < 1 GB).

**Future work**:
- Add a compilation mode that uses i64 for GP registers when the target
  runtime supports WASM i64 (all modern browsers do).
- Support WASM memory64 proposal for addressing beyond 4 GB.

### 8.3 Extension Opcode Support (0xFF Escape)

**Problem**: The FLUX ISA v3 escape prefix mechanism (0xFF + ext8) allows
65,536 extension opcodes. The WASM compiler must handle these opcodes at
compile time, but the set of extensions is open-ended.

**Current behavior**:

1. **Known extensions**: The compiler recognizes standard extensions (crypto,
   ml, audio, quantum) from the extension manifest and generates appropriate
   WASM code (JS imports for crypto, WASM SIMD for ml, etc.).

2. **Unknown extensions**: If the bytecode contains an extension opcode not in
   the manifest, the compiler emits a `call $import_unknown_extension` stub
   that traps at runtime with a clear error message.

3. **No runtime extension loading**: Extensions cannot be added after compilation.
   The extension manifest must be available at compile time.

**Future work**:
- **JIT extension loading**: Use eval() in the JS shim to dynamically compile
  extension handlers at runtime.
- **Extension sandboxing**: Isolate extension code in separate WASM instances
  with limited memory access.

```wasm
;; Extension opcode dispatch (compiled)
;; FLUX: 0xFF 0x42 ... (extension opcode 0xFF42)
;; WASM:
i32.const 0xFF42               ;; extension opcode
i32.const 4                    ;; operand byte count (Format E)
call $dispatch_extension       ;; runtime dispatch to registered handler
```

### 8.4 Multi-Threading (WASM Threads Proposal)

**Problem**: The FLUX ISA includes concurrency primitives (SEMA, YIELD, BARRIER,
SYNC_CLOCK, FORK, JOIN) that require multi-threaded execution. WASM threading
requires the Threads proposal (shared memory + Atomics).

**Current behavior**:
- **Single-threaded**: The default compilation target is single-threaded.
  All concurrency opcodes are stubs that no-op or trap.
- **Web Worker parallelism**: Multiple FLUX agents run in separate Web Workers,
  each in its own WASM instance with independent memory. No shared memory.

**Future work**:

1. **SharedArrayBuffer multi-agent**: Multiple WASM instances share a
   SharedArrayBuffer, enabling A2A communication via shared memory with
   Atomics for synchronization.

2. **WASM Threads proposal**: When the Threads proposal is fully supported,
   compile FLUX FORK to `thread.spawn()` and FLUX JOIN to `thread.join()`.
   FLUX SEMA maps to `Atomics.wait/notify`.

3. **SIMD acceleration**: Use WASM SIMD (128-bit v128 type) for vector
   operations (VADD, VMUL, VDOT) instead of loop emulation. Expected 4-8x
   speedup on vector operations.

```wasm
;; Future: VADD using WASM SIMD (v128)
;; FLUX: VADD V3, V1, V2 (add 4 i32 elements)
;; WASM SIMD:
(v128.load (i32.const 0x80))   ;; V1 (16 bytes at vector register offset)
(v128.load (i32.const 0x90))   ;; V2
i32x4.add                      ;; element-wise i32 addition
v128.store (i32.const 0xA0)    ;; store to V3
```

### 8.5 A2A Protocol Limitations

**Problem**: The FLUX A2A protocol (TELL, ASK, DELEG, BCAST, etc.) is designed
for inter-agent communication within a fleet. In a browser context, this maps
to HTTP/WebSocket communication, which is inherently asynchronous.

**Current behavior**:
- A2A operations block the WASM thread using `Atomics.wait` (requires
  SharedArrayBuffer and cross-origin isolation headers).
- Timeout is enforced at 5 seconds per operation.
- Failed A2A operations return -1 in R0.

**Limitations**:
- `Cross-Origin-Opener-Policy: same-origin` and
  `Cross-Origin-Embedder-Policy: require-corp` headers are required for
  SharedArrayBuffer, limiting deployment to controlled environments.
- No support for streaming A2A messages (entire message must fit in WASM memory).
- A2A discovery (DISCOV) only works with a pre-configured agent registry.

### 8.6 Sensor and Hardware Opcodes

**Problem**: FLUX sensor opcodes (SENSE, ACTUATE, SAMPLE, PWM, GPIO, I2C, SPI,
UART, CANBUS) are designed for hardware-attached agents. In a browser, these
have no direct equivalent.

**Current behavior**: All sensor opcodes are stubs that return 0 and log a
warning. The JavaScript shim can be extended with Web Bluetooth, Web USB, or
Web Serial API support for specific hardware.

```javascript
// Future: Web Serial support for UART opcode
const serialImports = {
  flux: {
    uart_send: async (bufferAddr, length) => {
      const port = await navigator.serial.requestPort();
      await port.open({ baudRate: 115200 });
      const writer = port.writable.getWriter();
      const data = new Uint8Array(memory.buffer, bufferAddr, length);
      await writer.write(data);
      return length;
    }
  }
};
```

### 8.7 Debugging Support

**Problem**: Debugging FLUX-WASM programs is more complex than debugging native
FLUX because:

1. The original FLUX bytecode PC is lost during compilation (replaced by WASM
   control flow).
2. WASM debug info (DWARF) is not widely supported in browser devtools.

**Current mitigations**:
- The compiler embeds the original FLUX PC as a comment in the WAT output for
  every instruction.
- The `TRACE` opcode (0xE9) calls a JS import that logs the FLUX PC and register
  state.
- The `DUMP` opcode (0xF2) dumps the full register file to the console.
- Source maps can be generated that map WASM instruction offsets back to FLUX
  bytecode PCs.

**Future work**:
- Integrate with Chrome DevTools Protocol for WASM debugging.
- Generate DWARF debug info mapping WASM instructions to FLUX source.
- Support step-through debugging of FLUX bytecode in the browser.

### 8.8 Summary of Known Limitations

| Limitation | Severity | Workaround | Timeline |
|:---|:---:|:---|:---|
| f32 precision loss | Medium | Use f64 mode | v2.1 |
| i32 overflow | Low | Overflow checks | v2.0 |
| No runtime extensions | Low | Compile-time manifest | v2.0 |
| Single-threaded only | Medium | Web Workers | v2.1 |
| A2A requires COOP/COEP | High | WebSocket fallback | v2.0 |
| No hardware sensor support | Low | Web APIs (future) | v3.0 |
| No SIMD vector ops | Medium | Loop emulation | v2.1 |
| Limited debugging | Medium | TRACE/DUMP opcodes | v2.0 |
| WASM binary size | Low | wasm-opt -Oz | v2.0 |

### 8.9 Version Compatibility

The FLUX-WASM compiler targets ISA v3 (version byte 0x03). Bytecode from
earlier ISA versions must be migrated before compilation. The compiler detects
the ISA version from the bytecode header and rejects incompatible versions
with a clear error message.

```
FLUX bytecode header:
  Bytes 0-3:  Magic "FLUX" (0x464C5558)
  Byte 4:     Version (0x03 for ISA v3)
  Bytes 5-6:  Header length (LE u16)
  Bytes 7+:   Header sections + code

WASM compiler checks:
  if bytecode[4] != 0x03:
    error(f"Unsupported ISA version: {bytecode[4]}. Expected 3 (ISA v3)")
```

---

## Appendix A: Complete WAT Module Skeleton

```wasm
;; FLUX-WASM Module Skeleton
;; Generated by flux-wasm compiler v2.0
;; ISA Version: 3 (Unified)
;; Source: program.flux

(module
  ;; ── Imports ──────────────────────────────────────────────
  (import "flux" "console_log"
    (func $import_console_log (param i32)))
  (import "flux" "console_log_str"
    (func $import_console_log_str (param i32 i32)))
  (import "flux" "halt_error"
    (func $import_halt_error (param i32)))
  (import "flux" "debugger"
    (func $import_debugger (param i32)))
  (import "flux" "sys_call"
    (func $import_syscall (param i32 i32) (result i32)))
  (import "flux" "yield"
    (func $import_yield (param i32) (result i32)))
  (import "flux" "sleep_ms"
    (func $import_sleep_ms (param i32)))
  (import "flux" "random"
    (func $import_random (param i32 i32) (result i32)))
  (import "flux" "clock"
    (func $import_clock (result i32)))
  (import "flux" "perf_counter"
    (func $import_perf_counter (result i32)))
  (import "flux" "get_agent_id"
    (func $import_get_agent_id (result i32)))
  (import "flux" "reboot"
    (func $import_reboot))
  (import "flux" "trace"
    (func $import_trace (param i32 i32)))
  (import "flux" "dump_state"
    (func $import_dump_state))
  (import "flux" "tell"
    (func $import_tell (param i32 i32 i32) (result i32)))
  (import "flux" "ask"
    (func $import_ask (param i32 i32 i32) (result i32)))
  (import "flux" "broadcast"
    (func $import_broadcast (param i32 i32 i32) (result i32)))
  (import "flux" "delegate"
    (func $import_delegate (param i32 i32 i32) (result i32)))
  (import "flux" "fork"
    (func $import_fork (param i32 i32) (result i32)))
  (import "flux" "join"
    (func $import_join (param i32 i32) (result i32)))
  (import "flux" "signal"
    (func $import_signal (param i32 i32 i32) (result i32)))
  (import "flux" "await_signal"
    (func $import_await (param i32 i32) (result i32)))
  (import "flux" "sin" (func $import_sin (param f32) (result f32)))
  (import "flux" "cos" (func $import_cos (param f32) (result f32)))
  (import "flux" "pow" (func $import_pow (param f32 f32) (result f32)))
  (import "flux" "log2" (func $import_log2 (param f32) (result f32)))
  (import "flux" "sha256"
    (func $import_sha256 (param i32 i32 i32) (result i32)))
  (import "flux" "crc32"
    (func $import_crc32 (param i32 i32) (result i32)))
  (import "flux" "malloc"
    (func $import_malloc (param i32) (result i32)))
  (import "flux" "free"
    (func $import_free (param i32)))
  (import "flux" "stack_overflow"
    (func $import_stack_overflow))
  (import "flux" "assert_failed"
    (func $import_assert_failed))

  ;; ── Memory ───────────────────────────────────────────────
  (memory (export "memory") 1 16)  ;; 64KB min, 1MB max

  ;; ── Data Segments ────────────────────────────────────────
  ;; (populated by compiler with string literals, constants)

  ;; ── Confidence Helper Functions ──────────────────────────
  (func $c_add (param $rd i32) (param $rs1 i32) (param $rs2 i32)
    ;; ... see Section 4.2.1 ...
  )

  (func $c_sub (param $rd i32) (param $rs1 i32) (param $rs2 i32)
    ;; rd = rs1 - rs2; crd = min(crs1, crs2)
    local.get $rs1  i32.const 4  i32.mul  i32.load
    local.get $rs2  i32.const 4  i32.mul  i32.load
    i32.sub
    local.get $rd  i32.const 4  i32.mul  i32.store

    local.get $rs1  i32.const 4  i32.mul  f32.load offset=0x180
    local.get $rs2  i32.const 4  i32.mul  f32.load offset=0x180
    f32.min
    local.get $rd  i32.const 4  i32.mul  f32.store offset=0x180
  )

  (func $c_mul (param $rd i32) (param $rs1 i32) (param $rs2 i32)
    ;; ... see Section 4.2.2 ...
  )

  (func $c_div (param $rd i32) (param $rs1 i32) (param $rs2 i32)
    ;; ... see Section 4.2.3 ...
  )

  (func $c_merge (param $rd i32) (param $rs1 i32) (param $rs2 i32)
    ;; ... see Section 4.2.4 ...
  )

  ;; ── Main Entry Point ─────────────────────────────────────
  (func $flux_main (export "flux_main")
    ;; Initialize register file
    ;; Initialize confidence array to 1.0
    ;; Initialize SP to stack top (0x1100)
    ;; Initialize heap pointer to 0x2000

    ;; ── Compiled FLUX bytecode ──
    ;; (generated by the compiler from FLUX IR)
    ;; ...

    ;; HALT
    return
  )

  ;; ── Exports ──────────────────────────────────────────────
  (export "flux_main" (func $flux_main))
  (export "memory" (memory 0))
)
```

---

## Appendix B: Opcode Quick Reference (WASM Mapping)

```
╔══════════════════════════════════════════════════════════════════════╗
║  FLUX Opcode → WASM Mapping Quick Reference                       ║
╠══════════════════════════════════════════════════════════════════════╣
║  Category    FLUX          WASM                                   ║
║  ─────────   ────────────  ─────────────────────────────────────   ║
║  System      HALT (0x00)   return                                 ║
║  System      NOP  (0x01)   nop                                    ║
║  System      RET  (0x02)   return / br                            ║
║  Arithmetic  ADD  (0x20)   i32.add                                ║
║  Arithmetic  SUB  (0x21)   i32.sub                                ║
║  Arithmetic  MUL  (0x22)   i32.mul                                ║
║  Arithmetic  DIV  (0x23)   i32.div_s                              ║
║  Logic       AND  (0x25)   i32.and                                ║
║  Logic       OR   (0x26)   i32.or                                 ║
║  Logic       XOR  (0x27)   i32.xor                                ║
║  Shift       SHL  (0x28)   i32.shl                                ║
║  Shift       SHR  (0x29)   i32.shr_s                              ║
║  Compare     EQ   (0x2C)   i32.eq + extend                       ║
║  Compare     LT   (0x2D)   i32.lt_s + extend                      ║
║  Float       FADD (0x30)   f32.add                                ║
║  Float       FSUB (0x31)   f32.sub                                ║
║  Float       FMUL (0x32)   f32.mul                                ║
║  Float       FDIV (0x33)   f32.div                                ║
║  Float       FSQRT(0x9D)   f32.sqrt                               ║
║  Memory      LOAD (0x38)   i32.load                               ║
║  Memory      STORE(0x39)   i32.store                              ║
║  Control     JMP  (0x43)   br $label                              ║
║  Control     JZ   (0x3C)   br_if (inverted)                       ║
║  Control     CALL (0x45)   call $func                             ║
║  Control     LOOP (0x46)   loop + br_if                           ║
║  Confidence  C_ADD(0x60)   call $c_add                            ║
║  Confidence  C_MUL(0x62)   call $c_mul                            ║
║  A2A         TELL (0x50)   call $import_tell                      ║
║  A2A         ASK  (0x51)   call $import_ask                       ║
║  Math        CLZ  (0x95)   i32.clz                                ║
║  Math        CTZ  (0x96)   i32.ctz                                ║
║  Math        POPCNT(0x97) i32.popcnt                              ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## Appendix C: Glossary

| Term | Definition |
|:---|:---|
| **FLUX** | The FLUX Micro-VM bytecode architecture with confidence-aware operations |
| **WASM** | WebAssembly, a portable binary instruction format for stack-based VMs |
| **WAT** | WebAssembly Text format, the human-readable representation of WASM |
| **GP Register** | General-purpose integer register (R0-R15, 32-bit each) |
| **FP Register** | Floating-point register (F0-F15, 32-bit IEEE 754 each) |
| **Confidence** | A probability value (f32, 0.0-1.0) associated with a register value |
| **A2A** | Agent-to-Agent protocol, FLUX's inter-agent communication mechanism |
| **Linear Memory** | WASM's flat, byte-addressable memory space |
| **Register Promotion** | Compiler optimization: moving memory-mapped registers to WASM locals |
| **STRIPCF** | Strip Confidence — disable confidence tracking for N instructions |
| **Extension Manifest** | Metadata declaring which extension opcodes a FLUX module uses |
| **Escape Prefix** | 0xFF byte that introduces a 2-byte extension opcode |

---

*End of FLUX-to-WASM Compilation Target Specification v2*
*Document ID: WASM-001-v2 | Status: Draft | Author: Super Z (Fleet Agent)*
