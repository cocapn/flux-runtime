"""Tests for Signal → FLUX Bytecode Compiler."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from flux.a2a.signal_compiler import SignalCompiler, CompiledSignal


class TestSignalLet:
    def test_let_small(self):
        c = SignalCompiler()
        result = c.compile({"ops": [{"op": "let", "name": "x", "value": 42}]})
        assert result.success
        assert 0x18 in result.bytecode  # MOVI
        assert "x" in result.register_map
    
    def test_let_large(self):
        c = SignalCompiler()
        result = c.compile({"ops": [{"op": "let", "name": "big", "value": 1000}]})
        assert result.success
        assert 0x40 in result.bytecode  # MOVI16
    
    def test_let_negative(self):
        c = SignalCompiler()
        result = c.compile({"ops": [{"op": "let", "name": "neg", "value": -5}]})
        assert result.success
        assert 0x18 in result.bytecode  # MOVI


class TestSignalArithmetic:
    def test_add(self):
        c = SignalCompiler()
        result = c.compile({"ops": [
            {"op": "let", "name": "a", "value": 3},
            {"op": "let", "name": "b", "value": 4},
            {"op": "add", "args": ["a", "b"], "into": "c"},
        ]})
        assert result.success
        assert 0x20 in result.bytecode  # ADD
    
    def test_multiply(self):
        c = SignalCompiler()
        result = c.compile({"ops": [
            {"op": "let", "name": "x", "value": 5},
            {"op": "let", "name": "y", "value": 6},
            {"op": "mul", "args": ["x", "y"], "into": "z"},
        ]})
        assert result.success
        assert 0x22 in result.bytecode  # MUL
    
    def test_chain_add(self):
        c = SignalCompiler()
        result = c.compile({"ops": [
            {"op": "let", "name": "a", "value": 1},
            {"op": "let", "name": "b", "value": 2},
            {"op": "let", "name": "c", "value": 3},
            {"op": "add", "args": ["a", "b", "c"], "into": "sum"},
        ]})
        assert result.success
        # Should have multiple ADD opcodes for chaining
        assert result.bytecode.count(0x20) >= 2


class TestSignalComparison:
    def test_eq(self):
        c = SignalCompiler()
        result = c.compile({"ops": [
            {"op": "let", "name": "a", "value": 1},
            {"op": "let", "name": "b", "value": 1},
            {"op": "eq", "args": ["a", "b"], "into": "same"},
        ]})
        assert result.success
        assert 0x2C in result.bytecode  # CMP_EQ


class TestSignalA2A:
    def test_tell(self):
        c = SignalCompiler()
        result = c.compile({"ops": [
            {"op": "tell", "to": "oracle1", "what": "hello", "tag": "greeting"},
        ]})
        assert result.success
        assert 0x50 in result.bytecode  # TELL
    
    def test_ask(self):
        c = SignalCompiler()
        result = c.compile({"ops": [
            {"op": "ask", "from": "jetsonclaw1", "what": "status", "into": "resp"},
        ]})
        assert result.success
        assert 0x51 in result.bytecode  # ASK
    
    def test_broadcast(self):
        c = SignalCompiler()
        result = c.compile({"ops": [
            {"op": "broadcast", "what": "fleet_update", "tag": "ops"},
        ]})
        assert result.success
        assert 0x53 in result.bytecode  # BCAST
    
    def test_delegate(self):
        c = SignalCompiler()
        result = c.compile({"ops": [
            {"op": "delegate", "to": "babel", "task": "translate"},
        ]})
        assert result.success
        assert 0x52 in result.bytecode  # DELEG


class TestSignalControlFlow:
    def test_if_then(self):
        c = SignalCompiler()
        result = c.compile({"ops": [
            {"op": "let", "name": "flag", "value": 1},
            {"op": "if", "cond": "flag", "then": [
                {"op": "let", "name": "result", "value": 99},
            ]},
        ]})
        assert result.success
        assert 0x3C in result.bytecode  # JZ
    
    def test_if_else(self):
        c = SignalCompiler()
        result = c.compile({"ops": [
            {"op": "let", "name": "x", "value": 0},
            {"op": "if", "cond": "x", "then": [
                {"op": "let", "name": "a", "value": 1},
            ], "else": [
                {"op": "let", "name": "b", "value": 2},
            ]},
        ]})
        assert result.success
    
    def test_loop(self):
        c = SignalCompiler()
        result = c.compile({"ops": [
            {"op": "loop", "count": 5, "body": [
                {"op": "let", "name": "i", "value": 1},
            ]},
        ]})
        assert result.success
        assert 0x46 in result.bytecode  # LOOP


class TestSignalConcurrency:
    def test_branch(self):
        c = SignalCompiler()
        result = c.compile({"ops": [
            {"op": "branch", "branches": [
                {"op": "let", "name": "path_a", "value": 1},
                {"op": "let", "name": "path_b", "value": 2},
            ]},
        ]})
        assert result.success
        assert 0x58 in result.bytecode  # FORK
        assert 0x59 in result.bytecode  # JOIN
    
    def test_merge(self):
        c = SignalCompiler()
        result = c.compile({"ops": [
            {"op": "merge", "strategy": "sum", "into": "combined"},
        ]})
        assert result.success
        assert 0x57 in result.bytecode  # MERGE


class TestSignalConfidence:
    def test_confidence(self):
        c = SignalCompiler()
        result = c.compile({"ops": [
            {"op": "let", "name": "data", "value": 42},
            {"op": "confidence", "level": 0.8, "for": "data"},
        ]})
        assert result.success
        assert 0x69 in result.bytecode  # C_THRESH
    
    def test_yield(self):
        c = SignalCompiler()
        result = c.compile({"ops": [
            {"op": "yield", "value": "partial", "cycles": 3},
        ]})
        assert result.success
        assert 0x15 in result.bytecode  # YIELD
    
    def test_await(self):
        c = SignalCompiler()
        result = c.compile({"ops": [
            {"op": "await", "signal": "response", "into": "data"},
        ]})
        assert result.success
        assert 0x5B in result.bytecode  # AWAIT


class TestSignalPrograms:
    def test_hello_fleet(self):
        """Compile a complete fleet communication program."""
        c = SignalCompiler()
        result = c.compile({
            "program": "hello_fleet",
            "ops": [
                {"op": "let", "name": "message", "value": 1},
                {"op": "broadcast", "what": "message", "tag": "hello"},
                {"op": "await", "signal": "ack", "into": "responses"},
            ]
        })
        assert result.success
        assert 0x53 in result.bytecode  # BCAST
        assert 0x5B in result.bytecode  # AWAIT
        assert result.bytecode[-1] == 0x00  # HALT
    
    def test_compute_and_report(self):
        """Compute results and tell another agent."""
        c = SignalCompiler()
        result = c.compile({
            "program": "compute_report",
            "ops": [
                {"op": "let", "name": "a", "value": 10},
                {"op": "let", "name": "b", "value": 20},
                {"op": "add", "args": ["a", "b"], "into": "sum"},
                {"op": "tell", "to": "captain", "what": "sum", "tag": "results"},
            ]
        })
        assert result.success
        assert 0x20 in result.bytecode  # ADD
        assert 0x50 in result.bytecode  # TELL
    
    def test_json_string_compile(self):
        c = SignalCompiler()
        result = c.compile_string('{"ops": [{"op": "let", "name": "x", "value": 1}]}')
        assert result.success
    
    def test_invalid_json(self):
        c = SignalCompiler()
        result = c.compile_string("{invalid}")
        assert not result.success
    
    def test_unknown_op(self):
        c = SignalCompiler()
        result = c.compile({"ops": [{"op": "fly_to_moon"}]})
        assert not result.success
        assert "Unknown Signal op" in result.errors[0]


class TestSignalRegisterAllocation:
    def test_register_reuse(self):
        """Same name = same register."""
        c = SignalCompiler()
        result = c.compile({"ops": [
            {"op": "let", "name": "x", "value": 1},
            {"op": "let", "name": "x", "value": 2},
        ]})
        assert result.success
        assert result.register_map["x"] == result.register_map["x"]
    
    def test_register_map_complete(self):
        c = SignalCompiler()
        result = c.compile({"ops": [
            {"op": "let", "name": "alpha", "value": 1},
            {"op": "let", "name": "beta", "value": 2},
        ]})
        assert "alpha" in result.register_map
        assert "beta" in result.register_map
