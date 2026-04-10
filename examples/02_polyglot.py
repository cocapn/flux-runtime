#!/usr/bin/env python3
"""FLUX Polyglot — Compiling mixed C + Python from a FLUX.MD document.

This example shows how FLUX.MD lets you mix C and Python in a single Markdown
document, then compile and run the embedded code blocks through the pipeline.

Run:
    PYTHONPATH=src python3 examples/02_polyglot.py
"""

from __future__ import annotations

import os

# ── ANSI helpers ──────────────────────────────────────────────────────────

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def header(text: str) -> None:
    width = 64
    print()
    print(f"{BOLD}{MAGENTA}{'═' * width}{RESET}")
    print(f"{BOLD}{MAGENTA}  {text}{RESET}")
    print(f"{BOLD}{MAGENTA}{'═' * width}{RESET}")


def info(text: str) -> None:
    print(f"  {GREEN}✓{RESET} {text}")


def detail(text: str) -> None:
    print(f"    {DIM}{text}{RESET}")


def section(text: str) -> None:
    print()
    print(f"{BOLD}{CYAN}── {text} {'─' * (56 - len(text))}{RESET}")


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print()
    print(f"{BOLD}{YELLOW}{'╔' + '═' * 62 + '╗'}{RESET}")
    print(f"{BOLD}{YELLOW}{'║'}  FLUX Polyglot — Mixed C + Python Compilation     {'║'}{RESET}")
    print(f"{BOLD}{YELLOW}{'║'}  One Markdown document, multiple languages         {'║'}{RESET}")
    print(f"{BOLD}{YELLOW}{'╚' + '═' * 62 + '╝'}{RESET}")

    # ── Load the FLUX.MD document ──────────────────────────────────────
    md_path = os.path.join(os.path.dirname(__file__), "02_polyglot.md")
    with open(md_path, "r") as f:
        md_source = f.read()

    header("FLUX.MD Source Document")
    print(f"{DIM}{md_source}{RESET}")

    # ── Parse the FLUX.MD document ─────────────────────────────────────
    section("Step 1: Parse FLUX.MD")
    try:
        from flux.parser import FluxMDParser
        from flux.parser.nodes import NativeBlock

        parser = FluxMDParser()
        doc = parser.parse(md_source)

        info(f"Parsed document: {len(doc.children)} top-level children")

        code_blocks = []
        for child in doc.children:
            if isinstance(child, NativeBlock):
                lang = (child.lang or "").lower().strip()
                code_blocks.append((lang, child.content))
                info(f"  Found {lang.upper()} block ({len(child.content)} chars)")

    except ImportError as e:
        print(f"  {YELLOW}⚠{RESET} Parser import failed: {e}")
        code_blocks = []
    except Exception as e:
        print(f"  {YELLOW}⚠{RESET} Parse error: {e}")
        code_blocks = []

    # ── Compile each code block ────────────────────────────────────────
    section("Step 2: Compile Each Code Block")

    if code_blocks:
        try:
            from flux.compiler.pipeline import FluxCompiler

            compiler = FluxCompiler()

            for lang, content in code_blocks:
                info(f"Compiling {lang.upper()} block...")
                try:
                    if lang == "c":
                        bytecode = compiler.compile_c(content, module_name="polyglot_c")
                    elif lang == "python":
                        bytecode = compiler.compile_python(content, module_name="polyglot_py")
                    else:
                        detail(f"  Skipping unsupported language: {lang}")
                        continue

                    info(f"  {lang.upper()} → {len(bytecode)} bytes of FLUX bytecode")
                    detail(f"  Magic: {bytecode[:4]}")
                except Exception as e:
                    detail(f"  Compilation error: {e}")

        except ImportError as e:
            print(f"  {YELLOW}⚠{RESET} Compiler import failed: {e}")

    # ── Run through full pipeline ──────────────────────────────────────
    section("Step 3: Run Through Full Pipeline")

    try:
        from flux.pipeline.e2e import FluxPipeline

        # Try the C code block
        c_code = code_blocks[0][1] if code_blocks else "int main() { return 42; }"

        detail(f"Compiling C source through FLUX.MD pipeline...")

        pipeline = FluxPipeline(optimize=True, execute=True)
        result = pipeline.run(md_source, lang="md", module_name="polyglot_full")

        if result.success:
            info("Pipeline completed successfully!")
            info(f"  Cycles: {result.cycles}")
            info(f"  Halted: {result.halted}")
        else:
            info("Pipeline completed with notes:")
            for err in result.errors:
                detail(f"  {err}")

        if result.bytecode:
            info(f"  Bytecode: {len(result.bytecode)} bytes")

    except Exception as e:
        print(f"  {YELLOW}⚠{RESET} Pipeline error: {e}")

    # ── Show the beauty of polyglot ────────────────────────────────────
    section("Summary: What Makes FLUX.MD Special")
    info("FLUX.MD is a literate programming format that:")
    detail("  • Embeds C, Python, and more in natural Markdown documents")
    detail("  • Compiles each code block through language-specific frontends")
    detail("  • Produces unified FLUX bytecode from mixed-language sources")
    detail("  • Lets you document AND execute in the same file")
    detail("  • Perfect for polyglot signal processing, ML pipelines, etc.")

    print()
    print(f"{BOLD}{GREEN}── Done! ──{RESET}")
    print()
