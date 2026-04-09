"""JIT Compiler — compiles FIR functions to optimized native-like code.

The JITCompiler takes FIR functions and produces JITFunction objects with:
- Optimized IR (after applying inlining, constant folding, DCE, layout)
- Virtual register allocation mapping SSA values to registers
- Hot-path metadata from the execution tracer
"""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass, field
from typing import Any, Optional

from flux.fir.types import FIRType, TypeContext
from flux.fir.values import Value
from flux.fir.instructions import Instruction
from flux.fir.blocks import FIRBlock, FIRFunction, FIRModule

from .ir_optimize import (
    const_fold_pass,
    dead_code_pass,
    inline_pass,
    block_layout_pass,
    _get_operand_values,
    _max_value_id,
)
from .cache import JITCache
from .tracing import ExecutionTracer

logger = logging.getLogger(__name__)


@dataclass
class RegisterAllocation:
    """Result of virtual register allocation.

    Maps SSA value IDs to virtual register numbers, simulating
    what a real register allocator would produce.
    """
    value_to_register: dict[int, int] = field(default_factory=dict)
    register_to_value: dict[int, int] = field(default_factory=dict)
    spill_count: int = 0
    total_registers_used: int = 0
    num_virtual_registers: int = 64  # matches FLUX VM's 64 registers


@dataclass
class JITFunction:
    """A JIT-compiled function with optimized IR and register allocation.

    Attributes:
        name: Function name.
        sig: Function type signature.
        blocks: Optimized basic blocks.
        register_alloc: Virtual register allocation result.
        optimization_stats: Statistics about optimizations applied.
        is_compiled: Whether the function has been through JIT compilation.
    """
    name: str
    sig: FIRType
    blocks: list[FIRBlock]
    register_alloc: RegisterAllocation
    optimization_stats: dict[str, int] = field(default_factory=dict)
    is_compiled: bool = True

    def instruction_count(self) -> int:
        """Return total number of instructions across all blocks."""
        return sum(len(b.instructions) for b in self.blocks)

    def block_count(self) -> int:
        """Return number of basic blocks."""
        return len(self.blocks)

    def __repr__(self) -> str:
        return (
            f"JITFunction(name={self.name!r}, "
            f"blocks={self.block_count()}, "
            f"instrs={self.instruction_count()}, "
            f"registers={self.register_alloc.total_registers_used})"
        )


class JITCompiler:
    """JIT compiler that takes FIR and produces optimized JITFunction objects.

    The compiler applies a sequence of optimization passes:
    1. Function inlining (small functions < threshold instructions)
    2. Constant folding and propagation
    3. Dead code elimination (unreachable blocks)
    4. Basic block layout optimization

    After optimization, it performs virtual register allocation to map
    SSA values to the 64 virtual registers of the FLUX VM.

    Compiled functions are cached in an LRU cache keyed by the function's
    serialized IR hash.

    Args:
        inline_threshold: Maximum instruction count for inlining. Defaults to 10.
        enable_tracing: Whether to profile execution for adaptive JIT. Defaults to False.
        cache_size: Maximum number of cached functions. Defaults to 64.
    """

    def __init__(
        self,
        inline_threshold: int = 10,
        enable_tracing: bool = False,
        cache_size: int = 64,
    ) -> None:
        self._inline_threshold = inline_threshold
        self._cache = JITCache(max_size=cache_size)
        self._tracer = ExecutionTracer() if enable_tracing else None

    @property
    def tracer(self) -> Optional[ExecutionTracer]:
        """Access the execution tracer (or None if tracing is disabled)."""
        return self._tracer

    @property
    def cache(self) -> JITCache:
        """Access the JIT code cache."""
        return self._cache

    def compile(self, func: FIRFunction) -> JITFunction:
        """Compile a FIRFunction into an optimized JITFunction.

        Applies optimization passes, performs register allocation, and
        caches the result.

        Args:
            func: FIRFunction to compile.

        Returns:
            JITFunction with optimized IR and register allocation.
        """
        # Check cache
        cache_key = JITCache.compute_key(self._serialize_function(func))
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug("JIT cache hit for function: %s", func.name)
            return cached

        logger.debug("JIT compiling function: %s", func.name)

        # Step 1: Create a temporary module for the function
        # (optimization passes operate on modules)
        temp_module = self._function_to_module(func)

        # Step 2: Apply optimization passes
        stats: dict[str, int] = {}

        changes = inline_pass(temp_module, threshold=self._inline_threshold)
        stats["inlined"] = changes

        changes = const_fold_pass(temp_module)
        stats["const_folded"] = changes

        changes = dead_code_pass(temp_module)
        stats["dead_blocks_removed"] = changes

        changes = block_layout_pass(temp_module)
        stats["blocks_reordered"] = changes

        # Get the optimized function
        optimized = temp_module.functions.get(func.name, func)

        # Step 3: Register allocation
        reg_alloc = self._allocate_registers(optimized)
        stats["registers_used"] = reg_alloc.total_registers_used
        stats["spills"] = reg_alloc.spill_count

        # Step 4: Create JITFunction
        result = JITFunction(
            name=optimized.name,
            sig=optimized.sig,
            blocks=optimized.blocks,
            register_alloc=reg_alloc,
            optimization_stats=stats,
        )

        # Cache the result
        self._cache.put(cache_key, result, size_bytes=self._estimate_size(result))

        logger.info(
            "JIT compiled %s: %d blocks, %d instrs, %d registers",
            func.name,
            result.block_count(),
            result.instruction_count(),
            reg_alloc.total_registers_used,
        )

        return result

    def compile_module(self, module: FIRModule) -> dict[str, JITFunction]:
        """Compile all functions in a module.

        Args:
            module: FIRModule containing functions to compile.

        Returns:
            Dictionary mapping function name to JITFunction.
        """
        results: dict[str, JITFunction] = {}
        for func_name in module.functions:
            func = module.functions[func_name]
            results[func_name] = self.compile(func)
        return results

    # ── Register Allocation ─────────────────────────────────────────────

    def _allocate_registers(self, func: FIRFunction) -> RegisterAllocation:
        """Perform linear-scan register allocation simulation.

        Maps SSA value IDs to virtual register numbers. Uses a simple
        greedy strategy: assign the next available register, reusing
        registers when a value's last use has been seen.

        Args:
            func: FIRFunction to allocate registers for.

        Returns:
            RegisterAllocation with the value-to-register mapping.
        """
        alloc = RegisterAllocation()

        # Collect all value IDs and their last use positions
        value_last_use: dict[int, int] = {}
        all_values: list[int] = []

        # Flatten (bi, ii) positions to a single integer for comparison.
        def _pos(bi: int, ii: int) -> int:
            return bi * 10000 + ii

        # Include block parameters
        for block in func.blocks:
            for pname, ptype in block.params:
                # Use a canonical ID for block params
                param_id = hash((block.label, pname))
                all_values.append(param_id)
                value_last_use[param_id] = 0  # params are "defined" at start

        # Scan all instructions to find value references and last uses
        for bi, block in enumerate(func.blocks):
            for ii, instr in enumerate(block.instructions):
                for v in _get_operand_values(instr):
                    vid = v.id
                    if vid not in value_last_use:
                        all_values.append(vid)
                    value_last_use[vid] = _pos(bi, ii)

        # Linear scan allocation
        free_registers: list[int] = list(range(alloc.num_virtual_registers))
        active: dict[int, int] = {}  # register -> expiry position

        # Sort values by their first definition position
        value_first_def: dict[int, tuple[int, int]] = {}
        for bi, block in enumerate(func.blocks):
            for ii, instr in enumerate(block.instructions):
                # Track "result" values — these are values that would
                # be assigned by the builder for instructions with result_type
                if instr.result_type is not None:
                    result_id = 100000 + bi * 10000 + ii
                    all_values.append(result_id)
                    value_first_def[result_id] = (bi, ii)
                    value_last_use[result_id] = value_last_use.get(result_id, _pos(bi, ii))

        # Allocate registers for all known values
        for vid in all_values:
            last_use = value_last_use.get(vid, 0)

            # Expire registers whose values are no longer live
            expired = [
                reg for reg, expiry in active.items()
                if expiry < last_use
            ]
            for reg in expired:
                free_registers.append(reg)
                del active[reg]

            if free_registers:
                reg = free_registers.pop(0)
                alloc.value_to_register[vid] = reg
                alloc.register_to_value[reg] = vid
                active[reg] = last_use
            else:
                # Spill: steal the register with the farthest expiry
                if active:
                    steal_reg = max(active, key=lambda r: active[r])
                    alloc.value_to_register[vid] = steal_reg
                    del active[steal_reg]
                    active[steal_reg] = last_use
                    alloc.spill_count += 1

        alloc.total_registers_used = len(alloc.value_to_register)
        return alloc

    # ── Helpers ─────────────────────────────────────────────────────────

    def _function_to_module(self, func: FIRFunction) -> FIRModule:
        """Wrap a single function in a temporary module."""
        # Reuse the function's type context if available from the sig
        ctx = TypeContext()
        module = FIRModule(
            name=f"_jit_{func.name}",
            type_ctx=ctx,
        )
        module.functions[func.name] = func
        return module

    @staticmethod
    def _serialize_function(func: FIRFunction) -> bytes:
        """Serialize a function for cache key computation.

        Uses pickle for deterministic serialization of the function's
        structural properties.
        """
        data = {
            "name": func.name,
            "blocks": [
                {
                    "label": b.label,
                    "params": [(n, str(t)) for n, t in b.params],
                    "instructions": [
                        instr.opcode for instr in b.instructions
                    ],
                }
                for b in func.blocks
            ],
        }
        return pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def _estimate_size(jit_func: JITFunction) -> int:
        """Estimate the memory footprint of a JITFunction."""
        base = 128  # overhead
        base += jit_func.instruction_count() * 32  # ~32 bytes per instruction
        base += jit_func.register_alloc.total_registers_used * 8
        return base

    def invalidate_cache(self) -> int:
        """Clear the entire JIT cache.

        Returns:
            Number of entries cleared.
        """
        return self._cache.clear()

    def __repr__(self) -> str:
        return (
            f"JITCompiler("
            f"cache={self._cache}, "
            f"inline_threshold={self._inline_threshold}, "
            f"tracing={self._tracer is not None})"
        )
