"""Tests for the FLUX Standard Library (stdlib).

Covers:
- Intrinsics: print, assert, panic, sizeof, alignof, type_of
- Collections: List, Map, Set, Queue, Stack
- Math: min, max, abs, clamp, lerp, sqrt
- Strings: concat, substring, split, join, length, format
- Agents: AgentRegistry, MessageQueue, TaskScheduler
"""

import sys
import pytest

sys.path.insert(0, "src")

from flux.fir.types import TypeContext, IntType, FloatType, BoolType, StringType
from flux.fir.values import Value
from flux.fir.builder import FIRBuilder
from flux.fir.blocks import FIRModule, FIRFunction
from flux.fir.instructions import Call, Unreachable, SetField, GetField, GetElem, SetElem, MemSet

from flux.stdlib.intrinsics import (
    IntrinsicFunction, PrintFn, AssertFn, PanicFn,
    SizeofFn, AlignofFn, TypeOfFn, STDLIB_INTRINSICS,
)
from flux.stdlib.collections import (
    CollectionImpl, ListImpl, MapImpl, SetImpl, QueueImpl, StackImpl,
    STDLIB_COLLECTIONS,
)
from flux.stdlib.math import (
    MathFunction, MinFn, MaxFn, AbsFn, ClampFn, LerpFn, SqrtFn,
    STDLIB_MATH, emit_lerp_instructions,
)
from flux.stdlib.strings import (
    StringFunction, ConcatFn, SubstringFn, SplitFn, JoinFn,
    LengthFn, FormatFn, STDLIB_STRINGS,
)
from flux.stdlib.agents import (
    AgentFunction, AgentRegistryImpl, MessageQueueImpl, TaskSchedulerImpl,
    STDLIB_AGENTS,
)


# ── Helpers ─────────────────────────────────────────────────────────────────


def make_builder() -> FIRBuilder:
    """Create a builder with a module, function, and entry block set up."""
    ctx = TypeContext()
    builder = FIRBuilder(ctx)
    i32 = ctx.get_int(32)
    mod = builder.new_module("test")
    func = builder.new_function(mod, "test_fn", [("x", i32)], [i32])
    entry = builder.new_block(func, "entry", [("x", i32)])
    builder.set_block(entry)
    return builder, mod, func


# ════════════════════════════════════════════════════════════════════════════
# Intrinsics Tests
# ════════════════════════════════════════════════════════════════════════════


class TestIntrinsics:
    """Tests for built-in intrinsic functions."""

    def test_stdlib_intrinsics_registry(self):
        """STDLIB_INTRINSICS contains all expected intrinsic functions."""
        expected = {"print", "assert", "panic", "sizeof", "alignof", "type_of"}
        assert set(STDLIB_INTRINSICS.keys()) == expected

    def test_print_emits_call(self):
        """PrintFn emits a call instruction to flux.print."""
        builder, mod, func = make_builder()
        i32 = builder._ctx.get_int(32)
        val = Value(id=0, name="x", type=i32)

        PrintFn().emit(builder, [val])

        instrs = func.entry_block.instructions
        assert len(instrs) == 1
        assert isinstance(instrs[0], Call)
        assert instrs[0].func == "flux.print"
        assert instrs[0].return_type is None

    def test_print_requires_argument(self):
        """PrintFn raises ValueError with no arguments."""
        builder, mod, func = make_builder()
        with pytest.raises(ValueError, match="at least 1 argument"):
            PrintFn().emit(builder, [])

    def test_assert_emits_call(self):
        """AssertFn emits a call instruction to flux.assert."""
        builder, mod, func = make_builder()
        i32 = builder._ctx.get_int(32)
        bool_t = builder._ctx.get_bool()
        cond = Value(id=0, name="cond", type=bool_t)

        AssertFn().emit(builder, [cond], message="test failed")

        instrs = func.entry_block.instructions
        assert len(instrs) == 1
        assert isinstance(instrs[0], Call)
        assert instrs[0].func == "flux.assert"

    def test_assert_requires_condition(self):
        """AssertFn raises ValueError with no arguments."""
        builder, mod, func = make_builder()
        with pytest.raises(ValueError, match="condition"):
            AssertFn().emit(builder, [])

    def test_panic_emits_call_and_unreachable(self):
        """PanicFn emits a call followed by unreachable."""
        builder, mod, func = make_builder()
        string_t = builder._ctx.get_string()
        msg = Value(id=0, name="msg", type=string_t)

        PanicFn().emit(builder, [msg])

        instrs = func.entry_block.instructions
        assert len(instrs) == 2
        assert isinstance(instrs[0], Call)
        assert instrs[0].func == "flux.panic"
        assert isinstance(instrs[1], Unreachable)

    def test_panic_without_arg(self):
        """PanicFn works without arguments (uses default message)."""
        builder, mod, func = make_builder()

        PanicFn().emit(builder, [])

        instrs = func.entry_block.instructions
        assert len(instrs) == 2
        assert isinstance(instrs[0], Call)
        assert isinstance(instrs[1], Unreachable)

    def test_sizeof_emits_call(self):
        """SizeofFn emits a call to flux.sizeof."""
        builder, mod, func = make_builder()
        i32 = builder._ctx.get_int(32)
        val = Value(id=0, name="x", type=i32)

        result = SizeofFn().emit(builder, [val])

        assert result is not None
        assert result.type == i32
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.sizeof" for i in instrs)

    def test_alignof_emits_call(self):
        """AlignofFn emits a call to flux.alignof."""
        builder, mod, func = make_builder()
        i32 = builder._ctx.get_int(32)
        val = Value(id=0, name="x", type=i32)

        result = AlignofFn().emit(builder, [val])

        assert result is not None
        assert result.type == i32

    def test_type_of_emits_call(self):
        """TypeOfFn emits a call to flux.type_of returning StringType."""
        builder, mod, func = make_builder()
        i32 = builder._ctx.get_int(32)
        val = Value(id=0, name="x", type=i32)

        result = TypeOfFn().emit(builder, [val])

        assert result is not None
        assert isinstance(result.type, StringType)
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.type_of" for i in instrs)

    def test_type_of_requires_argument(self):
        """TypeOfFn raises ValueError with no arguments."""
        builder, mod, func = make_builder()
        with pytest.raises(ValueError, match="value"):
            TypeOfFn().emit(builder, [])

    def test_intrinsic_repr(self):
        """Intrinsic functions have informative repr."""
        assert "print" in repr(PrintFn())
        assert "panic" in repr(PanicFn())


# ════════════════════════════════════════════════════════════════════════════
# Collections Tests
# ════════════════════════════════════════════════════════════════════════════


class TestCollections:
    """Tests for collection data structures."""

    def test_stdlib_collections_registry(self):
        """STDLIB_COLLECTIONS contains all expected collection types."""
        expected = {"List", "Map", "Set", "Queue", "Stack"}
        assert set(STDLIB_COLLECTIONS.keys()) == expected

    def test_list_struct_type(self):
        """ListImpl produces a valid struct type with 3 fields."""
        ctx = TypeContext()
        impl = ListImpl()
        struct_t = impl.get_struct_type(ctx)

        assert struct_t.name == "FluxList"
        assert len(struct_t.fields) == 3
        assert struct_t.fields[0][0] == "data"
        assert struct_t.fields[1][0] == "len"
        assert struct_t.fields[2][0] == "cap"

    def test_map_struct_type(self):
        """MapImpl produces a valid struct type."""
        ctx = TypeContext()
        impl = MapImpl()
        struct_t = impl.get_struct_type(ctx)

        assert struct_t.name == "FluxMap"
        assert len(struct_t.fields) == 3

    def test_set_struct_type(self):
        """SetImpl produces a valid struct type."""
        ctx = TypeContext()
        impl = SetImpl()
        struct_t = impl.get_struct_type(ctx)

        assert struct_t.name == "FluxSet"
        assert len(struct_t.fields) == 3

    def test_queue_struct_type(self):
        """QueueImpl produces a valid struct type with 5 fields."""
        ctx = TypeContext()
        impl = QueueImpl()
        struct_t = impl.get_struct_type(ctx)

        assert struct_t.name == "FluxQueue"
        assert len(struct_t.fields) == 5
        assert struct_t.fields[0][0] == "data"
        assert struct_t.fields[1][0] == "head"
        assert struct_t.fields[2][0] == "tail"
        assert struct_t.fields[3][0] == "len"
        assert struct_t.fields[4][0] == "cap"

    def test_stack_struct_type(self):
        """StackImpl produces a valid struct type with 3 fields."""
        ctx = TypeContext()
        impl = StackImpl()
        struct_t = impl.get_struct_type(ctx)

        assert struct_t.name == "FluxStack"
        assert len(struct_t.fields) == 3
        assert struct_t.fields[0][0] == "data"
        assert struct_t.fields[1][0] == "top"
        assert struct_t.fields[2][0] == "cap"

    def test_list_alloc_emits_alloca_and_memset(self):
        """ListImpl.emit_alloc emits alloca + memset instructions."""
        builder, mod, func = make_builder()
        i32 = builder._ctx.get_int(32)
        cap = Value(id=10, name="cap", type=i32)

        impl = ListImpl()
        result = impl.emit_alloc(builder, cap)

        assert result is not None
        instrs = func.entry_block.instructions
        assert len(instrs) >= 2
        # Should have alloca and memset
        opcodes = [i.opcode for i in instrs]
        assert "alloca" in opcodes
        assert "memset" in opcodes

    def test_queue_alloc_emits_memset(self):
        """QueueImpl.emit_alloc emits alloca + memset with correct size."""
        builder, mod, func = make_builder()
        i32 = builder._ctx.get_int(32)
        cap = Value(id=10, name="cap", type=i32)

        impl = QueueImpl()
        result = impl.emit_alloc(builder, cap)

        assert result is not None
        instrs = func.entry_block.instructions
        opcodes = [i.opcode for i in instrs]
        assert "alloca" in opcodes
        assert "memset" in opcodes

    def test_list_len_emits_getfield(self):
        """ListImpl.emit_len emits a getfield instruction for the len field."""
        builder, mod, func = make_builder()
        ctx = builder._ctx
        impl = ListImpl()
        struct_t = impl.get_struct_type(ctx)
        self_val = Value(id=0, name="list", type=struct_t)

        result = impl.emit_len(builder, self_val)

        assert result is not None
        instrs = func.entry_block.instructions
        assert len(instrs) >= 1
        assert isinstance(instrs[0], GetField)
        assert instrs[0].field_name == "len"

    def test_map_push_emits_call(self):
        """MapImpl.emit_push emits a runtime call."""
        builder, mod, func = make_builder()
        ctx = builder._ctx
        impl = MapImpl()
        struct_t = impl.get_struct_type(ctx)
        self_val = Value(id=0, name="map", type=struct_t)
        item = Value(id=1, name="item", type=ctx.get_int(32))

        impl.emit_push(builder, self_val, item)

        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.map_insert" for i in instrs)

    def test_queue_push_emits_call(self):
        """QueueImpl.emit_push emits a runtime call."""
        builder, mod, func = make_builder()
        ctx = builder._ctx
        impl = QueueImpl()
        struct_t = impl.get_struct_type(ctx)
        self_val = Value(id=0, name="queue", type=struct_t)
        item = Value(id=1, name="item", type=ctx.get_int(32))

        impl.emit_push(builder, self_val, item)

        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.queue_enqueue" for i in instrs)

    def test_stack_pop_emits_call(self):
        """StackImpl.emit_pop emits a runtime call and returns a value."""
        builder, mod, func = make_builder()
        ctx = builder._ctx
        impl = StackImpl()
        struct_t = impl.get_struct_type(ctx)
        self_val = Value(id=0, name="stack", type=struct_t)

        result = impl.emit_pop(builder, self_val)

        assert result is not None
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.stack_pop" for i in instrs)

    def test_set_get_emits_call(self):
        """SetImpl.emit_get emits a contains check call."""
        builder, mod, func = make_builder()
        ctx = builder._ctx
        impl = SetImpl()
        struct_t = impl.get_struct_type(ctx)
        self_val = Value(id=0, name="set", type=struct_t)
        index = Value(id=1, name="key", type=ctx.get_int(32))

        result = impl.emit_get(builder, self_val, index)

        assert result is not None
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.set_contains" for i in instrs)


# ════════════════════════════════════════════════════════════════════════════
# Math Tests
# ════════════════════════════════════════════════════════════════════════════


class TestMath:
    """Tests for math operations."""

    def test_stdlib_math_registry(self):
        """STDLIB_MATH contains all expected math functions."""
        expected = {"min", "max", "abs", "clamp", "lerp", "sqrt"}
        assert set(STDLIB_MATH.keys()) == expected

    def test_min_emits_call(self):
        """MinFn emits a call to flux.min."""
        builder, mod, func = make_builder()
        i32 = builder._ctx.get_int(32)
        a = Value(id=0, name="a", type=i32)
        b = Value(id=1, name="b", type=i32)

        result = MinFn().emit(builder, [a, b])

        assert result is not None
        assert result.type == i32
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.min" for i in instrs)

    def test_min_requires_two_args(self):
        """MinFn raises ValueError with less than 2 arguments."""
        builder, mod, func = make_builder()
        with pytest.raises(ValueError, match="2 arguments"):
            MinFn().emit(builder, [])

    def test_max_emits_call(self):
        """MaxFn emits a call to flux.max."""
        builder, mod, func = make_builder()
        i32 = builder._ctx.get_int(32)
        a = Value(id=0, name="a", type=i32)
        b = Value(id=1, name="b", type=i32)

        result = MaxFn().emit(builder, [a, b])

        assert result is not None
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.max" for i in instrs)

    def test_abs_emits_call(self):
        """AbsFn emits a call to flux.abs."""
        builder, mod, func = make_builder()
        i32 = builder._ctx.get_int(32)
        x = Value(id=0, name="x", type=i32)

        result = AbsFn().emit(builder, [x])

        assert result is not None
        assert result.type == i32
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.abs" for i in instrs)

    def test_clamp_emits_call(self):
        """ClampFn emits a call to flux.clamp with 3 args."""
        builder, mod, func = make_builder()
        i32 = builder._ctx.get_int(32)
        x = Value(id=0, name="x", type=i32)
        lo = Value(id=1, name="lo", type=i32)
        hi = Value(id=2, name="hi", type=i32)

        result = ClampFn().emit(builder, [x, lo, hi])

        assert result is not None
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.clamp" for i in instrs)
        # Check that 3 args were passed
        clamp_call = next(i for i in instrs if isinstance(i, Call) and i.func == "flux.clamp")
        assert len(clamp_call.args) == 3

    def test_lerp_emits_call(self):
        """LerpFn emits a call to flux.lerp with 3 args."""
        builder, mod, func = make_builder()
        i32 = builder._ctx.get_int(32)
        a = Value(id=0, name="a", type=i32)
        b = Value(id=1, name="b", type=i32)
        t = Value(id=2, name="t", type=i32)

        result = LerpFn().emit(builder, [a, b, t])

        assert result is not None
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.lerp" for i in instrs)

    def test_sqrt_emits_call(self):
        """SqrtFn emits a call to flux.sqrt."""
        builder, mod, func = make_builder()
        i32 = builder._ctx.get_int(32)
        x = Value(id=0, name="x", type=i32)

        result = SqrtFn().emit(builder, [x])

        assert result is not None
        assert result.type == i32
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.sqrt" for i in instrs)

    def test_emit_lerp_instructions(self):
        """emit_lerp_instructions produces correct FIR instruction sequence."""
        builder, mod, func = make_builder()
        i32 = builder._ctx.get_int(32)
        a = Value(id=0, name="a", type=i32)
        b = Value(id=1, name="b", type=i32)
        t = Value(id=2, name="t", type=i32)

        result = emit_lerp_instructions(builder, a, b, t)

        assert result is not None
        assert result.type == i32
        instrs = func.entry_block.instructions
        # Should have: isub, imul, iadd
        opcodes = [i.opcode for i in instrs]
        assert "isub" in opcodes
        assert "imul" in opcodes
        assert "iadd" in opcodes

    def test_math_function_names(self):
        """All math functions have proper name and description."""
        for name, fn in STDLIB_MATH.items():
            assert fn.name == name
            assert len(fn.description) > 0


# ════════════════════════════════════════════════════════════════════════════
# Strings Tests
# ════════════════════════════════════════════════════════════════════════════


class TestStrings:
    """Tests for string operations."""

    def test_stdlib_strings_registry(self):
        """STDLIB_STRINGS contains all expected string functions."""
        expected = {"concat", "substring", "split", "join", "length", "format"}
        assert set(STDLIB_STRINGS.keys()) == expected

    def test_concat_emits_call(self):
        """ConcatFn emits a call to flux.str_concat returning StringType."""
        builder, mod, func = make_builder()
        string_t = builder._ctx.get_string()
        a = Value(id=0, name="a", type=string_t)
        b = Value(id=1, name="b", type=string_t)

        result = ConcatFn().emit(builder, [a, b])

        assert result is not None
        assert isinstance(result.type, StringType)
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.str_concat" for i in instrs)

    def test_concat_requires_two_args(self):
        """ConcatFn raises ValueError with less than 2 arguments."""
        builder, mod, func = make_builder()
        with pytest.raises(ValueError, match="2 string"):
            ConcatFn().emit(builder, [])

    def test_substring_emits_call(self):
        """SubstringFn emits a call with 3 arguments."""
        builder, mod, func = make_builder()
        string_t = builder._ctx.get_string()
        i32 = builder._ctx.get_int(32)
        s = Value(id=0, name="s", type=string_t)
        start = Value(id=1, name="start", type=i32)
        end = Value(id=2, name="end", type=i32)

        result = SubstringFn().emit(builder, [s, start, end])

        assert result is not None
        instrs = func.entry_block.instructions
        sub_call = next(i for i in instrs if isinstance(i, Call) and i.func == "flux.str_substring")
        assert len(sub_call.args) == 3

    def test_split_emits_call(self):
        """SplitFn emits a call to flux.str_split."""
        builder, mod, func = make_builder()
        string_t = builder._ctx.get_string()
        s = Value(id=0, name="s", type=string_t)
        delim = Value(id=1, name="delim", type=string_t)

        result = SplitFn().emit(builder, [s, delim])

        assert result is not None
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.str_split" for i in instrs)

    def test_join_emits_call(self):
        """JoinFn emits a call to flux.str_join."""
        builder, mod, func = make_builder()
        string_t = builder._ctx.get_string()
        parts = Value(id=0, name="parts", type=string_t)
        sep = Value(id=1, name="sep", type=string_t)

        result = JoinFn().emit(builder, [parts, sep])

        assert result is not None
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.str_join" for i in instrs)

    def test_length_emits_call(self):
        """LengthFn emits a call to flux.str_length returning i32."""
        builder, mod, func = make_builder()
        string_t = builder._ctx.get_string()
        s = Value(id=0, name="s", type=string_t)

        result = LengthFn().emit(builder, [s])

        assert result is not None
        assert isinstance(result.type, IntType)
        assert result.type.bits == 32
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.str_length" for i in instrs)

    def test_format_emits_call(self):
        """FormatFn emits a call to flux.str_format."""
        builder, mod, func = make_builder()
        string_t = builder._ctx.get_string()
        template = Value(id=0, name="tmpl", type=string_t)

        result = FormatFn().emit(builder, [template])

        assert result is not None
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.str_format" for i in instrs)

    def test_format_parse_template(self):
        """FormatFn.emit_parse_template correctly extracts placeholders."""
        fn = FormatFn()
        placeholders = fn.emit_parse_template("Hello {0}, you are {1} years old")
        assert placeholders == ["0", "1"]

    def test_format_parse_no_placeholders(self):
        """FormatFn.emit_parse_template returns empty list for no placeholders."""
        fn = FormatFn()
        placeholders = fn.emit_parse_template("No placeholders here")
        assert placeholders == []

    def test_string_function_names(self):
        """All string functions have proper name and description."""
        for name, fn in STDLIB_STRINGS.items():
            assert fn.name == name
            assert len(fn.description) > 0


# ════════════════════════════════════════════════════════════════════════════
# Agents Tests
# ════════════════════════════════════════════════════════════════════════════


class TestAgents:
    """Tests for agent standard library utilities."""

    def test_stdlib_agents_registry(self):
        """STDLIB_AGENTS contains all expected agent functions."""
        expected = {"AgentRegistry", "MessageQueue", "TaskScheduler"}
        assert set(STDLIB_AGENTS.keys()) == expected

    def test_agent_registry_register_emits_call(self):
        """AgentRegistryImpl.emit_register emits a call to flux.agent_register."""
        builder, mod, func = make_builder()
        string_t = builder._ctx.get_string()
        name = Value(id=0, name="name", type=string_t)

        impl = AgentRegistryImpl()
        result = impl.emit_register(builder, name)

        assert result is not None
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.agent_register" for i in instrs)

    def test_agent_registry_unregister_emits_call(self):
        """AgentRegistryImpl.emit_unregister emits a void call."""
        builder, mod, func = make_builder()
        string_t = builder._ctx.get_string()
        name = Value(id=0, name="name", type=string_t)

        impl = AgentRegistryImpl()
        impl.emit_unregister(builder, name)

        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.agent_unregister" for i in instrs)

    def test_agent_registry_list_emits_call(self):
        """AgentRegistryImpl.emit_list emits a call returning a list ref."""
        builder, mod, func = make_builder()

        impl = AgentRegistryImpl()
        result = impl.emit_list(builder)

        assert result is not None
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.agent_list" for i in instrs)

    def test_agent_registry_count_emits_call(self):
        """AgentRegistryImpl.emit_count emits a call returning i32."""
        builder, mod, func = make_builder()

        impl = AgentRegistryImpl()
        result = impl.emit_count(builder)

        assert result is not None
        assert isinstance(result.type, IntType)
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.agent_count" for i in instrs)

    def test_message_queue_send_emits_call(self):
        """MessageQueueImpl.emit_send emits a call to flux.mq_send."""
        builder, mod, func = make_builder()
        string_t = builder._ctx.get_string()
        target = Value(id=0, name="target", type=string_t)
        message = Value(id=1, name="msg", type=string_t)

        impl = MessageQueueImpl()
        result = impl.emit_send(builder, target, message)

        assert result is not None
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.mq_send" for i in instrs)

    def test_message_queue_send_with_priority(self):
        """MessageQueueImpl.emit_send includes priority when provided."""
        builder, mod, func = make_builder()
        string_t = builder._ctx.get_string()
        i32 = builder._ctx.get_int(32)
        target = Value(id=0, name="target", type=string_t)
        message = Value(id=1, name="msg", type=string_t)
        priority = Value(id=2, name="prio", type=i32)

        impl = MessageQueueImpl()
        impl.emit_send(builder, target, message, priority=priority)

        instrs = func.entry_block.instructions
        mq_call = next(i for i in instrs if isinstance(i, Call) and i.func == "flux.mq_send")
        assert len(mq_call.args) == 3

    def test_message_queue_receive_emits_call(self):
        """MessageQueueImpl.emit_receive emits a call to flux.mq_receive."""
        builder, mod, func = make_builder()

        impl = MessageQueueImpl()
        result = impl.emit_receive(builder)

        assert result is not None
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.mq_receive" for i in instrs)

    def test_message_queue_drain_emits_call(self):
        """MessageQueueImpl.emit_drain emits a call to flux.mq_drain."""
        builder, mod, func = make_builder()

        impl = MessageQueueImpl()
        result = impl.emit_drain(builder)

        assert result is not None
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.mq_drain" for i in instrs)

    def test_task_scheduler_schedule_emits_call(self):
        """TaskSchedulerImpl.emit_schedule emits a call to flux.task_schedule."""
        builder, mod, func = make_builder()
        string_t = builder._ctx.get_string()
        agent_name = Value(id=0, name="agent", type=string_t)
        task_data = Value(id=1, name="data", type=string_t)

        impl = TaskSchedulerImpl()
        result = impl.emit_schedule(builder, agent_name, task_data)

        assert result is not None
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.task_schedule" for i in instrs)

    def test_task_scheduler_cancel_emits_call(self):
        """TaskSchedulerImpl.emit_cancel emits a call to flux.task_cancel."""
        builder, mod, func = make_builder()
        i64 = builder._ctx.get_int(64)
        task_id = Value(id=0, name="task_id", type=i64)

        impl = TaskSchedulerImpl()
        result = impl.emit_cancel(builder, task_id)

        assert result is not None
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.task_cancel" for i in instrs)

    def test_task_scheduler_status_emits_call(self):
        """TaskSchedulerImpl.emit_status emits a call to flux.task_status."""
        builder, mod, func = make_builder()
        i64 = builder._ctx.get_int(64)
        task_id = Value(id=0, name="task_id", type=i64)

        impl = TaskSchedulerImpl()
        result = impl.emit_status(builder, task_id)

        assert result is not None
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.task_status" for i in instrs)

    def test_task_scheduler_wait_with_timeout(self):
        """TaskSchedulerImpl.emit_wait includes timeout when provided."""
        builder, mod, func = make_builder()
        i64 = builder._ctx.get_int(64)
        i32 = builder._ctx.get_int(32)
        task_id = Value(id=0, name="task_id", type=i64)
        timeout = Value(id=1, name="timeout", type=i32)

        impl = TaskSchedulerImpl()
        impl.emit_wait(builder, task_id, timeout)

        instrs = func.entry_block.instructions
        wait_call = next(i for i in instrs if isinstance(i, Call) and i.func == "flux.task_wait")
        assert len(wait_call.args) == 2

    def test_task_scheduler_pending_count_emits_call(self):
        """TaskSchedulerImpl.emit_pending_count emits a call."""
        builder, mod, func = make_builder()

        impl = TaskSchedulerImpl()
        result = impl.emit_pending_count(builder)

        assert result is not None
        instrs = func.entry_block.instructions
        assert any(isinstance(i, Call) and i.func == "flux.task_pending_count" for i in instrs)


# ════════════════════════════════════════════════════════════════════════════
# Integration Tests
# ════════════════════════════════════════════════════════════════════════════


class TestStdlibIntegration:
    """Integration tests combining multiple stdlib components."""

    def test_multiple_stdlib_calls_in_sequence(self):
        """Multiple stdlib functions can be emitted in sequence."""
        builder, mod, func = make_builder()
        i32 = builder._ctx.get_int(32)
        f32 = builder._ctx.get_float(32)
        string_t = builder._ctx.get_string()

        x = Value(id=0, name="x", type=i32)
        y = Value(id=1, name="y", type=i32)

        # Math: min
        MinFn().emit(builder, [x, y])
        # Math: abs
        AbsFn().emit(builder, [x])
        # String: length
        s = Value(id=2, name="s", type=string_t)
        LengthFn().emit(builder, [s])
        # Intrinsic: print
        PrintFn().emit(builder, [x])
        # Intrinsic: type_of
        TypeOfFn().emit(builder, [x])

        instrs = func.entry_block.instructions
        call_funcs = [i.func for i in instrs if isinstance(i, Call)]
        assert "flux.min" in call_funcs
        assert "flux.abs" in call_funcs
        assert "flux.str_length" in call_funcs
        assert "flux.print" in call_funcs
        assert "flux.type_of" in call_funcs

    def test_list_then_print_pattern(self):
        """Common pattern: allocate list, push items, print length."""
        builder, mod, func = make_builder()
        ctx = builder._ctx
        i32 = ctx.get_int(32)

        cap = Value(id=10, name="cap", type=i32)
        impl = ListImpl()
        list_val = impl.emit_alloc(builder, cap)
        len_val = impl.emit_len(builder, list_val)

        # Print the length
        PrintFn().emit(builder, [len_val])

        instrs = func.entry_block.instructions
        opcodes = [i.opcode for i in instrs]
        assert "alloca" in opcodes
        assert "memset" in opcodes
        assert "getfield" in opcodes
        call_funcs = [i.func for i in instrs if isinstance(i, Call)]
        assert "flux.print" in call_funcs
