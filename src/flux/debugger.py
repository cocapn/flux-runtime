"""FLUX Bytecode Debugger — Interactive step debugger for FLUX bytecode.

Extends the Interpreter with debugging capabilities:
    - Single-step execution
    - Breakpoints
    - Register/memory inspection
    - Watch expressions
    - Backtrace/call stack
    - Continue until breakpoint

Example usage:
    debugger = FluxDebugger(bytecode)
    debugger.add_breakpoint(0x10)  # Set breakpoint at offset 0x10
    debugger.step()                # Execute one instruction
    debugger.continue_exec()       # Run until breakpoint
    print(debugger.inspect_reg(0)) # Check R0
"""

from __future__ import annotations

import struct
import sys
from typing import Optional, List, Dict, Any, Set, Callable
from dataclasses import dataclass, field

from flux.vm.interpreter import (
    Interpreter,
    VMError,
    VMHaltError,
)
from flux.bytecode.opcodes import Op, get_format
from flux.disasm import (
    FluxDisassembler,
    DisassembledInstruction,
    get_instruction_color,
    Colors,
)


# ── Debugger data structures ────────────────────────────────────────────────────

@dataclass
class StepResult:
    """Result of a single step operation."""
    success: bool
    instruction: Optional[DisassembledInstruction] = None
    pc_before: int = 0
    pc_after: int = 0
    cycles: int = 0
    halted: bool = False
    error: Optional[str] = None
    breakpoint_hit: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            "success": self.success,
            "pc_before": self.pc_before,
            "pc_after": self.pc_after,
            "cycles": self.cycles,
            "halted": self.halted,
            "breakpoint_hit": self.breakpoint_hit,
        }
        if self.instruction:
            result["instruction"] = self.instruction.to_dict()
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class Breakpoint:
    """A breakpoint at a specific byte offset."""
    offset: int
    enabled: bool = True
    hit_count: int = 0
    condition: Optional[str] = None  # Future: conditional breakpoints


@dataclass
class Watchpoint:
    """A watchpoint for a register (auto-display after each step)."""
    reg_num: int
    name: str = ""  # Optional custom name


# ── Main Debugger Class ────────────────────────────────────────────────────────

class FluxDebugger(Interpreter):
    """FLUX bytecode debugger with step, breakpoint, and inspection capabilities.

    Extends the Interpreter class with debugging features while maintaining
    full compatibility with the existing VM execution model.

    Example:
        debugger = FluxDebugger(bytecode)
        debugger.add_breakpoint(0x20)

        while not debugger.halted:
            result = debugger.step()
            print(result)

            # Check if breakpoint was hit
            if result.breakpoint_hit:
                # Inspect state
                print(f"R0 = {debugger.inspect_reg(0)}")
    """

    def __init__(self, bytecode: bytes, memory_size: int = 65536, max_cycles: int = 100_000):
        """Initialize the debugger.

        Args:
            bytecode: Raw bytecode to debug.
            memory_size: Memory region size in bytes.
            max_cycles: Maximum execution cycles (default higher for debugging).
        """
        # Initialize parent Interpreter class
        code = self._extract_code(bytecode)
        super().__init__(code, memory_size=memory_size, max_cycles=max_cycles)

        # Debugger state
        self._breakpoints: Dict[int, Breakpoint] = {}
        self._watchpoints: List[Watchpoint] = []
        self._disassembler = FluxDisassembler(color_output=False)
        self._original_bytecode = code
        self._call_stack: List[int] = []  # Track return addresses
        self._step_callback: Optional[Callable[[StepResult], None]] = None

    # ── Execution control ───────────────────────────────────────────────────────

    def step(self) -> StepResult:
        """Execute a single instruction and return detailed step info.

        Returns:
            StepResult with instruction info, state changes, and any errors.
        """
        if self.halted:
            return StepResult(
                success=True,
                halted=True,
                pc_before=self.pc,
                pc_after=self.pc,
                cycles=0,
            )

        pc_before = self.pc
        cycles_before = self.cycle_count

        # Disassemble the current instruction before executing
        instr = None
        try:
            instr = self._disassembler._disassemble_one(self._original_bytecode, pc_before)
        except Exception as e:
            return StepResult(
                success=False,
                pc_before=pc_before,
                pc_after=pc_before,
                cycles=0,
                error=f"Disassembly error: {e}",
            )

        # Check for breakpoint at this location
        breakpoint_hit = False
        if pc_before in self._breakpoints:
            bp = self._breakpoints[pc_before]
            if bp.enabled:
                bp.hit_count += 1
                breakpoint_hit = True

        # Execute one instruction using parent's _step method
        try:
            self._step()
            self.cycle_count += 1
        except VMHaltError:
            # Normal halt - not an error
            self.halted = True
        except VMError as e:
            return StepResult(
                success=False,
                instruction=instr,
                pc_before=pc_before,
                pc_after=self.pc,
                cycles=self.cycle_count - cycles_before,
                halted=self.halted,
                error=str(e),
            )
        except Exception as e:
            return StepResult(
                success=False,
                instruction=instr,
                pc_before=pc_before,
                pc_after=self.pc,
                cycles=self.cycle_count - cycles_before,
                halted=self.halted,
                error=f"Unexpected error: {e}",
            )

        result = StepResult(
            success=True,
            instruction=instr,
            pc_before=pc_before,
            pc_after=self.pc,
            cycles=self.cycle_count - cycles_before,
            halted=self.halted,
            breakpoint_hit=breakpoint_hit,
        )

        # Track call stack for RET instructions
        if instr and instr.opcode == Op.CALL:
            self._call_stack.append(self.pc)
        elif instr and instr.opcode == Op.RET and self._call_stack:
            self._call_stack.pop()

        # Call step callback if registered
        if self._step_callback:
            self._step_callback(result)

        return result

    def continue_exec(self) -> StepResult:
        """Continue execution until breakpoint, halt, or error.

        Returns:
            Final StepResult when execution stops.
        """
        while not self.halted:
            result = self.step()

            # Stop on breakpoint
            if result.breakpoint_hit:
                return result

            # Stop on error
            if not result.success:
                return result

            # Stop on halt
            if result.halted:
                return result

        # Already halted
        return StepResult(
            success=True,
            halted=True,
            pc_before=self.pc,
            pc_after=self.pc,
            cycles=0,
        )

    def run_to_offset(self, target_offset: int) -> StepResult:
        """Execute until reaching a specific offset or halt.

        Args:
            target_offset: Byte offset to stop at.

        Returns:
            StepResult when execution stops.
        """
        while not self.halted and self.pc != target_offset:
            result = self.step()

            if not result.success or result.halted:
                return result

        # Reached target
        return StepResult(
            success=True,
            halted=self.halted,
            pc_before=self.pc,
            pc_after=self.pc,
            cycles=0,
        )

    # ── Breakpoint management ───────────────────────────────────────────────────

    def add_breakpoint(self, offset: int, condition: Optional[str] = None) -> bool:
        """Add a breakpoint at the given byte offset.

        Args:
            offset: Byte offset in the bytecode.
            condition: Optional condition string (future support).

        Returns:
            True if breakpoint was added, False if already exists.
        """
        if offset not in self._breakpoints:
            self._breakpoints[offset] = Breakpoint(offset=offset, condition=condition)
            return True
        return False

    def remove_breakpoint(self, offset: int) -> bool:
        """Remove a breakpoint.

        Args:
            offset: Byte offset of the breakpoint.

        Returns:
            True if breakpoint was removed, False if not found.
        """
        if offset in self._breakpoints:
            del self._breakpoints[offset]
            return True
        return False

    def enable_breakpoint(self, offset: int) -> bool:
        """Enable a breakpoint.

        Returns:
            True if breakpoint was enabled, False if not found.
        """
        if offset in self._breakpoints:
            self._breakpoints[offset].enabled = True
            return True
        return False

    def disable_breakpoint(self, offset: int) -> bool:
        """Disable a breakpoint (without removing it).

        Returns:
            True if breakpoint was disabled, False if not found.
        """
        if offset in self._breakpoints:
            self._breakpoints[offset].enabled = False
            return True
        return False

    def list_breakpoints(self) -> List[Dict[str, Any]]:
        """List all breakpoints with their status.

        Returns:
            List of breakpoint info dictionaries.
        """
        return [
            {
                "offset": bp.offset,
                "enabled": bp.enabled,
                "hit_count": bp.hit_count,
                "condition": bp.condition,
            }
            for bp in sorted(self._breakpoints.values(), key=lambda x: x.offset)
        ]

    def clear_breakpoints(self) -> None:
        """Remove all breakpoints."""
        self._breakpoints.clear()

    # ── Watchpoint management ───────────────────────────────────────────────────

    def watch_reg(self, reg_num: int, name: str = "") -> None:
        """Add a watchpoint for a register (auto-display after each step).

        Args:
            reg_num: Register number (0-15 for GP registers).
            name: Optional custom name for the watchpoint.
        """
        self._watchpoints.append(Watchpoint(reg_num=reg_num, name=name or f"R{reg_num}"))

    def unwatch_reg(self, reg_num: int) -> bool:
        """Remove a watchpoint.

        Returns:
            True if watchpoint was removed, False if not found.
        """
        for i, wp in enumerate(self._watchpoints):
            if wp.reg_num == reg_num:
                self._watchpoints.pop(i)
                return True
        return False

    def list_watchpoints(self) -> List[str]:
        """List all active watchpoints.

        Returns:
            List of watchpoint names.
        """
        return [wp.name for wp in self._watchpoints]

    def clear_watchpoints(self) -> None:
        """Remove all watchpoints."""
        self._watchpoints.clear()

    # ── State inspection ────────────────────────────────────────────────────────

    def inspect_reg(self, reg_num: int) -> int:
        """Get the value of a general-purpose register.

        Args:
            reg_num: Register number (0-15).

        Returns:
            Register value.
        """
        return self.regs.read_gp(reg_num)

    def inspect_fp_reg(self, reg_num: int) -> float:
        """Get the value of a floating-point register.

        Args:
            reg_num: Register number (0-15).

        Returns:
            Float register value.
        """
        return self.regs.read_fp(reg_num)

    def set_reg(self, reg_num: int, value: int) -> None:
        """Set the value of a general-purpose register.

        Args:
            reg_num: Register number (0-15).
            value: Value to set.
        """
        self.regs.write_gp(reg_num, value)

    def inspect_mem(self, addr: int, length: int = 1) -> bytes:
        """Read bytes from the stack memory region.

        Args:
            addr: Memory address.
            length: Number of bytes to read.

        Returns:
            Bytes read from memory.
        """
        stack = self.memory.get_region("stack")
        return stack.read(addr, length)

    def write_mem(self, addr: int, data: bytes) -> None:
        """Write bytes to the stack memory region.

        Args:
            addr: Memory address.
            data: Bytes to write.
        """
        stack = self.memory.get_region("stack")
        stack.write(addr, data)

    def backtrace(self) -> List[Dict[str, Any]]:
        """Get the current call stack (backtrace).

        Returns:
            List of stack frame information.
        """
        frames = []
        # Add current frame
        frames.append({
            "pc": self.pc,
            "type": "current",
        })
        # Add return addresses from call stack
        for i, ret_addr in enumerate(reversed(self._call_stack)):
            frames.append({
                "pc": ret_addr,
                "type": "return",
                "depth": i + 1,
            })
        return frames

    def get_flags(self) -> Dict[str, bool]:
        """Get the current condition flag states.

        Returns:
            Dictionary of flag states.
        """
        return {
            "zero": self._flag_zero,
            "sign": self._flag_sign,
            "carry": self._flag_carry,
            "overflow": self._flag_overflow,
        }

    def get_register_dump(self) -> Dict[str, int]:
        """Get all general-purpose register values.

        Returns:
            Dictionary mapping register names to values.
        """
        return {f"R{i}": self.regs.read_gp(i) for i in range(16)}

    def get_stack_snapshot(self, num_words: int = 16) -> List[int]:
        """Get a snapshot of the stack (top N words).

        Args:
            num_words: Number of 32-bit words to read from SP.

        Returns:
            List of stack values (from SP upward).
        """
        values = []
        stack_region = self.memory.get_region("stack")
        stack_size = stack_region.size

        for i in range(num_words):
            addr = self.regs.sp + i * 4
            if addr < 0 or addr + 4 > stack_size:
                break
            try:
                val = struct.unpack_from("<i", stack_region.data, addr)[0]
                values.append(val)
            except (struct.error, IndexError, OSError):
                break
        return values

    # ── Disassembly integration ─────────────────────────────────────────────────

    def disassemble_at(self, offset: int, count: int = 5) -> List[DisassembledInstruction]:
        """Disassemble instructions starting at a given offset.

        Args:
            offset: Starting byte offset.
            count: Number of instructions to disassemble.

        Returns:
            List of disassembled instructions.
        """
        instructions = []
        current_offset = offset

        for _ in range(count):
            if current_offset >= len(self._original_bytecode):
                break
            try:
                instr = self._disassembler._disassemble_one(
                    self._original_bytecode, current_offset
                )
                instructions.append(instr)
                current_offset += instr.size
            except Exception:
                break

        return instructions

    def disassemble_current(self, count: int = 5) -> List[DisassembledInstruction]:
        """Disassemble instructions starting at the current PC.

        Args:
            count: Number of instructions to disassemble.

        Returns:
            List of disassembled instructions.
        """
        return self.disassemble_at(self.pc, count)

    # ── Callbacks ───────────────────────────────────────────────────────────────

    def on_step(self, callback: Callable[[StepResult], None]) -> None:
        """Register a callback to be called after each step.

        Args:
            callback: Function taking a StepResult argument.
        """
        self._step_callback = callback

    # ── Utility methods ─────────────────────────────────────────────────────────

    def _extract_code(self, bytecode: bytes) -> bytes:
        """Extract the code section from a FLUX binary file."""
        if len(bytecode) >= 18 and bytecode[:4] == b"FLUX":
            code_off = struct.unpack_from("<I", bytecode, 14)[0]
            if 18 <= code_off <= len(bytecode):
                return bytecode[code_off:]
        return bytecode

    def format_state(self) -> str:
        """Format the current VM state for display.

        Returns:
            Multi-line string with register, flag, and stack info.
        """
        lines = []

        # Header
        lines.append(f"PC=0x{self.pc:04x} | Cycles={self.cycle_count} | "
                    f"Halted={self.halted} | Running={self.running}")

        # Registers
        lines.append("\nRegisters:")
        for i in range(0, 16, 4):
            row = []
            for j in range(4):
                reg_num = i + j
                val = self.regs.read_gp(reg_num)
                # Mark special registers
                suffix = ""
                if reg_num == 11:
                    suffix = " (SP)"
                elif reg_num == 14:
                    suffix = " (FP)"
                elif reg_num == 15:
                    suffix = " (LR)"
                row.append(f"R{reg_num:d}={val:>12,}{suffix}")
            lines.append("  " + "  ".join(row))

        # Flags
        flags = self.get_flags()
        flag_str = " ".join(
            name.upper() for name, val in flags.items() if val
        )
        lines.append(f"\nFlags: {flag_str if flag_str else '(none)'}")

        # Stack
        lines.append("\nStack (top 8 words):")
        stack_vals = self.get_stack_snapshot(8)
        for i, val in enumerate(stack_vals):
            addr = self.regs.sp + i * 4
            lines.append(f"  0x{addr:04x}: {val}")

        # Current instruction
        lines.append("\nCurrent instruction:")
        current_instrs = self.disassemble_current(1)
        if current_instrs:
            instr = current_instrs[0]
            color = get_instruction_color(instr.opcode)
            lines.append(f"  {instr.offset:04x}: {instr.opcode_name} {instr.operands}")

        # Breakpoints
        if self._breakpoints:
            lines.append("\nBreakpoints:")
            for bp in sorted(self._breakpoints.values(), key=lambda x: x.offset):
                status = "+" if bp.enabled else "-"
                lines.append(f"  {status} 0x{bp.offset:04x} (hit {bp.hit_count} times)")

        # Watchpoints
        if self._watchpoints:
            lines.append("\nWatchpoints:")
            for wp in self._watchpoints:
                val = self.inspect_reg(wp.reg_num)
                lines.append(f"  {wp.name} = {val}")

        return "\n".join(lines)


# ── Convenience functions ───────────────────────────────────────────────────────

def create_debugger(bytecode: bytes) -> FluxDebugger:
    """Create a FluxDebugger instance from bytecode.

    Args:
        bytecode: Raw bytecode bytes.

    Returns:
        Configured FluxDebugger instance.
    """
    return FluxDebugger(bytecode)
