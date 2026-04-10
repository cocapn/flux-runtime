"""
Sandbox — isolated FLUX VM execution for safe code testing.

Agents can run untrusted bytecode in a sandbox that:
- Limits execution cycles (prevent infinite loops)
- Isolates memory (separate from host)
- Captures output (register state, cycle count, errors)
- Never affects the host environment
"""

import struct
from dataclasses import dataclass, field
from typing import Optional, Dict, List


@dataclass
class SandboxResult:
    """Result of a sandboxed FLUX execution."""
    success: bool
    registers: List[int] = field(default_factory=lambda: [0]*16)
    cycles: int = 0
    error: Optional[str] = None
    bytecode_hex: str = ""
    assembly: str = ""
    result_value: Optional[int] = None
    result_reg: int = 0
    
    def reg(self, idx: int) -> int:
        return self.registers[idx] if 0 <= idx < 16 else 0


class SandboxVM:
    """
    Minimal FLUX VM for sandboxed execution.
    Independent of the full flux.vm.interpreter — no imports, no deps.
    """
    
    def __init__(self, bytecode: bytes, max_cycles: int = 1_000_000):
        self.bc = bytecode
        self.gp = [0] * 16
        self.pc = 0
        self.halted = False
        self.cycles = 0
        self.max_cycles = max_cycles
        self.error = None
        self.stack = []
    
    def _u8(self) -> int:
        if self.pc >= len(self.bc):
            raise RuntimeError(f"PC out of bounds: {self.pc}")
        v = self.bc[self.pc]
        self.pc += 1
        return v
    
    def _i16(self) -> int:
        lo = self.bc[self.pc]
        hi = self.bc[self.pc + 1]
        self.pc += 2
        val = lo | (hi << 8)
        if val >= 32768:
            val -= 65536
        return val
    
    def execute(self) -> 'SandboxVM':
        """Run until HALT or max_cycles. Returns self for chaining."""
        self.halted = False
        self.cycles = 0
        self.error = None
        
        try:
            while not self.halted and self.pc < len(self.bc) and self.cycles < self.max_cycles:
                op = self._u8()
                self.cycles += 1
                
                if op == 0x80:    # HALT
                    self.halted = True
                elif op == 0x00:  # NOP
                    pass
                elif op == 0x01:  # MOV Rd, Rs
                    d, s = self._u8(), self._u8()
                    self.gp[d] = self.gp[s]
                elif op == 0x2B:  # MOVI Rd, imm16
                    d = self._u8()
                    v = self._i16()
                    self.gp[d] = v
                elif op == 0x08:  # IADD Rd, Ra, Rb
                    d, a, b = self._u8(), self._u8(), self._u8()
                    self.gp[d] = self.gp[a] + self.gp[b]
                elif op == 0x09:  # ISUB
                    d, a, b = self._u8(), self._u8(), self._u8()
                    self.gp[d] = self.gp[a] - self.gp[b]
                elif op == 0x0A:  # IMUL
                    d, a, b = self._u8(), self._u8(), self._u8()
                    self.gp[d] = self.gp[a] * self.gp[b]
                elif op == 0x0B:  # IDIV
                    d, a, b = self._u8(), self._u8(), self._u8()
                    if self.gp[b] == 0:
                        raise RuntimeError("Division by zero")
                    self.gp[d] = int(self.gp[a] / self.gp[b])
                elif op == 0x0E:  # INC
                    self.gp[self._u8()] += 1
                elif op == 0x0F:  # DEC
                    self.gp[self._u8()] -= 1
                elif op == 0x10:  # PUSH
                    self.stack.append(self.gp[self._u8()])
                elif op == 0x11:  # POP
                    if self.stack:
                        self.gp[self._u8()] = self.stack.pop()
                elif op == 0x06:  # JNZ Rd, off16
                    d = self._u8()
                    off = self._i16()
                    if self.gp[d] != 0:
                        self.pc += off
                elif op == 0x2E:  # JZ Rd, off16
                    d = self._u8()
                    off = self._i16()
                    if self.gp[d] == 0:
                        self.pc += off
                elif op == 0x07:  # JMP off16
                    self.pc += self._i16()
                elif op == 0x2D:  # CMP Ra, Rb → R13
                    a, b = self._u8(), self._u8()
                    self.gp[13] = (self.gp[a] > self.gp[b]) - (self.gp[a] < self.gp[b])
                else:
                    raise RuntimeError(f"Unknown opcode: 0x{op:02X} at PC={self.pc-1}")
                    
        except Exception as e:
            self.error = str(e)
        
        return self
    
    def result(self, reg: int = 0) -> SandboxResult:
        """Create a SandboxResult from current state."""
        return SandboxResult(
            success=self.error is None and self.halted,
            registers=list(self.gp),
            cycles=self.cycles,
            error=self.error,
            result_value=self.gp[reg],
            result_reg=reg,
        )
