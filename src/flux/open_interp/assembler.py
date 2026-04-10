"""
Assembler — lightweight text assembly to FLUX bytecode.

Parses simple assembly text (one instruction per line) into executable bytecode.
No labels, no forward references — just straightforward instruction encoding.
"""

import struct
from typing import Dict, Tuple, Optional


# Opcode table — matches the Python VM Format E encoding
OPCODES = {
    'NOP':  0x00,
    'MOV':  0x01,
    'MOVI': 0x2B,
    'IADD': 0x08,
    'ISUB': 0x09,
    'IMUL': 0x0A,
    'IDIV': 0x0B,
    'IMOD': 0x0C,
    'INEG': 0x0D,
    'INC':  0x0E,
    'DEC':  0x0F,
    'PUSH': 0x10,
    'POP':  0x11,
    'AND':  0x20,
    'OR':   0x21,
    'XOR':  0x22,
    'NOT':  0x23,
    'SHL':  0x24,
    'SHR':  0x25,
    'CMP':  0x2D,
    'JZ':   0x2E,
    'JNZ':  0x06,
    'JMP':  0x07,
    'JEQ':  0x31,
    'JNE':  0x32,
    'JLT':  0x33,
    'JGT':  0x34,
    'CALL': 0x40,
    'RET':  0x41,
    'LOAD': 0x50,
    'STORE':0x51,
    'HALT': 0x80,
    'YIELD':0x81,
}

# Instruction formats (number of bytes)
# Format: opcode -> [(format, size)]
# A = single register, B = register pair, C = register + imm16, D = three registers

def parse_reg(s: str) -> int:
    """Parse a register name like 'R0', 'R15', 'r3' → int."""
    s = s.strip().upper()
    if s.startswith('R'):
        return int(s[1:])
    return int(s)

def assemble_text(text: str) -> bytes:
    """
    Assemble FLUX assembly text into bytecode.
    
    Supports:
        MOVI R0, 7        → [0x2B, 0x00, 0x07, 0x00]
        IADD R0, R1, R2   → [0x08, 0x00, 0x01, 0x02]
        DEC R0             → [0x0F, 0x00]
        HALT               → [0x80]
    """
    bc = bytearray()
    
    for line in text.split('\n'):
        line = line.strip()
        # Skip empty lines and comments
        if not line or line.startswith(';') or line.startswith('//') or line.startswith('#'):
            continue
        
        # Remove inline comments
        if ';' in line:
            line = line[:line.index(';')].strip()
        
        # Parse instruction
        parts = line.replace(',', ' ').split()
        if not parts:
            continue
        
        mnemonic = parts[0].upper()
        
        if mnemonic not in OPCODES:
            raise ValueError(f"Unknown mnemonic: {mnemonic}")
        
        opcode = OPCODES[mnemonic]
        
        # One-byte: HALT, NOP, RET, YIELD
        if mnemonic in ('HALT', 'NOP', 'RET', 'YIELD'):
            bc.append(opcode)
        
        # Two-byte: INC, DEC, PUSH, POP, NOT, INEG
        elif mnemonic in ('INC', 'DEC', 'PUSH', 'POP', 'NOT', 'INEG'):
            bc.append(opcode)
            bc.append(parse_reg(parts[1]))
        
        # Three-byte: MOV Rd, Rs
        elif mnemonic in ('MOV',):
            bc.append(opcode)
            bc.append(parse_reg(parts[1]))
            bc.append(parse_reg(parts[2]))
        
        # Four-byte three-register: IADD, ISUB, IMUL, IDIV, IMOD, AND, OR, XOR, SHL, SHR, CMP
        elif mnemonic in ('IADD', 'ISUB', 'IMUL', 'IDIV', 'IMOD', 
                          'AND', 'OR', 'XOR', 'SHL', 'SHR', 'CMP'):
            bc.append(opcode)
            bc.append(parse_reg(parts[1]))
            bc.append(parse_reg(parts[2]))
            bc.append(parse_reg(parts[3]) if len(parts) > 3 else parse_reg(parts[2]))
        
        # Four-byte register + imm16: MOVI, JZ, JNZ
        elif mnemonic in ('MOVI', 'JZ', 'JNZ'):
            bc.append(opcode)
            bc.append(parse_reg(parts[1]))
            imm = int(parts[2])
            bc.extend(struct.pack('<h', imm))
        
        # Three-byte imm16: JMP
        elif mnemonic in ('JMP',):
            bc.append(opcode)
            imm = int(parts[1])
            bc.extend(struct.pack('<h', imm))
        
        else:
            bc.append(opcode)
    
    return bytes(bc)
