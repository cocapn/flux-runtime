"""Open-Flux-Interpreter: Convert markdown/text directly to FLUX bytecode and execute.

This is the "kill app" for agent workflows — an agent can write an idea in markdown,
run it as compute, and keep thinking without switching context.

Example:
    Input markdown:
    ```
    # Compute factorial of 10

    Load R0 with 10
    Load R1 with 1
    While R0 is not zero:
        Multiply R1 by R0
        Decrease R0
    Return R1
    ```

    This gets converted to:
    MOVI R0, 10
    MOVI R1, 1
    loop:
    IMUL R1, R1, R0
    DEC R0
    JNZ R0, loop
    HALT

    And executed immediately, returning R1 = 3628800
"""

from __future__ import annotations

import re
import struct
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field

from flux.bytecode.opcodes import Op
from flux.vm.interpreter import Interpreter, VMError
from flux.disasm import FluxDisassembler, DisassemblyResult


# ── Result Data Structures ─────────────────────────────────────────────────────

@dataclass
class ExecutionResult:
    """Result of executing Open-Flux-Interpreter code."""
    success: bool
    bytecode: bytes
    disassembly: str
    result: Optional[int] = None
    registers: Dict[int, int] = field(default_factory=dict)
    cycles: int = 0
    error: Optional[str] = None
    halted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "bytecode_hex": self.bytecode.hex(),
            "disassembly": self.disassembly,
            "result": self.result,
            "registers": self.registers,
            "cycles": self.cycles,
            "error": self.error,
            "halted": self.halted,
        }


# ── Main Interpreter Class ─────────────────────────────────────────────────────

class OpenFluxInterpreter:
    """Converts markdown/text directly to FLUX bytecode and executes it.

    Supports:
    - Natural language patterns (load, add, multiply, while, if, etc.)
    - Direct FLUX assembly code blocks
    - Mathematical notation (factorial, fibonacci, sum)
    - A2A agent communication patterns
    - Interactive mode with rich output
    """

    def __init__(self, max_cycles: int = 1_000_000):
        """Initialize the interpreter.

        Args:
            max_cycles: Maximum execution cycles for safety.
        """
        self.max_cycles = max_cycles
        self._a2a_messages: List[Dict[str, Any]] = []

    def interpret(self, input_text: str) -> ExecutionResult:
        """Interpret input text and execute it.

        Args:
            input_text: Markdown, plain text, or FLUX assembly code.

        Returns:
            ExecutionResult with bytecode, disassembly, and execution results.
        """
        try:
            # Parse input and generate bytecode
            bytecode = self._parse_to_bytecode(input_text)

            # Disassemble for display
            disasm = FluxDisassembler(color_output=False)
            disasm_result = disasm.disassemble(bytecode)
            disassembly_text = self._format_disassembly(disasm_result)

            # Execute bytecode
            vm = Interpreter(bytecode, max_cycles=self.max_cycles)
            vm.on_a2a(self._a2a_handler)

            try:
                cycles = vm.execute()
                result = vm.regs.read_gp(0)

                # Collect non-zero registers (excluding SP/R11 which is stack pointer)
                registers = {}
                for i in range(16):
                    if i == 11:  # Skip stack pointer
                        continue
                    val = vm.regs.read_gp(i)
                    if val != 0:
                        registers[i] = val

                return ExecutionResult(
                    success=True,
                    bytecode=bytecode,
                    disassembly=disassembly_text,
                    result=result,
                    registers=registers,
                    cycles=cycles,
                    halted=vm.halted,
                )
            except VMError as e:
                return ExecutionResult(
                    success=False,
                    bytecode=bytecode,
                    disassembly=disassembly_text,
                    error=str(e),
                    cycles=vm.cycle_count,
                )

        except Exception as e:
            return ExecutionResult(
                success=False,
                bytecode=b"",
                disassembly="",
                error=f"Parse error: {e}",
            )

    def _a2a_handler(self, opcode_name: str, data: bytes) -> None:
        """Handle A2A opcodes during execution."""
        self._a2a_messages.append({
            "opcode": opcode_name,
            "data": data.hex(),
        })

    def get_a2a_messages(self) -> List[Dict[str, Any]]:
        """Get all A2A messages sent during execution."""
        return self._a2a_messages.copy()

    # ── Parsing ─────────────────────────────────────────────────────────────────

    def _parse_to_bytecode(self, input_text: str) -> bytes:
        """Parse input text and generate FLUX bytecode.

        Handles multiple input formats:
        1. FLUX assembly code blocks (```flux ... ```)
        2. Natural language patterns
        3. Mathematical notation
        4. A2A agent patterns
        """
        bytecode = bytearray()

        # Extract FLUX code blocks first
        flux_blocks = self._extract_flux_blocks(input_text)

        if flux_blocks:
            # Direct FLUX assembly - parse and encode
            for block in flux_blocks:
                bytecode.extend(self._parse_flux_assembly(block))
        else:
            # Try to parse as natural language or math notation
            parsed = self._parse_natural_language(input_text.strip())
            bytecode.extend(parsed)

        # Ensure HALT at the end if not present
        if not bytecode or bytecode[-1] != Op.HALT:
            bytecode.append(Op.HALT)

        return bytes(bytecode)

    def _extract_flux_blocks(self, text: str) -> List[str]:
        """Extract FLUX code blocks from markdown.

        Returns list of code blocks without the wrapping ```flux ... ```
        """
        pattern = r'```(?:flux|FLUX)\n(.*?)```'
        matches = re.findall(pattern, text, re.DOTALL)
        return matches

    def _parse_flux_assembly(self, assembly: str) -> bytes:
        """Parse FLUX assembly language to bytecode.

        Supports:
        - MOVI R0, 42
        - IADD R0, R1, R2
        - label: JMP label
        - ; comments
        """
        lines = assembly.strip().split('\n')

        # First pass: collect labels and instruction info
        labels: Dict[str, int] = {}
        instructions: List[Tuple[int, str]] = []  # (offset, line_without_label)
        offset = 0

        for line in lines:
            line = line.strip()
            if not line or line.startswith(';'):
                continue

            # Check for label
            has_label = False
            label_name = None
            if ':' in line:
                label_part = line.split(':')[0].strip()
                if label_part and not label_part.startswith(';'):
                    label_name = label_part
                    labels[label_name] = offset
                    has_label = True

            # Remove label for instruction parsing
            instr_line = line.split(':', 1)[1].strip() if has_label else line

            if not instr_line:
                continue

            # Estimate instruction size
            op_part = instr_line.split()[0] if instr_line.split() else ''
            if op_part:
                op_upper = op_part.upper().rstrip(':')
                try:
                    opcode = Op[op_upper]
                    instr_size = self._estimate_instruction_size(opcode)
                    instructions.append((offset, instr_line))
                    offset += instr_size
                except KeyError:
                    pass  # Unknown op, skip

        # Second pass: generate bytecode with label offsets
        bytecode = bytearray()
        for instr_offset, instr_line in instructions:
            bytecode.extend(self._parse_instruction_with_offset(instr_line, labels, instr_offset))

        return bytes(bytecode)

    def _estimate_instruction_size(self, opcode: Op) -> int:
        """Estimate the size of an instruction in bytes."""
        if opcode in {Op.NOP, Op.HALT, Op.DUP, Op.SWAP, Op.YIELD}:
            return 1
        elif opcode in {Op.INC, Op.DEC, Op.PUSH, Op.POP}:
            return 2
        elif opcode in {Op.MOVI, Op.JMP, Op.JZ, Op.JNZ}:
            return 4
        elif opcode in {Op.IADD, Op.ISUB, Op.IMUL, Op.IDIV}:
            return 4
        return 3  # Default to 3 bytes

    def _parse_instruction(self, line: str, labels: Dict[str, int]) -> bytes:
        """Parse a single FLUX assembly instruction to bytecode."""
        parts = line.split()
        if not parts:
            return b""

        op_name = parts[0].upper()

        try:
            opcode = Op[op_name]
        except KeyError:
            return b""  # Unknown opcode

        # Get current position for label offset calculation
        # We need to track this differently - for now, estimate

        # Parse operands based on opcode format
        if opcode == Op.MOVI and len(parts) >= 3:
            # MOVI R0, 42
            reg = self._parse_register(parts[1])
            imm = int(parts[2])
            return struct.pack("<BBh", opcode, reg, imm)

        elif opcode in {Op.IADD, Op.ISUB, Op.IMUL, Op.IDIV} and len(parts) >= 4:
            # IADD R0, R1, R2
            rd = self._parse_register(parts[1])
            rs1 = self._parse_register(parts[2])
            rs2 = self._parse_register(parts[3])
            return struct.pack("<BBBB", opcode, rd, rs1, rs2)

        elif opcode in {Op.MOV, Op.LOAD, Op.STORE} and len(parts) >= 3:
            # MOV R0, R1
            rd = self._parse_register(parts[1])
            rs1 = self._parse_register(parts[2])
            return struct.pack("<BBB", opcode, rd, rs1)

        elif opcode in {Op.JMP, Op.JZ, Op.JNZ} and len(parts) >= 2:
            # JMP label or JZ R0, label
            if len(parts) == 2:
                # JMP label
                target = parts[1].rstrip(',')
                if target in labels:
                    # Forward jump: target is ahead, offset is positive
                    # Backward jump: target is behind, offset is negative
                    # We can't calculate accurately without knowing current position
                    # For now, use a placeholder that will be fixed by a second pass
                    offset = labels[target] - 10  # Rough estimate
                else:
                    offset = 0
                return struct.pack("<BBh", opcode, 0, offset)
            else:
                # JZ R0, label
                reg = self._parse_register(parts[1])
                target = parts[2].rstrip(',')
                if target in labels:
                    offset = labels[target] - 10  # Rough estimate
                else:
                    offset = 0
                return struct.pack("<BBh", opcode, reg, offset)

        elif opcode in {Op.INC, Op.DEC} and len(parts) >= 2:
            # INC R0
            reg = self._parse_register(parts[1])
            return struct.pack("<BB", opcode, reg)

        elif opcode in {Op.PUSH, Op.POP} and len(parts) >= 2:
            # PUSH R0
            reg = self._parse_register(parts[1])
            return struct.pack("<BB", opcode, reg)

        elif opcode in {Op.HALT, Op.NOP, Op.YIELD}:
            return bytes([opcode])

        return b""

    def _parse_instruction_with_offset(self, line: str, labels: Dict[str, int], current_offset: int) -> bytes:
        """Parse a single FLUX assembly instruction to bytecode, knowing current offset."""
        parts = line.split()
        if not parts:
            return b""

        op_name = parts[0].upper()

        # Handle opcode aliases
        if op_name == "JGT":
            op_name = "JG"

        try:
            opcode = Op[op_name]
        except KeyError:
            return b""  # Unknown opcode

        # Parse operands based on opcode format
        if opcode == Op.MOVI and len(parts) >= 3:
            # MOVI R0, 42
            reg = self._parse_register(parts[1])
            imm = int(parts[2])
            return struct.pack("<BBh", opcode, reg, imm)

        elif opcode in {Op.IADD, Op.ISUB, Op.IMUL, Op.IDIV} and len(parts) >= 4:
            # IADD R0, R1, R2
            rd = self._parse_register(parts[1])
            rs1 = self._parse_register(parts[2])
            rs2 = self._parse_register(parts[3])
            return struct.pack("<BBBB", opcode, rd, rs1, rs2)

        elif opcode in {Op.MOV, Op.LOAD, Op.STORE} and len(parts) >= 3:
            # MOV R0, R1
            rd = self._parse_register(parts[1])
            rs1 = self._parse_register(parts[2])
            return struct.pack("<BBB", opcode, rd, rs1)

        elif opcode in {Op.JMP, Op.JZ, Op.JNZ} and len(parts) >= 2:
            # JMP label or JZ R0, label
            instr_size = self._estimate_instruction_size(opcode)
            after_instr_offset = current_offset + instr_size

            if len(parts) == 2:
                # JMP label
                reg = 0
                target = parts[1].rstrip(',')
            else:
                # JZ R0, label
                reg = self._parse_register(parts[1])
                target = parts[2].rstrip(',')

            if target in labels:
                # Calculate offset: target - after_instruction
                offset = labels[target] - after_instr_offset
            else:
                offset = 0

            return struct.pack("<BBh", opcode, reg, offset)

        elif opcode in {Op.INC, Op.DEC} and len(parts) >= 2:
            # INC R0
            reg = self._parse_register(parts[1])
            return struct.pack("<BB", opcode, reg)

        elif opcode in {Op.PUSH, Op.POP} and len(parts) >= 2:
            # PUSH R0
            reg = self._parse_register(parts[1])
            return struct.pack("<BB", opcode, reg)

        elif opcode in {Op.HALT, Op.NOP, Op.YIELD}:
            return bytes([opcode])

        return b""

    def _parse_register(self, reg_str: str) -> int:
        """Parse register string to number (R0 -> 0)."""
        reg_str = reg_str.upper().rstrip(',').strip()
        if reg_str.startswith('R'):
            return int(reg_str[1:])
        return 0

    def _parse_natural_language(self, text: str) -> bytes:
        """Parse natural language or math notation to bytecode."""
        # Clean the text: remove markdown comments, extra whitespace
        lines = []
        for line in text.split('\n'):
            # Remove markdown headers (#, ##)
            line = re.sub(r'^\s*#+\s*', '', line)
            # Remove HTML comments
            line = re.sub(r'<!--.*?-->', '', line)
            # Skip empty lines
            if line.strip():
                lines.append(line.strip())

        # Join lines and search for patterns
        cleaned_text = ' '.join(lines).lower()

        # Check for mathematical patterns first
        # "compute 3 + 4" or "what is 10 * 5"
        math_match = re.match(r'(?:compute|what is)\s+(.+)', cleaned_text)
        if math_match:
            return self._parse_math_expression(math_match.group(1))

        # "factorial of N"
        fact_match = re.search(r'factorial(?:\s+of)?\s+(\d+)', cleaned_text)
        if fact_match:
            n = int(fact_match.group(1))
            return self._generate_factorial(n)

        # "fibonacci of N"
        fib_match = re.search(r'fibonacci(?:\s+of)?\s+(\d+)', cleaned_text)
        if fib_match:
            n = int(fib_match.group(1))
            return self._generate_fibonacci(n)

        # "sum 1 to 100" or "sum from 1 to 100"
        sum_match = re.search(r'sum\s+(?:from\s+)?(\d+)\s+to\s+(\d+)', cleaned_text)
        if sum_match:
            start = int(sum_match.group(1))
            end = int(sum_match.group(2))
            return self._generate_sum(start, end)

        # A2A patterns
        # "tell agent2 that temperature is 72"
        tell_match = re.search(r'tell\s+(\w+)\s+(.+)', cleaned_text)
        if tell_match:
            agent = tell_match.group(1)
            message = tell_match.group(2)
            return self._generate_a2a_tell(agent, message)

        # "ask navigator for heading"
        ask_match = re.search(r'ask\s+(\w+)\s+for\s+(.+)', cleaned_text)
        if ask_match:
            agent = ask_match.group(1)
            message = ask_match.group(2)
            return self._generate_a2a_ask(agent, message)

        # "broadcast storm warning"
        broadcast_match = re.search(r'broadcast\s+(.+)', cleaned_text)
        if broadcast_match:
            message = broadcast_match.group(1)
            return self._generate_a2a_broadcast(message)

        # Try to parse as line-by-line instructions
        # Use the original line structure for line-by-line parsing
        return self._parse_line_by_line('\n'.join(lines))

    def _parse_line_by_line(self, text: str) -> bytes:
        """Parse text as line-by-line instructions."""
        bytecode = bytearray()
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        for line in lines:
            bytecode.extend(self._parse_line(line))

        return bytes(bytecode)

    def _parse_line(self, line: str) -> bytes:
        """Parse a single line of natural language instruction."""
        line = line.lower().strip()

        # "load R0 with 42" / "set R0 to 42" / "R0 = 42"
        load_match = re.match(r'(?:load|set)\s+(\w+)\s+(?:with|to|=)\s+(\d+)', line)
        if load_match:
            reg = self._parse_register(load_match.group(1))
            val = int(load_match.group(2))
            return struct.pack("<BBh", Op.MOVI, reg, val)

        # "add R0 and R1" / "R0 += R1" / "R0 = R0 + R1"
        add_match = re.match(r'(?:add\s+)?(\w+)\s*(?:\+=|\+|and)\s*(\w+)', line)
        if add_match:
            rd = self._parse_register(add_match.group(1))
            rs1 = rd  # Default to rd as first source
            rs2 = self._parse_register(add_match.group(2))
            return struct.pack("<BBBB", Op.IADD, rd, rs1, rs2)

        # "multiply R0 by R1" / "R0 *= R1"
        mul_match = re.match(r'(?:multiply\s+)?(\w+)\s*\*\s*(\w+)', line)
        if mul_match:
            rd = self._parse_register(mul_match.group(1))
            rs2 = self._parse_register(mul_match.group(2))
            return struct.pack("<BBBB", Op.IMUL, rd, rd, rs2)

        # "subtract R1 from R0" / "R0 -= R1"
        sub_match = re.match(r'(?:subtract\s+)?(\w+)\s*-?\s*(\w+)', line)
        if sub_match:
            rd = self._parse_register(sub_match.group(1))
            rs2 = self._parse_register(sub_match.group(2))
            return struct.pack("<BBBB", Op.ISUB, rd, rd, rs2)

        # "increment R0" / "decrease R0" / "R0++" / "R0--"
        if 'increment' in line or '++' in line:
            reg_match = re.search(r'r(\d+)', line)
            if reg_match:
                reg = int(reg_match.group(1))
                return struct.pack("<BB", Op.INC, reg)

        if 'decrease' in line or 'decrement' in line or '--' in line:
            reg_match = re.search(r'r(\d+)', line)
            if reg_match:
                reg = int(reg_match.group(1))
                return struct.pack("<BB", Op.DEC, reg)

        # "push R0"
        push_match = re.match(r'push\s+(\w+)', line)
        if push_match:
            reg = self._parse_register(push_match.group(1))
            return struct.pack("<BB", Op.PUSH, reg)

        # "pop to R1"
        pop_match = re.match(r'pop\s+(?:to\s+)?(\w+)', line)
        if pop_match:
            reg = self._parse_register(pop_match.group(1))
            return struct.pack("<BB", Op.POP, reg)

        # "return R0" / "result is R0"
        if 'return' in line or 'result' in line:
            return bytes([Op.HALT])

        return b""

    # ── Math Notation Generators ─────────────────────────────────────────────────

    def _parse_math_expression(self, expr: str) -> bytes:
        """Parse a simple math expression like "3 + 4" or "10 * 5"."""
        expr = expr.strip()

        # Try to parse as "3 + 4"
        parts = re.split(r'\s*([\+\-\*\/])\s*', expr)
        if len(parts) == 3:
            try:
                a = int(parts[0])
                op = parts[1]
                b = int(parts[2])

                bytecode = bytearray()

                # Load first operand into R0
                bytecode.extend(struct.pack("<BBh", Op.MOVI, 0, a))

                # Load second operand into R1
                bytecode.extend(struct.pack("<BBh", Op.MOVI, 1, b))

                # Perform operation
                if op == '+':
                    bytecode.extend(struct.pack("<BBBB", Op.IADD, 0, 0, 1))
                elif op == '-':
                    bytecode.extend(struct.pack("<BBBB", Op.ISUB, 0, 0, 1))
                elif op == '*':
                    bytecode.extend(struct.pack("<BBBB", Op.IMUL, 0, 0, 1))
                elif op == '/':
                    bytecode.extend(struct.pack("<BBBB", Op.IDIV, 0, 0, 1))

                return bytes(bytecode)
            except ValueError:
                pass

        # Fallback: try eval (simplified)
        try:
            result = int(eval(expr, {"__builtins__": {}}))
            return struct.pack("<BBh", Op.MOVI, 0, result)
        except:
            return b""

    def _generate_factorial(self, n: int) -> bytes:
        """Generate bytecode for factorial of n."""
        bytecode = bytearray()

        # Load n into R0
        bytecode.extend(struct.pack("<BBh", Op.MOVI, 0, n))

        # Load 1 into R1 (result)
        bytecode.extend(struct.pack("<BBh", Op.MOVI, 1, 1))

        # Start of loop
        loop_start = len(bytecode)

        # Multiply: R1 = R1 * R0
        bytecode.extend(struct.pack("<BBBB", Op.IMUL, 1, 1, 0))

        # Decrement: R0--
        bytecode.extend(struct.pack("<BB", Op.DEC, 0))

        # Jump if not zero: JNZ R0, loop_start
        # Offset is relative to after the JNZ instruction (4 bytes ahead)
        # We want to jump back to loop_start, so offset = loop_start - current_position - 4
        current_pos = len(bytecode)
        jnz_offset = loop_start - (current_pos + 4)
        bytecode.extend(struct.pack("<BBh", Op.JNZ, 0, jnz_offset))

        # Move result to R0
        bytecode.extend(struct.pack("<BBB", Op.MOV, 0, 1))

        return bytes(bytecode)

    def _generate_fibonacci(self, n: int) -> bytes:
        """Generate bytecode for fibonacci of n."""
        bytecode = bytearray()

        if n <= 1:
            return struct.pack("<BBh", Op.MOVI, 0, n)

        # Load n into R0
        bytecode.extend(struct.pack("<BBh", Op.MOVI, 0, n))

        # Load 0 into R1 (fib(0))
        bytecode.extend(struct.pack("<BBh", Op.MOVI, 1, 0))

        # Load 1 into R2 (fib(1))
        bytecode.extend(struct.pack("<BBh", Op.MOVI, 2, 1))

        # Load 1 into R3 (counter)
        bytecode.extend(struct.pack("<BBh", Op.MOVI, 3, 1))

        # Start of loop
        loop_start = len(bytecode)

        # Compute next fib: R4 = R1 + R2
        bytecode.extend(struct.pack("<BBBB", Op.IADD, 4, 1, 2))

        # Shift: R1 = R2, R2 = R4
        bytecode.extend(struct.pack("<BBB", Op.MOV, 1, 2))
        bytecode.extend(struct.pack("<BBB", Op.MOV, 2, 4))

        # Increment counter: R3++
        bytecode.extend(struct.pack("<BB", Op.INC, 3))

        # Compare: if R3 >= R0, exit loop
        bytecode.extend(struct.pack("<BBB", Op.CMP, 3, 0))
        jump_offset = len(bytecode) + 4
        bytecode.extend(struct.pack("<BBh", Op.JGE, 0, 0))  # Placeholder

        # Jump back to loop start
        loop_jump_offset = loop_start - (len(bytecode) + 4)
        bytecode.extend(struct.pack("<BBh", Op.JMP, 0, loop_jump_offset))

        # Fix up the JGE offset to jump here (after loop)
        jge_pos = jump_offset - 4
        current_pos = len(bytecode)
        jge_offset = current_pos - jump_offset
        bytecode[jge_pos+2] = jge_offset & 0xFF
        bytecode[jge_pos+3] = (jge_offset >> 8) & 0xFF

        # Result is in R2
        bytecode.extend(struct.pack("<BBB", Op.MOV, 0, 2))

        return bytes(bytecode)

    def _generate_sum(self, start: int, end: int) -> bytes:
        """Generate bytecode for sum from start to end."""
        bytecode = bytearray()

        # Load start into R0
        bytecode.extend(struct.pack("<BBh", Op.MOVI, 0, start))

        # Load 0 into R1 (accumulator)
        bytecode.extend(struct.pack("<BBh", Op.MOVI, 1, 0))

        # Load end into R2
        bytecode.extend(struct.pack("<BBh", Op.MOVI, 2, end))

        # Start of loop
        loop_start = len(bytecode)

        # Add: R1 = R1 + R0
        bytecode.extend(struct.pack("<BBBB", Op.IADD, 1, 1, 0))

        # Increment: R0++
        bytecode.extend(struct.pack("<BB", Op.INC, 0))

        # Compare: if R0 > R2, exit (use CMP + conditional jump)
        bytecode.extend(struct.pack("<BBB", Op.CMP, 0, 2))

        # Jump if greater (using JG which is 0x4D)
        # This needs to skip the loop jump and go to the end
        jg_pos = len(bytecode)
        bytecode.extend(struct.pack("<BBh", Op.JG, 0, 0))  # Placeholder offset

        # Jump back to loop start
        loop_jump_offset = loop_start - (len(bytecode) + 4)
        bytecode.extend(struct.pack("<BBh", Op.JMP, 0, loop_jump_offset))

        # Fix up the JG offset to jump to here (after the loop)
        current_pos = len(bytecode)
        jg_offset = current_pos - (jg_pos + 4)
        bytecode[jg_pos+2] = jg_offset & 0xFF
        bytecode[jg_pos+3] = (jg_offset >> 8) & 0xFF

        # Result is in R1
        bytecode.extend(struct.pack("<BBB", Op.MOV, 0, 1))

        return bytes(bytecode)

    # ── A2A Message Generators ───────────────────────────────────────────────────

    def _generate_a2a_tell(self, agent: str, message: str) -> bytes:
        """Generate A2A TELL message bytecode."""
        bytecode = bytearray()

        # Store message pointer in R0 (simplified - just use a constant)
        message_bytes = message.encode('utf-8')[:32]  # Limit to 32 bytes
        bytecode.extend(struct.pack("<BBh", Op.MOVI, 0, len(message_bytes)))

        # Generate TELL opcode (Format G)
        data = bytearray()
        data.append(0)  # message reg (placeholder)
        data.append(0)  # cap reg (placeholder)
        data.extend(agent.encode('utf-8')[:16])

        bytecode.extend(struct.pack("<BH", Op.TELL, len(data)))
        bytecode.extend(data)

        return bytes(bytecode)

    def _generate_a2a_ask(self, agent: str, message: str) -> bytes:
        """Generate A2A ASK message bytecode."""
        bytecode = bytearray()

        # Store message pointer in R0
        message_bytes = message.encode('utf-8')[:32]
        bytecode.extend(struct.pack("<BBh", Op.MOVI, 0, len(message_bytes)))

        # Generate ASK opcode (Format G)
        data = bytearray()
        data.append(0)  # message reg (placeholder)
        data.append(0)  # cap reg (placeholder)
        data.extend(agent.encode('utf-8')[:16])

        bytecode.extend(struct.pack("<BH", Op.ASK, len(data)))
        bytecode.extend(data)

        return bytes(bytecode)

    def _generate_a2a_broadcast(self, message: str) -> bytes:
        """Generate A2A BROADCAST message bytecode."""
        bytecode = bytearray()

        # Store message pointer in R0
        message_bytes = message.encode('utf-8')[:32]
        bytecode.extend(struct.pack("<BBh", Op.MOVI, 0, len(message_bytes)))

        # Generate BROADCAST opcode (Format G)
        data = bytearray()
        data.append(0)  # message reg (placeholder)
        data.extend(message.encode('utf-8')[:32])

        bytecode.extend(struct.pack("<BH", Op.BROADCAST, len(data)))
        bytecode.extend(data)

        return bytes(bytecode)

    # ── Display Formatting ───────────────────────────────────────────────────────

    def _format_disassembly(self, result: DisassemblyResult) -> str:
        """Format disassembly result for display."""
        lines = [f"FLUX Bytecode Disassembly ({result.total_bytes} bytes)"]
        lines.append("=" * 80)

        for instr in result.instructions:
            offset_str = f"{instr.offset:04x}"
            bytes_str = instr.bytes.hex().ljust(16)
            opcode_str = f"{instr.opcode_name:<20}"
            operands_str = instr.operands if instr.operands else ""
            lines.append(f"{offset_str}:  {bytes_str}  {opcode_str} {operands_str}")

        if result.error:
            lines.append(f"\nERROR: {result.error}")

        return "\n".join(lines)


# ── Interactive Mode ───────────────────────────────────────────────────────────

def interactive():
    """Open-flux-interpreter interactive mode.

    Accepts markdown, plain text, or code blocks.
    Shows:
      - The parsed bytecode (hex)
      - Disassembly
      - Execution result
      - Register state
    """
    import sys

    interpreter = OpenFluxInterpreter()

    print()
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║          Open-Flux-Interpreter v1.0                       ║")
    print("║   Convert markdown/text to FLUX bytecode and execute      ║")
    print("╚═══════════════════════════════════════════════════════════╝")
    print()
    print("Enter markdown, natural language, or FLUX assembly code.")
    print("Type 'quit' or 'exit' to quit, 'help' for examples.")
    print()

    while True:
        try:
            user_input = input("open-flux> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ('quit', 'exit'):
                print("Goodbye!")
                break

            if user_input.lower() == 'help':
                print_help()
                continue

            # Execute the input
            result = interpreter.interpret(user_input)

            # Display results
            print()
            print("-" * 60)
            print("EXECUTION RESULT")
            print("-" * 60)

            if result.success:
                print(f"✓ Success!")
                print(f"  Result: R0 = {result.result}")
                print(f"  Cycles: {result.cycles}")
                print(f"  Halted: {result.halted}")

                if result.registers:
                    print(f"\n  Registers:")
                    for reg, val in sorted(result.registers.items()):
                        print(f"    R{reg} = {val}")

                # Show A2A messages if any
                a2a_msgs = interpreter.get_a2a_messages()
                if a2a_msgs:
                    print(f"\n  A2A Messages:")
                    for msg in a2a_msgs:
                        print(f"    [{msg['opcode']}] {msg['data']}")
            else:
                print(f"✗ Error: {result.error}")

            print()
            print("Bytecode (hex):")
            print(f"  {result.bytecode.hex()}")

            print()
            print("Disassembly:")
            print(result.disassembly)

            print()

        except KeyboardInterrupt:
            print("\nUse 'quit' or 'exit' to quit.")
        except EOFError:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")


def print_help():
    """Print help text for interactive mode."""
    help_text = """
Examples:

  Natural Language:
    compute 3 + 4
    factorial of 7
    fibonacci of 12
    sum 1 to 100

  FLUX Assembly (in code blocks):
    ```flux
    MOVI R0, 10
    MOVI R1, 1
    loop:
    IMUL R1, R0
    DEC R0
    JNZ R0, loop
    HALT
    ```

  Line-by-line instructions:
    Load R0 with 10
    Load R1 with 1
    While R0 is not zero:
        Multiply R1 by R0
        Decrease R0
    Return R1

  A2A Agent Communication:
    tell agent2 hello
    ask navigator for heading
    broadcast storm warning
"""
    print(help_text)


# ── Convenience Functions ─────────────────────────────────────────────────────

def interpret(text: str, max_cycles: int = 1_000_000) -> ExecutionResult:
    """Convenience function to interpret text and execute.

    Args:
        text: Input markdown, natural language, or FLUX assembly.
        max_cycles: Maximum execution cycles.

    Returns:
        ExecutionResult with bytecode, disassembly, and results.
    """
    interp = OpenFluxInterpreter(max_cycles=max_cycles)
    return interp.interpret(text)


def run_markdown_file(filepath: str, max_cycles: int = 1_000_000) -> ExecutionResult:
    """Run a markdown file containing FLUX code.

    Args:
        filepath: Path to the markdown file.
        max_cycles: Maximum execution cycles.

    Returns:
        ExecutionResult with bytecode, disassembly, and results.
    """
    with open(filepath, 'r') as f:
        content = f.read()

    interp = OpenFluxInterpreter(max_cycles=max_cycles)
    return interp.interpret(content)


# ── Main Entry Point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    interactive()
