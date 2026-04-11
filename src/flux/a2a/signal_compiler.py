"""
Signal → FLUX Bytecode Compiler

Babel designed Signal (flux-a2a): JSON IS the AST.
Oracle1 designed FORMAT_A-G: byte encodings for the VM.

This compiler bridges them. Signal JSON programs compile to FLUX bytecodes.
Any agent can write in Signal and execute on any FLUX VM.

Signal opcodes → FLUX bytecodes:
  tell       → TELL (0x50)
  ask        → ASK (0x52)  
  delegate   → DELEG (0x52)
  broadcast  → BCAST (0x53)
  add/sub..  → ADD/SUB (0x20-0x24)
  seq        → (sequential emission)
  if         → CMP_EQ + JZ
  loop       → MOVI + LOOP (0x46)
  while      → JZ/JNZ pattern
  branch     → FORK (0x58)
  fork       → FORK (0x58)
  merge      → MERGE (0x57) + JOIN (0x59)
  let/get/set → MOVI + LOAD/STORE
  confidence → C_ADD etc (0x60+)
  yield      → YIELD (0x15)
  await      → AWAIT (0x5B)
"""
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class CompiledSignal:
    """Result of compiling a Signal program to FLUX bytecode."""
    bytecode: bytes
    register_map: Dict[str, int]  # name → register
    label_map: Dict[str, int]     # label → byte offset
    source_map: Dict[int, int]    # byte offset → JSON line
    errors: List[str] = field(default_factory=list)
    
    @property
    def success(self) -> bool:
        return len(self.errors) == 0


class SignalCompiler:
    """
    Compiles Signal JSON programs to FLUX FORMAT_A-G bytecodes.
    
    Signal program structure:
    {
      "program": "name",
      "lang": "signal",
      "ops": [
        {"op": "let", "name": "x", "value": 42},
        {"op": "tell", "to": "agent-1", "what": "hello"},
        ...
      ]
    }
    """
    
    def __init__(self, num_registers: int = 64):
        self.num_registers = num_registers
        self.reset()
    
    def reset(self):
        self._bytecode: List[int] = []
        self._reg_counter: int = 0
        self._register_map: Dict[str, int] = {}
        self._label_map: Dict[str, int] = {}
        self._source_map: Dict[int, int] = {}
        self._errors: List[str] = []
        self._pending_jumps: List[Tuple[int, str]] = []  # (offset, label)
    
    def _alloc_reg(self, name: str) -> int:
        if name in self._register_map:
            return self._register_map[name]
        if self._reg_counter >= self.num_registers:
            self._errors.append(f"Register overflow: no room for '{name}'")
            return 0
        reg = self._reg_counter
        self._register_map[name] = reg
        self._reg_counter += 1
        return reg
    
    def _emit(self, *bytes_: int, source_line: int = 0) -> int:
        """Emit bytes, return start offset."""
        offset = len(self._bytecode)
        for b in bytes_:
            self._bytecode.append(b & 0xFF)
        if source_line:
            self._source_map[offset] = source_line
        return offset
    
    def _emit_label(self, label: str):
        """Mark current position as a label."""
        self._label_map[label] = len(self._bytecode)
    
    def _resolve_jumps(self):
        """Back-patch pending jumps with resolved label addresses."""
        for offset, label in self._pending_jumps:
            target = self._label_map.get(label)
            if target is None:
                self._errors.append(f"Unresolved label: {label}")
                continue
            # Calculate relative offset from the jump instruction
            # Jump is at offset, instruction is 4 bytes (Format F)
            rel = target - (offset + 4)
            self._bytecode[offset + 2] = (rel >> 8) & 0xFF
            self._bytecode[offset + 3] = rel & 0xFF
        self._pending_jumps.clear()
    
    # ── Emit helpers for each FORMAT ──
    
    def _emit_format_a(self, opcode: int, source_line: int = 0) -> int:
        return self._emit(opcode, source_line=source_line)
    
    def _emit_format_b(self, opcode: int, rd: int, source_line: int = 0) -> int:
        return self._emit(opcode, rd, source_line=source_line)
    
    def _emit_format_d(self, opcode: int, rd: int, imm8: int, source_line: int = 0) -> int:
        return self._emit(opcode, rd, imm8 & 0xFF, source_line=source_line)
    
    def _emit_format_e(self, opcode: int, rd: int, rs1: int, rs2: int, source_line: int = 0) -> int:
        return self._emit(opcode, rd, rs1, rs2, source_line=source_line)
    
    def _emit_format_f(self, opcode: int, rd: int, imm16: int, source_line: int = 0) -> int:
        imm16 = imm16 & 0xFFFF
        return self._emit(opcode, rd, (imm16 >> 8) & 0xFF, imm16 & 0xFF, source_line=source_line)
    
    # ── Signal op compilers ──
    
    def _compile_let(self, op: dict, line: int):
        """let: bind name to value → MOVI or MOVI16"""
        name = op.get("name", "")
        value = op.get("value", 0)
        rd = self._alloc_reg(name)
        
        if isinstance(value, str):
            # String reference — store as register reference
            rs = self._alloc_reg(value)
            self._emit_format_e(0x3A, rd, rs, 0, source_line=line)  # MOV
        elif -128 <= value <= 127:
            self._emit_format_d(0x18, rd, value, source_line=line)  # MOVI
        else:
            self._emit_format_f(0x40, rd, value, source_line=line)  # MOVI16
    
    def _compile_arithmetic(self, op: dict, line: int):
        """add, sub, mul, div, mod → Format E"""
        op_name = op.get("op", "")
        result_name = op.get("into", op.get("as", f"_t{self._reg_counter}"))
        
        opcode_map = {
            "add": 0x20, "sub": 0x21, "mul": 0x22, "div": 0x23, "mod": 0x24,
        }
        opcode = opcode_map.get(op_name)
        if opcode is None:
            self._errors.append(f"Unknown arithmetic op: {op_name}")
            return
        
        args = op.get("args", [])
        if len(args) < 2:
            self._errors.append(f"{op_name} needs at least 2 args")
            return
        
        rd = self._alloc_reg(result_name)
        
        # First pair
        if isinstance(args[0], str):
            rs1 = self._register_map.get(args[0], self._alloc_reg(args[0]))
        else:
            rs1 = self._alloc_reg(f"_imm_{args[0]}")
            self._emit_format_d(0x18, rs1, args[0], source_line=line)
        
        if isinstance(args[1], str):
            rs2 = self._register_map.get(args[1], self._alloc_reg(args[1]))
        else:
            rs2 = self._alloc_reg(f"_imm_{args[1]}")
            self._emit_format_d(0x18, rs2, args[1], source_line=line)
        
        self._emit_format_e(opcode, rd, rs1, rs2, source_line=line)
        
        # Chain remaining args
        for i in range(2, len(args)):
            if isinstance(args[i], str):
                rs = self._register_map.get(args[i], self._alloc_reg(args[i]))
            else:
                rs = self._alloc_reg(f"_imm_{args[i]}")
                self._emit_format_d(0x18, rs, args[i], source_line=line)
            self._emit_format_e(opcode, rd, rd, rs, source_line=line)
    
    def _compile_comparison(self, op: dict, line: int):
        """eq, neq, lt, lte, gt, gte → Format E"""
        op_name = op.get("op", "")
        result_name = op.get("into", f"_cmp{self._reg_counter}")
        
        opcode_map = {
            "eq": 0x2C, "neq": 0x2F, "lt": 0x2D, "lte": 0x2D, "gt": 0x2E, "gte": 0x2E,
        }
        opcode = opcode_map.get(op_name)
        if opcode is None:
            self._errors.append(f"Unknown comparison: {op_name}")
            return
        
        args = op.get("args", [])
        rd = self._alloc_reg(result_name)
        rs1 = self._register_map.get(args[0], self._alloc_reg(str(args[0]))) if args else 0
        rs2 = self._register_map.get(args[1], self._alloc_reg(str(args[1]))) if len(args) > 1 else 0
        
        self._emit_format_e(opcode, rd, rs1, rs2, source_line=line)
    
    def _compile_logic(self, op: dict, line: int):
        """and, or, not, xor"""
        op_name = op.get("op", "")
        result_name = op.get("into", f"_log{self._reg_counter}")
        
        if op_name == "not":
            rs = self._register_map.get(op.get("args", [""])[0], 0)
            rd = self._alloc_reg(result_name)
            self._emit_format_b(0x0A, rd, source_line=line)  # NOT
            return
        
        opcode_map = {"and": 0x25, "or": 0x26, "xor": 0x27}
        opcode = opcode_map.get(op_name, 0x25)
        args = op.get("args", [])
        rd = self._alloc_reg(result_name)
        rs1 = self._register_map.get(args[0], self._alloc_reg(str(args[0]))) if args else 0
        rs2 = self._register_map.get(args[1], self._alloc_reg(str(args[1]))) if len(args) > 1 else 0
        self._emit_format_e(opcode, rd, rs1, rs2, source_line=line)
    
    def _compile_tell(self, op: dict, line: int):
        """tell: send info to agent → TELL (0x50)"""
        to_name = op.get("to", "")
        what = op.get("what", "")
        tag = op.get("tag", "")
        
        rd = self._alloc_reg(f"_tag_{tag}" if tag else f"_msg{self._reg_counter}")
        rs1 = self._alloc_reg(f"_agent_{to_name}")
        rs2 = self._alloc_reg(f"_data_{what}")
        
        self._emit_format_e(0x50, rd, rs1, rs2, source_line=line)  # TELL
    
    def _compile_ask(self, op: dict, line: int):
        """ask: request info from agent → ASK (0x51)"""
        to_name = op.get("from", op.get("to", ""))
        what = op.get("what", "")
        into = op.get("into", f"_resp{self._reg_counter}")
        
        rd = self._alloc_reg(into)
        rs1 = self._alloc_reg(f"_agent_{to_name}")
        rs2 = self._alloc_reg(f"_query_{what}")
        
        self._emit_format_e(0x51, rd, rs1, rs2, source_line=line)  # ASK
    
    def _compile_delegate(self, op: dict, line: int):
        """delegate: assign task → DELEG (0x52)"""
        to_name = op.get("to", "")
        task = op.get("task", "")
        
        rd = self._alloc_reg(f"_deleg{self._reg_counter}")
        rs1 = self._alloc_reg(f"_agent_{to_name}")
        rs2 = self._alloc_reg(f"_task_{task}")
        
        self._emit_format_e(0x52, rd, rs1, rs2, source_line=line)  # DELEG
    
    def _compile_broadcast(self, op: dict, line: int):
        """broadcast: send to all → BCAST (0x53)"""
        what = op.get("what", "")
        tag = op.get("tag", "")
        
        rd = self._alloc_reg(f"_btag_{tag}" if tag else f"_bcast{self._reg_counter}")
        rs1 = 0  # broadcast target = 0 (all)
        rs2 = self._alloc_reg(f"_bdata_{what}")
        
        self._emit_format_e(0x53, rd, rs1, rs2, source_line=line)  # BCAST
    
    def _compile_seq(self, op: dict, line: int):
        """seq: sequential execution — just compile children in order"""
        for i, child in enumerate(op.get("body", [])):
            self._compile_op(child, line=line)
    
    def _compile_if(self, op: dict, line: int):
        """if: conditional → CMP + JZ"""
        cond_name = op.get("cond", "")
        label_else = f"_else_{line}_{self._reg_counter}"
        label_end = f"_endif_{line}_{self._reg_counter}"
        
        cond_reg = self._register_map.get(cond_name, self._alloc_reg(cond_name))
        
        # JZ: if cond == 0, jump to else
        jump_offset = self._emit_format_e(0x3C, cond_reg, 0, 0, source_line=line)  # JZ
        
        # Compile "then" body
        for child in op.get("then", []):
            self._compile_op(child, line=line)
        
        if "else" in op:
            # Jump over else block
            else_jump = self._emit_format_f(0x43, 0, 0, source_line=line)  # JMP
            self._pending_jumps.append((else_jump, label_end))
        
        self._emit_label(label_else)
        
        # Compile "else" body
        for child in op.get("else", []):
            self._compile_op(child, line=line)
        
        self._emit_label(label_end)
        
        # Back-patch the JZ jump
        else_target = self._label_map.get(label_else, 0)
        rel = else_target - (jump_offset + 4)
        self._bytecode[jump_offset + 2] = (rel >> 8) & 0xFF
        self._bytecode[jump_offset + 3] = rel & 0xFF
    
    def _compile_loop(self, op: dict, line: int):
        """loop: counted iteration → MOVI + LOOP (0x46)"""
        count_name = op.get("count", op.get("times", ""))
        body = op.get("body", [])
        counter = self._alloc_reg(f"_loop_ctr_{self._reg_counter}")
        
        if isinstance(count_name, int):
            self._emit_format_d(0x18, counter, count_name, source_line=line)  # MOVI
        else:
            src = self._register_map.get(count_name, self._alloc_reg(count_name))
            self._emit_format_e(0x3A, counter, src, 0, source_line=line)  # MOV
        
        label_start = f"_loop_start_{line}_{counter}"
        self._emit_label(label_start)
        
        for child in body:
            self._compile_op(child, line=line)
        
        # LOOP: decrement counter, jump back if > 0
        loop_back = len(self._bytecode) - self._label_map[label_start]
        self._emit_format_f(0x46, counter, loop_back, source_line=line)  # LOOP
    
    def _compile_branch(self, op: dict, line: int):
        """branch/fork: parallel execution → FORK (0x58)"""
        branches = op.get("branches", op.get("body", []))
        n = len(branches)
        
        for i, branch in enumerate(branches):
            child_reg = self._alloc_reg(f"_fork_{i}")
            self._emit_format_e(0x58, child_reg, i, n, source_line=line)  # FORK
            if isinstance(branch, dict):
                self._compile_op(branch, line)
        
        # JOIN all forks
        join_reg = self._alloc_reg(f"_join_{self._reg_counter}")
        self._emit_format_e(0x59, join_reg, n, 0, source_line=line)  # JOIN
    
    def _compile_merge(self, op: dict, line: int):
        """merge: join branches with strategy → MERGE (0x57)"""
        strategy = op.get("strategy", "last")
        result_name = op.get("into", f"_merge{self._reg_counter}")
        
        rd = self._alloc_reg(result_name)
        rs1 = self._alloc_reg(f"_strategy_{strategy}")
        rs2 = 0
        
        self._emit_format_e(0x57, rd, rs1, rs2, source_line=line)  # MERGE
    
    def _compile_confidence(self, op: dict, line: int):
        """confidence: set confidence level"""
        level = op.get("level", 1.0)
        target = op.get("for", "")
        
        rd = self._register_map.get(target, self._alloc_reg(target))
        imm8 = int(level * 255)
        
        self._emit_format_d(0x69, rd, imm8, source_line=line)  # C_THRESH
    
    def _compile_yield(self, op: dict, line: int):
        """yield: suspend execution"""
        value_name = op.get("value", "")
        cycles = op.get("cycles", 1)
        self._emit(0x15, cycles, source_line=line)  # YIELD (Format C)
    
    def _compile_await(self, op: dict, line: int):
        """await: wait for signal/result"""
        signal_name = op.get("signal", "")
        into = op.get("into", f"_await{self._reg_counter}")
        
        rd = self._alloc_reg(into)
        rs1 = 0
        rs2 = self._alloc_reg(f"_sig_{signal_name}")
        self._emit_format_e(0x5B, rd, rs1, rs2, source_line=line)  # AWAIT
    
    # ── Dispatcher ──
    
    def _compile_op(self, op: dict, line: int = 0, **kwargs):
        """Compile a single Signal operation."""
        op_name = op.get("op", "")
        
        dispatch = {
            "let": self._compile_let,
            "add": self._compile_arithmetic,
            "sub": self._compile_arithmetic,
            "mul": self._compile_arithmetic,
            "div": self._compile_arithmetic,
            "mod": self._compile_arithmetic,
            "eq": self._compile_comparison,
            "neq": self._compile_comparison,
            "lt": self._compile_comparison,
            "lte": self._compile_comparison,
            "gt": self._compile_comparison,
            "gte": self._compile_comparison,
            "and": self._compile_logic,
            "or": self._compile_logic,
            "not": self._compile_logic,
            "xor": self._compile_logic,
            "tell": self._compile_tell,
            "ask": self._compile_ask,
            "delegate": self._compile_delegate,
            "broadcast": self._compile_broadcast,
            "seq": self._compile_seq,
            "if": self._compile_if,
            "loop": self._compile_loop,
            "while": self._compile_if,  # simplified: uses same conditional pattern
            "branch": self._compile_branch,
            "fork": self._compile_branch,
            "merge": self._compile_merge,
            "confidence": self._compile_confidence,
            "yield": self._compile_yield,
            "await": self._compile_await,
        }
        
        compiler = dispatch.get(op_name)
        if compiler:
            compiler(op, line)
        else:
            self._errors.append(f"Unknown Signal op: {op_name}")
    
    def compile(self, program: dict) -> CompiledSignal:
        """Compile a complete Signal program to FLUX bytecode."""
        self.reset()
        
        ops = program.get("ops", [])
        for i, op in enumerate(ops):
            self._compile_op(op, line=i + 1)
        
        self._emit_format_a(0x00)  # HALT
        
        self._resolve_jumps()
        
        return CompiledSignal(
            bytecode=bytes(self._bytecode),
            register_map=dict(self._register_map),
            label_map=dict(self._label_map),
            source_map=dict(self._source_map),
            errors=list(self._errors),
        )
    
    def compile_string(self, json_string: str) -> CompiledSignal:
        """Compile a Signal program from JSON string."""
        try:
            program = json.loads(json_string)
        except json.JSONDecodeError as e:
            return CompiledSignal(
                bytecode=b"", register_map={}, label_map={}, source_map={},
                errors=[f"JSON parse error: {e}"]
            )
        return self.compile(program)
