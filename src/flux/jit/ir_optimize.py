"""FIR-level optimization passes used by the JIT compiler.

Provides constant folding, dead code elimination, function inlining,
and basic block layout optimization for FIRModules.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field, replace, is_dataclass
from typing import Optional, Any

from flux.fir.types import FIRType, IntType, FloatType, BoolType
from flux.fir.values import Value
from flux.fir.instructions import (
    Instruction, is_terminator,
    IAdd, ISub, IMul, IDiv, IMod, INeg,
    FAdd, FSub, FMul, FDiv, FNeg,
    IAnd, IOr, IXor, IShl, IShr, INot,
    IEq, INe, ILt, IGt, ILe, IGe,
    FEq, FLt, FGt, FLe, FGe,
    ITrunc, ZExt, SExt, FTrunc, FExt, Bitcast,
    Load, Store, Alloca, GetField, SetField, GetElem, SetElem,
    MemCopy, MemSet,
    Jump, Branch, Switch, Call, Return, Unreachable,
    Tell, Ask, Delegate, TrustCheck, CapRequire,
)
from flux.fir.blocks import FIRBlock, FIRFunction, FIRModule

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

_SIDE_EFFECT_OPCODES = frozenset({
    "store", "call", "tell", "ask", "delegate", "trustcheck", "caprequire",
    "jump", "branch", "switch", "return", "unreachable",
    "setfield", "setelem", "memcpy", "memset",
})

_BINARY_OPS = frozenset({
    "iadd", "isub", "imul", "idiv", "imod",
    "fadd", "fsub", "fmul", "fdiv",
    "iand", "ior", "ixor", "ishl", "ishr",
    "ieq", "ine", "ilt", "igt", "ile", "ige",
    "feq", "flt", "fgt", "fle", "fge",
})

_UNARY_OPS = frozenset({
    "ineg", "fneg", "inot",
    "itrunc", "zext", "sext", "ftrunc", "fext", "bitcast",
})


def _get_operand_values(instr: Instruction) -> list[Value]:
    """Extract all Value references from an instruction."""
    values: list[Value] = []
    for attr in ("lhs", "rhs", "value", "cond", "ptr",
                 "struct_val", "array_val", "message",
                 "target_agent", "cap", "authority", "threshold",
                 "src", "dst"):
        v = getattr(instr, attr, None)
        if isinstance(v, Value):
            values.append(v)
    # Handle args lists (Jump, Branch, Call)
    args = getattr(instr, "args", None)
    if isinstance(args, list):
        for a in args:
            if isinstance(a, Value):
                values.append(a)
    return values


def _has_side_effects(instr: Instruction) -> bool:
    """Check if an instruction has observable side effects."""
    return instr.opcode in _SIDE_EFFECT_OPCODES


def _evaluate_binary(opcode: str, lhs: Any, rhs: Any) -> Any:
    """Evaluate a binary arithmetic/comparison operation on known constants."""
    try:
        ops = {
            "iadd": lambda a, b: a + b,
            "isub": lambda a, b: a - b,
            "imul": lambda a, b: a * b,
            "idiv": lambda a, b: a // b if b != 0 else None,
            "imod": lambda a, b: a % b if b != 0 else None,
            "fadd": lambda a, b: a + b,
            "fsub": lambda a, b: a - b,
            "fmul": lambda a, b: a * b,
            "fdiv": lambda a, b: a / b if b != 0 else None,
            "iand": lambda a, b: a & b,
            "ior": lambda a, b: a | b,
            "ixor": lambda a, b: a ^ b,
            "ishl": lambda a, b: a << b if b >= 0 else None,
            "ishr": lambda a, b: a >> b if b >= 0 else None,
            "ieq": lambda a, b: a == b,
            "ine": lambda a, b: a != b,
            "ilt": lambda a, b: a < b,
            "igt": lambda a, b: a > b,
            "ile": lambda a, b: a <= b,
            "ige": lambda a, b: a >= b,
            "feq": lambda a, b: a == b,
            "flt": lambda a, b: a < b,
            "fgt": lambda a, b: a > b,
            "fle": lambda a, b: a <= b,
            "fge": lambda a, b: a >= b,
        }
        fn = ops.get(opcode)
        return fn(lhs, rhs) if fn else None
    except (ZeroDivisionError, OverflowError, TypeError, ValueError):
        return None


def _evaluate_unary(opcode: str, val: Any) -> Any:
    """Evaluate a unary operation on a known constant."""
    try:
        ops = {
            "ineg": lambda a: -a,
            "fneg": lambda a: -a,
            "inot": lambda a: ~a,
        }
        fn = ops.get(opcode)
        return fn(val) if fn else None
    except (OverflowError, TypeError):
        return None


def _build_block_reachability(func: FIRFunction) -> set[str]:
    """Compute set of reachable block labels from the entry block."""
    reachable: set[str] = set()
    worklist: list[str] = []

    if not func.blocks:
        return reachable

    entry_label = func.blocks[0].label
    reachable.add(entry_label)
    worklist.append(entry_label)

    while worklist:
        label = worklist.pop()
        block_map = {b.label: b for b in func.blocks}
        block = block_map.get(label)
        if block is None or not block.instructions:
            continue

        terminator = block.terminator
        if terminator is None:
            continue

        targets: list[str] = []
        if isinstance(terminator, Jump):
            targets.append(terminator.target_block)
        elif isinstance(terminator, Branch):
            targets.extend([terminator.true_block, terminator.false_block])
        elif isinstance(terminator, Switch):
            targets.extend(terminator.cases.values())
            if terminator.default_block:
                targets.append(terminator.default_block)

        for t in targets:
            if t not in reachable:
                reachable.add(t)
                worklist.append(t)

    return reachable


def _clone_value(value: Value, id_offset: int, name_prefix: str = "") -> Value:
    """Clone a Value with shifted ID and optional name prefix."""
    return Value(
        id=value.id + id_offset,
        name=name_prefix + value.name,
        type=value.type,
    )


def _remap_instruction_values(
    instr: Instruction,
    value_map: dict[int, Value],
) -> Instruction:
    """Create a new instruction with Value references remapped.

    value_map maps old value.id -> new Value object.
    """
    if not is_dataclass(instr) or isinstance(instr, type):
        return instr

    changes: dict[str, Any] = {}
    for f in instr.__dataclass_fields__:
        attr_val = getattr(instr, f, None)
        if isinstance(attr_val, Value) and attr_val.id in value_map:
            changes[f] = value_map[attr_val.id]
        elif isinstance(attr_val, list):
            new_list = []
            for item in attr_val:
                if isinstance(item, Value) and item.id in value_map:
                    new_list.append(value_map[item.id])
                else:
                    new_list.append(item)
            if new_list != attr_val:
                changes[f] = new_list

    if changes:
        return replace(instr, **changes)
    return instr


def _count_instructions(func: FIRFunction) -> int:
    """Count total instructions across all blocks (excluding terminators)."""
    return sum(
        len(b.instructions) - 1  # exclude terminator
        for b in func.blocks
        if b.terminator is not None
    )


def _get_block_successors(block: FIRBlock) -> list[str]:
    """Get successor block labels for a block."""
    t = block.terminator
    if t is None:
        return []
    if isinstance(t, Jump):
        return [t.target_block]
    if isinstance(t, Branch):
        return [t.true_block, t.false_block]
    if isinstance(t, Switch):
        result = list(t.cases.values())
        if t.default_block:
            result.append(t.default_block)
        return result
    return []


# ── Optimization Passes ─────────────────────────────────────────────────────

def const_fold_pass(
    module: FIRModule,
    known_constants: Optional[dict[int, Any]] = None,
) -> int:
    """Fold constant expressions and propagate known values.

    Args:
        module: FIRModule to optimize.
        known_constants: Mapping from Value.id to constant numeric value.
            The JIT compiler (or tests) seeds this with known operand values.

    Returns:
        Number of instructions folded or removed.
    """
    if known_constants is None:
        known_constants = {}

    total_changes = 0

    for func in module.functions.values():
        # Build a per-function constant map that includes both
        # user-provided constants and constants discovered during folding.
        const_vals: dict[int, Any] = dict(known_constants)

        for block in func.blocks:
            new_instructions: list[Instruction] = []

            for instr in block.instructions:
                operands = _get_operand_values(instr)

                if not _has_side_effects(instr):
                    folded = None

                    if len(operands) == 2 and instr.opcode in _BINARY_OPS:
                        lhs_val = const_vals.get(operands[0].id)
                        rhs_val = const_vals.get(operands[1].id)
                        if lhs_val is not None and rhs_val is not None:
                            folded = _evaluate_binary(
                                instr.opcode, lhs_val, rhs_val
                            )

                    elif len(operands) == 1 and instr.opcode in _UNARY_OPS:
                        val = const_vals.get(operands[0].id)
                        if val is not None:
                            folded = _evaluate_unary(instr.opcode, val)

                    if folded is not None:
                        # Record the folded result for subsequent instructions.
                        # The "result" of this instruction gets the next
                        # canonical ID based on builder convention.
                        if instr.result_type is not None:
                            # Compute the result value ID that the builder
                            # would assign. Since we process in order and
                            # track const_vals by value.id, we assign a
                            # synthetic ID that the builder would produce.
                            # We use a high-offset ID to avoid collisions.
                            result_id = _compute_result_id(
                                func, block, instr, new_instructions
                            )
                            if result_id is not None:
                                const_vals[result_id] = folded
                        total_changes += 1
                        continue  # Skip adding this instruction

                new_instructions.append(instr)

            block.instructions = new_instructions

    return total_changes


def _compute_result_id(
    func: FIRFunction,
    block: FIRBlock,
    instr: Instruction,
    new_instructions_so_far: list[Instruction],
) -> Optional[int]:
    """Compute the canonical value ID for an instruction's result.

    Follows the builder convention: params are numbered first (per block,
    in order), then instruction results in order. Returns the ID that
    the builder would assign to this instruction's result.

    Uses a negative-offset scheme to avoid collisions with user-assigned IDs.
    """
    # Count params and instruction results before this instruction
    # We use a deterministic offset based on the function/block/instruction position
    func_idx = list(func.blocks).index(block) if block in func.blocks else 0
    block_pos = func_idx
    instr_pos = len(new_instructions_so_far)
    param_count = len(block.params)

    # Use a deterministic but non-colliding ID scheme
    # Offset by 100000 to avoid collisions with manually-assigned IDs
    return 100000 + block_pos * 10000 + param_count + instr_pos


def dead_code_pass(module: FIRModule) -> int:
    """Remove unreachable blocks from all functions.

    Computes reachability from each function's entry block and removes
    blocks that cannot be reached via control flow.

    Returns:
        Number of blocks removed.
    """
    total_removed = 0

    for func in module.functions.values():
        if not func.blocks:
            continue

        reachable = _build_block_reachability(func)

        before = len(func.blocks)
        func.blocks = [b for b in func.blocks if b.label in reachable]
        removed = before - len(func.blocks)
        total_removed += removed

    return total_removed


def inline_pass(module: FIRModule, threshold: int = 10) -> int:
    """Inline small functions at their call sites.

    Functions with fewer than ``threshold`` non-terminator instructions
    are candidates for inlining. Only single-block callees are fully
    inlined; multi-block callees are skipped.

    Args:
        module: FIRModule to optimize.
        threshold: Maximum instruction count for a function to be inlined.

    Returns:
        Number of call sites inlined.
    """
    # Identify inlineable functions
    inlineable: dict[str, FIRFunction] = {}
    for name, func in module.functions.items():
        instr_count = _count_instructions(func)
        if instr_count > 0 and instr_count < threshold:
            inlineable[name] = func

    if not inlineable:
        return 0

    total_inlined = 0

    for func in list(module.functions.values()):
        for block in func.blocks:
            new_instructions: list[Instruction] = []
            max_value_id = _max_value_id(func)

            for instr in block.instructions:
                if (
                    isinstance(instr, Call)
                    and instr.func in inlineable
                    and instr.func != func.name  # no self-recursion
                ):
                    callee = inlineable[instr.func]
                    inlined = _inline_single_block_call(
                        callee, instr.args, max_value_id
                    )
                    if inlined is not None:
                        new_instructions.extend(inlined)
                        max_value_id += _count_inline_values(callee)
                        total_inlined += 1
                        continue

                new_instructions.append(instr)

            block.instructions = new_instructions

    return total_inlined


def _inline_single_block_call(
    callee: FIRFunction,
    call_args: list[Value],
    value_id_offset: int,
) -> Optional[list[Instruction]]:
    """Inline a single-block callee at a call site.

    Creates a copy of the callee's instructions (excluding Return) with
    parameter values mapped to call arguments and value IDs shifted.

    Returns list of instructions to insert, or None if inlining is not possible.
    """
    if len(callee.blocks) != 1:
        return None

    block = callee.blocks[0]
    if not block.params:
        # No params — just copy non-terminator instructions
        value_map: dict[int, Value] = {}
        result = []
        for instr in block.instructions:
            if isinstance(instr, Return):
                break
            new_instr = _remap_instruction_values(instr, value_map)
            result.append(new_instr)
        return result if result else None

    if len(block.params) != len(call_args):
        return None  # Argument count mismatch

    # Map callee param value IDs to call argument Value objects
    # Callee params get IDs starting from 0 (builder convention)
    value_map: dict[int, Value] = {}
    for i, (pname, ptype) in enumerate(block.params):
        value_map[i] = call_args[i]

    # Shift all other value IDs by offset
    for instr in block.instructions:
        if isinstance(instr, Return):
            break
        for v in _get_operand_values(instr):
            if v.id not in value_map:
                new_id = v.id + value_id_offset
                value_map[v.id] = Value(id=new_id, name=v.name, type=v.type)

    # Build inlined instructions
    result: list[Instruction] = []
    for instr in block.instructions:
        if isinstance(instr, Return):
            break
        new_instr = _remap_instruction_values(instr, value_map)
        result.append(new_instr)

    return result if result else None


def _count_inline_values(callee: FIRFunction) -> int:
    """Count the number of values that inlining would introduce."""
    count = 0
    for block in callee.blocks:
        count += len(block.params)
        for instr in block.instructions:
            if isinstance(instr, Return):
                break
            if instr.result_type is not None:
                count += 1
    return count


def _max_value_id(func: FIRFunction) -> int:
    """Find the maximum value ID referenced in a function."""
    max_id = -1
    for block in func.blocks:
        for instr in block.instructions:
            for v in _get_operand_values(instr):
                max_id = max(max_id, v.id)
    return max_id + 1 if max_id >= 0 else 0


def block_layout_pass(module: FIRModule) -> int:
    """Optimize basic block ordering for fallthrough.

    Uses a greedy heuristic: place the most common successor of each
    block immediately after it in the layout. This minimizes unconditional
    jumps and improves instruction cache locality.

    Returns:
        Number of blocks reordered.
    """
    total_reorders = 0

    for func in module.functions.values():
        if len(func.blocks) <= 2:
            continue

        # Count successor frequencies across all terminators
        edge_freq: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for block in func.blocks:
            successors = _get_block_successors(block)
            for succ in successors:
                edge_freq[block.label][succ] += 1

        # Greedy layout: start with entry, then place best successor
        block_map = {b.label: b for b in func.blocks}
        entry_label = func.blocks[0].label

        placed: list[str] = [entry_label]
        remaining = set(block_map.keys()) - {entry_label}

        while remaining:
            current = placed[-1]
            # Find the best successor that hasn't been placed yet
            best_succ = None
            best_freq = -1
            for succ, freq in edge_freq[current].items():
                if succ in remaining and freq > best_freq:
                    best_freq = freq
                    best_succ = succ

            if best_succ is None:
                # No unplaced successor — pick any remaining block
                best_succ = next(iter(remaining))

            placed.append(best_succ)
            remaining.discard(best_succ)

        # Check if layout changed
        old_order = [b.label for b in func.blocks]
        if placed != old_order:
            total_reorders += 1
            func.blocks = [block_map[label] for label in placed]

    return total_reorders
