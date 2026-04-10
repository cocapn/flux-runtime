#!/usr/bin/env python3
"""FLUX Analyze — Reverse-engineer existing code into FLUX concepts.

Usage:
    python tools/flux_analyze.py /path/to/file.py
    python tools/flux_analyze.py /path/to/file.py --json
    python tools/flux_analyze.py /path/to/file.py --graph
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# ═══════════════════════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class FuncInfo:
    """Detailed analysis of one function."""
    name: str
    qualname: str  # Class.method or module.function
    lineno: int
    end_lineno: int = 0
    is_async: bool = False
    is_method: bool = False
    params: int = 0
    defaults: int = 0
    returns_annotation: str = ""
    decorators: List[str] = field(default_factory=list)

    # Complexity metrics
    cyclomatic: int = 1
    nesting_depth: int = 0
    branches: int = 0
    loops: int = 0
    calls: int = 0
    try_except: int = 0
    comprehensions: int = 0
    lambdas: int = 0
    loc: int = 0

    # Calls made inside this function
    calls_made: List[str] = field(default_factory=list)

    # Callers (populated after full analysis)
    callers: List[str] = field(default_factory=list)

    # Heat & tile mapping
    heat_level: str = ""
    recommended_tile: str = ""
    recommended_language: str = ""

    # Pattern tags
    pattern_tags: List[str] = field(default_factory=list)


@dataclass
class ClassInfo:
    name: str
    lineno: int
    bases: List[str] = field(default_factory=list)
    methods: List[FuncInfo] = field(default_factory=list)
    class_vars: List[str] = field(default_factory=list)
    decorators: List[str] = field(default_factory=list)


@dataclass
class ImportInfo:
    module: str
    names: List[str] = field(default_factory=list)
    is_from: bool = False
    lineno: int = 0
    alias: str = ""


@dataclass
class GlobalVarInfo:
    name: str
    lineno: int
    type_hint: str = ""


@dataclass
class FileAnalysis:
    filepath: str
    module_name: str
    source_hash: str = ""

    # Structural elements
    functions: List[FuncInfo] = field(default_factory=list)
    classes: List[ClassInfo] = field(default_factory=list)
    imports: List[ImportInfo] = field(default_factory=list)
    globals: List[GlobalVarInfo] = field(default_factory=list)

    # Line counts
    total_lines: int = 0
    code_lines: int = 0
    comment_lines: int = 0
    blank_lines: int = 0
    docstring_lines: int = 0

    # Aggregates
    total_functions: int = 0
    total_methods: int = 0
    avg_cyclomatic: float = 0.0
    max_cyclomatic: int = 0

    # Call graph adjacency
    call_graph: Dict[str, List[str]] = field(default_factory=dict)

    # Dependency graph (module-level imports)
    dependencies: Set[str] = field(default_factory=set)

    # Tile mapping
    tile_distribution: Dict[str, int] = field(default_factory=dict)

    # Statistics
    estimated_tiles: int = 0
    hot_paths: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# AST helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _get_decorator_name(dec: ast.expr) -> str:
    """Extract a readable name from a decorator node."""
    if isinstance(dec, ast.Name):
        return dec.id
    elif isinstance(dec, ast.Attribute):
        parts: list[str] = []
        node = dec
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        return ".".join(reversed(parts))
    elif isinstance(dec, ast.Call):
        inner = _get_decorator_name(dec.func)
        return f"{inner}()"
    return "?"


def _get_annotation_str(node: Optional[ast.expr]) -> str:
    """Get a string representation of a type annotation."""
    if node is None:
        return ""
    return ast.dump(node) if hasattr(ast, "unparse") else ast.dump(node)


def _extract_calls(node: ast.AST) -> List[str]:
    """Extract all function/method call names from an AST subtree."""
    names: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name):
                names.append(child.func.id)
            elif isinstance(child.func, ast.Attribute):
                names.append(ast.dump(child.func).split("'")[1] if "'" in ast.dump(child.func) else "?attr")
    return names


def _cyclomatic_complexity(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Compute McCabe cyclomatic complexity."""
    complexity = 1  # base
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.IfExp)):
            complexity += 1
        elif isinstance(child, (ast.For, ast.While, ast.AsyncFor)):
            complexity += 1
        elif isinstance(child, ast.ExceptHandler):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            # and/or add to complexity
            complexity += len(child.values) - 1
        elif isinstance(child, ast.comprehension):
            complexity += 1  # each 'for ... if' in comprehension
    return complexity


def _max_nesting(node: ast.AST, depth: int = 0) -> int:
    """Compute maximum nesting depth."""
    nesting_blocks = (ast.If, ast.For, ast.While, ast.AsyncFor, ast.With, ast.AsyncWith, ast.Try, ast.ExceptHandler)
    max_depth = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, nesting_blocks):
            d = _max_nesting(child, depth + 1)
            if d > max_depth:
                max_depth = d
        else:
            d = _max_nesting(child, depth)
            if d > max_depth:
                max_depth = d
    return max_depth


def _classify_heat(cyclomatic: int, nesting: int, calls: int) -> str:
    """Classify function heat level."""
    score = cyclomatic + nesting + calls // 3
    if score <= 3:
        return "COOL"
    elif score <= 8:
        return "WARM"
    elif score <= 15:
        return "HOT"
    else:
        return "INFERNO"


def _recommend_tile(node: ast.FunctionDef | ast.AsyncFunctionDef, info: FuncInfo) -> str:
    """Recommend FLUX tile pattern."""
    tags: list[str] = []

    if info.is_async:
        tags.append("AgentTile")

    has_for = any(isinstance(c, ast.For) for c in ast.walk(node))
    has_async_for = any(isinstance(c, ast.AsyncFor) for c in ast.walk(node))
    has_if = any(isinstance(c, ast.If) for c in ast.walk(node))
    has_try = any(isinstance(c, ast.Try) for c in ast.walk(node))
    has_call = any(isinstance(c, ast.Call) for c in ast.walk(node))
    has_listcomp = any(isinstance(c, ast.ListComp) for c in ast.walk(node))
    has_dictcomp = any(isinstance(c, ast.DictComp) for c in ast.walk(node))
    has_lambda = any(isinstance(c, ast.Lambda) for c in ast.walk(node))
    has_yield = any(isinstance(c, ast.Yield) for c in ast.walk(node))
    has_return = any(isinstance(c, ast.Return) and c.value is not None for c in ast.walk(node))

    if has_async_for or (info.is_async and has_for):
        if "AgentTile" not in tags:
            tags.append("AgentTile")
    if has_for and has_if:
        tags.append("FilterTile")
    if has_for and not has_if:
        tags.append("MapTile")
    if has_try:
        tags.append("ErrorTile")
    if has_listcomp or has_dictcomp:
        tags.append("TransformTile")
    if has_lambda:
        tags.append("LambdaTile")
    if has_yield:
        tags.append("StreamTile")
    if not tags:
        if has_call:
            tags.append("ChainTile")
        elif has_return:
            tags.append("ComputeTile")
        else:
            tags.append("ComputeTile")

    info.pattern_tags = tags
    return tags[0]


def _recommend_language(heat: str) -> str:
    """Map heat to language tier."""
    return {
        "COOL": "Python",
        "WARM": "FIR",
        "HOT": "FIR+ASM",
        "INFERNO": "ASM/C",
    }.get(heat, "Python")


# ═══════════════════════════════════════════════════════════════════════════════
# Core analysis
# ═══════════════════════════════════════════════════════════════════════════════


def analyze_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    class_name: str = "",
) -> FuncInfo:
    """Perform deep analysis of a single function/method."""
    is_async = isinstance(node, ast.AsyncFunctionDef)
    end = getattr(node, "end_lineno", node.lineno) or node.lineno
    loc = max(end - node.lineno + 1, 1)

    decorators = [_get_decorator_name(d) for d in node.decorator_list]

    # Params
    args = node.args
    params = len(args.args) + len(args.kwonlyargs) + len(args.posonlyargs)
    params += 1 if args.vararg else 0
    params += 1 if args.kwarg else 0
    defaults = len(args.defaults) + len(args.kw_defaults)

    # Complexity
    cyc = _cyclomatic_complexity(node)
    nesting = _max_nesting(node)
    calls_made = _extract_calls(node)

    # Count specific constructs
    branches = sum(1 for c in ast.walk(node) if isinstance(c, (ast.If, ast.IfExp)))
    loops = sum(1 for c in ast.walk(node) if isinstance(c, (ast.For, ast.While, ast.AsyncFor)))
    calls = sum(1 for c in ast.walk(node) if isinstance(c, ast.Call))
    try_except = sum(1 for c in ast.walk(node) if isinstance(c, ast.Try))
    comprehensions = sum(1 for c in ast.walk(node) if isinstance(c, (ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp)))
    lambdas = sum(1 for c in ast.walk(node) if isinstance(c, ast.Lambda))

    qualname = f"{class_name}.{node.name}" if class_name else node.name

    info = FuncInfo(
        name=node.name,
        qualname=qualname,
        lineno=node.lineno,
        end_lineno=end,
        is_async=is_async,
        is_method=bool(class_name),
        params=params,
        defaults=defaults,
        decorators=decorators,
        cyclomatic=cyc,
        nesting_depth=nesting,
        branches=branches,
        loops=loops,
        calls=calls,
        try_except=try_except,
        comprehensions=comprehensions,
        lambdas=lambdas,
        loc=loc,
        calls_made=calls_made,
    )

    info.heat_level = _classify_heat(cyc, nesting, calls)
    info.recommended_tile = _recommend_tile(node, info)
    info.recommended_language = _recommend_language(info.heat_level)

    return info


def analyze_file(filepath: str) -> FileAnalysis:
    """Perform deep AST analysis of a Python file."""
    path = Path(filepath)
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError, OSError) as exc:
        return FileAnalysis(filepath=filepath, module_name=path.stem)

    module_name = path.stem
    if path.name == "__init__.py":
        module_name = path.parent.name

    # Line counts
    lines = source.splitlines()
    total_lines = len(lines)
    blank_lines = sum(1 for l in lines if not l.strip())
    comment_lines = sum(1 for l in lines if l.strip().startswith("#") and not l.strip().startswith("#!"))
    code_lines = total_lines - blank_lines - comment_lines

    # Count docstrings
    docstring_lines = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            ds = ast.get_docstring(node)
            if ds:
                docstring_lines += ds.count("\n") + 1

    # Imports
    imports: List[ImportInfo] = []
    deps: Set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(ImportInfo(module=alias.name, names=[alias.name], is_from=False, lineno=node.lineno, alias=alias.asname or ""))
                top = alias.name.split(".")[0]
                if top != module_name:
                    deps.add(top)
        elif isinstance(node, ast.ImportFrom):
            names = [a.name for a in node.names]
            mod = node.module or ""
            imports.append(ImportInfo(module=mod, names=names, is_from=True, lineno=node.lineno))
            if mod:
                top = mod.split(".")[0]
                if top != module_name:
                    deps.add(top)
            elif node.level and node.level > 0:
                deps.add(f".{'.' * (node.level - 1)}")

    # Globals
    globals_: List[GlobalVarInfo] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    globals_.append(GlobalVarInfo(name=target.id, lineno=node.lineno))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            globals_.append(GlobalVarInfo(name=node.target.id, lineno=node.lineno, type_hint=_get_annotation_str(node.annotation)))

    # Functions (top-level)
    functions: List[FuncInfo] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(analyze_function(node))

    # Classes
    classes: List[ClassInfo] = []
    class_methods: List[FuncInfo] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            bases = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    bases.append(base.id)
                elif isinstance(base, ast.Attribute):
                    parts: list[str] = []
                    n = base
                    while isinstance(n, ast.Attribute):
                        parts.append(n.attr)
                        n = n.value
                    if isinstance(n, ast.Name):
                        parts.append(n.id)
                    bases.append(".".join(reversed(parts)))

            decs = [_get_decorator_name(d) for d in node.decorator_list]
            class_vars: list[str] = []
            methods: list[FuncInfo] = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(analyze_function(item, class_name=node.name))
                elif isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            class_vars.append(target.id)
                elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    class_vars.append(item.target.id)

            classes.append(ClassInfo(
                name=node.name,
                lineno=node.lineno,
                bases=bases,
                methods=methods,
                class_vars=class_vars,
                decorators=decs,
            ))
            class_methods.extend(methods)

    all_functions = functions + class_methods
    total_methods = len(class_methods)

    # Cyclomatic stats
    if all_functions:
        avg_cyc = sum(f.cyclomatic for f in all_functions) / len(all_functions)
        max_cyc = max(f.cyclomatic for f in all_functions)
    else:
        avg_cyc = 0.0
        max_cyc = 0

    # Build call graph
    call_graph: Dict[str, List[str]] = {}
    func_names = {f.name for f in all_functions}
    for f in all_functions:
        # Resolve calls to known functions
        resolved = []
        for call in f.calls_made:
            if call in func_names or call in {c.qualname for c in all_functions}:
                resolved.append(call)
        call_graph[f.qualname] = resolved

    # Populate callers
    callers_map: Dict[str, List[str]] = defaultdict(list)
    for caller, callees in call_graph.items():
        for callee in callees:
            callers_map[callee].append(caller)
    for f in all_functions:
        f.callers = callers_map.get(f.name, callers_map.get(f.qualname, []))

    # Tile distribution
    tile_dist: Dict[str, int] = defaultdict(int)
    for f in all_functions:
        tile_dist[f.recommended_tile] += 1

    # Hot paths (most called functions)
    call_counts: Dict[str, int] = defaultdict(int)
    for callees in call_graph.values():
        for callee in callees:
            call_counts[callee] += 1
    hot_paths = sorted(call_counts, key=call_counts.get, reverse=True)[:10]

    # Estimated tiles
    est_tiles = sum(max(1, f.cyclomatic // 2) for f in all_functions)

    return FileAnalysis(
        filepath=filepath,
        module_name=module_name,
        functions=functions,
        classes=classes,
        imports=imports,
        globals=globals_,
        total_lines=total_lines,
        code_lines=code_lines,
        comment_lines=comment_lines,
        blank_lines=blank_lines,
        docstring_lines=docstring_lines,
        total_functions=len(all_functions),
        total_methods=total_methods,
        avg_cyclomatic=round(avg_cyc, 1),
        max_cyclomatic=max_cyc,
        call_graph=call_graph,
        dependencies=deps,
        tile_distribution=dict(tile_dist),
        estimated_tiles=est_tiles,
        hot_paths=hot_paths,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Output formatters
# ═══════════════════════════════════════════════════════════════════════════════


def _box(title: str, body: str, width: int = 82) -> str:
    """Wrap text in a box-drawing frame."""
    top = "╔" + "═" * (width - 2) + "╗"
    bot = "╚" + "═" * (width - 2) + "╝"
    sep = "╠" + "═" * (width - 2) + "╣"
    title_line = "║ " + title.center(width - 4) + " ║"
    inner: list[str] = []
    for line in body.splitlines():
        if not line:
            inner.append("║" + " " * (width - 2) + "║")
        elif len(line) <= width - 4:
            inner.append("║ " + line.ljust(width - 4) + " ║")
        else:
            words = line.split()
            current = ""
            for word in words:
                if len(current) + len(word) + 1 > width - 4:
                    inner.append("║ " + current.ljust(width - 4) + " ║")
                    current = word
                else:
                    current = (current + " " + word) if current else word
            if current:
                inner.append("║ " + current.ljust(width - 4) + " ║")
    return "\n".join([top, title_line, sep] + inner + [bot])


def _heat_bar(heat: str, width: int = 12) -> str:
    """Return a colored bar for heat level."""
    mapping = {
        "COOL":    ("░" * width, "\033[36m"),
        "WARM":    ("▒" * (width // 2) + "░" * (width // 2), "\033[33m"),
        "HOT":     ("▓" * (width * 2 // 3) + "▒" * (width // 3), "\033[31m"),
        "INFERNO": ("█" * width, "\033[35m"),
    }
    bar, color = mapping.get(heat, ("░" * width, "\033[0m"))
    reset = "\033[0m"
    return f"{color}{bar}{reset}"


def format_table(analysis: FileAnalysis) -> str:
    """Format analysis as a beautiful terminal table."""
    sections: list[str] = []

    # ── Header ─────────────────────────────────────────────────────────────
    sections.append(_box(
        "FLUX ANALYZE — Code Intelligence Report",
        f"File      : {analysis.filepath}\n"
        f"Module    : {analysis.module_name}\n"
        f"Functions : {analysis.total_functions} ({analysis.total_methods} methods)\n"
        f"Classes   : {len(analysis.classes)}\n"
        f"Imports   : {len(analysis.imports)}\n"
        f"Globals   : {len(analysis.globals)}",
    ))

    # ── Line Statistics ────────────────────────────────────────────────────
    total = analysis.total_lines or 1
    sections.append(_box(
        "LINE STATISTICS",
        f"{'Total lines':.<25} {analysis.total_lines:>6}\n"
        f"{'Code lines':.<25} {analysis.code_lines:>6}  ({analysis.code_lines * 100 // total}%)\n"
        f"{'Comment lines':.<25} {analysis.comment_lines:>6}  ({analysis.comment_lines * 100 // total}%)\n"
        f"{'Blank lines':.<25} {analysis.blank_lines:>6}  ({analysis.blank_lines * 100 // total}%)\n"
        f"{'Docstring lines':.<25} {analysis.docstring_lines:>6}\n"
        f"{'Avg cyclomatic':.<25} {analysis.avg_cyclomatic:>6}\n"
        f"{'Max cyclomatic':.<25} {analysis.max_cyclomatic:>6}\n"
        f"{'Estimated tiles':.<25} {analysis.estimated_tiles:>6}",
    ))

    # ── Imports ────────────────────────────────────────────────────────────
    if analysis.imports:
        imp_lines = [f"{'Module':.<30} {'Names':<25} {'Line':>5}"]
        imp_lines.append("─" * 62)
        for imp in analysis.imports:
            names_str = ", ".join(imp.names[:3])
            if len(imp.names) > 3:
                names_str += f" +{len(imp.names) - 3}"
            prefix = "from " if imp.is_from else "import"
            mod_str = f"{prefix} {imp.module}" if imp.is_from else imp.names[0] if imp.names else ""
            imp_lines.append(f"{mod_str:<30} {names_str:<25} {imp.lineno:>5}")
        sections.append(_box("IMPORTS & DEPENDENCIES", "\n".join(imp_lines)))

    # ── Classes ────────────────────────────────────────────────────────────
    for cls in analysis.classes:
        lines = []
        bases = f"({', '.join(cls.bases)})" if cls.bases else ""
        decs = f"  decorators: [{', '.join(cls.decorators)}]" if cls.decorators else ""
        lines.append(f"class {cls.name}{bases}:  # line {cls.lineno}{decs}")
        if cls.class_vars:
            lines.append(f"  class vars: {', '.join(cls.class_vars)}")
        lines.append("")
        m_hdr = f"  {'Method':<28} {'Cyc':>4} {'Nest':>5} {'Br':>3} {'Lp':>3} {'Ca':>3} {'LOC':>4} {'Heat':>8} {'Tile':<15}"
        m_sep = "  " + "─" * 82
        lines.append(m_hdr)
        lines.append(m_sep)
        for m in cls.methods:
            prefix = "async " if m.is_async else "      "
            lines.append(
                f"  {prefix}{m.name:<23} {m.cyclomatic:>4} {m.nesting_depth:>5} "
                f"{m.branches:>3} {m.loops:>3} {m.calls:>3} {m.loc:>4} "
                f"{m.heat_level:>8} {m.recommended_tile:<15}"
            )
        sections.append(_box(f"CLASS: {cls.name}", "\n".join(lines)))

    # ── Functions ──────────────────────────────────────────────────────────
    top_funcs = analysis.functions
    if top_funcs:
        lines = []
        f_hdr = f"  {'Function':<25} {'Params':>6} {'Cyc':>4} {'Nest':>5} {'Br':>3} {'Lp':>3} {'Ca':>3} {'Try':>3} {'LOC':>4} {'Heat':>8} {'Tile':<15} {'Lang':<8}"
        f_sep = "  " + "─" * 95
        lines.append(f_hdr)
        lines.append(f_sep)
        for f in top_funcs:
            prefix = "async " if f.is_async else "      "
            lines.append(
                f"  {prefix}{f.name:<20} {f.params:>6} {f.cyclomatic:>4} {f.nesting_depth:>5} "
                f"{f.branches:>3} {f.loops:>3} {f.calls:>3} {f.try_except:>3} {f.loc:>4} "
                f"{f.heat_level:>8} {f.recommended_tile:<15} {f.recommended_language:<8}"
            )
        sections.append(_box("TOP-LEVEL FUNCTIONS", "\n".join(lines)))

    # ── All Functions/Methods Combined ─────────────────────────────────────
    all_funcs = analysis.functions + [m for c in analysis.classes for m in c.methods]
    if all_funcs:
        lines = []
        f_hdr = f"  {'QualifiedName':<35} {'Type':>7} {'Cyc':>4} {'Nest':>5} {'LOC':>4} {'Heat':>8} {'Tile':<15}"
        f_sep = "  " + "─" * 85
        lines.append(f_hdr)
        lines.append(f_sep)
        for f in sorted(all_funcs, key=lambda x: x.cyclomatic, reverse=True):
            ftype = "method" if f.is_method else "func"
            if f.is_async:
                ftype = "a" + ftype
            lines.append(
                f"  {f.qualname:<35} {ftype:>7} {f.cyclomatic:>4} {f.nesting_depth:>5} "
                f"{f.loc:>4} {f.heat_level:>8} {f.recommended_tile:<15}"
            )
        sections.append(_box("ALL FUNCTIONS (sorted by complexity)", "\n".join(lines)))

    # ── Tile Distribution ──────────────────────────────────────────────────
    if analysis.tile_distribution:
        total_tiles = sum(analysis.tile_distribution.values())
        lines = []
        for tile, count in sorted(analysis.tile_distribution.items(), key=lambda x: -x[1]):
            pct = count / max(total_tiles, 1) * 100
            bar_len = int(pct / 5)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            lines.append(f"  {tile:<20} {count:>3}  ({pct:>5.1f}%)  {bar}")
        sections.append(_box("TILE PATTERN DISTRIBUTION", "\n".join(lines)))

    # ── Call Graph ─────────────────────────────────────────────────────────
    if analysis.call_graph:
        lines = []
        for caller, callees in sorted(analysis.call_graph.items()):
            if callees:
                targets = ", ".join(callees[:5])
                if len(callees) > 5:
                    targets += f" +{len(callees) - 5}"
                lines.append(f"  {caller:<30} → {targets}")
        if lines:
            sections.append(_box("CALL GRAPH", "\n".join(lines)))

    # ── Hot Paths ──────────────────────────────────────────────────────────
    if analysis.hot_paths:
        call_counts: Dict[str, int] = defaultdict(int)
        for callees in analysis.call_graph.values():
            for callee in callees:
                call_counts[callee] += 1
        lines = []
        for name in analysis.hot_paths:
            count = call_counts[name]
            bar = "▓" * min(count * 3, 40)
            lines.append(f"  {name:<30} called {count:>3}x  {bar}")
        sections.append(_box("HOT PATHS (most called)", "\n".join(lines)))

    # ── Dependencies ───────────────────────────────────────────────────────
    if analysis.dependencies:
        deps = sorted(analysis.dependencies)
        dep_str = ", ".join(deps)
        sections.append(_box("EXTERNAL DEPENDENCIES", dep_str))

    return "\n\n".join(sections)


def format_json(analysis: FileAnalysis) -> str:
    """Format analysis as JSON."""
    all_funcs = analysis.functions + [m for c in analysis.classes for m in c.methods]
    data = {
        "file": analysis.filepath,
        "module": analysis.module_name,
        "statistics": {
            "total_lines": analysis.total_lines,
            "code_lines": analysis.code_lines,
            "comment_lines": analysis.comment_lines,
            "blank_lines": analysis.blank_lines,
            "docstring_lines": analysis.docstring_lines,
            "total_functions": analysis.total_functions,
            "total_methods": analysis.total_methods,
            "total_classes": len(analysis.classes),
            "total_imports": len(analysis.imports),
            "avg_cyclomatic": analysis.avg_cyclomatic,
            "max_cyclomatic": analysis.max_cyclomatic,
            "estimated_tiles": analysis.estimated_tiles,
        },
        "functions": [
            {
                "name": f.name,
                "qualname": f.qualname,
                "is_async": f.is_async,
                "is_method": f.is_method,
                "params": f.params,
                "lineno": f.lineno,
                "end_lineno": f.end_lineno,
                "loc": f.loc,
                "cyclomatic": f.cyclomatic,
                "nesting_depth": f.nesting_depth,
                "branches": f.branches,
                "loops": f.loops,
                "calls": f.calls,
                "try_except": f.try_except,
                "comprehensions": f.comprehensions,
                "lambdas": f.lambdas,
                "decorators": f.decorators,
                "calls_made": f.calls_made,
                "callers": f.callers,
                "heat_level": f.heat_level,
                "recommended_tile": f.recommended_tile,
                "recommended_language": f.recommended_language,
                "pattern_tags": f.pattern_tags,
            }
            for f in all_funcs
        ],
        "classes": [
            {
                "name": c.name,
                "lineno": c.lineno,
                "bases": c.bases,
                "methods": [m.name for m in c.methods],
                "class_vars": c.class_vars,
                "decorators": c.decorators,
            }
            for c in analysis.classes
        ],
        "imports": [
            {
                "module": i.module,
                "names": i.names,
                "is_from": i.is_from,
                "lineno": i.lineno,
            }
            for i in analysis.imports
        ],
        "globals": [g.name for g in analysis.globals],
        "call_graph": analysis.call_graph,
        "dependencies": sorted(analysis.dependencies),
        "tile_distribution": analysis.tile_distribution,
        "hot_paths": analysis.hot_paths,
    }
    return json.dumps(data, indent=2)


def format_dot(analysis: FileAnalysis) -> str:
    """Format analysis as a DOT graph."""
    lines: list[str] = []
    lines.append(f'digraph "{analysis.module_name}" {{')
    lines.append('  rankdir=LR;')
    lines.append('  node [shape=box, style=filled, fontname="monospace"];')
    lines.append('')

    # Functions as nodes
    all_funcs = analysis.functions + [m for c in analysis.classes for m in c.methods]
    for f in all_funcs:
        heat_color = {
            "COOL": "lightblue",
            "WARM": "lightyellow",
            "HOT": "lightsalmon",
            "INFERNO": "red",
        }.get(f.heat_level, "white")
        lines.append(f'  "{f.qualname}" [fillcolor={heat_color}, tooltip="{f.recommended_tile}"];')

    lines.append('')

    # Call graph edges
    for caller, callees in analysis.call_graph.items():
        for callee in callees:
            lines.append(f'  "{caller}" -> "{callee}";')

    # Dependencies
    lines.append('')
    lines.append('  // External dependencies')
    for dep in sorted(analysis.dependencies):
        lines.append(f'  "imports" -> "{dep}" [style=dashed, color=gray];')

    lines.append('}')
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="flux_analyze",
        description="Reverse-engineer existing Python code into FLUX concepts.",
    )
    parser.add_argument("file", help="Path to a Python file to analyze")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--graph", action="store_true", help="Output as DOT graph")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show additional details")
    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print(f"[ERROR] File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    if not args.file.endswith(".py"):
        print(f"[WARN] {args.file} is not a .py file; attempting parse anyway.", file=sys.stderr)

    analysis = analyze_file(args.file)

    if args.json:
        print(format_json(analysis))
    elif args.graph:
        print(format_dot(analysis))
    else:
        print(format_table(analysis))


if __name__ == "__main__":
    main()
