"""
Vocabulary — user-defined word → bytecode pattern mappings.

Each vocabulary folder contains .fluxvocab files:

    # vocabularies/math/operations.fluxvocab
    
    pattern: "compute $a + $b"
    expand: |
        MOVI R0, ${a}
        MOVI R1, ${b}
        IADD R0, R0, R1
        HALT
    result: R0
    
    pattern: "factorial of $n"
    template: factorial
    args: {"n": "$n"}

Vocabularies are loaded at runtime. Agents can create their own folders
and teach the interpreter new words.
"""

import os
import re
import struct
import json
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field


@dataclass
class VocabEntry:
    """A single vocabulary entry: pattern → bytecode expansion."""
    pattern: str           # regex or template pattern like "compute $a + $b"
    bytecode_template: str # FLUX assembly text with ${var} substitutions
    result_reg: int = 0    # which register holds the result
    name: str = ""         # human-readable name
    description: str = ""  # what this word does
    tags: List[str] = field(default_factory=list)
    
    # Compiled regex (built from pattern)
    _regex: Optional[re.Pattern] = field(default=None, repr=False)
    
    def compile(self):
        """Convert $var patterns to regex capture groups."""
        regex_str = self.pattern
        # Replace $var with named capture groups
        regex_str = re.sub(r'\$(\w+)', r'(?P<\1>\\d+)', regex_str)
        # Allow flexible whitespace and case
        regex_str = regex_str.strip()
        self._regex = re.compile(regex_str, re.IGNORECASE)
    
    def match(self, text: str) -> Optional[Dict[str, str]]:
        """Try to match text against this pattern. Returns captured groups."""
        if self._regex is None:
            self.compile()
        m = self._regex.search(text)
        if m:
            return {k: v for k, v in m.groupdict().items() if v is not None}
        return None


@dataclass 
class BytecodeTemplate:
    """A reusable bytecode template with parameters."""
    name: str
    assembly: str        # FLUX assembly with ${param} placeholders
    result_reg: int = 0
    description: str = ""


class Vocabulary:
    """Manages vocabulary entries loaded from folders."""
    
    def __init__(self):
        self.entries: List[VocabEntry] = []
        self.templates: Dict[str, BytecodeTemplate] = {}
        self._loaded_paths: set = set()
    
    def load_folder(self, path: str):
        """Load all .fluxvocab files from a folder."""
        if path in self._loaded_paths:
            return
        self._loaded_paths.add(path)
        
        if not os.path.isdir(path):
            return
        
        for fname in sorted(os.listdir(path)):
            fpath = os.path.join(path, fname)
            if fname.endswith('.fluxvocab'):
                self._load_vocab_file(fpath)
            elif fname.endswith('.fluxtpl'):
                self._load_template_file(fpath)
    
    def _load_vocab_file(self, path: str):
        """Parse a .fluxvocab file into VocabEntry objects."""
        with open(path) as f:
            content = f.read()
        
        # Split into entries separated by ---
        blocks = re.split(r'^---\s*$', content, flags=re.MULTILINE)
        
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            
            entry = self._parse_entry(block, path)
            if entry:
                self.entries.append(entry)
    
    def _parse_entry(self, block: str, source: str) -> Optional[VocabEntry]:
        """Parse a single vocab entry from text block."""
        lines = block.split('\n')
        pattern = ""
        expand_lines = []
        result_reg = 0
        name = ""
        description = ""
        tags = []
        in_expand = False
        
        for line in lines:
            line = line.strip()
            if line.startswith('pattern:'):
                pattern = line.split(':', 1)[1].strip().strip('"').strip("'")
                in_expand = False
            elif line.startswith('expand:'):
                in_expand = True
                rest = line.split(':', 1)[1].strip()
                if rest and not rest.startswith('|'):
                    expand_lines.append(rest)
            elif line.startswith('result:'):
                r = line.split(':', 1)[1].strip()
                result_reg = int(r.replace('R', '').strip())
                in_expand = False
            elif line.startswith('name:'):
                name = line.split(':', 1)[1].strip()
                in_expand = False
            elif line.startswith('description:'):
                description = line.split(':', 1)[1].strip()
                in_expand = False
            elif line.startswith('tags:'):
                tags_str = line.split(':', 1)[1].strip()
                tags = [t.strip() for t in tags_str.split(',')]
                in_expand = False
            elif in_expand:
                if line.startswith('|'):
                    line = line[1:].strip()
                if line:
                    expand_lines.append(line)
        
        if not pattern or not expand_lines:
            return None
        
        entry = VocabEntry(
            pattern=pattern,
            bytecode_template='\n'.join(expand_lines),
            result_reg=result_reg,
            name=name or pattern[:40],
            description=description,
            tags=tags,
        )
        entry.compile()
        return entry
    
    def _load_template_file(self, path: str):
        """Parse a .fluxtpl template file."""
        with open(path) as f:
            content = f.read()
        
        name = ""
        assembly_lines = []
        result_reg = 0
        description = ""
        in_asm = False
        
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('name:'):
                name = line.split(':', 1)[1].strip()
            elif line.startswith('result:'):
                r = line.split(':', 1)[1].strip()
                result_reg = int(r.replace('R', '').strip())
            elif line.startswith('description:'):
                description = line.split(':', 1)[1].strip()
            elif line.startswith('assembly:'):
                in_asm = True
            elif in_asm and line:
                assembly_lines.append(line)
        
        if name and assembly_lines:
            self.templates[name] = BytecodeTemplate(
                name=name,
                assembly='\n'.join(assembly_lines),
                result_reg=result_reg,
                description=description,
            )
    
    def find_match(self, text: str) -> Optional[Tuple[VocabEntry, Dict[str, str]]]:
        """Find the first vocabulary entry that matches the text."""
        for entry in self.entries:
            groups = entry.match(text)
            if groups is not None:
                return entry, groups
        return None
    
    def list_words(self) -> List[str]:
        """List all loaded vocabulary patterns."""
        return [e.pattern for e in self.entries]
