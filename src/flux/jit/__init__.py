"""FLUX JIT Module — just-in-time compilation framework.

Provides:
- JITCompiler: compiles FIR functions to optimized native-like code
- JITCache: LRU cache for compiled functions
- ExecutionTracer: profiles hot paths for JIT decisions
- Optimization passes: const_fold_pass, dead_code_pass, inline_pass, block_layout_pass
"""

from .compiler import JITCompiler, JITFunction, RegisterAllocation
from .cache import JITCache, CacheEntry
from .tracing import ExecutionTracer, BlockProfile, FunctionProfile
from .ir_optimize import (
    const_fold_pass,
    dead_code_pass,
    inline_pass,
    block_layout_pass,
)

__all__ = [
    "JITCompiler",
    "JITFunction",
    "RegisterAllocation",
    "JITCache",
    "CacheEntry",
    "ExecutionTracer",
    "BlockProfile",
    "FunctionProfile",
    "const_fold_pass",
    "dead_code_pass",
    "inline_pass",
    "block_layout_pass",
]
