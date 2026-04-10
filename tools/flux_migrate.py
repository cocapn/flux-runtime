#!/usr/bin/env python3
"""FLUX Migrate — Convert existing Python projects to FLUX modules.

Usage:
    python tools/flux_migrate.py /path/to/project --output flux_output/
    python tools/flux_migrate.py /path/to/project --dry-run  # just show plan
    python tools/flux_migrate.py /path/to/module.py  # single file
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ═══════════════════════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class FuncInfo:
    """Complexity profile of a single function."""
    name: str
    lineno: int
    end_lineno: int = 0
    is_async: bool = False
    is_method: bool = False
    params: int = 0
    branches: int = 0
    loops: int = 0
    calls: int = 0
    nesting_depth: int = 0
    decorators: List[str] = field(default_factory=list)
    loc: int = 0
    heat_level: str = ""
    language_tier: str = ""
    recommended_tile: str = ""


@dataclass
class ClassInfo:
    """Profile of a single class."""
    name: str
    lineno: int
    methods: List[FuncInfo] = field(default_factory=list)
    bases: List[str] = field(default_factory=list)


@dataclass
class ImportInfo:
    """A single import statement."""
    module: str
    names: List[str] = field(default_factory=list)
    is_from: bool = False
    lineno: int = 0


@dataclass
class FileInfo:
    """Complete analysis of a single Python file."""
    filepath: str
    module_name: str
    functions: List[FuncInfo] = field(default_factory=list)
    classes: List[ClassInfo] = field(default_factory=list)
    imports: List[ImportInfo] = field(default_factory=list)
    total_lines: int = 0
    total_loc: int = 0  # non-blank, non-comment
    avg_complexity: float = 0.0
    hierarchy_path: str = ""
    estimated_tiles: int = 0


@dataclass
class ProjectInfo:
    """Complete analysis of a project."""
    root: str
    files: List[FileInfo] = field(default_factory=list)
    total_files: int = 0
    total_functions: int = 0
    total_classes: int = 0
    total_lines: int = 0
    avg_complexity: float = 0.0
    total_tiles: int = 0


# ═══════════════════════════════════════════════════════════════════════════════
# 8-Level Module Hierarchy
# ═══════════════════════════════════════════════════════════════════════════════

HIERARCHY_LEVELS = [
    "TRAIN",       # Level 0 — root / top-level package
    "CARRIAGE",    # Level 1 — major subsystem
    "COACH",       # Level 2 — subsystem subdivision
    "COMPARTMENT", # Level 3 — module group
    "SHELF",       # Level 4 — individual module
    "PORTMANTEAU", # Level 5 — submodule
    "LUGGAGE",     # Level 6 — nested component
    "POCKET",      # Level 7 — leaf element
]


def map_to_hierarchy(path: str, base: str) -> str:
    """Map a file path to the 8-level FLUX hierarchy.

    The path is relative to the project base. Each directory component
    maps to a hierarchy level. Files beyond level 7 fold into POCKET.
    """
    rel = os.path.relpath(str(path), str(base))
    parts: list[str] = []
    if rel.endswith(".py"):
        rel = rel[:-3]
    elif rel.endswith(os.sep):
        rel = rel.rstrip(os.sep)
    components = [p for p in rel.split(os.sep) if p and p != "__init__"]
    for i, comp in enumerate(components):
        level = HIERARCHY_LEVELS[min(i, len(HIERARCHY_LEVELS) - 1)]
        parts.append(f"{level}/{comp}")
    return "/".join(parts) if parts else HIERARCHY_LEVELS[0] + "/root"


# ═══════════════════════════════════════════════════════════════════════════════
# Complexity analysis
# ═══════════════════════════════════════════════════════════════════════════════


def _count_node_complexity(node: ast.AST) -> Tuple[int, int, int, int]:
    """Walk an AST subtree and return (branches, loops, calls, max_nesting)."""
    branches = 0
    loops = 0
    calls = 0
    max_nesting = 0

    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.IfExp)):
            branches += 1
        elif isinstance(child, (ast.For, ast.While, ast.AsyncFor)):
            loops += 1
        elif isinstance(child, ast.Call):
            calls += 1
        elif isinstance(child, ast.Try):
            branches += 1

    # Measure nesting depth via recursive descent
    def _nest_depth(n: ast.AST, depth: int = 0) -> int:
        nonlocal max_nesting
        if depth > max_nesting:
            max_nesting = depth
        for child in ast.iter_child_nodes(n):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.AsyncFor, ast.With, ast.Try)):
                _nest_depth(child, depth + 1)
            else:
                _nest_depth(child, depth)

    _nest_depth(node)
    return branches, loops, calls, max_nesting


def analyze_function(node: ast.FunctionDef | ast.AsyncFunctionDef, *,
                     is_method: bool = False) -> FuncInfo:
    """Analyze function complexity and return a FuncInfo."""
    branches, loops, calls, nesting = _count_node_complexity(node)
    is_async = isinstance(node, ast.AsyncFunctionDef)
    end = getattr(node, "end_lineno", node.lineno) or node.lineno
    loc = max(end - node.lineno + 1, 1)

    decorators = []
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name):
            decorators.append(dec.id)
        elif isinstance(dec, ast.Attribute):
            decorators.append(ast.dump(dec).split("'")[1] if "'" in ast.dump(dec) else "?")
        elif isinstance(dec, ast.Call):
            if isinstance(dec.func, ast.Name):
                decorators.append(dec.func.id + "()")
            else:
                decorators.append("...()")

    info = FuncInfo(
        name=node.name,
        lineno=node.lineno,
        end_lineno=end,
        is_async=is_async,
        is_method=is_method,
        params=len(node.args.args) + len(node.args.kwonlyargs) + (1 if node.args.vararg else 0) + (1 if node.args.kwarg else 0),
        branches=branches,
        loops=loops,
        calls=calls,
        nesting_depth=nesting,
        decorators=decorators,
        loc=loc,
    )
    info.heat_level = classify_complexity(info)
    info.language_tier = recommend_language(info.heat_level)
    info.recommended_tile = recommend_tile(node, info)
    return info


def _cyclomatic(info: FuncInfo) -> int:
    """Simple cyclomatic-like score: branches + loops + 1."""
    return info.branches + info.loops + 1


def classify_complexity(info: FuncInfo) -> str:
    """Map complexity to a heat level: COOL / WARM / HOT / INFERNO."""
    score = _cyclomatic(info) + info.calls // 2 + info.nesting_depth
    if score <= 2:
        return "COOL"
    elif score <= 6:
        return "WARM"
    elif score <= 12:
        return "HOT"
    else:
        return "INFERNO"


def recommend_language(heat_level: str) -> str:
    """Map heat level to recommended implementation language tier."""
    mapping = {
        "COOL":    "Python  (simple logic — high productivity)",
        "WARM":    "FIR      (intermediate — good balance)",
        "HOT":     "FIR+ASM  (performance-critical — low level)",
        "INFERNO": "ASM/C    (maximum performance — bare metal)",
    }
    return mapping.get(heat_level, "Python")


def recommend_tile(node: ast.FunctionDef | ast.AsyncFunctionDef, info: FuncInfo) -> str:
    """Guess which FLUX tile pattern this function maps to."""
    if info.is_async:
        return "AgentTile"
    if any(isinstance(c, (ast.For, ast.AsyncFor)) for c in ast.walk(node)):
        if any(isinstance(c, ast.If) for c in ast.walk(node)):
            return "FilterTile"
        return "MapTile"
    if any(isinstance(c, ast.If) for c in ast.walk(node)):
        return "BranchTile"
    if any(isinstance(c, ast.Call) for c in ast.walk(node)):
        return "ChainTile"
    return "ComputeTile"


# ═══════════════════════════════════════════════════════════════════════════════
# File & project analysis
# ═══════════════════════════════════════════════════════════════════════════════


def analyze_file(filepath: str, base: str = "") -> FileInfo:
    """Parse a single Python file and return FileInfo."""
    try:
        source = Path(filepath).read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=filepath)
    except (SyntaxError, UnicodeDecodeError, OSError) as exc:
        # Return a minimal FileInfo on parse failure
        return FileInfo(filepath=filepath, module_name=Path(filepath).stem)

    module_name = Path(filepath).stem
    if Path(filepath).name == "__init__.py":
        module_name = Path(filepath).parent.name

    functions: List[FuncInfo] = []
    classes: List[ClassInfo] = []
    imports: List[ImportInfo] = []

    # Count lines
    lines = source.splitlines()
    total_lines = len(lines)
    total_loc = sum(1 for l in lines if l.strip() and not l.strip().startswith("#"))

    # Imports
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
            imports.append(ImportInfo(module="", names=names, is_from=False, lineno=node.lineno))
        elif isinstance(node, ast.ImportFrom):
            names = [a.name for a in node.names]
            imports.append(ImportInfo(module=node.module or "", names=names, is_from=True, lineno=node.lineno))

    # Top-level functions
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(analyze_function(node))

    # Classes
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            bases = []
            for base_node in node.bases:
                if isinstance(base_node, ast.Name):
                    bases.append(base_node.id)
                elif isinstance(base_node, ast.Attribute):
                    bases.append(ast.dump(base_node))
            methods: List[FuncInfo] = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(analyze_function(item, is_method=True))
            classes.append(ClassInfo(name=node.name, lineno=node.lineno, methods=methods, bases=bases))
            functions.extend(methods)

    # Compute average complexity
    if functions:
        avg_c = sum(_cyclomatic(f) for f in functions) / len(functions)
    else:
        avg_c = 0.0

    # Estimate tiles: roughly one tile per function, more for complex ones
    est_tiles = sum(max(1, _cyclomatic(f) // 3) for f in functions)
    if not functions and classes:
        est_tiles = len(classes)

    hierarchy = map_to_hierarchy(filepath, base) if base else map_to_hierarchy(filepath, str(Path(filepath).parent.parent))

    return FileInfo(
        filepath=filepath,
        module_name=module_name,
        functions=functions,
        classes=classes,
        imports=imports,
        total_lines=total_lines,
        total_loc=total_loc,
        avg_complexity=round(avg_c, 1),
        hierarchy_path=hierarchy,
        estimated_tiles=est_tiles,
    )


def scan_project(path: str) -> ProjectInfo:
    """Walk a project directory, find all .py files, analyze each."""
    root = os.path.abspath(path)
    if os.path.isfile(root):
        if not root.endswith(".py"):
            print(f"[WARN] {root} is not a .py file; skipping.", file=sys.stderr)
            return ProjectInfo(root=root)
        fi = analyze_file(root, base=str(Path(root).parent))
        return ProjectInfo(
            root=root,
            files=[fi],
            total_files=1,
            total_functions=len(fi.functions),
            total_classes=len(fi.classes),
            total_lines=fi.total_lines,
            avg_complexity=fi.avg_complexity,
            total_tiles=fi.estimated_tiles,
        )

    py_files: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip hidden and common non-source dirs
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in (
            "__pycache__", "node_modules", ".git", "venv", ".venv", "env",
            "dist", "build", ".eggs", ".tox", ".mypy_cache", ".pytest_cache",
        )]
        for fn in sorted(filenames):
            if fn.endswith(".py"):
                py_files.append(os.path.join(dirpath, fn))

    file_infos: List[FileInfo] = []
    for fp in py_files:
        fi = analyze_file(fp, base=root)
        file_infos.append(fi)

    total_funcs = sum(len(f.functions) for f in file_infos)
    total_classes = sum(len(f.classes) for f in file_infos)
    total_lines = sum(f.total_lines for f in file_infos)
    all_complexities = [f.avg_complexity for f in file_infos if f.functions]
    avg_c = sum(all_complexities) / len(all_complexities) if all_complexities else 0.0
    total_tiles = sum(f.estimated_tiles for f in file_infos)

    return ProjectInfo(
        root=root,
        files=file_infos,
        total_files=len(file_infos),
        total_functions=total_funcs,
        total_classes=total_classes,
        total_lines=total_lines,
        avg_complexity=round(avg_c, 1),
        total_tiles=total_tiles,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# FLUX.MD generation
# ═══════════════════════════════════════════════════════════════════════════════


def generate_flux_md(fi: FileInfo) -> str:
    """Generate a FLUX.MD wrapper for a analyzed file."""
    lines: list[str] = []
    w = lines.append

    w(f"# {fi.module_name}")
    w("")
    w(f"> Auto-generated FLUX module wrapper")
    w(f"> Source: `{fi.filepath}`")
    w(f"> Hierarchy: `{fi.hierarchy_path}`")
    w(f"> Functions: {len(fi.functions)}  |  Classes: {len(fi.classes)}  |  LOC: {fi.total_loc}")
    w(f"> Avg cyclomatic: {fi.avg_complexity}  |  Estimated tiles: {fi.estimated_tiles}")
    w("")

    # Imports section
    if fi.imports:
        w("## Imports")
        w("")
        for imp in fi.imports:
            if imp.is_from:
                w(f"- `from {imp.module} import {', '.join(imp.names)}`")
            else:
                w(f"- `import {', '.join(imp.names)}`")
        w("")

    # Classes
    for cls in fi.classes:
        w(f"## Class: {cls.name}")
        if cls.bases:
            w(f"  Inherits: {', '.join(cls.bases)}")
        w("")
        for m in cls.methods:
            w(f"### {m.name}({'...' if m.params else ''})")
            w(f"| param | value |")
            w(f"|-------|-------|")
            w(f"| async | {m.is_async} |")
            w(f"| params | {m.params} |")
            w(f"| branches | {m.branches} |")
            w(f"| loops | {m.loops} |")
            w(f"| calls | {m.calls} |")
            w(f"| nesting | {m.nesting_depth} |")
            w(f"| LOC | {m.loc} |")
            w(f"| heat | **{m.heat_level}** |")
            w(f"| language | {m.language_tier} |")
            w(f"| tile | {m.recommended_tile} |")
            w("")

    # Top-level functions
    top_funcs = [f for f in fi.functions if not f.is_method]
    if top_funcs:
        w("## Functions")
        w("")
        for func in top_funcs:
            prefix = "async " if func.is_async else ""
            w(f"### {prefix}{func.name}({'...' if func.params else ''})")
            w(f"| param | value |")
            w(f"|-------|-------|")
            w(f"| params | {func.params} |")
            w(f"| branches | {func.branches} |")
            w(f"| loops | {func.loops} |")
            w(f"| calls | {func.calls} |")
            w(f"| nesting | {func.nesting_depth} |")
            w(f"| LOC | {func.loc} |")
            w(f"| heat | **{func.heat_level}** |")
            w(f"| language | {func.language_tier} |")
            w(f"| tile | {func.recommended_tile} |")
            w("")

    # Original source
    try:
        source = Path(fi.filepath).read_text(encoding="utf-8", errors="replace")
        lang = "python"
        w("## Original Source")
        w("")
        w(f"```{lang}")
        w(source.rstrip())
        w("```")
        w("")
    except OSError:
        pass

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Migration plan
# ═══════════════════════════════════════════════════════════════════════════════


def _box(title: str, body: str, width: int = 78) -> str:
    """Wrap text in a box-drawing frame."""
    top = "╔" + "═" * (width - 2) + "╗"
    bot = "╚" + "═" * (width - 2) + "╝"
    sep = "╠" + "═" * (width - 2) + "╣"
    title_line = "║ " + title.center(width - 4) + " ║"
    inner = []
    for line in body.splitlines():
        if len(line) > width - 4:
            # wrap long lines
            words = line.split()
            current = ""
            for word in words:
                if len(current) + len(word) + 1 > width - 4:
                    inner.append("║ " + current.ljust(width - 4) + " ║")
                    current = word
                else:
                    current = current + " " + word if current else word
            if current:
                inner.append("║ " + current.ljust(width - 4) + " ║")
        else:
            inner.append("║ " + line.ljust(width - 4) + " ║")
    parts = [top, title_line, sep] + inner + [bot]
    return "\n".join(parts)


def generate_migration_plan(project: ProjectInfo) -> str:
    """Generate a full migration plan as formatted text."""
    sections: list[str] = []

    # ── Summary ────────────────────────────────────────────────────────────
    effort_low = project.total_functions * 15  # minutes per function (low est)
    effort_high = project.total_functions * 45
    effort_days_low = effort_low // 60
    effort_days_high = effort_high // 60

    summary = (
        f"Project root       : {project.root}\n"
        f"Python files       : {project.total_files}\n"
        f"Total functions    : {project.total_functions}\n"
        f"Total classes      : {project.total_classes}\n"
        f"Total lines        : {project.total_lines}\n"
        f"Avg complexity     : {project.avg_complexity}\n"
        f"Estimated tiles    : {project.total_tiles}\n"
        f"Effort estimate    : {effort_days_low}–{effort_days_high} person-days"
    )
    sections.append(_box("FLUX MIGRATION PLAN — SUMMARY", summary))

    # ── Per-file breakdown ─────────────────────────────────────────────────
    header = (
        f"{'File':<40} {'Funcs':>5} {'Cls':>4} {'LOC':>5} {'Cplx':>5} {'Tiles':>5} {'Heat':>8}"
    )
    sep = "─" * len(header)
    rows = [header, sep]
    for fi in project.files:
        rel = os.path.relpath(fi.filepath, project.root)
        # Determine dominant heat level
        heat_counts: dict[str, int] = {}
        for f in fi.functions:
            heat_counts[f.heat_level] = heat_counts.get(f.heat_level, 0) + 1
        dominant = max(heat_counts, key=heat_counts.get) if heat_counts else "—"
        rows.append(
            f"{rel:<40} {len(fi.functions):>5} {len(fi.classes):>4} "
            f"{fi.total_loc:>5} {fi.avg_complexity:>5.1f} {fi.estimated_tiles:>5} {dominant:>8}"
        )
    sections.append(_box("FILE BREAKDOWN", "\n".join(rows)))

    # ── Top hot functions ──────────────────────────────────────────────────
    all_funcs = []
    for fi in project.files:
        for f in fi.functions:
            rel = os.path.relpath(fi.filepath, project.root)
            all_funcs.append((f, rel))
    all_funcs.sort(key=lambda x: _cyclomatic(x[0]) + x[0].calls, reverse=True)
    top_funcs = all_funcs[:20]

    if top_funcs:
        hot_header = (
            f"{'Function':<30} {'File':<25} {'Cplx':>5} {'Nest':>5} {'Heat':>8}"
        )
        hot_sep = "─" * len(hot_header)
        hot_rows = [hot_header, hot_sep]
        for f, rel in top_funcs:
            hot_rows.append(
                f"{f.name:<30} {rel:<25} {_cyclomatic(f):>5} {f.nesting_depth:>5} {f.heat_level:>8}"
            )
        sections.append(_box("TOP HOT FUNCTIONS (by complexity)", "\n".join(hot_rows)))

    # ── Hierarchy mapping ──────────────────────────────────────────────────
    hier_lines = set()
    for fi in project.files:
        hier_lines.add(fi.hierarchy_path)
    hier_sorted = sorted(hier_lines)
    hier_header = f"{'Hierarchy Path':<50} {'Level':>6}"
    hier_sep = "─" * len(hier_header)
    hier_rows = [hier_header, hier_sep]
    for hp in hier_sorted:
        parts = hp.split("/")
        level = len(parts) // 2
        level_name = HIERARCHY_LEVELS[min(level, len(HIERARCHY_LEVELS) - 1)]
        hier_rows.append(f"{hp:<50} {level_name:>6}")
    sections.append(_box("MODULE HIERARCHY MAPPING", "\n".join(hier_rows)))

    # ── Language tier recommendations ──────────────────────────────────────
    tier_counts: dict[str, int] = {}
    for fi in project.files:
        for f in fi.functions:
            tier = f.language_tier.split("(")[0].strip()
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

    tier_header = f"{'Language Tier':<20} {'Functions':>10} {'Percent':>8}"
    tier_sep = "─" * len(tier_header)
    tier_rows = [tier_header, tier_sep]
    for tier, count in sorted(tier_counts.items(), key=lambda x: -x[1]):
        pct = (count / max(project.total_functions, 1)) * 100
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        tier_rows.append(f"{tier:<20} {count:>10} {pct:>7.1f}%  {bar}")
    sections.append(_box("LANGUAGE TIER RECOMMENDATIONS", "\n".join(tier_rows)))

    # ── Tile distribution ──────────────────────────────────────────────────
    tile_counts: dict[str, int] = {}
    for fi in project.files:
        for f in fi.functions:
            tile_counts[f.recommended_tile] = tile_counts.get(f.recommended_tile, 0) + 1

    tile_header = f"{'Tile Type':<20} {'Count':>8}"
    tile_sep = "─" * len(tile_header)
    tile_rows = [tile_header, tile_sep]
    for tile, count in sorted(tile_counts.items(), key=lambda x: -x[1]):
        bar = "█" * min(count * 2, 40)
        tile_rows.append(f"{tile:<20} {count:>8}  {bar}")
    sections.append(_box("TILE PATTERN DISTRIBUTION", "\n".join(tile_rows)))

    return "\n\n".join(sections)


# ═══════════════════════════════════════════════════════════════════════════════
# Output helpers
# ═══════════════════════════════════════════════════════════════════════════════


def write_migration(project: ProjectInfo, output_dir: str) -> None:
    """Write FLUX.MD files and a summary to output_dir."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    md_dir = out / "flux_modules"
    md_dir.mkdir(parents=True, exist_ok=True)

    for fi in project.files:
        md_content = generate_flux_md(fi)
        # Create subdirectories matching hierarchy
        rel_path = os.path.relpath(fi.filepath, project.root)
        if rel_path == "." or rel_path == os.curdir:
            rel_path = Path(fi.filepath).name
        rel_path = rel_path.replace(".py", ".FLUX.MD")
        dest = md_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(md_content, encoding="utf-8")

    # Write summary JSON
    summary = {
        "root": project.root,
        "total_files": project.total_files,
        "total_functions": project.total_functions,
        "total_classes": project.total_classes,
        "total_lines": project.total_lines,
        "avg_complexity": project.avg_complexity,
        "total_tiles": project.total_tiles,
        "files": [
            {
                "path": os.path.relpath(fi.filepath, project.root),
                "module": fi.module_name,
                "functions": len(fi.functions),
                "classes": len(fi.classes),
                "loc": fi.total_loc,
                "complexity": fi.avg_complexity,
                "tiles": fi.estimated_tiles,
                "hierarchy": fi.hierarchy_path,
            }
            for fi in project.files
        ],
    }
    summary_path = out / "migration_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Write the migration plan text
    plan = generate_migration_plan(project)
    plan_path = out / "MIGRATION_PLAN.txt"
    plan_path.write_text(plan, encoding="utf-8")

    print(f"\n  Output written to: {out}")
    print(f"    - {md_dir}/        ({project.total_files} FLUX.MD files)")
    print(f"    - {summary_path}   (JSON summary)")
    print(f"    - {plan_path}      (text plan)")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="flux_migrate",
        description="Convert existing Python projects to FLUX modules.",
    )
    parser.add_argument("path", help="Path to a Python project directory or single .py file")
    parser.add_argument("--output", "-o", default="flux_output",
                        help="Output directory for generated FLUX.MD files (default: flux_output)")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Show migration plan without writing files")
    parser.add_argument("--json", action="store_true",
                        help="Output summary as JSON instead of pretty-printed plan")
    args = parser.parse_args()

    if not os.path.exists(args.path):
        print(f"[ERROR] Path does not exist: {args.path}", file=sys.stderr)
        sys.exit(1)

    print(f"╔══════════════════════════════════════════════════════════════════╗")
    print(f"║                   FLUX MIGRATE v1.0                            ║")
    print(f"║           Python → FLUX Module Converter                       ║")
    print(f"╚══════════════════════════════════════════════════════════════════╝")
    print(f"\n  Scanning: {os.path.abspath(args.path)}")

    project = scan_project(args.path)

    if args.json:
        data = {
            "root": project.root,
            "total_files": project.total_files,
            "total_functions": project.total_functions,
            "total_classes": project.total_classes,
            "total_lines": project.total_lines,
            "avg_complexity": project.avg_complexity,
            "total_tiles": project.total_tiles,
            "files": [
                {
                    "path": os.path.relpath(fi.filepath, project.root),
                    "module": fi.module_name,
                    "functions": len(fi.functions),
                    "classes": len(fi.classes),
                    "loc": fi.total_loc,
                    "complexity": fi.avg_complexity,
                    "tiles": fi.estimated_tiles,
                    "hierarchy": fi.hierarchy_path,
                }
                for fi in project.files
            ],
        }
        print(json.dumps(data, indent=2))
        return

    plan = generate_migration_plan(project)
    print(f"\n{plan}")

    if args.dry_run:
        print(f"\n  ─── DRY RUN — no files written ───")
    else:
        write_migration(project, args.output)


if __name__ == "__main__":
    main()
