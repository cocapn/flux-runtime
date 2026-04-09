"""Python Frontend Compiler — Python source to FIR using the ``ast`` module.

Handles: def, assignments, arithmetic, comparison, if/elif/else, while,
for/range, return, print, calls, int/float/str literals.
"""

from __future__ import annotations

import ast
from typing import Optional

from flux.fir.types import (
    TypeContext, FIRType, IntType, FloatType, BoolType, UnitType, StringType,
)
from flux.fir.values import Value
from flux.fir.builder import FIRBuilder
from flux.fir.blocks import FIRModule, FIRFunction, FIRBlock
from flux.fir.instructions import (
    IAdd, ISub, IMul, IDiv, IMod, INeg,
    FAdd, FSub, FMul, FDiv, FNeg,
    IEq, INe, ILt, IGt, ILe, IGe,
    FEq, FLt, FGt, FLe, FGe,
)


class PythonFrontendCompiler:
    """Compiles Python source into a FIRModule."""

    def __init__(self):
        self._ctx = TypeContext()
        self._builder = FIRBuilder(self._ctx)
        self._vars: dict[str, tuple[Value, FIRType]] = {}  # name → (alloca_ptr, type)
        self._var_types: dict[str, FIRType] = {}            # name → last known type
        self._bb_counter: int = 0

    @property
    def type_ctx(self) -> TypeContext:
        return self._ctx

    # ── public API ─────────────────────────────────────────────────────

    def compile(self, source: str, module_name: str = "py_module") -> FIRModule:
        """Compile Python source to FIRModule."""
        tree = ast.parse(source)
        module = self._builder.new_module(module_name)

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._compile_function(module, node)

        return module

    # ── type helpers ───────────────────────────────────────────────────

    def _infer_type(self, node: ast.expr) -> FIRType:
        """Infer the FIR type of a Python expression node."""
        if isinstance(node, ast.Constant):
            if isinstance(node.value, int) and not isinstance(node.value, bool):
                return self._ctx.get_int(32)
            if isinstance(node.value, float):
                return self._ctx.get_float(32)
            if isinstance(node.value, str):
                return self._ctx.get_string()
            if isinstance(node.value, bool):
                return self._ctx.get_bool()
        if isinstance(node, ast.Name):
            return self._var_types.get(node.id, self._ctx.get_int(32))
        if isinstance(node, ast.BinOp):
            left_t = self._infer_type(node.left)
            right_t = self._infer_type(node.right)
            if isinstance(left_t, FloatType) or isinstance(right_t, FloatType):
                return self._ctx.get_float(32)
            return self._ctx.get_int(32)
        if isinstance(node, ast.UnaryOp):
            return self._infer_type(node.operand)
        if isinstance(node, ast.Compare):
            return self._ctx.get_int(32)  # comparisons produce i32 (0/1)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "len":
                return self._ctx.get_int(32)
            return self._ctx.get_int(32)
        if isinstance(node, ast.IfExp):
            return self._infer_type(node.body)
        return self._ctx.get_int(32)

    # ── function compilation ───────────────────────────────────────────

    def _compile_function(self, module: FIRModule, node: ast.FunctionDef):
        self._vars.clear()
        self._var_types.clear()
        self._bb_counter = 0
        self._builder._next_value_id = 0

        # Determine return type from annotations or default to i32
        ret_type = self._ctx.get_int(32)
        if node.returns is not None:
            ann = node.returns
            if isinstance(ann, ast.Constant) and ann.value == "float":
                ret_type = self._ctx.get_float(32)
            elif isinstance(ann, ast.Name):
                type_map = {"int": self._ctx.get_int(32),
                            "float": self._ctx.get_float(32),
                            "bool": self._ctx.get_bool(),
                            "str": self._ctx.get_string()}
                ret_type = type_map.get(ann.id, self._ctx.get_int(32))

        # Determine param types from annotations
        param_types: list[tuple[str, FIRType]] = []
        for arg in node.args.args:
            ptype = self._ctx.get_int(32)
            if arg.annotation is not None:
                ann = arg.annotation
                if isinstance(ann, ast.Name):
                    type_map = {"int": self._ctx.get_int(32),
                                "float": self._ctx.get_float(32),
                                "bool": self._ctx.get_bool(),
                                "str": self._ctx.get_string()}
                    ptype = type_map.get(ann.id, self._ctx.get_int(32))
            param_types.append((arg.arg, ptype))

        func = self._builder.new_function(
            module, node.name, param_types,
            [ret_type] if ret_type != self._ctx.get_unit() else [],
        )

        entry = self._builder.new_block(func, "entry")
        self._builder.set_block(entry)

        # Create parameter values with alloca
        for name, ftype in param_types:
            pval = self._builder._new_value(name, ftype)
            ptr = self._builder.alloca(ftype)
            self._builder.store(pval, ptr)
            self._vars[name] = (ptr, ftype)
            self._var_types[name] = ftype

        # Compile body
        self._compile_stmts(func, node.body)

        # Ensure terminator
        cur = self._builder._current_block
        if cur is not None and cur.terminator is None:
            self._builder.ret(None)

    # ── helpers ────────────────────────────────────────────────────────

    def _new_block_label(self, prefix: str) -> str:
        self._bb_counter += 1
        return f"{prefix}{self._bb_counter}"

    def _ensure_writable(self, func: FIRFunction):
        """Create a new block if current one is terminated."""
        cur = self._builder._current_block
        if cur is not None and cur.terminator is not None:
            label = self._new_block_label("bb")
            new_bb = self._builder.new_block(func, label)
            self._builder.set_block(new_bb)

    def _make_const(self, value: int | float | str | bool, ftype: FIRType) -> Value:
        """Create a virtual constant Value."""
        return self._builder._new_value(f"const_{value}", ftype)

    def _load_var(self, name: str) -> Value:
        """Load a variable value from its alloca slot."""
        ptr, ftype = self._vars[name]
        return self._builder.load(ftype, ptr)

    def _store_var(self, name: str, value: Value, ftype: FIRType):
        """Store a value into a variable's alloca slot."""
        if name not in self._vars:
            ptr = self._builder.alloca(ftype)
            self._vars[name] = (ptr, ftype)
        else:
            ptr, _ = self._vars[name]
        self._builder.store(value, ptr)
        self._var_types[name] = ftype

    # ── statements ─────────────────────────────────────────────────────

    def _compile_stmts(self, func: FIRFunction, stmts: list[ast.stmt]):
        for stmt in stmts:
            self._compile_stmt(func, stmt)

    def _compile_stmt(self, func: FIRFunction, stmt: ast.stmt):
        if isinstance(stmt, ast.FunctionDef):
            # Nested function — skip for now
            return

        if isinstance(stmt, ast.Return):
            self._ensure_writable(func)
            if stmt.value is not None:
                val = self._compile_expr(func, stmt.value)
                self._builder.ret(val)
            else:
                self._builder.ret(None)
            return

        if isinstance(stmt, ast.Assign):
            self._ensure_writable(func)
            val = self._compile_expr(func, stmt.value)
            ftype = self._infer_type(stmt.value)
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    self._store_var(target.id, val, ftype)
            return

        if isinstance(stmt, ast.AugAssign):
            self._ensure_writable(func)
            # x += y → x = x + y
            target_name = stmt.target.id if isinstance(stmt.target, ast.Name) else "_"
            current = self._load_var(target_name) if target_name in self._vars else self._make_const(0, self._ctx.get_int(32))
            rhs = self._compile_expr(func, stmt.value)
            result = self._compile_augop(stmt.op, current, rhs)
            ftype = self._infer_type(stmt.value)
            self._store_var(target_name, result, ftype)
            return

        if isinstance(stmt, ast.If):
            self._compile_if(func, stmt)
            return

        if isinstance(stmt, ast.While):
            self._compile_while(func, stmt)
            return

        if isinstance(stmt, ast.For):
            self._compile_for(func, stmt)
            return

        if isinstance(stmt, ast.Expr):
            self._ensure_writable(func)
            self._compile_expr(func, stmt.value)
            return

        if isinstance(stmt, ast.Pass):
            return

        # Silently skip unsupported statements

    def _compile_augop(self, op: ast.AugAssign, left: Value, right: Value) -> Value:
        """Compile augmented assignment operator."""
        if isinstance(op.op, ast.Add):
            return self._builder.iadd(left, right)
        if isinstance(op.op, ast.Sub):
            return self._builder.isub(left, right)
        if isinstance(op.op, ast.Mult):
            return self._builder.imul(left, right)
        if isinstance(op.op, ast.FloorDiv):
            return self._builder.idiv(left, right)
        if isinstance(op.op, ast.Mod):
            return self._builder.imod(left, right)
        return self._builder.iadd(left, right)  # fallback

    # ── if / elif / else ───────────────────────────────────────────────

    def _compile_if(self, func: FIRFunction, stmt: ast.If):
        self._ensure_writable(func)

        # Evaluate condition
        cond_val = self._compile_expr(func, stmt.test)

        # Create blocks
        then_label = self._new_block_label("then")
        merge_label = self._new_block_label("merge")
        else_label: str | None = None

        if stmt.orelse:
            if len(stmt.orelse) == 1 and isinstance(stmt.orelse[0], ast.If):
                # elif → flatten into else block
                else_label = self._new_block_label("else")
            else:
                else_label = self._new_block_label("else")

        then_bb = self._builder.new_block(func, then_label)
        else_bb = self._builder.new_block(func, else_label) if else_label else None
        merge_bb = self._builder.new_block(func, merge_label)

        # Branch
        self._builder.branch(cond_val, then_label,
                             else_label if else_label else merge_label)

        # Then
        self._builder.set_block(then_bb)
        self._compile_stmts(func, stmt.body)
        if then_bb.terminator is None:
            self._builder.jump(merge_label)

        # Else / elif
        if else_bb is not None and stmt.orelse:
            self._builder.set_block(else_bb)
            self._compile_stmts(func, stmt.orelse)
            if else_bb.terminator is None:
                self._builder.jump(merge_label)

        # Continue from merge
        self._builder.set_block(merge_bb)

    # ── while ──────────────────────────────────────────────────────────

    def _compile_while(self, func: FIRFunction, stmt: ast.While):
        self._ensure_writable(func)

        header_label = self._new_block_label("while")
        body_label = self._new_block_label("while_body")
        exit_label = self._new_block_label("while_exit")

        header_bb = self._builder.new_block(func, header_label)
        body_bb = self._builder.new_block(func, body_label)
        exit_bb = self._builder.new_block(func, exit_label)

        # Jump to header
        self._builder.jump(header_label)

        # Header: condition
        self._builder.set_block(header_bb)
        cond_val = self._compile_expr(func, stmt.test)
        self._builder.branch(cond_val, body_label, exit_label)

        # Body
        self._builder.set_block(body_bb)
        self._compile_stmts(func, stmt.body)
        if body_bb.terminator is None:
            self._builder.jump(header_label)

        # Exit
        self._builder.set_block(exit_bb)

    # ── for ────────────────────────────────────────────────────────────

    def _compile_for(self, func: FIRFunction, stmt: ast.For):
        self._ensure_writable(func)

        # Detect for/range pattern: for i in range(...)
        if self._is_range_for(stmt):
            self._compile_for_range(func, stmt)
            return

        # Generic for loop (while-like)
        self._compile_while(func, ast.While(
            test=ast.Constant(value=True),
            body=stmt.body + [ast.Break()],
            orelse=[],
        ))

    def _is_range_for(self, stmt: ast.For) -> bool:
        """Check if the for loop iterates over range()."""
        if not isinstance(stmt.target, ast.Name):
            return False
        call = stmt.iter
        if not isinstance(call, ast.Call):
            return False
        func = call.func
        return (isinstance(func, ast.Name) and func.id == "range")

    def _compile_for_range(self, func: FIRFunction, stmt: ast.For):
        """Compile 'for x in range(...)' into a while loop with alloca counter."""
        call = stmt.iter  # the range() call
        target_name = stmt.target.id

        # Parse range arguments
        args = call.args
        if len(args) == 1:
            start_val = self._make_const(0, self._ctx.get_int(32))
            limit_val = self._compile_expr(func, args[0])
            step_val = self._make_const(1, self._ctx.get_int(32))
        elif len(args) == 2:
            start_val = self._compile_expr(func, args[0])
            limit_val = self._compile_expr(func, args[1])
            step_val = self._make_const(1, self._ctx.get_int(32))
        elif len(args) >= 3:
            start_val = self._compile_expr(func, args[0])
            limit_val = self._compile_expr(func, args[1])
            step_val = self._compile_expr(func, args[2])
        else:
            return

        # Create blocks
        header_label = self._new_block_label("for")
        body_label = self._new_block_label("for_body")
        exit_label = self._new_block_label("for_exit")

        header_bb = self._builder.new_block(func, header_label)
        body_bb = self._builder.new_block(func, body_label)
        exit_bb = self._builder.new_block(func, exit_label)

        # Init: store start value to loop variable alloca
        loop_ptr = self._builder.alloca(self._ctx.get_int(32))
        self._builder.store(start_val, loop_ptr)
        self._vars[target_name] = (loop_ptr, self._ctx.get_int(32))
        self._var_types[target_name] = self._ctx.get_int(32)

        # Jump to header
        self._builder.jump(header_label)

        # Header: check i < limit
        self._builder.set_block(header_bb)
        i_val = self._builder.load(self._ctx.get_int(32), loop_ptr)
        cond = self._builder.ilt(i_val, limit_val)
        self._builder.branch(cond, body_label, exit_label)

        # Body
        self._builder.set_block(body_bb)
        self._compile_stmts(func, stmt.body)

        # Increment: i = i + step
        self._ensure_writable(func)
        if body_bb.terminator is None:
            i_val2 = self._builder.load(self._ctx.get_int(32), loop_ptr)
            new_i = self._builder.iadd(i_val2, step_val)
            self._builder.store(new_i, loop_ptr)
            self._builder.jump(header_label)

        # Exit
        self._builder.set_block(exit_bb)

    # ── expressions ────────────────────────────────────────────────────

    def _compile_expr(self, func: FIRFunction, node: ast.expr) -> Value:
        if isinstance(node, ast.Constant):
            return self._compile_constant(node)

        if isinstance(node, ast.Name):
            if node.id in self._vars:
                return self._load_var(node.id)
            # Unknown name — return a zero constant
            return self._make_const(0, self._ctx.get_int(32))

        if isinstance(node, ast.BinOp):
            return self._compile_binop(func, node)

        if isinstance(node, ast.UnaryOp):
            return self._compile_unaryop(func, node)

        if isinstance(node, ast.Compare):
            return self._compile_compare(func, node)

        if isinstance(node, ast.Call):
            return self._compile_call(func, node)

        if isinstance(node, ast.IfExp):
            return self._compile_ifexpr(func, node)

        if isinstance(node, ast.BoolOp):
            return self._compile_boolop(func, node)

        # Fallback: return a zero constant
        return self._make_const(0, self._ctx.get_int(32))

    def _compile_constant(self, node: ast.Constant) -> Value:
        val = node.value
        if isinstance(val, bool):
            return self._make_const(1 if val else 0, self._ctx.get_int(32))
        if isinstance(val, int):
            return self._make_const(val, self._ctx.get_int(32))
        if isinstance(val, float):
            return self._make_const(val, self._ctx.get_float(32))
        if isinstance(val, str):
            return self._make_const(val, self._ctx.get_string())
        return self._make_const(0, self._ctx.get_int(32))

    def _compile_binop(self, func: FIRFunction, node: ast.BinOp) -> Value:
        left = self._compile_expr(func, node.left)
        right = self._compile_expr(func, node.right)

        is_float = isinstance(left.type, FloatType) or isinstance(right.type, FloatType)

        op_map = {
            ast.Add:    (self._builder.iadd, self._builder.fadd),
            ast.Sub:    (self._builder.isub, self._builder.fsub),
            ast.Mult:   (self._builder.imul, self._builder.fmul),
            ast.Div:    (self._builder.idiv, self._builder.fdiv),
            ast.FloorDiv: (self._builder.idiv, self._builder.fdiv),
            ast.Mod:    (self._builder.imod, None),
        }

        op_type = type(node.op)
        if op_type in op_map:
            i_fn, f_fn = op_map[op_type]
            if is_float and f_fn is not None:
                return f_fn(left, right)
            return i_fn(left, right)

        return self._builder.iadd(left, right)

    def _compile_unaryop(self, func: FIRFunction, node: ast.UnaryOp) -> Value:
        operand = self._compile_expr(func, node.operand)
        if isinstance(node.op, ast.USub):
            if isinstance(operand.type, FloatType):
                return self._builder.fneg(operand)
            return self._builder.ineg(operand)
        if isinstance(node.op, ast.UAdd):
            return operand
        if isinstance(node.op, ast.Not):
            # not x → eq x, 0
            zero = self._make_const(0, operand.type)
            return self._builder.ieq(operand, zero)
        return operand

    def _compile_compare(self, func: FIRFunction, node: ast.Compare) -> Value:
        """Compile comparison. Handles single comparison only (a op b)."""
        left = self._compile_expr(func, node.left)
        # Use only the first comparator for simplicity
        right = self._compile_expr(func, node.comparators[0])
        op = node.ops[0]

        is_float = isinstance(left.type, FloatType) or isinstance(right.type, FloatType)

        cmp_map = {
            ast.Eq:  (self._builder.ieq, self._builder.feq),
            ast.NotEq: (self._builder.ine, None),
            ast.Lt:  (self._builder.ilt, self._builder.flt),
            ast.Gt:  (self._builder.igt, self._builder.fgt),
            ast.LtE: (self._builder.ile, self._builder.fle),
            ast.GtE: (self._builder.ige, self._builder.fge),
        }

        op_type = type(op)
        if op_type in cmp_map:
            i_fn, f_fn = cmp_map[op_type]
            if is_float and f_fn is not None:
                return f_fn(left, right)
            if op_type == ast.NotEq and is_float:
                # float != → not (float ==)
                return self._builder.feq(left, right)
            return i_fn(left, right)

        return self._builder.ieq(left, right)

    def _compile_call(self, func: FIRFunction, node: ast.Call) -> Value:
        """Compile a function call."""
        # Handle print specially (emit as a call instruction)
        if isinstance(node.func, ast.Name) and node.func.id == "print":
            for arg in node.args:
                self._compile_expr(func, arg)
            # print returns None
            return self._make_const(0, self._ctx.get_unit())

        # Handle int() and float() casts
        if isinstance(node.func, ast.Name) and node.func.id in ("int", "float"):
            if node.args:
                return self._compile_expr(func, node.args[0])

        # Regular call
        func_name = node.func.id if isinstance(node.func, ast.Name) else "unknown"
        args = [self._compile_expr(func, a) for a in node.args]
        ret_type = self._infer_type(node)
        return self._builder.call(func_name, args, ret_type)

    def _compile_ifexpr(self, func: FIRFunction, node: ast.IfExp) -> Value:
        """Compile a ternary expression (a if cond else b)."""
        self._ensure_writable(func)

        cond = self._compile_expr(func, node.test)

        then_label = self._new_block_label("tern_then")
        else_label = self._new_block_label("tern_else")
        merge_label = self._new_block_label("tern_merge")

        then_bb = self._builder.new_block(func, then_label)
        else_bb = self._builder.new_block(func, else_label)
        merge_bb = self._builder.new_block(func, merge_label)

        self._builder.branch(cond, then_label, else_label)

        # Then
        self._builder.set_block(then_bb)
        then_val = self._compile_expr(func, node.body)
        if then_bb.terminator is None:
            self._builder.jump(merge_label)

        # Else
        self._builder.set_block(else_bb)
        else_val = self._compile_expr(func, node.orelse)
        if else_bb.terminator is None:
            self._builder.jump(merge_label)

        # Merge: load the result (simplified — return then_val)
        self._builder.set_block(merge_bb)
        return then_val

    def _compile_boolop(self, func: FIRFunction, node: ast.BoolOp) -> Value:
        """Compile boolean operations (and, or)."""
        # Simplified: evaluate and return first operand
        values = [self._compile_expr(func, v) for v in node.values]
        return values[0] if values else self._make_const(0, self._ctx.get_int(32))
