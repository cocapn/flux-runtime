"""FluxCompiler Pipeline — unified compilation from C, Python, or FLUX.MD to bytecode.

Provides:
  compile_c(source)     → bytes
  compile_python(source) → bytes
  compile_md(source)    → bytes
"""

from __future__ import annotations

from flux.fir.blocks import FIRModule
from flux.fir.types import TypeContext, IntType
from flux.fir.values import Value
from flux.fir.builder import FIRBuilder
from flux.bytecode.encoder import BytecodeEncoder


class FluxCompiler:
    """Unified compilation pipeline for multiple source languages.

    Each ``compile_*`` method takes source code as a string and returns
    FLUX bytecode as ``bytes``.
    """

    def __init__(self):
        self._encoder = BytecodeEncoder()

    # ── C ─────────────────────────────────────────────────────────────────

    def compile_c(self, source: str, module_name: str = "c_module") -> bytes:
        """Compile C source to FLUX bytecode.

        Supports: int/float functions, variables, if/else, while, for,
        return, arithmetic, comparison, calls, literals.
        """
        from flux.frontend.c_frontend import CFrontendCompiler

        compiler = CFrontendCompiler()
        module = compiler.compile(source, module_name=module_name)
        return self._encoder.encode(module)

    # ── Python ────────────────────────────────────────────────────────────

    def compile_python(self, source: str, module_name: str = "py_module") -> bytes:
        """Compile Python source to FLUX bytecode.

        Supports: def, assignments, arithmetic, comparison, if/elif/else,
        while, for/range, return, print, calls, literals.
        """
        from flux.frontend.python_frontend import PythonFrontendCompiler

        compiler = PythonFrontendCompiler()
        module = compiler.compile(source, module_name=module_name)
        return self._encoder.encode(module)

    # ── FLUX.MD ──────────────────────────────────────────────────────────

    def compile_md(self, source: str, module_name: str = "md_module") -> bytes:
        """Compile FLUX.MD source to FLUX bytecode.

        Extracts native code blocks (C or Python) from the Markdown
        document and compiles them into a single module.
        """
        from flux.parser import FluxMDParser
        from flux.parser.nodes import NativeBlock

        parser = FluxMDParser()
        doc = parser.parse(source)

        # Find all native code blocks
        code_blocks: list[tuple[str, str]] = []  # (lang, content)
        for child in doc.children:
            if isinstance(child, NativeBlock):
                lang = (child.lang or "").lower().strip()
                if lang in ("c", "python"):
                    code_blocks.append((lang, child.content))

        if not code_blocks:
            # Empty module — return minimal valid bytecode
            ctx = TypeContext()
            builder = FIRBuilder(ctx)
            module = builder.new_module(module_name)
            return self._encoder.encode(module)

        # Compile the first code block (single-module output)
        lang, content = code_blocks[0]
        if lang == "c":
            return self.compile_c(content, module_name=module_name)
        elif lang == "python":
            return self.compile_python(content, module_name=module_name)

        # Fallback: empty module
        ctx = TypeContext()
        builder = FIRBuilder(ctx)
        module = builder.new_module(module_name)
        return self._encoder.encode(module)
