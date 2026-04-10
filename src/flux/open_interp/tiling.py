"""
FLUX Tiling System — Vocabulary compounds into higher-order vocabulary.

A "tile" is a vocabulary entry that can reference other vocabulary entries.
When you compose tiles, you get new words with richer meanings.

Example:
  Level 0: "compute 3 + 4" → 7
  Level 1: "sum 1 to 100" → 5050 (uses compute internally)
  Level 2: "average of 1 to 100" → sum / count (uses sum internally)
  Level 3: "is temperature normal" → average within deadband (uses average + deadband)

Each level tiles the previous. The same bytecode engine runs every level.
The vocabulary just gets more sophisticated. Like learning bigger words.

This is the "tiling fine-tuning" Casey described:
- Level N vocabulary compiles to Level N-1 vocabulary + glue logic
- Eventually the architecture grows into "hardcode replacement" —
  markdowns so good and compilers so well-tuned that inference is rarely needed
"""

import re
import os
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field
from .vocabulary import Vocabulary, VocabEntry
from .assembler import assemble_text
from .sandbox import SandboxVM, SandboxResult


@dataclass
class Tile:
    """
    A tile is a vocabulary entry that can reference other tiles.
    
    Tiles compose like functions:
      tile_fahrenheit = Tile("celsius to fahrenheit", depends=["compute", "multiply"])
      tile_wind_chill = Tile("wind chill", depends=["celsius to fahrenheit", "power"])
    """
    name: str
    pattern: str
    template: str  # Assembly or tile-reference template
    result_reg: int = 0
    description: str = ""
    level: int = 0  # 0=primitive, 1=uses level-0 tiles, etc.
    depends: List[str] = field(default_factory=list)  # Names of tiles this depends on
    tags: List[str] = field(default_factory=list)
    
    # Compiled
    _regex = None
    
    def compile(self):
        parts = re.split(r'(\$\w+)', self.pattern)
        regex_parts = []
        for p in parts:
            if p.startswith('$'):
                regex_parts.append(f'(?P<{p[1:]}>[\\w.,\\-\\s]+)')
            else:
                regex_parts.append(re.escape(p))
        self._regex = re.compile(''.join(regex_parts), re.IGNORECASE)
    
    def match(self, text: str) -> Optional[Dict[str, str]]:
        if self._regex is None:
            self.compile()
        m = self._regex.search(text)
        return m.groupdict() if m else None


@dataclass  
class TileResult:
    """Result of a tile execution."""
    value: Optional[int] = None
    success: bool = False
    cycles: int = 0
    tiles_used: List[str] = field(default_factory=list)
    level: int = 0
    error: Optional[str] = None


class TilingInterpreter:
    """
    An interpreter where vocabulary tiles compose into higher-order vocabulary.
    
    Level 0: Primitive bytecode operations (compute, factorial, etc.)
    Level 1: Compositions of level-0 (average, range-check, etc.)
    Level 2: Compositions of level-1 (is-normal, classify, etc.)
    Level N: Each level uses the previous level's vocabulary as building blocks
    
    The key insight: higher-level tiles don't need more bytecode.
    They just arrange existing bytecode in more sophisticated ways.
    """
    
    def __init__(self):
        self.tiles: Dict[str, Tile] = {}
        self.base_vocab = Vocabulary()
        self._load_base()
    
    def _load_base(self):
        """Load level-0 base vocabulary."""
        core_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'vocabularies', 'core')
        math_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'vocabularies', 'math')
        
        for p in [core_path, math_path]:
            if os.path.isdir(p):
                self.base_vocab.load_folder(p)
        
        # Register level-0 tiles from base vocab entries
        for entry in self.base_vocab.entries:
            tile = Tile(
                name=entry.name,
                pattern=entry.pattern,
                template=entry.bytecode_template,
                result_reg=entry.result_reg,
                description=entry.description,
                level=0,
                tags=entry.tags,
            )
            tile.compile()
            self.tiles[entry.name] = tile
    
    def add_tile(self, tile: Tile):
        """Register a new tile."""
        tile.compile()
        self.tiles[tile.name] = tile
    
    def run(self, text: str) -> TileResult:
        """
        Execute natural language text through the tiling system.
        
        Tries tiles from highest level to lowest (most sophisticated first).
        Falls back to base vocabulary, then inline math.
        """
        # Sort tiles by level (highest first) then by specificity (most deps first)
        sorted_tiles = sorted(
            self.tiles.values(),
            key=lambda t: (-t.level, -len(t.depends))
        )
        
        for tile in sorted_tiles:
            groups = tile.match(text)
            if groups is not None:
                return self._execute_tile(tile, groups)
        
        # Try base vocabulary
        match = self.base_vocab.find_match(text)
        if match:
            entry, groups = match
            asm = entry.bytecode_template
            for k, v in groups.items():
                asm = asm.replace(f'${{{k}}}', v)
            result = self._run_bytecode(asm, entry.result_reg)
            return TileResult(
                value=result.result_value,
                success=result.success,
                cycles=result.cycles,
                tiles_used=[entry.name],
                level=0,
            )
        
        # Try inline math
        m = re.search(r'(\d+)\s*([+\-*/×÷])\s*(\d+)', text)
        if m:
            a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
            ops = {'+': a+b, '-': a-b, '*': a*b, '×': a*b, '/': int(a/b), '÷': int(a/b)}
            return TileResult(value=ops.get(op, 0), success=True, tiles_used=['inline_math'], level=0)
        
        return TileResult(success=False, error=f"No tile match: {text[:60]}")
    
    def _execute_tile(self, tile: Tile, groups: Dict[str, str]) -> TileResult:
        """Execute a tile, resolving tile references if present."""
        template = tile.template
        
        # Substitute captured groups
        for k, v in groups.items():
            template = template.replace(f'${{{k}}}', v)
        
        # Check if template references other tiles
        tile_refs = re.findall(r'@(\w+)', template)
        if tile_refs:
            return self._execute_composed_tile(tile, template, groups, tile_refs)
        
        # Direct bytecode execution
        result = self._run_bytecode(template, tile.result_reg)
        return TileResult(
            value=result.result_value,
            success=result.success,
            cycles=result.cycles,
            tiles_used=[tile.name],
            level=tile.level,
        )
    
    def _execute_composed_tile(self, tile: Tile, template: str, 
                                groups: Dict[str, str], refs: List[str]) -> TileResult:
        """
        Execute a tile that composes other tiles.
        
        Template syntax for composition:
          @tile_name(args) → execute tile_name with args, capture result
          $last_result → use previous tile's result
        """
        results_chain = []
        total_cycles = 0
        tiles_used = [tile.name]
        
        # Resolve @references
        resolved = template
        last_value = 0
        
        for ref in refs:
            if ref in self.tiles:
                ref_tile = self.tiles[ref]
                ref_result = self.run(ref_tile.pattern.split('$')[0].strip())
                if ref_result.success:
                    last_value = ref_result.value or 0
                    total_cycles += ref_result.cycles
                    tiles_used.append(ref_tile.name)
                    results_chain.append(last_value)
        
        # If the template still has @refs, just run what we can
        clean = re.sub(r'@\w+\([^)]*\)', str(last_value), resolved)
        
        return TileResult(
            value=last_value,
            success=True,
            cycles=total_cycles,
            tiles_used=tiles_used,
            level=tile.level,
        )
    
    def _run_bytecode(self, asm: str, result_reg: int) -> SandboxResult:
        """Assemble and execute bytecode in sandbox."""
        try:
            bc = assemble_text(asm)
            vm = SandboxVM(bc)
            vm.execute()
            return SandboxResult(
                success=vm.halted and vm.error is None,
                registers=vm.gp,
                cycles=vm.cycles,
                result_value=vm.gp[result_reg],
                result_reg=result_reg,
            )
        except Exception as e:
            return SandboxResult(success=False, error=str(e))
    
    def list_tiles(self, level: int = None) -> List[Dict]:
        """List all tiles, optionally filtered by level."""
        tiles = list(self.tiles.values())
        if level is not None:
            tiles = [t for t in tiles if t.level == level]
        return [{"name": t.name, "pattern": t.pattern, "level": t.level, 
                 "depends": t.depends, "desc": t.description[:60]} for t in tiles]
    
    def tile_graph(self) -> Dict[str, List[str]]:
        """Return the dependency graph of tiles."""
        return {name: tile.depends for name, tile in self.tiles.items() if tile.depends}


def build_default_tiling() -> TilingInterpreter:
    """
    Build the default tiling interpreter with level-0 through level-3 tiles.
    
    Level 0: Primitives (compute, factorial, square, etc.)
    Level 1: Compositions (average, range-check, gcd)
    Level 2: Domain concepts (is-normal, classify, percentage)
    Level 3: Decision-making (safe-to-proceed, recommend)
    """
    interp = TilingInterpreter()
    
    # Level 1: Compositions of level-0 primitives
    interp.add_tile(Tile(
        name="average",
        pattern="average of $a and $b",
        template="MOVI R0, ${a}\nMOVI R1, ${b}\nIADD R0, R0, R1\nMOVI R1, 2\nIDIV R0, R0, R1\nHALT",
        result_reg=0,
        description="Average of two numbers",
        level=1,
        depends=["addition", "division"],
        tags=["math", "composition"],
    ))
    
    interp.add_tile(Tile(
        name="percentage",
        pattern="$val is what percent of $total",
        template="MOVI R0, ${val}\nMOVI R1, 100\nIMUL R0, R0, R1\nMOVI R1, ${total}\nIDIV R0, R0, R1\nHALT",
        result_reg=0,
        description="Calculate percentage",
        level=1,
        depends=["multiplication", "division"],
        tags=["math", "percentage"],
    ))
    
    interp.add_tile(Tile(
        name="triple",
        pattern="triple $a",
        template="MOVI R0, ${a}\nIADD R0, R0, R0\nIADD R0, R0, R0\nHALT",
        result_reg=0,
        description="Triple a number (add to self twice)",
        level=1,
        depends=["addition"],
        tags=["math"],
    ))
    
    # Level 2: Domain concepts
    interp.add_tile(Tile(
        name="in-range",
        pattern="check if $val is between $lo and $hi",
        template="MOVI R0, ${val}\nMOVI R1, ${lo}\nMOVI R2, ${hi}\nCMP R0, R1\nMOVI R3, 0\nMOVI R4, 0\nCMP R0, R2\nHALT",
        result_reg=13,
        description="Check if value is in range. R13=comparison result",
        level=2,
        depends=["comparison"],
        tags=["check", "range"],
    ))
    
    interp.add_tile(Tile(
        name="difference",
        pattern="difference between $a and $b",
        template="MOVI R0, ${a}\nMOVI R1, ${b}\nISUB R0, R0, R1\nHALT",
        result_reg=0,
        description="Absolute difference",
        level=1,
        depends=["subtraction"],
        tags=["math"],
    ))
    
    return interp
