#!/usr/bin/env python3
"""
FLUX Flowchart — Markdown to Visual Flowchart to Bytecode

Converts markdown descriptions into:
1. Visual ASCII flowchart (for humans)
2. FLUX bytecode (for execution)

This bridges the gap between human-readable intention and machine-executable bytecode.

Usage:
    PYTHONPATH=src python3 flux_flowchart.py << 'EOF'
    # Factorial Calculator
    Start → Load N into R0, Load 1 into R1
    Loop: Multiply R1 by R0, Decrement R0
    If R0 ≠ 0 → Loop
    Done → Return R1
    EOF
"""

import sys
import os
import re
import struct

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from flux.bytecode.opcodes import Op

# ── ANSI Colors ──────────────────────────────────────────────────
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BLUE = "\033[94m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

# ── Flowchart Node Types ─────────────────────────────────────────
class NodeType:
    START = "start"
    PROCESS = "process"
    DECISION = "decision"
    IO = "io"
    END = "end"

class FlowNode:
    def __init__(self, name, node_type, instruction=None, yes_target=None, no_target=None):
        self.name = name
        self.node_type = node_type
        self.instruction = instruction  # (opcode, operands) tuple
        self.yes_target = yes_target
        self.no_target = no_target
        self.offset = 0  # bytecode offset

    def box(self, width=30):
        """Return ASCII box representation."""
        label = self.name[:width-4]
        if self.node_type == NodeType.START:
            return f"  ╭{'─'*(width-2)}╮\n  │ {label:^{width-4}} │\n  ╰{'─'*(width-2)}╯"
        elif self.node_type == NodeType.END:
            return f"  ╭{'─'*(width-2)}╮\n  │ {label:^{width-4}} │\n  ╰{'─'*(width-2)}╯"
        elif self.node_type == NodeType.DECISION:
            # Diamond shape
            pad = width - len(label) - 6
            lp = pad // 2
            rp = pad - lp
            return f"  ╱{'─'*lp} {label} {'─'*rp}╲\n  ╲{'─'*lp}{'─'*len(label)+2}{'─'*rp}╱"
        else:
            return f"  ┌{'─'*(width-2)}┐\n  │ {label:^{width-4}} │\n  └{'─'*(width-2)}┘"

def parse_markdown_flowchart(md_text):
    """Parse markdown into flow nodes."""
    nodes = []
    lines = md_text.strip().split('\n')

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        # Arrow patterns: A → B or A -> B
        # Start node
        if re.match(r'^(start|begin|beginning)', line, re.I):
            nodes.append(FlowNode("START", NodeType.START))

        # End node
        elif re.match(r'^(end|done|finish|return|halt)', line, re.I):
            name = line.strip()
            if 'return' in line.lower() or 'result' in line.lower():
                reg_match = re.search(r'[Rr](\d+)', line)
                if reg_match:
                    nodes.append(FlowNode(f"Return R{reg_match.group(1)}", NodeType.END,
                                          instruction=('halt', [])))
                else:
                    nodes.append(FlowNode("HALT", NodeType.END, instruction=('halt', [])))
            else:
                nodes.append(FlowNode("HALT", NodeType.END, instruction=('halt', [])))

        # Decision: "If R0 ≠ 0" or "while" or "check"
        elif re.match(r'^(if|while|check|when)', line, re.I):
            reg_match = re.search(r'[Rr](\d+)', line)
            reg = int(reg_match.group(1)) if reg_match else 0
            if '≠' in line or '!=' in line or 'not zero' in line or 'is not' in line:
                nodes.append(FlowNode(f"R{reg} ≠ 0?", NodeType.DECISION,
                                      instruction=('jnz', [reg])))
            elif '=' in line or 'zero' in line or 'is zero' in line:
                nodes.append(FlowNode(f"R{reg} = 0?", NodeType.DECISION,
                                      instruction=('jz', [reg])))

        # Process: load, set, multiply, add, decrement, etc.
        elif re.match(r'^(load|set|initialize|put)', line, re.I):
            # "Load N into R0" or "Load 42 into R1"
            reg_match = re.search(r'[Rr](\d+)', line)
            reg = int(reg_match.group(1)) if reg_match else 0
            # Extract value
            val_match = re.search(r'(?:with|to|into|=\s*)(-?\d+)', line)
            if not val_match:
                # Named values: N, M, etc → use placeholder
                val_match = re.search(r'(\d+)', line)
            val = int(val_match.group(1)) if val_match else 0
            nodes.append(FlowNode(f"MOVI R{reg}, {val}", NodeType.PROCESS,
                                  instruction=('movi', [reg, val])))

        elif re.match(r'^(multiply|mult|times)', line, re.I):
            regs = re.findall(r'[Rr](\d+)', line)
            if len(regs) >= 2:
                nodes.append(FlowNode(f"R{regs[0]} × R{regs[1]}", NodeType.PROCESS,
                                      instruction=('imul', [int(regs[0]), int(regs[1])])))
            elif len(regs) == 1:
                nodes.append(FlowNode(f"IMUL R{regs[0]}", NodeType.PROCESS,
                                      instruction=('imul', [int(regs[0])])))

        elif re.match(r'^(add|plus|increment)', line, re.I):
            regs = re.findall(r'[Rr](\d+)', line)
            if len(regs) >= 2:
                nodes.append(FlowNode(f"R{regs[0]} + R{regs[1]}", NodeType.PROCESS,
                                      instruction=('iadd', [int(regs[0]), int(regs[1])])))

        elif re.match(r'^(subtract|minus|decrement)', line, re.I):
            regs = re.findall(r'[Rr](\d+)', line)
            if len(regs) >= 2:
                nodes.append(FlowNode(f"R{regs[0]} - R{regs[1]}", NodeType.PROCESS,
                                      instruction=('isub', [int(regs[0]), int(regs[1])])))
            else:
                reg = int(regs[0]) if regs else 0
                nodes.append(FlowNode(f"DEC R{reg}", NodeType.PROCESS,
                                      instruction=('dec', [reg])))

        elif re.match(r'^(decrement|decrease|dec)', line, re.I):
            reg_match = re.search(r'[Rr](\d+)', line)
            reg = int(reg_match.group(1)) if reg_match else 0
            nodes.append(FlowNode(f"DEC R{reg}", NodeType.PROCESS,
                                  instruction=('dec', [reg])))

        # Loop label
        elif line.endswith(':') or re.match(r'^(loop|repeat|iterate)', line, re.I):
            name = line.rstrip(':').strip()
            nodes.append(FlowNode(f"[{name}]", NodeType.PROCESS))

        # Arrow connector → skip
        elif '→' in line or '->' in line:
            continue

        # Default: try to extract an instruction
        else:
            nodes.append(FlowNode(line[:30], NodeType.PROCESS))

    if not nodes:
        nodes.append(FlowNode("START", NodeType.START))
        nodes.append(FlowNode("HALT", NodeType.END, instruction=('halt', [])))

    return nodes

def render_flowchart(nodes):
    """Render flowchart as ASCII art."""
    lines = []
    lines.append(f"\n{BOLD}{CYAN}┌─────────────────────────────────────┐{RESET}")
    lines.append(f"{BOLD}{CYAN}│      FLUX Flowchart Visualization    │{RESET}")
    lines.append(f"{BOLD}{CYAN}└─────────────────────────────────────┘{RESET}\n")

    for i, node in enumerate(nodes):
        # Color based on type
        if node.node_type == NodeType.START:
            color = GREEN
        elif node.node_type == NodeType.END:
            color = RED
        elif node.node_type == NodeType.DECISION:
            color = YELLOW
        else:
            color = CYAN

        # Node box
        box_lines = node.box().split('\n')
        for bl in box_lines:
            lines.append(f"  {color}{bl}{RESET}")

        # Arrow to next
        if i < len(nodes) - 1:
            if node.node_type == NodeType.DECISION:
                lines.append(f"  {YELLOW}│ Yes              No ────┐{RESET}")
                lines.append(f"  {YELLOW}▼                        │{RESET}")
            else:
                lines.append(f"  {DIM}│{RESET}")
                lines.append(f"  {DIM}▼{RESET}")

    lines.append("")
    return '\n'.join(lines)

def nodes_to_bytecode(nodes):
    """Convert flow nodes to FLUX bytecode (Python VM Format E)."""
    bc = bytearray()

    for i, node in enumerate(nodes):
        node.offset = len(bc)
        if not node.instruction:
            continue

        op_name = node.instruction[0]
        args = node.instruction[1]

        if op_name == 'halt':
            bc.append(Op.HALT)
        elif op_name == 'movi':
            bc.extend(struct.pack('<BBh', Op.MOVI, args[0], args[1]))
        elif op_name == 'iadd':
            if len(args) == 2:
                bc.extend(bytes([Op.IADD, args[0], args[0], args[1]]))
            else:
                bc.extend(bytes([Op.IADD, args[0]]))
        elif op_name == 'isub':
            if len(args) == 2:
                bc.extend(bytes([Op.ISUB, args[0], args[0], args[1]]))
        elif op_name == 'imul':
            if len(args) == 2:
                bc.extend(bytes([Op.IMUL, args[0], args[0], args[1]]))
            else:
                bc.extend(bytes([Op.IMUL, args[0]]))
        elif op_name == 'inc':
            bc.extend(bytes([Op.INC, args[0]]))
        elif op_name == 'dec':
            bc.extend(bytes([Op.DEC, args[0]]))
        elif op_name == 'jnz':
            # JNZ with back-reference to the loop start
            # Find the nearest "loop" label before this node
            target = 0
            for j in range(i-1, -1, -1):
                if nodes[j].name.startswith('[') or 'loop' in nodes[j].name.lower():
                    target = nodes[j].offset
                    break
            offset = target - (len(bc) + 4)  # relative to after JNZ instruction
            bc.extend(struct.pack('<BBh', Op.JNZ, args[0], offset))
        elif op_name == 'jz':
            offset = 0  # forward jump — would need target resolution
            bc.extend(struct.pack('<BBh', Op.JZ, args[0], offset))

    return bytes(bc)

def main():
    print(f"{BOLD}{MAGENTA}╔════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{MAGENTA}║      FLUX Flowchart: Markdown → Bytecode      ║{RESET}")
    print(f"{BOLD}{MAGENTA}╚════════════════════════════════════════════════╝{RESET}")

    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            md_text = f.read()
    else:
        print(f"\n{DIM}Enter markdown flowchart (Ctrl+D to finish):{RESET}\n")
        md_text = sys.stdin.read()

    # Parse markdown → flow nodes
    nodes = parse_markdown_flowchart(md_text)

    # Render visual flowchart
    print(render_flowchart(nodes))

    # Generate bytecode
    bc = nodes_to_bytecode(nodes)

    # Show bytecode
    print(f"{BOLD}{CYAN}Generated Bytecode:{RESET}")
    hex_str = ' '.join(f'{b:02X}' for b in bc)
    print(f"  {GREEN}{hex_str}{RESET}")
    print(f"  ({len(bc)} bytes)\n")

    # Show disassembly
    print(f"{BOLD}{CYAN}Disassembly:{RESET}")
    pos = 0
    while pos < len(bc):
        op = bc[pos]
        op_name = "???"
        for name in dir(Op):
            if not name.startswith('_') and getattr(Op, name) == op:
                op_name = name
                break

        if op == Op.HALT:
            print(f"  {pos:04d}: {YELLOW}{op_name}{RESET}")
            pos += 1
        elif op == Op.MOVI:
            reg = bc[pos+1]
            imm = struct.unpack_from('<h', bc, pos+2)[0]
            print(f"  {pos:04d}: {GREEN}MOVI R{reg}, {imm}{RESET}")
            pos += 4
        elif op in (Op.IADD, Op.ISUB, Op.IMUL, Op.IDIV):
            names = {Op.IADD:'IADD', Op.ISUB:'ISUB', Op.IMUL:'IMUL', Op.IDIV:'IDIV'}
            rd, rs1, rs2 = bc[pos+1], bc[pos+2], bc[pos+3]
            print(f"  {pos:04d}: {CYAN}{names[op]} R{rd}, R{rs1}, R{rs2}{RESET}")
            pos += 4
        elif op in (Op.INC, Op.DEC):
            names = {Op.INC:'INC', Op.DEC:'DEC'}
            reg = bc[pos+1]
            print(f"  {pos:04d}: {CYAN}{names[op]} R{reg}{RESET}")
            pos += 2
        elif op in (Op.JNZ, Op.JZ):
            names = {Op.JNZ:'JNZ', Op.JZ:'JZ'}
            reg = bc[pos+1]
            off = struct.unpack_from('<h', bc, pos+2)[0]
            target = pos + 4 + off
            print(f"  {pos:04d}: {YELLOW}{names[op]} R{reg}, → {target:04d} ({off:+d}){RESET}")
            pos += 4
        else:
            print(f"  {pos:04d}: {RED}??? 0x{op:02X}{RESET}")
            pos += 1

    # Execute if possible
    if len(bc) > 0:
        try:
            from flux.vm.interpreter import Interpreter
            print(f"\n{BOLD}{GREEN}Executing...{RESET}")
            vm = Interpreter(bc, memory_size=4096)
            cycles = vm.execute()
            print(f"  Cycles: {cycles}")
            for i in range(16):
                val = vm.regs.read_gp(i)
                if val != 0:
                    specials = {11:"(SP)", 14:"(FP)", 15:"(LR)"}
                    suffix = specials.get(i, "")
                    print(f"  {BOLD}R{i:2d} = {GREEN}{val}{RESET} {DIM}{suffix}{RESET}")
        except Exception as e:
            print(f"\n  {RED}Execution error: {e}{RESET}")

if __name__ == '__main__':
    main()
