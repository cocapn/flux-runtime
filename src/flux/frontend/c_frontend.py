"""C Frontend Compiler — simple C subset to FIR via recursive descent.

Handles: int/float functions, variables, if/else, while, for, return,
arithmetic (+,-,*,/,%), comparison (==,!=,<,>,<=,>=), calls, int/float literals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Union

from flux.fir.types import TypeContext, FIRType, IntType, FloatType, UnitType
from flux.fir.values import Value
from flux.fir.builder import FIRBuilder
from flux.fir.blocks import FIRModule, FIRFunction, FIRBlock
from flux.fir.instructions import (
    IAdd, ISub, IMul, IDiv, IMod, INeg,
    FAdd, FSub, FMul, FDiv, FNeg,
    IEq, INe, ILt, IGt, ILe, IGe,
    FEq, FLt, FGt, FLe, FGe,
)


# ── C AST Node Types ────────────────────────────────────────────────────────

CExpr = Union["CIntLiteral", "CFloatLiteral", "CVarRef", "CBinOp",
              "CUnaryOp", "CCall"]
CStmt = Union["CReturn", "CVarDecl", "CAssign", "CIf", "CWhile",
              "CFor", "CExprStmt"]


@dataclass
class CIntLiteral:
    value: int


@dataclass
class CFloatLiteral:
    value: float


@dataclass
class CVarRef:
    name: str


@dataclass
class CBinOp:
    op: str       # +, -, *, /, %, ==, !=, <, >, <=, >=
    left: CExpr
    right: CExpr


@dataclass
class CUnaryOp:
    op: str       # -, +
    operand: CExpr


@dataclass
class CCall:
    func_name: str
    args: list


@dataclass
class CReturn:
    value: Optional[CExpr]


@dataclass
class CVarDecl:
    type_name: str
    var_name: str
    init_value: Optional[CExpr]


@dataclass
class CAssign:
    var_name: str
    value: CExpr


@dataclass
class CIf:
    condition: CExpr
    then_body: list
    else_body: Optional[list]


@dataclass
class CWhile:
    condition: CExpr
    body: list


@dataclass
class CFor:
    init: Optional[CStmt]
    condition: Optional[CExpr]
    update: Optional[CStmt]
    body: list


@dataclass
class CExprStmt:
    expr: CExpr


@dataclass
class CFunction:
    return_type: str
    name: str
    params: list        # list of (type_name: str, param_name: str)
    body: list          # list of CStmt


# ── Tokenizer ───────────────────────────────────────────────────────────────

_TOKEN_SPEC = [
    ("FLOAT_LIT",    r"\d+\.\d*"),
    ("INT_LIT",      r"\d+"),
    ("IDENT",        r"[a-zA-Z_]\w*"),
    ("LE",           r"<="),
    ("GE",           r">="),
    ("EQ",           r"=="),
    ("NEQ",          r"!="),
    ("LT",           r"<"),
    ("GT",           r">"),
    ("PLUS",         r"\+"),
    ("MINUS",        r"-"),
    ("STAR",         r"\*"),
    ("SLASH",        r"/"),
    ("PERCENT",      r"%"),
    ("ASSIGN",       r"="),
    ("LPAREN",       r"\("),
    ("RPAREN",       r"\)"),
    ("LBRACE",       r"\{"),
    ("RBRACE",       r"\}"),
    ("SEMI",         r";"),
    ("COMMA",        r","),
    ("LINE_COMMENT", r"//[^\n]*"),
    ("BLOCK_COMMENT",r"/\*[\s\S]*?\*/"),
    ("SKIP",         r"[ \t\n\r]+"),
]

_KEYWORDS = {"int", "float", "void", "if", "else", "while", "for", "return"}

_TOKEN_RE = re.compile(
    "|".join(f"(?P<{name}>{pattern})" for name, pattern in _TOKEN_SPEC),
    re.DOTALL,
)


@dataclass
class Token:
    kind: str
    value: str
    pos: int


class CTokenizer:
    """Tokenize a C source string."""

    def __init__(self, source: str):
        self._source = source

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []
        for m in _TOKEN_RE.finditer(self._source):
            kind = m.lastgroup
            value = m.group()
            if kind in ("SKIP", "LINE_COMMENT", "BLOCK_COMMENT"):
                continue
            if kind == "IDENT" and value in _KEYWORDS:
                kind = value.upper()  # 'int' → 'INT', 'if' → 'IF', etc.
            if kind == "INT_LIT":
                # strip potential type suffixes (L, U, LL, etc.)
                value = re.sub(r"[uUlL]+$", "", value)
            tokens.append(Token(kind=kind, value=value, pos=m.start()))
        tokens.append(Token(kind="EOF", value="", pos=len(self._source)))
        return tokens


# ── Parser ──────────────────────────────────────────────────────────────────

class CParseError(Exception):
    pass


class CParser:
    """Recursive descent parser for a simple C subset."""

    def __init__(self, tokens: list[Token]):
        self._tokens = tokens
        self._pos = 0

    # ── helpers ────────────────────────────────────────────────────────

    def _peek(self) -> Token:
        return self._tokens[self._pos]

    def _advance(self) -> Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _expect(self, kind: str) -> Token:
        tok = self._advance()
        if tok.kind != kind:
            raise CParseError(
                f"Expected {kind}, got {tok.kind} ('{tok.value}') at pos {tok.pos}"
            )
        return tok

    def _match(self, *kinds: str) -> Optional[Token]:
        if self._peek().kind in kinds:
            return self._advance()
        return None

    # ── public API ─────────────────────────────────────────────────────

    def parse(self) -> list[CFunction]:
        """Parse the full translation unit (list of function definitions)."""
        functions: list[CFunction] = []
        while self._peek().kind != "EOF":
            functions.append(self._parse_function())
        return functions

    # ── function ───────────────────────────────────────────────────────

    def _parse_function(self) -> CFunction:
        ret_type = self._parse_type_specifier()
        name_tok = self._expect("IDENT")
        self._expect("LPAREN")
        params = self._parse_param_list()
        self._expect("RPAREN")
        body = self._parse_block()
        return CFunction(
            return_type=ret_type,
            name=name_tok.value,
            params=params,
            body=body,
        )

    def _parse_type_specifier(self) -> str:
        tok = self._advance()
        if tok.kind in ("INT", "FLOAT", "VOID"):
            return tok.value
        if tok.kind == "IDENT":
            return tok.value  # user-defined type
        raise CParseError(
            f"Expected type specifier, got {tok.kind} ('{tok.value}')"
        )

    def _parse_param_list(self) -> list[tuple[str, str]]:
        params: list[tuple[str, str]] = []
        if self._peek().kind == "RPAREN":
            return params
        params.append(self._parse_param())
        while self._match("COMMA"):
            params.append(self._parse_param())
        return params

    def _parse_param(self) -> tuple[str, str]:
        type_name = self._parse_type_specifier()
        name_tok = self._expect("IDENT")
        return (type_name, name_tok.value)

    # ── statements ─────────────────────────────────────────────────────

    def _parse_block(self) -> list:
        self._expect("LBRACE")
        stmts: list = []
        while self._peek().kind != "RBRACE":
            stmts.append(self._parse_stmt())
        self._expect("RBRACE")
        return stmts

    def _parse_stmt(self) -> CStmt:
        tok = self._peek()

        # return
        if tok.kind == "RETURN":
            return self._parse_return()

        # if
        if tok.kind == "IF":
            return self._parse_if()

        # while
        if tok.kind == "WHILE":
            return self._parse_while()

        # for
        if tok.kind == "FOR":
            return self._parse_for()

        # variable declaration: type_name identifier ...
        if tok.kind in ("INT", "FLOAT", "VOID") or (
            tok.kind == "IDENT" and self._is_type_name(tok.value)
        ):
            return self._parse_var_decl_or_assign()

        # assignment or expression statement: identifier = ... | expr ;
        if tok.kind == "IDENT":
            return self._parse_assign_or_expr()

        # expression statement
        expr = self._parse_expr()
        self._expect("SEMI")
        return CExprStmt(expr)

    def _is_type_name(self, name: str) -> bool:
        """Heuristic: check if a following token could be an identifier."""
        return False  # simple C subset — only built-in types for now

    def _parse_return(self) -> CReturn:
        self._expect("RETURN")
        if self._peek().kind == "SEMI":
            self._advance()
            return CReturn(value=None)
        expr = self._parse_expr()
        self._expect("SEMI")
        return CReturn(value=expr)

    def _parse_if(self) -> CIf:
        self._expect("IF")
        self._expect("LPAREN")
        condition = self._parse_expr()
        self._expect("RPAREN")
        then_body = self._parse_block()
        else_body = None
        if self._match("ELSE"):
            if self._peek().kind == "IF":
                else_body = [self._parse_if()]
            else:
                else_body = self._parse_block()
        return CIf(condition=condition, then_body=then_body, else_body=else_body)

    def _parse_while(self) -> CWhile:
        self._expect("WHILE")
        self._expect("LPAREN")
        condition = self._parse_expr()
        self._expect("RPAREN")
        body = self._parse_block()
        return CWhile(condition=condition, body=body)

    def _parse_for(self) -> CFor:
        self._expect("FOR")
        self._expect("LPAREN")

        # init
        init = None
        if self._peek().kind != "SEMI":
            if self._peek().kind in ("INT", "FLOAT", "VOID"):
                init = self._parse_var_decl()  # includes SEMI
            else:
                init = self._parse_assign_stmt()  # includes SEMI
        else:
            self._advance()  # consume SEMI

        # condition
        condition = None
        if self._peek().kind != "SEMI":
            condition = self._parse_expr()
        self._expect("SEMI")

        # update
        update = None
        if self._peek().kind != "RPAREN":
            if self._peek().kind == "IDENT" and self._pos + 1 < len(self._tokens) \
                    and self._tokens[self._pos + 1].kind == "ASSIGN":
                update = self._parse_assign_stmt()
            else:
                expr = self._parse_expr()
                update = CExprStmt(expr)
        self._expect("RPAREN")

        body = self._parse_block()
        return CFor(init=init, condition=condition, update=update, body=body)

    def _parse_var_decl(self) -> CVarDecl:
        """Parse a variable declaration (including the semicolon)."""
        type_name = self._parse_type_specifier()
        name_tok = self._expect("IDENT")
        init_value = None
        if self._match("ASSIGN"):
            init_value = self._parse_expr()
        self._expect("SEMI")
        return CVarDecl(
            type_name=type_name,
            var_name=name_tok.value,
            init_value=init_value,
        )

    def _parse_var_decl_or_assign(self) -> CStmt:
        """Distinguish variable declaration from assignment at statement level."""
        # Look ahead to determine: type ident ... vs ident = ...
        # For built-in types, we already know it's a declaration.
        type_name = self._parse_type_specifier()
        name_tok = self._expect("IDENT")

        if self._match("ASSIGN"):
            init_value = self._parse_expr()
            self._expect("SEMI")
            return CVarDecl(
                type_name=type_name,
                var_name=name_tok.value,
                init_value=init_value,
            )
        self._expect("SEMI")
        return CVarDecl(type_name=type_name, var_name=name_tok.value, init_value=None)

    def _parse_assign_stmt(self) -> CAssign:
        """Parse assignment (including semicolon)."""
        name_tok = self._expect("IDENT")
        self._expect("ASSIGN")
        value = self._parse_expr()
        self._expect("SEMI")
        return CAssign(var_name=name_tok.value, value=value)

    def _parse_assign_or_expr(self) -> CStmt:
        """Parse an assignment or expression statement."""
        name_tok = self._advance()  # consume IDENT
        if self._match("ASSIGN"):
            value = self._parse_expr()
            self._expect("SEMI")
            return CAssign(var_name=name_tok.value, value=value)

        # It was the start of an expression — reconstruct
        self._pos -= 1  # put back the IDENT
        expr = self._parse_expr()
        self._expect("SEMI")
        return CExprStmt(expr)

    # ── expressions (precedence climbing) ──────────────────────────────

    def _parse_expr(self) -> CExpr:
        return self._parse_comparison()

    def _parse_comparison(self) -> CExpr:
        left = self._parse_additive()
        while self._peek().kind in ("EQ", "NEQ", "LT", "GT", "LE", "GE"):
            op_tok = self._advance()
            right = self._parse_additive()
            op_map = {
                "EQ": "==", "NEQ": "!=", "LT": "<", "GT": ">",
                "LE": "<=", "GE": ">=",
            }
            left = CBinOp(op=op_map[op_tok.kind], left=left, right=right)
        return left

    def _parse_additive(self) -> CExpr:
        left = self._parse_multiplicative()
        while self._peek().kind in ("PLUS", "MINUS"):
            op_tok = self._advance()
            right = self._parse_multiplicative()
            left = CBinOp(op=op_tok.value, left=left, right=right)
        return left

    def _parse_multiplicative(self) -> CExpr:
        left = self._parse_unary()
        while self._peek().kind in ("STAR", "SLASH", "PERCENT"):
            op_tok = self._advance()
            right = self._parse_unary()
            left = CBinOp(op=op_tok.value, left=left, right=right)
        return left

    def _parse_unary(self) -> CExpr:
        if self._peek().kind == "MINUS":
            self._advance()
            operand = self._parse_unary()
            return CUnaryOp(op="-", operand=operand)
        if self._peek().kind == "PLUS":
            self._advance()
            return self._parse_unary()
        return self._parse_primary()

    def _parse_primary(self) -> CExpr:
        tok = self._peek()

        # parenthesized expression
        if tok.kind == "LPAREN":
            self._advance()
            expr = self._parse_expr()
            self._expect("RPAREN")
            return expr

        # integer literal
        if tok.kind == "INT_LIT":
            self._advance()
            return CIntLiteral(value=int(tok.value))

        # float literal
        if tok.kind == "FLOAT_LIT":
            self._advance()
            return CFloatLiteral(value=float(tok.value))

        # function call or variable reference
        if tok.kind == "IDENT":
            self._advance()
            if self._peek().kind == "LPAREN":
                self._advance()  # consume LPAREN
                args: list = []
                if self._peek().kind != "RPAREN":
                    args.append(self._parse_expr())
                    while self._match("COMMA"):
                        args.append(self._parse_expr())
                self._expect("RPAREN")
                return CCall(func_name=tok.value, args=args)
            return CVarRef(name=tok.value)

        raise CParseError(
            f"Unexpected token {tok.kind} ('{tok.value}') at pos {tok.pos}"
        )


# ── FIR Code Generator ──────────────────────────────────────────────────────

class CFrontendCompiler:
    """Compiles a C source string into a FIRModule."""

    def __init__(self):
        self._ctx = TypeContext()
        self._builder = FIRBuilder(self._ctx)
        self._vars: dict[str, tuple[Value, FIRType]] = {}  # name → (alloca_ptr, type)
        self._bb_counter: int = 0

    @property
    def type_ctx(self) -> TypeContext:
        return self._ctx

    # ── public API ─────────────────────────────────────────────────────

    def compile(self, source: str, module_name: str = "c_module") -> FIRModule:
        """Compile C source to FIRModule."""
        tokens = CTokenizer(source).tokenize()
        functions = CParser(tokens).parse()
        module = self._builder.new_module(module_name)
        for func_def in functions:
            self._compile_function(module, func_def)
        return module

    # ── type mapping ───────────────────────────────────────────────────

    def _map_type(self, type_name: str) -> FIRType:
        if type_name == "int":
            return self._ctx.get_int(32)
        if type_name == "float":
            return self._ctx.get_float(32)
        if type_name == "void":
            return self._ctx.get_unit()
        return self._ctx.get_int(32)  # default: i32

    # ── function compilation ───────────────────────────────────────────

    def _compile_function(self, module: FIRModule, func_def: CFunction):
        self._vars.clear()
        self._bb_counter = 0
        self._builder._next_value_id = 0

        ret_type = self._map_type(func_def.return_type)
        param_types = [(name, self._map_type(t)) for t, name in func_def.params]

        func = self._builder.new_function(module, func_def.name, param_types,
                                          [ret_type] if ret_type != self._ctx.get_unit() else [])

        entry = self._builder.new_block(func, "entry")
        self._builder.set_block(entry)

        # Create parameter values and alloca slots for them
        for name, ftype in param_types:
            pval = self._builder._new_value(name, ftype)
            ptr = self._builder.alloca(ftype)
            self._builder.store(pval, ptr)
            self._vars[name] = (ptr, ftype)

        # Compile function body
        self._compile_stmts(func, func_def.body)

        # Ensure the function has a terminator in the entry block
        if entry.terminator is None:
            # Check the last block we're in
            cur = self._builder._current_block
            if cur is not None and cur.terminator is None:
                self._builder.ret(None)

    # ── helpers ────────────────────────────────────────────────────────

    def _new_block_label(self, prefix: str) -> str:
        self._bb_counter += 1
        return f"{prefix}{self._bb_counter}"

    def _ensure_writable(self, func: FIRFunction):
        """If the current block already has a terminator, create a new block."""
        cur = self._builder._current_block
        if cur is not None and cur.terminator is not None:
            label = self._new_block_label("bb")
            new_bb = self._builder.new_block(func, label)
            self._builder.set_block(new_bb)

    def _make_const(self, value: int | float, ftype: FIRType) -> Value:
        """Create a virtual constant Value."""
        return self._builder._new_value(f"const_{value}", ftype)

    def _load_var(self, name: str) -> Value:
        """Load a variable's value from its alloca slot."""
        ptr, ftype = self._vars[name]
        return self._builder.load(ftype, ptr)

    def _store_var(self, name: str, value: Value):
        """Store a value into a variable's alloca slot."""
        ptr, _ = self._vars[name]
        self._builder.store(value, ptr)

    def _decl_var(self, name: str, ftype: FIRType, init_value: Value | None = None):
        """Declare a new variable with an alloca slot."""
        ptr = self._builder.alloca(ftype)
        if init_value is not None:
            self._builder.store(init_value, ptr)
        self._vars[name] = (ptr, ftype)

    # ── statements ─────────────────────────────────────────────────────

    def _compile_stmts(self, func: FIRFunction, stmts: list):
        for stmt in stmts:
            self._compile_stmt(func, stmt)

    def _compile_stmt(self, func: FIRFunction, stmt: CStmt):
        if isinstance(stmt, CReturn):
            self._ensure_writable(func)
            if stmt.value is not None:
                val = self._compile_expr(stmt.value)
                self._builder.ret(val)
            else:
                self._builder.ret(None)

        elif isinstance(stmt, CVarDecl):
            self._ensure_writable(func)
            ftype = self._map_type(stmt.type_name)
            init_val = None
            if stmt.init_value is not None:
                init_val = self._compile_expr(stmt.init_value)
            self._decl_var(stmt.var_name, ftype, init_val)

        elif isinstance(stmt, CAssign):
            self._ensure_writable(func)
            val = self._compile_expr(stmt.value)
            self._store_var(stmt.var_name, val)

        elif isinstance(stmt, CExprStmt):
            self._ensure_writable(func)
            self._compile_expr(stmt.expr)

        elif isinstance(stmt, CIf):
            self._compile_if(func, stmt)

        elif isinstance(stmt, CWhile):
            self._compile_while(func, stmt)

        elif isinstance(stmt, CFor):
            self._compile_for(func, stmt)

    def _compile_if(self, func: FIRFunction, stmt: CIf):
        self._ensure_writable(func)

        # Evaluate condition in current block
        cond_val = self._compile_expr(stmt.condition)

        # Create blocks
        then_label = self._new_block_label("then")
        else_label = self._new_block_label("else") if stmt.else_body else None
        merge_label = self._new_block_label("merge")

        then_bb = self._builder.new_block(func, then_label)
        else_bb = self._builder.new_block(func, else_label) if else_label else None
        merge_bb = self._builder.new_block(func, merge_label)

        # Branch
        self._builder.branch(cond_val, then_label,
                             else_label if else_label else merge_label)

        # Then block
        self._builder.set_block(then_bb)
        self._compile_stmts(func, stmt.then_body)
        if then_bb.terminator is None:
            self._builder.jump(merge_label)

        # Else block
        if else_bb is not None:
            self._builder.set_block(else_bb)
            self._compile_stmts(func, stmt.else_body)
            if else_bb.terminator is None:
                self._builder.jump(merge_label)

        # Continue from merge
        self._builder.set_block(merge_bb)

    def _compile_while(self, func: FIRFunction, stmt: CWhile):
        self._ensure_writable(func)

        header_label = self._new_block_label("while")
        body_label = self._new_block_label("while_body")
        exit_label = self._new_block_label("while_exit")

        header_bb = self._builder.new_block(func, header_label)
        body_bb = self._builder.new_block(func, body_label)
        exit_bb = self._builder.new_block(func, exit_label)

        # Jump from current block to header
        self._builder.jump(header_label)

        # Header: evaluate condition
        self._builder.set_block(header_bb)
        cond_val = self._compile_expr(stmt.condition)
        self._builder.branch(cond_val, body_label, exit_label)

        # Body
        self._builder.set_block(body_bb)
        self._compile_stmts(func, stmt.body)
        if body_bb.terminator is None:
            self._builder.jump(header_label)

        # Exit: continue from here
        self._builder.set_block(exit_bb)

    def _compile_for(self, func: FIRFunction, stmt: CFor):
        self._ensure_writable(func)

        # Init
        if stmt.init is not None:
            self._compile_stmt(func, stmt.init)

        # Create blocks
        header_label = self._new_block_label("for")
        body_label = self._new_block_label("for_body")
        exit_label = self._new_block_label("for_exit")

        header_bb = self._builder.new_block(func, header_label)
        body_bb = self._builder.new_block(func, body_label)
        exit_bb = self._builder.new_block(func, exit_label)

        # Jump to header
        self._builder.jump(header_label)

        # Header: evaluate condition
        self._builder.set_block(header_bb)
        if stmt.condition is not None:
            cond_val = self._compile_expr(stmt.condition)
            self._builder.branch(cond_val, body_label, exit_label)
        else:
            self._builder.jump(body_label)

        # Body
        self._builder.set_block(body_bb)
        self._compile_stmts(func, stmt.body)

        # Update
        if stmt.update is not None:
            self._ensure_writable(func)
            if body_bb.terminator is None:
                self._compile_stmt(func, stmt.update)

        if body_bb.terminator is None:
            self._builder.jump(header_label)

        # Exit
        self._builder.set_block(exit_bb)

    # ── expressions ────────────────────────────────────────────────────

    def _compile_expr(self, expr: CExpr) -> Value:
        if isinstance(expr, CIntLiteral):
            return self._make_const(expr.value, self._ctx.get_int(32))

        if isinstance(expr, CFloatLiteral):
            return self._make_const(expr.value, self._ctx.get_float(32))

        if isinstance(expr, CVarRef):
            return self._load_var(expr.name)

        if isinstance(expr, CUnaryOp):
            operand = self._compile_expr(expr.operand)
            if expr.op == "-":
                if isinstance(operand.type, FloatType):
                    return self._builder.fneg(operand)
                return self._builder.ineg(operand)
            return operand  # unary +

        if isinstance(expr, CBinOp):
            return self._compile_binop(expr)

        if isinstance(expr, CCall):
            args = [self._compile_expr(a) for a in expr.args]
            # Determine return type — default i32 if unknown
            ret_type = self._ctx.get_int(32)
            return self._builder.call(expr.func_name, args, ret_type)

        raise CParseError(f"Unknown expression type: {type(expr).__name__}")

    def _compile_binop(self, expr: CBinOp) -> Value:
        left = self._compile_expr(expr.left)
        right = self._compile_expr(expr.right)

        is_float = isinstance(left.type, FloatType) or isinstance(right.type, FloatType)

        # Arithmetic
        arith_ops = {
            "+": (self._builder.iadd, self._builder.fadd),
            "-": (self._builder.isub, self._builder.fsub),
            "*": (self._builder.imul, self._builder.fmul),
            "/": (self._builder.idiv, self._builder.fdiv),
            "%": (self._builder.imod, None),
        }
        if expr.op in arith_ops:
            i_fn, f_fn = arith_ops[expr.op]
            if is_float and f_fn is not None:
                return f_fn(left, right)
            return i_fn(left, right)

        # Comparison
        cmp_ops = {
            "==": (self._builder.ieq, self._builder.feq),
            "!=": (self._builder.ine, None),
            "<":  (self._builder.ilt, self._builder.flt),
            ">":  (self._builder.igt, self._builder.fgt),
            "<=": (self._builder.ile, self._builder.fle),
            ">=": (self._builder.ige, self._builder.fge),
        }
        if expr.op in cmp_ops:
            i_fn, f_fn = cmp_ops[expr.op]
            if is_float and f_fn is not None:
                return f_fn(left, right)
            if expr.op == "!=" and is_float:
                return self._builder.feq(left, right)
            return i_fn(left, right)

        raise CParseError(f"Unknown binary operator: {expr.op}")
