"""
Vocabulary Pruning System — Copy everything, compile only what you need.

Agents copy entire vocabulary collections into their repos as signals
to other agents: "here's what I know, here's what I'm working with."
But at compile time, unused vocabulary gets pruned to produce a minimal
runtime optimized for the actual hardware.

Like a hermit crab: carry everything when you're exploring,
pack only what you need when you move to a new shell.

Usage:
    from flux.open_interp.pruning import UsageTracker, VocabularyPruner, RuntimeCompiler

    tracker = UsageTracker()
    # ... agent runs, vocabulary gets used ...
    tracker.mark_used("factorial")
    tracker.mark_used("compute")

    pruner = VocabularyPruner()
    pruned = pruner.prune(vocab, tracker, min_calls=1)

    compiler = RuntimeCompiler()
    compiler.compile(pruned, "my_agent_flux.py", name="MyAgentFlux")
"""

import os
import re
import time
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import Counter


@dataclass
class UsageStats:
    """Statistics about vocabulary entry usage."""
    entry_name: str
    call_count: int
    last_used: float  # timestamp
    first_used: float
    dependents: List[str] = field(default_factory=list)  # entries that depend on this


class UsageTracker:
    """
    Tracks which vocabulary entries are actually used during execution.
    
    Agents mark entries as used during their normal operation.
    The tracker records frequency, recency, and dependency information.
    """
    
    def __init__(self):
        self._usage: Dict[str, int] = Counter()
        self._first_seen: Dict[str, float] = {}
        self._last_seen: Dict[str, float] = {}
    
    def mark_used(self, entry_name: str) -> None:
        """Record that a vocabulary entry was used."""
        now = time.time()
        self._usage[entry_name] += 1
        if entry_name not in self._first_seen:
            self._first_seen[entry_name] = now
        self._last_seen[entry_name] = now
    
    def get_call_count(self, entry_name: str) -> int:
        """Get the number of times an entry was used."""
        return self._usage.get(entry_name, 0)
    
    def get_usage_stats(self) -> Dict[str, UsageStats]:
        """Get detailed usage statistics for all tracked entries."""
        stats = {}
        for name in self._usage:
            stats[name] = UsageStats(
                entry_name=name,
                call_count=self._usage[name],
                last_used=self._last_seen.get(name, 0),
                first_used=self._first_seen.get(name, 0),
            )
        return stats
    
    def get_most_used(self, n: int = 10) -> List[Tuple[str, int]]:
        """Get the top-N most used entries."""
        return self._usage.most_common(n)
    
    def get_unused(self, all_names: List[str]) -> List[str]:
        """Get entries that were never used."""
        return [n for n in all_names if n not in self._usage]
    
    def reset(self) -> None:
        """Clear all usage data."""
        self._usage.clear()
        self._first_seen.clear()
        self._last_seen.clear()
    
    def to_dict(self) -> dict:
        """Serialize usage data."""
        return {
            "usage": dict(self._usage),
            "first_seen": self._first_seen,
            "last_seen": self._last_seen,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'UsageTracker':
        """Deserialize usage data."""
        tracker = cls()
        tracker._usage = Counter(data.get("usage", {}))
        tracker._first_seen = data.get("first_seen", {})
        tracker._last_seen = data.get("last_seen", {})
        return tracker


@dataclass
class PruneReport:
    """Report from a pruning operation."""
    original_count: int
    pruned_count: int
    removed: List[str]
    kept: List[str]
    warnings: List[str]
    savings_percent: float


class VocabularyPruner:
    """
    Prunes vocabulary to only what's needed.
    
    Three pruning strategies:
    1. By usage: keep only entries that were actually called
    2. By size: keep top-N most used entries
    3. By dependency: keep entries and their transitive dependencies
    """
    
    def prune(self, vocab, tracker: UsageTracker, min_calls: int = 1) -> 'Vocabulary':
        """
        Prune vocabulary to only entries with min_calls or more uses.
        Also keeps any entries that are dependencies of kept entries.
        """
        from .vocabulary import Vocabulary, VocabEntry
        
        # Find entries that meet the threshold
        kept_names = set()
        for entry in vocab.entries:
            if tracker.get_call_count(entry.name) >= min_calls:
                kept_names.add(entry.name)
        
        # Expand to include dependencies
        kept_names = self._expand_dependencies(vocab, kept_names)
        
        # Build pruned vocabulary
        pruned = Vocabulary()
        for entry in vocab.entries:
            if entry.name in kept_names:
                pruned.entries.append(entry)
        
        return pruned
    
    def prune_to_size(self, vocab, tracker: UsageTracker, max_entries: int = 100) -> 'Vocabulary':
        """Keep only the top-N most used entries plus their dependencies."""
        most_used = tracker.get_most_used(max_entries)
        kept_names = {name for name, _ in most_used}
        kept_names = self._expand_dependencies(vocab, kept_names)
        
        from .vocabulary import Vocabulary
        pruned = Vocabulary()
        for entry in vocab.entries:
            if entry.name in kept_names:
                pruned.entries.append(entry)
        
        return pruned
    
    def prune_for_hardware(self, vocab, tracker: UsageTracker,
                           target: str = "embedded") -> 'Vocabulary':
        """
        Prune vocabulary based on hardware constraints.
        
        Targets:
        - "embedded": only L0 primitives, no loops, max 20 entries
        - "edge": L0 + L1, max 50 entries
        - "server": everything used at least once
        - "gpu": only compute-heavy entries (no I/O patterns)
        """
        from .vocabulary import Vocabulary
        
        if target == "embedded":
            pruned = Vocabulary()
            for entry in vocab.entries:
                # Only keep simple primitives, no loops
                tags = set(t.lower() for t in entry.tags)
                if "loop" not in tags and "control-flow" not in tags:
                    if tracker.get_call_count(entry.name) >= 1:
                        pruned.entries.append(entry)
                        if len(pruned.entries) >= 20:
                            break
            return pruned
        
        elif target == "edge":
            return self.prune_to_size(vocab, tracker, max_entries=50)
        
        elif target == "gpu":
            pruned = Vocabulary()
            compute_tags = {"math", "compute", "arithmetic", "matrix", "tensor"}
            for entry in vocab.entries:
                tags = set(t.lower() for t in entry.tags)
                if tags & compute_tags:
                    pruned.entries.append(entry)
            return pruned
        
        else:  # server
            return self.prune(vocab, tracker, min_calls=1)
    
    def dead_code_report(self, vocab, tracker: UsageTracker) -> PruneReport:
        """Generate a report on unused vocabulary entries."""
        kept = []
        removed = []
        warnings = []
        
        for entry in vocab.entries:
            if tracker.get_call_count(entry.name) > 0:
                kept.append(entry.name)
            else:
                removed.append(entry.name)
        
        # Check if any kept entry depends on a removed entry
        removed_set = set(removed)
        kept_set = set(kept)
        for entry in vocab.entries:
            if entry.name in kept_set:
                for dep in getattr(entry, 'depends', []):
                    if dep in removed_set:
                        warnings.append(
                            f"⚠ {entry.name} depends on {dep} which is unused"
                        )
        
        original = len(vocab.entries)
        savings = (len(removed) / original * 100) if original > 0 else 0
        
        return PruneReport(
            original_count=original,
            pruned_count=len(kept),
            removed=removed,
            kept=kept,
            warnings=warnings,
            savings_percent=round(savings, 1),
        )
    
    def _expand_dependencies(self, vocab, kept_names: Set[str]) -> Set[str]:
        """Expand kept set to include transitive dependencies."""
        name_to_deps = {}
        for entry in vocab.entries:
            name_to_deps[entry.name] = getattr(entry, 'depends', [])
        
        changed = True
        while changed:
            changed = False
            for name in list(kept_names):
                for dep in name_to_deps.get(name, []):
                    if dep not in kept_names:
                        kept_names.add(dep)
                        changed = True
        
        return kept_names
    
    def dependency_check(self, vocab, removed_names: List[str]) -> List[str]:
        """Check if any remaining entry depends on a removed entry."""
        removed_set = set(removed_names)
        warnings = []
        
        for entry in vocab.entries:
            if entry.name not in removed_set:
                for dep in getattr(entry, 'depends', []):
                    if dep in removed_set:
                        warnings.append(f"{entry.name} → {dep}")
        
        return warnings


class RuntimeCompiler:
    """
    Compiles a pruned vocabulary into a standalone Python runtime.
    
    Generates a single .py file with:
    - Minimal VM (only needed opcodes)
    - Assembler (only needed patterns)
    - Vocabulary entries that survived pruning
    - run(text) function for natural language input
    
    Zero dependencies. Copy it to any agent's repo and it works.
    """
    
    # Opcode set
    OP_MOVI = 0x2B
    OP_IADD = 0x08
    OP_ISUB = 0x09
    OP_IMUL = 0x0A
    OP_IDIV = 0x0B
    OP_INC = 0x0E
    OP_DEC = 0x0F
    OP_JNZ = 0x06
    OP_JZ = 0x2E
    OP_CMP = 0x2D
    OP_HALT = 0x80
    OP_NOP = 0x00
    OP_MOV = 0x01
    
    def compile(self, vocab, output_path: str, name: str = "CustomFlux") -> str:
        """
        Compile a pruned vocabulary into a standalone Python file.
        """
        lines = []
        lines.append(f'"""')
        lines.append(f'{name} — Auto-generated FLUX runtime.')
        lines.append(f'Pruned and compiled from vocabulary entries.')
        lines.append(f'Generated: {time.strftime("%Y-%m-%d %H:%M UTC")}')
        lines.append(f'Entries: {len(vocab.entries)}')
        lines.append(f'Zero dependencies. Copy anywhere.')
        lines.append(f'"""')
        lines.append('')
        
        # Collect needed opcodes
        needed_ops = self._scan_opcodes(vocab)
        
        # Inline VM
        lines.append('# === VM ===')
        lines.append(self._generate_vm(needed_ops))
        lines.append('')
        
        # Inline assembler
        lines.append('# === Assembler ===')
        lines.append(self._generate_assembler())
        lines.append('')
        
        # Vocabulary entries
        lines.append('# === Vocabulary ===')
        lines.append(self._generate_vocabulary(vocab))
        lines.append('')
        
        # Interpreter
        lines.append('# === Interpreter ===')
        lines.append(self._generate_interpreter(vocab, name))
        
        # Write file
        content = '\n'.join(lines)
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        with open(output_path, 'w') as f:
            f.write(content)
        
        return content
    
    def _scan_opcodes(self, vocab) -> Set[int]:
        """Scan vocabulary entries to find which opcodes are needed."""
        ops = set()
        op_names = {
            'MOVI': self.OP_MOVI, 'IADD': self.OP_IADD, 'ISUB': self.OP_ISUB,
            'IMUL': self.OP_IMUL, 'IDIV': self.OP_IDIV, 'INC': self.OP_INC,
            'DEC': self.OP_DEC, 'JNZ': self.OP_JNZ, 'JZ': self.OP_JZ,
            'CMP': self.OP_CMP, 'HALT': self.OP_HALT, 'NOP': self.OP_NOP,
            'MOV': self.OP_MOV,
        }
        for entry in vocab.entries:
            asm = getattr(entry, 'bytecode_template', '') or ''
            for name, code in op_names.items():
                if name in asm.upper():
                    ops.add(code)
        # Always need HALT and MOVI
        ops.add(self.OP_HALT)
        ops.add(self.OP_MOVI)
        return ops
    
    def _generate_vm(self, needed_ops: Set[int]) -> str:
        """Generate a minimal VM with only needed opcodes."""
        return '''class FluxVM:
    """Minimal bytecode VM."""
    NUM_REGS = 16
    MAX_CYCLES = 1000000

    def __init__(self, bytecode: bytes):
        self.bc = bytecode
        self.gp = [0] * self.NUM_REGS
        self.pc = 0
        self.halted = False
        self.cycles = 0
        self.flags = 0

    def execute(self) -> int:
        while self.pc + 3 < len(self.bc) and not self.halted and self.cycles < self.MAX_CYCLES:
            op = self.bc[self.pc]
            b1, b2, b3 = self.bc[self.pc+1], self.bc[self.pc+2], self.bc[self.pc+3]
            self.pc += 4
            self.cycles += 1

            if op == 0x00: pass  # NOP
            elif op == 0x01: self.gp[b1] = self.gp[b2]  # MOV
            elif op == 0x02 or op == 0x2B:  # MOVI
                imm = b2 | (b3 << 8)
                if imm >= 32768: imm -= 65536
                self.gp[b1] = imm
            elif op == 0x08: self.gp[b1] = self.gp[b2] + self.gp[b3]
            elif op == 0x09: self.gp[b1] = self.gp[b2] - self.gp[b3]
            elif op == 0x0A: self.gp[b1] = self.gp[b2] * self.gp[b3]
            elif op == 0x0B:
                if self.gp[b3] != 0: self.gp[b1] = self.gp[b2] // self.gp[b3]
            elif op == 0x0E: self.gp[b1] += 1
            elif op == 0x0F: self.gp[b1] -= 1
            elif op == 0x2D:  # CMP
                self.flags = 1 if self.gp[b1] == self.gp[b2] else 0
            elif op == 0x06:  # JNZ
                if self.gp[b1] != 0:
                    off = b2 | (b3 << 8)
                    if off >= 32768: off -= 65536
                    self.pc = self.pc + off
            elif op == 0x2E:  # JZ
                if self.gp[b1] == 0:
                    off = b2 | (b3 << 8)
                    if off >= 32768: off -= 65536
                    self.pc = self.pc + off
            elif op == 0x80: self.halted = True
        return self.gp[0]'''
    
    def _generate_assembler(self) -> str:
        """Generate a simple assembler."""
        return '''def assemble(text: str) -> bytes:
    """Assemble FLUX text to bytecode."""
    lines = []
    for line in text.split('\\n'):
        line = line.split('--')[0].split('//')[0].strip()
        if line: lines.append(line)
    
    opcodes = {
        'NOP': 0x00, 'MOV': 0x01, 'MOVI': 0x2B,
        'IADD': 0x08, 'ISUB': 0x09, 'IMUL': 0x0A, 'IDIV': 0x0B,
        'INC': 0x0E, 'DEC': 0x0F,
        'CMP': 0x2D, 'JNZ': 0x06, 'JZ': 0x2E,
        'HALT': 0x80,
    }
    register = lambda r: int(r.upper().replace('R', ''))
    
    bytecode = bytearray()
    for line in lines:
        parts = line.replace(',', ' ').split()
        if not parts: continue
        op = parts[0].upper()
        if op in opcodes:
            bytecode.append(opcodes[op])
            args = parts[1:]
            if op in ('IADD', 'ISUB', 'IMUL', 'IDIV'):
                bytecode.extend([register(args[0]), register(args[1]), register(args[2])])
            elif op in ('MOVI',):
                bytecode.extend([register(args[0]), int(args[1]) & 0xFF, (int(args[1]) >> 8) & 0xFF])
            elif op in ('JNZ', 'JZ'):
                bytecode.extend([register(args[0]), int(args[1]) & 0xFF, (int(args[1]) >> 8) & 0xFF])
            elif op in ('MOV', 'CMP'):
                bytecode.extend([register(args[0]), register(args[1]), 0x00])
            elif op in ('INC', 'DEC'):
                bytecode.extend([register(args[0]), 0x00, 0x00])
            else:
                bytecode.extend([0, 0, 0])
    return bytes(bytecode)'''
    
    def _generate_vocabulary(self, vocab) -> str:
        """Generate vocabulary pattern list."""
        lines = ['VOCAB = [']
        for entry in vocab.entries:
            import json
            name_json = json.dumps(entry.name)
            pattern_json = json.dumps(entry.pattern)
            template_json = json.dumps(getattr(entry, 'bytecode_template', '') or '')
            result_reg = getattr(entry, 'result_reg', 0)
            lines.append(f"    {{'name': {name_json}, 'pattern': {pattern_json}, 'template': {template_json}, 'result_reg': {result_reg}}},")
        lines.append(']')
        return '\n'.join(lines)
    
    def _generate_interpreter(self, vocab, name: str) -> str:
        """Generate the interpreter with run() function."""
        interp_code = (
            "import re\n\n"
            f"class {name}:\n"
            f'    """Auto-generated FLUX interpreter with {len(vocab.entries)} vocabulary entries."""\n'
            "\n"
            "    def __init__(self):\n"
            "        self.patterns = []\n"
            "        for entry in VOCAB:\n"
            "            pat = entry['pattern']\n"
            "            parts = re.split(r'(\\$\\w+)', pat)\n"
            "            regex_parts = []\n"
            "            for p in parts:\n"
            "                if p.startswith('$'):\n"
            "                    gname = p[1:]\n"
            "                    regex_parts.append(f'(?P<{gname}>[\\w.,\\-\\s]+)')\n"
            "                else:\n"
            "                    regex_parts.append(re.escape(p))\n"
            "            compiled = re.compile(''.join(regex_parts), re.IGNORECASE)\n"
            "            self.patterns.append((compiled, entry))\n"
            "\n"
            "    def run(self, text: str) -> dict:\n"
            '        """Execute natural language text through vocabulary."""\n'
            "        for regex, entry in self.patterns:\n"
            "            m = regex.search(text)\n"
            "            if m:\n"
            "                groups = m.groupdict()\n"
            "                asm = entry['template']\n"
            "                for gk, gv in groups.items():\n"
            "                    asm = asm.replace('${' + gk + '}', gv.strip())\n"
            "                try:\n"
            "                    bc = assemble(asm)\n"
            "                    vm = FluxVM(bc)\n"
            "                    result = vm.execute()\n"
            "                    return {'success': True, 'value': result, 'name': entry['name'],\n"
            "                            'cycles': vm.cycles, 'pattern': entry['pattern']}\n"
            "                except Exception as e:\n"
            "                    return {'success': False, 'error': str(e)}\n"
            "        return {'success': False, 'error': 'No pattern match: '+text[:60]}\n"
            "\n"
            f"_interpreter = {name}()\n"
            "\n"
            "def run(text: str) -> dict:\n"
            '    """Run natural language through the FLUX interpreter."""\n'
            "    return _interpreter.run(text)\n"
            "\n"
            "if __name__ == '__main__':\n"
            "    import sys\n"
            "    if len(sys.argv) > 1:\n"
            "        r = run(' '.join(sys.argv[1:]))\n"
            "        print(r)\n"
            "    else:\n"
            "        for test in ['hello', 'compute 3 + 4', 'factorial of 5', 'double 21']:\n"
            "            r = run(test)\n"
            "            s = '✓' if r['success'] else '✗'\n"
            "            v = r.get('value', r.get('error', '?'))\n"
            "            print(f'  {s} {test:25s} → {v}')\n"
        )
        return interp_code
