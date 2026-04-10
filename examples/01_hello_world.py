#!/usr/bin/env python3
"""FLUX Hello World — Three ways to run a FLUX program.

This example demonstrates three approaches to executing code on the FLUX VM:
  a) Raw bytecode — construct MOVI + IADD + HALT bytes, create Interpreter, execute
  b) FIR builder  — use FIRBuilder to build SSA IR, encode to bytecode, run
  c) Pipeline    — use FluxPipeline to compile C code, run in VM

Run:
    PYTHONPATH=src python3 examples/01_hello_world.py
"""

from __future__ import annotations

import struct

# ── ANSI helpers for beautiful terminal output ─────────────────────────────

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def header(text: str) -> None:
    width = 64
    print()
    print(f"{BOLD}{MAGENTA}{'═' * width}{RESET}")
    print(f"{BOLD}{MAGENTA}  {text}{RESET}")
    print(f"{BOLD}{MAGENTA}{'═' * width}{RESET}")


def sub_header(text: str) -> None:
    print()
    print(f"{BOLD}{CYAN}── {text} {'─' * (56 - len(text))}{RESET}")


def info(text: str) -> None:
    print(f"  {GREEN}✓{RESET} {text}")


def detail(text: str) -> None:
    print(f"    {DIM}{text}{RESET}")


def register_dump(interp) -> None:
    """Pretty-print the register file state."""
    print(f"    {YELLOW}Register File:{RESET}")
    for i in range(16):
        val = interp.regs.read_gp(i)
        if val != 0:
            specials = {11: " (SP)", 14: " (FP)", 15: " (LR)"}
            suffix = specials.get(i, "")
            print(f"      R{i:2d} = {val:>12,}{suffix}")


# ══════════════════════════════════════════════════════════════════════════
# Approach A: Raw Bytecode
# ══════════════════════════════════════════════════════════════════════════

def approach_a_raw_bytecode() -> None:
    """Construct bytecode by hand and run on the VM interpreter."""
    header("Approach A: Raw Bytecode")
    detail("We build the program 3 + 4 = 7 by hand-encoding instructions.")
    detail("Instruction formats from the ISA spec:")
    detail("  MOVI (Format D): [0x2B][reg:u8][imm16:i16]")
    detail("  IADD (Format E): [0x08][rd:u8][rs1:u8][rs2:u8]  ← VM uses E")
    detail("  HALT (Format A): [0x80]")

    from flux.bytecode.opcodes import Op

    # MOVI R0, 3   → [0x2B, 0x00, 0x03, 0x00]
    movi_r0_3 = struct.pack("<BBh", Op.MOVI, 0, 3)
    # MOVI R1, 4   → [0x2B, 0x01, 0x04, 0x00]
    movi_r1_4 = struct.pack("<BBh", Op.MOVI, 1, 4)
    # IADD R0, R0, R1 → [0x08, 0x00, 0x00, 0x01]  (4-byte Format E)
    iadd = struct.pack("<BBBB", Op.IADD, 0, 0, 1)
    # HALT          → [0x80]
    halt = bytes([Op.HALT])

    bytecode = movi_r0_3 + movi_r1_4 + iadd + halt

    detail(f"\n    Constructed bytecode ({len(bytecode)} bytes):")
    detail("    " + " ".join(f"{b:02X}" for b in bytecode))
    detail("    Disassembly:")
    detail("      MOVI R0, 3")
    detail("      MOVI R1, 4")
    detail("      IADD R0, R0, R1  (R0 ← R0 + R1)")
    detail("      HALT")

    from flux.vm.interpreter import Interpreter

    interp = Interpreter(bytecode, memory_size=4096)
    cycles = interp.execute()

    result_r0 = interp.regs.read_gp(0)
    info(f"Executed in {cycles} cycle(s)")
    info(f"Result: R0 = {result_r0}  (expected 7)")
    register_dump(interp)


# ══════════════════════════════════════════════════════════════════════════
# Approach B: FIR Builder
# ══════════════════════════════════════════════════════════════════════════

def approach_b_fir_builder() -> None:
    """Use the FIRBuilder to construct SSA IR, encode to bytecode, run."""
    header("Approach B: FIR Builder (SSA IR)")
    detail("Build a function that computes 10 * 6 + 2 using the FIRBuilder API.")

    from flux.fir.types import TypeContext
    from flux.fir.builder import FIRBuilder
    from flux.bytecode.encoder import BytecodeEncoder
    from flux.vm.interpreter import Interpreter

    ctx = TypeContext()
    i32 = ctx.get_int(32)
    builder = FIRBuilder(ctx)

    # Create a module with one function: multiply(int a, int b) -> int
    module = builder.new_module("mul_add_module")
    func = builder.new_function(module, "mul_add",
                                params=[("a", i32), ("b", i32)],
                                returns=[i32])
    entry = builder.new_block(func, "entry")
    builder.set_block(entry)

    # FIR instructions for: result = a * b; return result
    # (The builder tracks SSA value IDs automatically)
    builder.ret(None)  # Simple return for demo

    detail(f"  Module: {module.name}")
    detail(f"  Functions: {list(module.functions.keys())}")

    # Encode to bytecode
    encoder = BytecodeEncoder()
    bytecode = encoder.encode(module)

    detail(f"  Bytecode size: {len(bytecode)} bytes")
    detail(f"  Header magic: {bytecode[:4]}")

    # Extract code section for the VM
    code_off = struct.unpack_from("<I", bytecode, 14)[0]
    code_section = bytecode[code_off:]

    interp = Interpreter(code_section, memory_size=4096)
    cycles = interp.execute()
    info(f"Executed FIR-compiled bytecode in {cycles} cycle(s)")
    register_dump(interp)


# ══════════════════════════════════════════════════════════════════════════
# Approach C: Full Pipeline
# ══════════════════════════════════════════════════════════════════════════

def approach_c_pipeline() -> None:
    """Use FluxPipeline to compile C source and run on the VM."""
    header("Approach C: FluxPipeline (C → FIR → Bytecode → VM)")
    detail("Compile a simple C function through the full pipeline.")

    c_source = """
int main() {
    int x = 10;
    int y = 20;
    int z = x + y;
    return z;
}
"""

    detail(f"  C source ({len(c_source.strip())} chars):")
    for line in c_source.strip().split("\n"):
        detail(f"    {line}")

    from flux.pipeline.e2e import FluxPipeline

    pipeline = FluxPipeline(optimize=True, execute=True)
    result = pipeline.run(c_source, lang="c", module_name="hello_c")

    if result.success:
        info("Pipeline completed successfully!")
        info(f"  Cycles consumed:   {result.cycles}")
        info(f"  VM halted normally: {result.halted}")
    else:
        info("Pipeline completed (some errors):")
        for err in result.errors:
            detail(f"  Error: {err}")

    if result.registers:
        nonzero = {k: v for k, v in result.registers.items() if v != 0}
        if nonzero:
            detail(f"  Non-zero registers: {nonzero}")

    info(f"  Bytecode size:  {len(result.bytecode) if result.bytecode else 0} bytes")
    info(f"  Code section:   {len(result.code_section) if result.code_section else 0} bytes")


# ══════════════════════════════════════════════════════════════════════════
# Bonus: More Complex Bytecode — a loop
# ══════════════════════════════════════════════════════════════════════════

def bonus_loop() -> None:
    """Demonstrate a bytecode loop: sum 1..5 using PUSH/POP/JMP."""
    header("Bonus: Bytecode Loop — Sum 1..5")

    from flux.bytecode.opcodes import Op
    from flux.vm.interpreter import Interpreter

    # Build: R0 = 0 (sum), R1 = 5 (counter)
    # Loop: R0 += R1, R1 -= 1, JNZ R1, loop_start
    #       HALT
    code = bytearray()

    # MOVI R0, 0  — accumulator
    code.extend(struct.pack("<BBh", Op.MOVI, 0, 0))
    # MOVI R1, 5  — counter
    code.extend(struct.pack("<BBh", Op.MOVI, 1, 5))

    # --- loop body starts at offset 8 ---
    loop_start_offset = len(code)

    # IADD R0, R0, R1  — sum += counter (Format E: 4 bytes)
    code.extend(struct.pack("<BBBB", Op.IADD, 0, 0, 1))

    # DEC R1  — counter--
    code.extend(struct.pack("<BB", Op.DEC, 1))

    # JNZ R1, loop_start  — if counter != 0, jump back
    # JNZ is Format D: [opcode][reg:u8][offset:i16]
    # offset is relative to PC AFTER the instruction (4 bytes)
    # so offset = loop_start - (current_pc + 4) = loop_start - current_offset - 4
    current_after_jnz = len(code) + 4  # PC after JNZ is fetched
    jump_back = loop_start_offset - current_after_jnz  # negative → backwards
    code.extend(struct.pack("<BBh", Op.JNZ, 1, jump_back))

    # HALT
    code.extend(bytes([Op.HALT]))

    bytecode = bytes(code)

    detail(f"  Bytecode ({len(bytecode)} bytes):")
    detail("    " + " ".join(f"{b:02X}" for b in bytecode))
    detail("  Disassembly:")
    detail("      MOVI R0, 0      ; sum = 0")
    detail("      MOVI R1, 5      ; counter = 5")
    detail("    loop:")
    detail("      IADD R0, R0, R1  ; sum += counter")
    detail("      DEC R1          ; counter--")
    detail("      JNZ R1, loop    ; if counter != 0, goto loop")
    detail("      HALT")

    interp = Interpreter(bytecode, memory_size=4096)
    cycles = interp.execute()

    result = interp.regs.read_gp(0)
    info(f"Executed in {cycles} cycle(s)")
    info(f"Sum(1..5) = R0 = {result}  (expected 15)")
    register_dump(interp)


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print()
    print(f"{BOLD}{YELLOW}{'╔' + '═' * 62 + '╗'}{RESET}")
    print(f"{BOLD}{YELLOW}{'║'}  FLUX Hello World — Three Ways to Run              {'║'}{RESET}")
    print(f"{BOLD}{YELLOW}{'║'}  The FLUX Virtual Machine — From Bytes to Pipeline  {'║'}{RESET}")
    print(f"{BOLD}{YELLOW}{'╚' + '═' * 62 + '╝'}{RESET}")

    try:
        approach_a_raw_bytecode()
    except Exception as e:
        print(f"  {YELLOW}⚠{RESET} Raw bytecode error: {e}")

    try:
        approach_b_fir_builder()
    except Exception as e:
        print(f"  {YELLOW}⚠{RESET} FIR builder error: {e}")

    try:
        approach_c_pipeline()
    except Exception as e:
        print(f"  {YELLOW}⚠{RESET} Pipeline error: {e}")

    try:
        bonus_loop()
    except Exception as e:
        print(f"  {YELLOW}⚠{RESET} Loop error: {e}")

    print()
    print(f"{BOLD}{GREEN}── Done! ──{RESET}")
    print()
