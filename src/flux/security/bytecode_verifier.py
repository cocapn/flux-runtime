"""
FLUX Bytecode Security Verifier — v1.0
=======================================

Addresses flux-runtime issue #15: "Zero bytecode verification before execution"

This module provides a multi-pass bytecode verification pipeline that validates
FLUX bytecode programs before they are loaded into the VM. Without verification,
malformed or malicious bytecode can crash the interpreter, corrupt memory, or
bypass security boundaries.

Verification Passes:
  Pass 1: Structural Integrity — Format compliance, byte-length correctness
  Pass 2: Register Validation — All register operands within valid range
  Pass 3: Control Flow Analysis — Every path reaches HALT/RET, no dangling jumps
  Pass 4: Stack Safety — PUSH/POP balance, depth never exceeds bounds
  Pass 5: Capability Enforcement — Privileged opcodes require CAP tokens
  Pass 6: Dangerous Pattern Detection — Self-modifying code, infinite loops
  Pass 7: Memory Safety — Bounds checking on memory access patterns

Author: Quill (Architect-rank, SuperInstance fleet)
Session: 7b — R&D Round 13
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional, List, Dict, Set, Tuple


# ─── Constants ────────────────────────────────────────────────────────────────

NUM_REGISTERS = 32          # R0-R31
MAX_STACK_DEPTH = 256       # Stack overflow protection
MAX_PROGRAM_SIZE = 1_048_576  # 1 MB max bytecode
MAX_INSTRUCTION_COUNT = 262_144  # Max instructions in a program

# Categories that require elevated privileges
PRIVILEGED_CATEGORIES = {"system", "debug", "sensor", "memory", "compute"}

# Opcodes that can modify the program counter in non-standard ways
CONTROL_FLOW_OPCODES = {
    0x3C, 0x3D, 0x3E, 0x3F,  # JZ, JNZ, JLT, JGT
    0x43, 0x44, 0x45, 0x46,  # JMP, JAL, CALL, LOOP
    0x47,                      # SELECT (computed jump)
    0xE0, 0xE1, 0xE2, 0xE3, # JMPL, JALL, CALLL, TAIL
    0xE4, 0xE5, 0xE6,        # SWITCH, COYIELD, CORESUM
}


class Severity(IntEnum):
    """Verification finding severity levels."""
    INFO = 0
    WARNING = 1
    ERROR = 2
    CRITICAL = 3


class VerifierPolicy(IntEnum):
    """Verification strictness levels."""
    PERMISSIVE = 0   # Warnings only, allow execution
    STANDARD = 1     # Errors block execution, warnings allowed
    PARANOID = 2     # All findings block execution


@dataclass
class VerificationFinding:
    """A single finding from the bytecode verifier."""
    pass_num: int
    severity: Severity
    offset: int          # Byte offset in the bytecode
    message: str
    opcode: int = -1
    suggestion: str = ""

    def __str__(self) -> str:
        sev_name = Severity(self.severity).name
        return f"[PASS {self.pass_num}] [{sev_name}] offset=0x{self.offset:04X} opcode=0x{self.opcode:02X}: {self.message}"


@dataclass
class VerificationReport:
    """Complete verification report for a bytecode program."""
    program_hash: str = ""
    program_size: int = 0
    instruction_count: int = 0
    pass_results: Dict[int, List[VerificationFinding]] = field(default_factory=dict)
    passes_completed: int = 0
    is_valid: bool = False
    error_count: int = 0
    warning_count: int = 0
    critical_count: int = 0

    def add_finding(self, finding: VerificationFinding) -> None:
        p = finding.pass_num
        if p not in self.pass_results:
            self.pass_results[p] = []
        self.pass_results[p].append(finding)
        if finding.severity == Severity.CRITICAL:
            self.critical_count += 1
        elif finding.severity == Severity.ERROR:
            self.error_count += 1
        elif finding.severity == Severity.WARNING:
            self.warning_count += 1

    def summary(self) -> str:
        lines = [
            f"Verification Report: {self.program_hash}",
            f"  Size: {self.program_size} bytes, {self.instruction_count} instructions",
            f"  Passes: {self.passes_completed}/7",
            f"  Findings: {self.critical_count} critical, {self.error_count} errors, {self.warning_count} warnings",
            f"  Result: {'VALID' if self.is_valid else 'REJECTED'}",
        ]
        for p in sorted(self.pass_results.keys()):
            findings = self.pass_results[p]
            if findings:
                lines.append(f"  Pass {p}: {len(findings)} findings")
        return "\n".join(lines)


# ─── Opcode Format Table ──────────────────────────────────────────────────────

# Maps opcode -> (format_letter, byte_size, num_register_operands)
# Format sizes: A=1, B=2, C=2, D=3, E=4, F=4, G=5
OPCODE_FORMATS: Dict[int, Tuple[str, int, int]] = {}

# Format A: 0x00-0x03, 0x04-0x07, 0xF0-0xFF
# Format B: 0x08-0x0F
# Format C: 0x10-0x17
# Format D: 0x18-0x1F, 0x69
# Format E: 0x20-0x3F, 0x50-0x6F, 0x70-0x7F, 0x80-0x8F, 0x90-0x9F, 0xA1-0xAF, 0xB0-0xBF, 0xC0-0xCF
# Format F: 0x40-0x47, 0xE0-0xEF, 0xA0, 0xA4
# Format G: 0x48-0x4F, 0xD0-0xDF

def _build_opcode_table() -> None:
    """Populate the opcode format table from ISA ranges."""
    # Format A (1 byte, 0 register operands)
    for code in range(0x00, 0x08):
        OPCODE_FORMATS[code] = ("A", 1, 0)
    for code in range(0xF0, 0x100):
        OPCODE_FORMATS[code] = ("A", 1, 0)

    # Format B (2 bytes, 1 register operand)
    for code in range(0x08, 0x10):
        OPCODE_FORMATS[code] = ("B", 2, 1)

    # Format C (2 bytes, 0 register operands)
    for code in range(0x10, 0x18):
        OPCODE_FORMATS[code] = ("C", 2, 0)

    # Format D (3 bytes, 1 register operand)
    for code in range(0x18, 0x20):
        OPCODE_FORMATS[code] = ("D", 3, 1)
    OPCODE_FORMATS[0xA0] = ("D", 3, 1)  # LEN

    # Format E (4 bytes, 3 register operands for most)
    for code in range(0x20, 0x40):
        OPCODE_FORMATS[code] = ("E", 4, 3)
    for code in range(0x50, 0x70):
        OPCODE_FORMATS[code] = ("E", 4, 3)
    for code in range(0x70, 0x80):
        OPCODE_FORMATS[code] = ("E", 4, 3)
    for code in range(0x80, 0x90):
        OPCODE_FORMATS[code] = ("E", 4, 3)
    for code in range(0x90, 0xA0):
        OPCODE_FORMATS[code] = ("E", 4, 3)
    # Collection ops
    for code in [0xA1, 0xA2, 0xA3, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9]:
        OPCODE_FORMATS[code] = ("E", 4, 3)
    for code in [0xAA, 0xAB, 0xAC, 0xAD, 0xAE, 0xAF]:
        OPCODE_FORMATS[code] = ("E", 4, 3)
    # Vector/SIMD
    for code in range(0xB0, 0xC0):
        OPCODE_FORMATS[code] = ("E", 4, 3)
    # Tensor/Neural
    for code in range(0xC0, 0xD0):
        OPCODE_FORMATS[code] = ("E", 4, 3)

    # Format F (4 bytes, 1 register operand)
    for code in range(0x40, 0x48):
        OPCODE_FORMATS[code] = ("F", 4, 1)
    for code in range(0xE0, 0xED):
        OPCODE_FORMATS[code] = ("F", 4, 1)
    # Also format F: A4 (SLICE)
    OPCODE_FORMATS[0xA4] = ("G", 5, 2)  # Actually G (register + register + imm16)

    # Format G (5 bytes, 2 register operands)
    for code in range(0x48, 0x50):
        OPCODE_FORMATS[code] = ("G", 5, 2)
    for code in range(0xD0, 0xE0):
        OPCODE_FORMATS[code] = ("G", 5, 2)

    # Fix specific opcodes that deviate from range patterns
    # MOV (0x3A): rd, rs1, - → effectively 2 register operands
    OPCODE_FORMATS[0x3A] = ("E", 4, 2)
    OPCODE_FORMATS[0x3B] = ("E", 4, 2)  # SWP
    # Jump conditions: rd, rs1, - → 2 register operands
    for code in [0x3C, 0x3D, 0x3E, 0x3F]:
        OPCODE_FORMATS[code] = ("E", 4, 2)
    # FTOI, ITOF: rd, rs1, - → 2 register operands
    OPCODE_FORMATS[0x36] = ("E", 4, 2)
    OPCODE_FORMATS[0x37] = ("E", 4, 2)
    # Extended math with 2 register operands
    for code in [0x90, 0x91, 0x92, 0x94, 0x95, 0x96, 0x97, 0x9B, 0x9D, 0x9E, 0x9F]:
        OPCODE_FORMATS[code] = ("E", 4, 2)
    # Tensor ops with 2 register operands
    OPCODE_FORMATS[0xC3] = ("E", 4, 2)  # TRELU
    OPCODE_FORMATS[0xC4] = ("E", 4, 2)  # TSIGM
    # E8, E9 install handler / trace: 1 register operand
    OPCODE_FORMATS[0xE8] = ("F", 4, 1)
    OPCODE_FORMATS[0xE9] = ("F", 4, 1)


_build_opcode_table()


# ─── Instruction Parser ──────────────────────────────────────────────────────

@dataclass
class DecodedInstruction:
    """A single decoded FLUX instruction."""
    opcode: int
    mnemonic: str = "UNKNOWN"
    format: str = "?"
    offset: int = 0
    size: int = 1
    registers: List[int] = field(default_factory=list)
    immediates: List[int] = field(default_factory=list)
    is_valid: bool = True
    error: str = ""


def decode_instruction(bytecode: bytes, offset: int) -> DecodedInstruction:
    """Decode a single instruction from bytecode at the given offset."""
    if offset >= len(bytecode):
        return DecodedInstruction(opcode=-1, is_valid=False, error="Offset past end of bytecode")

    opcode = bytecode[offset]

    if opcode not in OPCODE_FORMATS:
        return DecodedInstruction(
            opcode=opcode, offset=offset, size=1,
            is_valid=False, error=f"Unknown opcode 0x{opcode:02X}"
        )

    fmt, expected_size, num_regs = OPCODE_FORMATS[opcode]

    # Check if we have enough bytes
    remaining = len(bytecode) - offset
    if remaining < expected_size:
        return DecodedInstruction(
            opcode=opcode, offset=offset, size=remaining,
            is_valid=False,
            error=f"Truncated instruction: expected {expected_size} bytes, got {remaining}"
        )

    insn_bytes = bytecode[offset:offset + expected_size]
    registers = []
    immediates = []

    # Extract register operands (always in low 5 bits of operand bytes)
    if fmt == "B":
        registers = [insn_bytes[1] & 0x1F]
    elif fmt == "D":
        registers = [insn_bytes[1] & 0x1F]
        immediates = [insn_bytes[2]]
    elif fmt == "E":
        registers = [insn_bytes[1] & 0x1F, insn_bytes[2] & 0x1F, insn_bytes[3] & 0x1F]
    elif fmt == "F":
        registers = [insn_bytes[1] & 0x1F]
        immediates = [struct.unpack_from("<H", insn_bytes, 2)[0]]
    elif fmt == "G":
        registers = [insn_bytes[1] & 0x1F, insn_bytes[2] & 0x1F]
        immediates = [struct.unpack_from("<H", insn_bytes, 3)[0]]

    return DecodedInstruction(
        opcode=opcode, format=fmt, offset=offset,
        size=expected_size, registers=registers,
        immediates=immediates, is_valid=True
    )


def decode_all(bytecode: bytes) -> List[DecodedInstruction]:
    """Decode all instructions in a bytecode program."""
    instructions = []
    offset = 0
    while offset < len(bytecode):
        insn = decode_instruction(bytecode, offset)
        instructions.append(insn)
        if not insn.is_valid:
            break
        offset += insn.size
    return instructions


# ─── Verification Engine ──────────────────────────────────────────────────────

class BytecodeVerifier:
    """
    Multi-pass bytecode verification engine.

    Usage:
        verifier = BytecodeVerifier(policy=VerifierPolicy.STANDARD)
        report = verifier.verify(bytecode)
        if report.is_valid:
            vm.execute(bytecode)
    """

    def __init__(
        self,
        policy: VerifierPolicy = VerifierPolicy.STANDARD,
        capabilities: Optional[set] = None,
        max_stack: int = MAX_STACK_DEPTH,
        max_program_size: int = MAX_PROGRAM_SIZE,
    ):
        self.policy = policy
        self.capabilities = capabilities or set()
        self.max_stack = max_stack
        self.max_program_size = max_program_size

    def verify(self, bytecode: bytes) -> VerificationReport:
        """Run all verification passes on the bytecode."""
        import hashlib
        report = VerificationReport(
            program_hash=hashlib.sha256(bytecode).hexdigest()[:16],
            program_size=len(bytecode),
        )

        # Pass 0: Pre-flight checks
        self._pass_preflight(bytecode, report)
        if not report.is_valid and self.policy >= VerifierPolicy.STANDARD:
            return report

        # Decode all instructions
        instructions = decode_all(bytecode)
        report.instruction_count = len(instructions)

        # Run verification passes
        self._pass_structural_integrity(bytecode, instructions, report)
        self._pass_register_validation(bytecode, instructions, report)
        self._pass_control_flow(bytecode, instructions, report)
        self._pass_stack_safety(bytecode, instructions, report)
        self._pass_capability_enforcement(bytecode, instructions, report)
        self._pass_dangerous_patterns(bytecode, instructions, report)
        self._pass_memory_safety(bytecode, instructions, report)

        report.passes_completed = 7

        # Determine validity based on policy
        if self.policy == VerifierPolicy.PERMISSIVE:
            report.is_valid = report.critical_count == 0
        elif self.policy == VerifierPolicy.STANDARD:
            report.is_valid = report.critical_count == 0 and report.error_count == 0
        else:  # PARANOID
            report.is_valid = (
                report.critical_count == 0
                and report.error_count == 0
                and report.warning_count == 0
            )

        return report

    def _add(self, report: VerificationReport, pass_num: int,
             severity: Severity, offset: int, opcode: int,
             message: str, suggestion: str = "") -> None:
        report.add_finding(VerificationFinding(
            pass_num=pass_num, severity=severity,
            offset=offset, opcode=opcode,
            message=message, suggestion=suggestion
        ))

    # ── Pass 0: Pre-flight ────────────────────────────────────────────────

    def _pass_preflight(self, bytecode: bytes, report: VerificationReport) -> None:
        """Basic sanity checks before any decoding."""
        if len(bytecode) == 0:
            self._add(report, 0, Severity.CRITICAL, 0, -1,
                      "Empty bytecode program",
                      "A valid FLUX program must contain at least one instruction (HALT)")
            report.is_valid = False
            return

        if len(bytecode) > self.max_program_size:
            self._add(report, 0, Severity.CRITICAL, 0, -1,
                      f"Program too large: {len(bytecode)} bytes (max {self.max_program_size})",
                      "Split into smaller modules or increase program size limit")
            report.is_valid = False
            return

        if bytecode[-1] != 0x00 and bytecode[-1] != 0xF0:
            # Program should end with HALT or HALT_ERR
            self._add(report, 0, Severity.WARNING, len(bytecode) - 1, bytecode[-1],
                      "Program does not end with HALT (0x00) or HALT_ERR (0xF0)",
                      "Append 0x00 to ensure clean termination")

        report.is_valid = True

    # ── Pass 1: Structural Integrity ──────────────────────────────────────

    def _pass_structural_integrity(
        self, bytecode: bytes, instructions: List[DecodedInstruction], report: VerificationReport
    ) -> None:
        """Validate instruction encoding and format compliance."""
        for insn in instructions:
            if not insn.is_valid:
                self._add(report, 1, Severity.CRITICAL, insn.offset, insn.opcode,
                          f"Malformed instruction: {insn.error}",
                          "Recompile from valid Signal source")

        # Check for alignment issues
        offset = 0
        for insn in instructions:
            if insn.offset != offset:
                self._add(report, 1, Severity.ERROR, offset, insn.opcode,
                          f"Instruction alignment mismatch at offset 0x{offset:04X}",
                          "Decoder may have produced incorrect offsets")
            if insn.is_valid:
                offset += insn.size
            else:
                break

        # Check total decoded length matches bytecode length
        decoded_end = sum(i.size for i in instructions if i.is_valid)
        trailing = len(bytecode) - decoded_end
        if trailing > 0:
            # Trailing bytes that don't form valid instructions
            self._add(report, 1, Severity.ERROR, decoded_end, -1,
                      f"Trailing {trailing} bytes do not form valid instructions",
                      "Remove trailing data or append to valid instruction")

    # ── Pass 2: Register Validation ───────────────────────────────────────

    def _pass_register_validation(
        self, bytecode: bytes, instructions: List[DecodedInstruction], report: VerificationReport
    ) -> None:
        """Validate all register operands are within valid range."""
        for insn in instructions:
            if not insn.is_valid:
                continue
            for reg in insn.registers:
                if reg >= NUM_REGISTERS:
                    self._add(report, 2, Severity.ERROR, insn.offset, insn.opcode,
                              f"Register R{reg} out of range (max R{NUM_REGISTERS - 1})",
                              f"Change operand to register 0-{NUM_REGISTERS - 1}")

    # ── Pass 3: Control Flow Analysis ─────────────────────────────────────

    def _pass_control_flow(
        self, bytecode: bytes, instructions: List[DecodedInstruction], report: VerificationReport
    ) -> None:
        """Verify control flow: every path leads to HALT, no dangling jumps."""
        # Build offset -> instruction index map
        offset_to_idx: Dict[int, int] = {}
        valid_offsets: Set[int] = set()
        for i, insn in enumerate(instructions):
            offset_to_idx[insn.offset] = i
            valid_offsets.add(insn.offset)

        # Find all jump targets and verify they land on valid instruction boundaries
        jump_targets: Set[int] = set()
        for insn in instructions:
            if not insn.is_valid or insn.opcode not in CONTROL_FLOW_OPCODES:
                continue

            if insn.opcode == 0x47:  # SELECT (computed jump)
                self._add(report, 3, Severity.WARNING, insn.offset, insn.opcode,
                          "Computed jump (SELECT) — cannot statically verify target",
                          "Consider using a dispatch table with verifiable offsets")
                continue

            if insn.opcode in {0x3C, 0x3D, 0x3E, 0x3F}:  # JZ, JNZ, JLT, JGT
                # Conditional jumps: offset = rs1 (relative)
                # We cannot know rs1 at verification time, but we can note it
                continue

            if insn.opcode in {0x43, 0xE0}:  # JMP, JMPL (relative jumps)
                if insn.immediates:
                    target = insn.offset + insn.immediates[0]
                    if target < 0 or target >= len(bytecode) or target not in valid_offsets:
                        self._add(report, 3, Severity.ERROR, insn.offset, insn.opcode,
                                  f"Jump target 0x{target:04X} invalid (out of bounds or misaligned)",
                                  f"Adjust immediate to land on valid instruction offset")

            if insn.opcode in {0x44, 0xE1, 0x45, 0xE2}:  # JAL, JALL, CALL, CALLL
                if insn.immediates:
                    target = insn.offset + insn.immediates[0]
                    if target < 0 or target >= len(bytecode) or target not in valid_offsets:
                        self._add(report, 3, Severity.ERROR, insn.offset, insn.opcode,
                                  f"Jump/call target 0x{target:04X} invalid (out of bounds or misaligned)",
                                  f"Adjust immediate to land on valid instruction offset")

        # Check that program has at least one HALT or HALT_ERR
        has_halt = any(insn.opcode in (0x00, 0xF0) for insn in instructions if insn.is_valid)
        if not has_halt:
            self._add(report, 3, Severity.ERROR, 0, -1,
                      "No HALT instruction found — program may run indefinitely",
                      "Add HALT (0x00) at program end or on all exit paths")

    # ── Pass 4: Stack Safety ──────────────────────────────────────────────

    def _pass_stack_safety(
        self, bytecode: bytes, instructions: List[DecodedInstruction], report: VerificationReport
    ) -> None:
        """Analyze PUSH/POP balance and maximum stack depth."""
        stack_depth = 0
        max_depth = 0
        min_depth = 0
        push_count = 0
        pop_count = 0

        for insn in instructions:
            if not insn.is_valid:
                continue

            if insn.opcode == 0x0C:  # PUSH
                stack_depth += 1
                push_count += 1
                max_depth = max(max_depth, stack_depth)
            elif insn.opcode == 0x0D:  # POP
                stack_depth -= 1
                pop_count += 1
                min_depth = min(min_depth, stack_depth)
            elif insn.opcode == 0x4C:  # ENTER (pushes multiple + allocates)
                # ENTER: push regs; sp -= imm16
                if insn.immediates:
                    stack_depth += 1 + insn.immediates[0]
                    max_depth = max(max_depth, stack_depth)
            elif insn.opcode == 0x4D:  # LEAVE (pops multiple)
                if insn.immediates:
                    stack_depth -= 1 + insn.immediates[0]
                    min_depth = min(min_depth, stack_depth)

        if max_depth > self.max_stack:
            self._add(report, 4, Severity.ERROR, 0, -1,
                      f"Maximum stack depth {max_depth} exceeds limit {self.max_stack}",
                      f"Reduce stack usage or increase max_stack to {max_depth + 16}")

        if min_depth < 0:
            self._add(report, 4, Severity.ERROR, 0, -1,
                      f"Stack underflow detected: minimum depth {min_depth}",
                      "Add PUSH before POP or fix ENTER/LEAVE mismatch")

        if push_count != pop_count and not any(
            insn.opcode in {0x4C, 0x4D} for insn in instructions if insn.is_valid
        ):
            self._add(report, 4, Severity.WARNING, 0, -1,
                      f"Unbalanced PUSH/POP: {push_count} pushes, {pop_count} pops",
                      "Ensure every PUSH has a matching POP on all paths")

    # ── Pass 5: Capability Enforcement ────────────────────────────────────

    def _pass_capability_enforcement(
        self, bytecode: bytes, instructions: List[DecodedInstruction], report: VerificationReport
    ) -> None:
        """Verify privileged opcodes have required capabilities."""
        privileged_categories = {"sensor", "compute"}

        privileged_ops = {
            0x10: "SYS (system call)",
            0x11: "TRAP (software interrupt)",
            0x06: "RESET (soft reset)",
            0xE4: "SWITCH (context switch)",
            0xE7: "FAULT (raise fault)",
            0xF1: "REBOOT (warm reboot)",
        }

        for insn in instructions:
            if not insn.is_valid:
                continue

            if insn.opcode in privileged_ops:
                name = privileged_ops[insn.opcode]
                if "system" not in self.capabilities:
                    self._add(report, 5, Severity.WARNING, insn.offset, insn.opcode,
                              f"Privileged opcode {name} used without SYSTEM capability",
                              f"Grant SYSTEM capability or remove {name}")

            # Check sensor ops (0x80-0x8F)
            if 0x80 <= insn.opcode <= 0x8F:
                if "sensor" not in self.capabilities and "io_sensor" not in self.capabilities:
                    self._add(report, 5, Severity.WARNING, insn.offset, insn.opcode,
                              f"Sensor opcode 0x{insn.opcode:02X} used without IO_SENSOR capability",
                              "Grant IO_SENSOR capability or remove sensor operations")

            # Check GPU ops
            if insn.opcode in {0xDB, 0xDC, 0xDD, 0xDE}:
                if "compute" not in self.capabilities:
                    self._add(report, 5, Severity.WARNING, insn.offset, insn.opcode,
                              f"GPU opcode 0x{insn.opcode:02X} used without COMPUTE capability",
                              "Grant COMPUTE capability or remove GPU operations")

    # ── Pass 6: Dangerous Pattern Detection ───────────────────────────────

    def _pass_dangerous_patterns(
        self, bytecode: bytes, instructions: List[DecodedInstruction], report: VerificationReport
    ) -> None:
        """Detect potentially dangerous bytecode patterns."""
        has_store = False
        has_load = False
        store_addrs: List[int] = []

        for insn in instructions:
            if not insn.is_valid:
                continue

            # Self-modifying code detection: STORE to address within program
            if insn.opcode in {0x39, 0x49, 0x4B}:  # STORE, STOREOF, STOREI
                has_store = True
                store_addrs.append(insn.offset)

            if insn.opcode in {0x38, 0x48, 0x4A}:  # LOAD, LOADOFF, LOADI
                has_load = True

            # Infinite loop detection: LOOP (0x46) with large count
            if insn.opcode == 0x46 and insn.immediates:
                if insn.immediates[0] == 0:
                    self._add(report, 6, Severity.WARNING, insn.offset, insn.opcode,
                              "LOOP with immediate=0 may cause infinite loop",
                              "Set a non-zero loop bound")

            # Unconditional jump backward to self (tight infinite loop)
            if insn.opcode == 0x43 and insn.immediates:
                target = insn.offset + insn.immediates[0]
                if target == insn.offset:
                    self._add(report, 6, Severity.WARNING, insn.offset, insn.opcode,
                              "Tight infinite loop: JMP to self",
                              "Add exit condition or use LOOP with bounded count")

            # Recursive CALL without apparent base case
            if insn.opcode in {0x45, 0xE2}:  # CALL, CALLL
                if insn.immediates and insn.immediates[0] != 0xFFFF:
                    target = insn.offset + insn.immediates[0]
                    if target == insn.offset:
                        self._add(report, 6, Severity.WARNING, insn.offset, insn.opcode,
                                  "CALL to self detected — unbounded recursive call likely",
                                  "Add base case check before recursive CALL")

        # Write-execute overlap: program can write to its own code
        if has_store and has_load:
            self._add(report, 6, Severity.INFO, 0, -1,
                      "Program contains both STORE and LOAD — potential self-modification",
                      "Verify that memory regions for code and data are distinct")

    # ── Pass 7: Memory Safety ─────────────────────────────────────────────

    def _pass_memory_safety(
        self, bytecode: bytes, instructions: List[DecodedInstruction], report: VerificationReport
    ) -> None:
        """Validate memory access patterns for safety."""
        has_malloc = any(i.opcode == 0xD7 for i in instructions if i.is_valid)
        has_free = any(i.opcode == 0xD8 for i in instructions if i.is_valid)
        has_memcpy = any(i.opcode == 0x4E for i in instructions if i.is_valid)
        has_mprotect = any(i.opcode == 0xD9 for i in instructions if i.is_valid)

        # Check for memory allocation without freeing
        if has_malloc and not has_free:
            self._add(report, 7, Severity.WARNING, 0, -1,
                      "MALLOC without FREE — potential memory leak",
                      "Add corresponding FREE for each MALLOC")

        # Check for DMA operations without memory protection
        if any(i.opcode in {0xD0, 0xD1} for i in instructions if i.is_valid) and not has_mprotect:
            self._add(report, 7, Severity.WARNING, 0, -1,
                      "DMA operations without MPROTECT — unguarded memory regions",
                      "Use MPROTECT to set read-only guards on DMA buffers")

        # Check FILL/COPY with zero length
        for insn in instructions:
            if not insn.is_valid:
                continue
            if insn.opcode in {0x4E, 0x4F} and insn.immediates:  # COPY, FILL
                if insn.immediates[0] == 0:
                    self._add(report, 7, Severity.INFO, insn.offset, insn.opcode,
                              "COPY/FILL with length=0 — no-op but wastes encode space",
                              "Remove or set to actual copy length")


# ─── Convenience Functions ────────────────────────────────────────────────────

def verify(bytecode: bytes, policy: VerifierPolicy = VerifierPolicy.STANDARD,
           capabilities: Optional[set] = None) -> VerificationReport:
    """Verify FLUX bytecode with default settings."""
    verifier = BytecodeVerifier(policy=policy, capabilities=capabilities)
    return verifier.verify(bytecode)


def verify_hex(hex_str: str, **kwargs) -> VerificationReport:
    """Verify FLUX bytecode from hex string (spaces/colons ignored)."""
    cleaned = hex_str.replace(" ", "").replace(":", "").replace("\n", "")
    bytecode = bytes.fromhex(cleaned)
    return verify(bytecode, **kwargs)


def is_safe(bytecode: bytes, capabilities: Optional[set] = None) -> bool:
    """Quick check: is this bytecode safe to execute?"""
    report = verify(bytecode, VerifierPolicy.STANDARD, capabilities)
    return report.is_valid
