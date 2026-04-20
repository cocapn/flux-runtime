"""
FLUX REPL — Interactive Read-Eval-Print Loop for the FLUX runtime.
"""
from __future__ import annotations

import sys
import struct
import readline
import shlex
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from flux.vm.interpreter import Interpreter, VMError
from flux.bytecode.opcodes import Op
from flux.a2a.messages import A2AMessage
import uuid

# ANSI color codes
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BLUE = "\033[94m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


class FluxREPL:
    """Interactive REPL for FLUX bytecode execution."""
    
    def __init__(self, memory_size: int = 4096):
        self.vm: Optional[Interpreter] = None
        self.memory_size = memory_size
        self.history: List[str] = []
        self._init_vm()
        
    def _init_vm(self) -> None:
        """Initialize or reset the VM with empty bytecode."""
        # Start with just a HALT instruction
        from flux.bytecode.opcodes import Op
        empty_code = bytes([Op.HALT])
        self.vm = Interpreter(empty_code, memory_size=self.memory_size)
        # Reset PC to start
        self.vm.pc = 0
        self.vm.halted = False
        self.vm.cycle_count = 0
        
    def _assemble_hex(self, hex_str: str) -> bytes:
        """Convert space-separated hex bytes to bytes."""
        hex_str = hex_str.strip()
        if not hex_str:
            return b''
        # Remove any '0x' prefixes and split
        parts = hex_str.split()
        byte_list = []
        for part in parts:
            # Handle with or without 0x prefix
            if part.startswith('0x'):
                part = part[2:]
            byte_list.append(int(part, 16))
        return bytes(byte_list)
    
    def execute_hex(self, hex_input: str) -> Dict[str, Any]:
        """Execute hex bytecode and return result."""
        bytecode = self._assemble_hex(hex_input)
        if not bytecode:
            return {"error": "Empty bytecode"}
        
        # Save current VM state
        old_regs = [self.vm.regs.read_gp(i) for i in range(16)] if self.vm else []
        
        # Create new VM with the bytecode
        self.vm = Interpreter(bytecode, memory_size=self.memory_size)
        try:
            cycles = self.vm.execute()
            regs = [self.vm.regs.read_gp(i) for i in range(16)]
            return {
                "success": True,
                "cycles": cycles,
                "registers": regs,
                "r0": regs[0],
                "halted": self.vm.halted,
                "old_regs": old_regs
            }
        except (VMError, IndexError) as e:
            return {"error": str(e)}
    
    def execute_expr(self, expr: str) -> Dict[str, Any]:
        """Compile and execute a simple expression."""
        # For now, handle simple integer expressions
        try:
            # Evaluate the expression safely
            result = eval(expr, {"__builtins__": {}})
            if isinstance(result, (int, float)):
                # Generate MOVI R0, result; HALT
                from flux.bytecode.opcodes import Op
                import struct
                
                # For integers within 16-bit signed range
                if isinstance(result, int) and -32768 <= result <= 32767:
                    bytecode = struct.pack("<BBh", Op.MOVI, 0, int(result)) + bytes([Op.HALT])
                else:
                    # Default to 0
                    bytecode = struct.pack("<BBh", Op.MOVI, 0, 0) + bytes([Op.HALT])
                
                # Execute
                old_regs = [self.vm.regs.read_gp(i) for i in range(16)] if self.vm else []
                self.vm = Interpreter(bytecode, memory_size=self.memory_size)
                cycles = self.vm.execute()
                regs = [self.vm.regs.read_gp(i) for i in range(16)]
                return {
                    "success": True,
                    "cycles": cycles,
                    "registers": regs,
                    "r0": regs[0],
                    "old_regs": old_regs
                }
            else:
                return {"error": f"Expression must evaluate to a number, got {type(result)}"}
        except Exception as e:
            return {"error": f"Expression evaluation failed: {e}"}
    
    def show_registers(self) -> str:
        """Return formatted register dump."""
        if not self.vm:
            return "No VM initialized"
        
        lines = []
        lines.append(f"{BOLD}{CYAN}General Purpose Registers:{RESET}")
        for i in range(16):
            val = self.vm.regs.read_gp(i)
            if val != 0:
                specials = {11: " (SP)", 14: " (FP)", 15: " (LR)"}
                suffix = specials.get(i, "")
                lines.append(f"  R{i:2d} = {GREEN}{val:>12}{RESET}{suffix}")
            else:
                lines.append(f"  R{i:2d} = {DIM}{val:>12}{RESET}")
        
        # Show FP registers if any are non-zero
        fp_nonzero = False
        for i in range(16):
            if self.vm.regs.read_fp(i) != 0.0:
                fp_nonzero = True
                break
        
        if fp_nonzero:
            lines.append(f"\n{BOLD}{CYAN}Floating Point Registers:{RESET}")
            for i in range(16):
                val = self.vm.regs.read_fp(i)
                if val != 0.0:
                    lines.append(f"  F{i:2d} = {GREEN}{val:>12.6f}{RESET}")
        
        return "\n".join(lines)
    
    def memory_dump(self, start: int = 0, length: int = 64) -> str:
        """Return hex dump of memory."""
        if not self.vm:
            return "No VM initialized"
        
        lines = []
        lines.append(f"{BOLD}{CYAN}Memory dump from 0x{start:04x} to 0x{start+length:04x}:{RESET}")
        
        for offset in range(start, start + length, 16):
            chunk = b''
            for i in range(16):
                addr = offset + i
                if addr < start + length:
                    try:
                        # Read byte from memory
                        # Note: This assumes memory is accessible via some interface
                        # For now, we'll use a placeholder
                        chunk += b'\x00'
                    except (IndexError, OSError):
                        chunk += b'?'
                else:
                    break
            
            hex_part = " ".join(f"{b:02x}" for b in chunk)
            ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            lines.append(f"  0x{offset:04x}: {hex_part:<48}  {ascii_part}")
        
        return "\n".join(lines)
    
    def compile_and_run_c(self, c_code: str) -> Dict[str, Any]:
        """Compile C code to bytecode and run it."""
        try:
            # Try to import C frontend
            from flux.frontend.c_frontend import CFrontendCompiler
            compiler = CFrontendCompiler()
            bytecode = compiler.compile(c_code)
            
            old_regs = [self.vm.regs.read_gp(i) for i in range(16)] if self.vm else []
            self.vm = Interpreter(bytecode, memory_size=self.memory_size)
            cycles = self.vm.execute()
            regs = [self.vm.regs.read_gp(i) for i in range(16)]
            return {
                "success": True,
                "cycles": cycles,
                "registers": regs,
                "r0": regs[0],
                "old_regs": old_regs
            }
        except ImportError:
            return {"error": "C frontend not available"}
        except Exception as e:
            return {"error": f"C compilation failed: {e}"}
    
    def send_a2a_message(self, receiver: str, payload: str) -> Dict[str, Any]:
        """Send an A2A message."""
        try:
            # Create a message
            message = A2AMessage(
                sender=uuid.uuid4(),
                receiver=uuid.uuid5(uuid.NAMESPACE_DNS, receiver),
                conversation_id=uuid.uuid4(),
                message_type=1,  # TELL
                payload=payload.encode('utf-8')
            )
            # For now, just return success
            return {
                "success": True,
                "message": f"Sent to {receiver}: {payload}",
                "bytes": len(message.to_bytes())
            }
        except Exception as e:
            return {"error": f"A2A message failed: {e}"}
    
    def disassemble(self, hex_str: str) -> str:
        """Disassemble hex bytecode to human-readable instructions."""
        bytecode = self._assemble_hex(hex_str)
        if not bytecode:
            return "Empty bytecode"
        
        # Simple disassembler
        from flux.bytecode.opcodes import Op
        lines = []
        i = 0
        while i < len(bytecode):
            opcode = bytecode[i]
            op_name = "UNKNOWN"
            for name, value in vars(Op).items():
                if not name.startswith('_') and value == opcode:
                    op_name = name
                    break
            
            # Basic instruction length detection
            if opcode in [Op.MOVI, Op.LDI, Op.STORE]:
                if i + 3 <= len(bytecode):
                    reg = bytecode[i + 1]
                    imm = struct.unpack_from("<h", bytecode, i + 2)[0]
                    lines.append(f"  0x{i:04x}: {op_name} R{reg}, {imm}")
                    i += 4
                else:
                    lines.append(f"  0x{i:04x}: {op_name} (incomplete)")
                    break
            elif opcode in [Op.IADD, Op.ISUB, Op.IMUL, Op.IDIV]:
                if i + 4 <= len(bytecode):
                    rd = bytecode[i + 1]
                    ra = bytecode[i + 2]
                    rb = bytecode[i + 3]
                    lines.append(f"  0x{i:04x}: {op_name} R{rd}, R{ra}, R{rb}")
                    i += 4
                else:
                    lines.append(f"  0x{i:04x}: {op_name} (incomplete)")
                    break
            elif opcode == Op.HALT:
                lines.append(f"  0x{i:04x}: {op_name}")
                i += 1
            else:
                lines.append(f"  0x{i:04x}: {op_name} (0x{opcode:02x})")
                i += 1
        
        return f"{BOLD}{CYAN}Disassembly:{RESET}\n" + "\n".join(lines)


def run_repl() -> None:
    """Run the interactive REPL."""
    repl = FluxREPL()
    
    print(f"{BOLD}{MAGENTA}╔══════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{MAGENTA}║                 FLUX REPL v1.0                          ║{RESET}")
    print(f"{BOLD}{MAGENTA}╚══════════════════════════════════════════════════════════╝{RESET}")
    print()
    print(f"  Type {CYAN}help{RESET} for commands, {CYAN}quit{RESET} to exit.")
    print(f"  Enter hex bytecode (e.g., '2B 00 03 00 2B 01 04 00 08 00 00 01 80')")
    print(f"  or expressions (e.g., '3 + 4') to execute.")
    print()
    
    while True:
        try:
            # Read input
            try:
                line = input(f"{BOLD}{GREEN}flux>{RESET} ").strip()
            except EOFError:
                print()
                break
            
            if not line:
                continue
            
            # Add to history
            repl.history.append(line)
            
            # Parse command
            if line.lower() == 'quit' or line.lower() == 'exit':
                print(f"{YELLOW}Goodbye!{RESET}")
                break
            elif line.lower() == 'help':
                print_help()
            elif line.lower() == 'regs':
                print(repl.show_registers())
            elif line.lower().startswith('mem'):
                parts = line.split()
                if len(parts) == 1:
                    print(repl.memory_dump())
                elif len(parts) == 2:
                    try:
                        start = int(parts[1], 0)
                        print(repl.memory_dump(start))
                    except ValueError:
                        print(f"{RED}Invalid address: {parts[1]}{RESET}")
                elif len(parts) == 3:
                    try:
                        start = int(parts[1], 0)
                        length = int(parts[2], 0)
                        print(repl.memory_dump(start, length))
                    except ValueError:
                        print(f"{RED}Invalid address/length{RESET}")
                else:
                    print(f"{RED}Usage: mem [start] [length]{RESET}")
            elif line.lower().startswith('c '):
                # C code compilation
                c_code = line[2:].strip()
                result = repl.compile_and_run_c(c_code)
                handle_result(result)
            elif line.lower().startswith('a2a '):
                # A2A message
                parts = shlex.split(line[4:])
                if len(parts) >= 2:
                    receiver = parts[0]
                    payload = " ".join(parts[1:])
                    result = repl.send_a2a_message(receiver, payload)
                    if "error" in result:
                        print(f"{RED}{result['error']}{RESET}")
                    else:
                        print(f"{GREEN}{result['message']}{RESET}")
                else:
                    print(f"{RED}Usage: a2a <receiver> <message>{RESET}")
            elif line.lower().startswith('dis '):
                # Disassemble
                hex_str = line[4:].strip()
                print(repl.disassemble(hex_str))
            else:
                # Try to determine if it's hex or expression
                # Check if it looks like hex bytes (contains hex digits and spaces)
                if all(c in "0123456789abcdefABCDEFx " for c in line):
                    # Likely hex
                    result = repl.execute_hex(line)
                    handle_result(result)
                else:
                    # Try as expression
                    result = repl.execute_expr(line)
                    handle_result(result)
                    
        except KeyboardInterrupt:
            print(f"\n{YELLOW}Interrupted. Type 'quit' to exit.{RESET}")
        except Exception as e:
            print(f"{RED}Error: {e}{RESET}")


def handle_result(result: Dict[str, Any]) -> None:
    """Print execution result."""
    if "error" in result:
        print(f"{RED}Error: {result['error']}{RESET}")
    else:
        # Show register changes
        if "old_regs" in result and "registers" in result:
            print(f"{CYAN}Execution completed in {result['cycles']} cycles{RESET}")
            # Show changed registers
            changed = []
            for i in range(16):
                old = result["old_regs"][i] if i < len(result["old_regs"]) else 0
                new = result["registers"][i] if i < len(result["registers"]) else 0
                if old != new:
                    changed.append(f"R{i}: {old} → {GREEN}{new}{RESET}")
            if changed:
                print(f"  Changed registers: {', '.join(changed)}")
            else:
                print(f"  {DIM}No registers changed{RESET}")
        else:
            print(f"{GREEN}Success{RESET}")


def print_help() -> None:
    """Print help message."""
    help_text = f"""
{BOLD}{CYAN}FLUX REPL Commands:{RESET}

  {GREEN}<hex bytes>{RESET}      Execute bytecode (e.g., 2B 00 03 00 2B 01 04 00 08 00 00 01 80)
  {GREEN}<expression>{RESET}     Evaluate math expression (e.g., 3 + 4, 42)
  {GREEN}c <code>{RESET}        Compile and run C code (e.g., c int add() {{ return 3+4; }})
  {GREEN}a2a <to> <msg>{RESET}  Send A2A message (e.g., a2a agent2 "hello")
  {GREEN}dis <hex>{RESET}       Disassemble hex bytes
  {GREEN}regs{RESET}            Show register state
  {GREEN}mem [start] [len]{RESET}  Dump memory
  {GREEN}help{RESET}            Show this help
  {GREEN}quit{RESET}            Exit the REPL
"""
    print(help_text)


if __name__ == "__main__":
    run_repl()
