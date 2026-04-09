"""Collection data structures for the FLUX standard library.

Each collection type provides FIR-level implementations that emit appropriate
memory operations (alloca, load, store, getelem, setelem) via the builder.
Collections are modeled as structs with internal fields managed through
the FIR memory model.
"""

from __future__ import annotations

from typing import Optional

from flux.fir.types import (
    FIRType, TypeContext, IntType, BoolType,
)
from flux.fir.values import Value
from flux.fir.builder import FIRBuilder


# ── Base ────────────────────────────────────────────────────────────────────


class CollectionImpl:
    """Base class for FIR-level collection implementations.

    Each collection defines its struct layout and provides methods that emit
    FIR instructions for common operations.
    """

    name: str = ""
    description: str = ""

    def get_struct_type(self, ctx: TypeContext) -> FIRType:
        """Return the FIR struct type for this collection."""
        raise NotImplementedError

    def emit_alloc(self, builder: FIRBuilder, capacity: Value) -> Value:
        """Emit instructions to allocate a new collection instance."""
        raise NotImplementedError

    def emit_len(self, builder: FIRBuilder, self_val: Value) -> Value:
        """Emit instructions to get the length of the collection."""
        raise NotImplementedError

    def emit_push(self, builder: FIRBuilder, self_val: Value, item: Value) -> None:
        """Emit instructions to append an item to the collection."""
        raise NotImplementedError

    def emit_pop(self, builder: FIRBuilder, self_val: Value) -> Optional[Value]:
        """Emit instructions to remove and return an item."""
        raise NotImplementedError

    def emit_get(self, builder: FIRBuilder, self_val: Value, index: Value) -> Value:
        """Emit instructions to get an item by index."""
        raise NotImplementedError

    def emit_set(self, builder: FIRBuilder, self_val: Value, index: Value, item: Value) -> None:
        """Emit instructions to set an item by index."""
        raise NotImplementedError


# ── List (dynamic array) ───────────────────────────────────────────────────


class ListImpl(CollectionImpl):
    """Dynamic array with amortized O(1) push, O(1) indexed access.

    FIR struct layout:
        - data:   ref<i32>  (pointer to element storage)
        - len:    i32       (current number of elements)
        - cap:    i32       (allocated capacity)
    """

    name = "List"
    description = "Dynamic array with amortized O(1) push and O(1) indexed access."

    # Field indices
    FIELD_DATA = 0
    FIELD_LEN = 1
    FIELD_CAP = 2

    def get_struct_type(self, ctx: TypeContext) -> FIRType:
        i32 = ctx.get_int(32)
        return ctx.get_struct("FluxList", (
            ("data", ctx.get_ref(i32)),
            ("len", i32),
            ("cap", i32),
        ))

    def emit_alloc(self, builder: FIRBuilder, capacity: Value) -> Value:
        struct_type = self.get_struct_type(builder._ctx)
        ptr = builder.alloca(struct_type)
        # Initialize: len=0, cap=capacity via memset
        builder.memset(ptr, 0, 12)  # 3 x i32 = 12 bytes zeroed
        return ptr

    def emit_len(self, builder: FIRBuilder, self_val: Value) -> Value:
        i32 = builder._ctx.get_int(32)
        return builder.getfield(self_val, "len", self.FIELD_LEN, i32)

    def emit_push(self, builder: FIRBuilder, self_val: Value, item: Value) -> None:
        struct_type = self.get_struct_type(builder._ctx)
        i32 = builder._ctx.get_int(32)
        # Load current len
        len_val = self.emit_len(builder, self_val)
        # Load data pointer
        data_ptr = builder.getfield(self_val, "data", self.FIELD_DATA, builder._ctx.get_ref(i32))
        # Store item at data[len]
        builder.setelem(data_ptr, len_val, item)
        # Increment len
        new_len = builder.iadd(len_val, Value(id=-1, name="one", type=i32))
        # Note: setfield here uses self_val directly
        from flux.fir.instructions import SetField
        builder._current_block.instructions.append(
            SetField(self_val, "len", self.FIELD_LEN, new_len)
        )

    def emit_pop(self, builder: FIRBuilder, self_val: Value) -> Optional[Value]:
        i32 = builder._ctx.get_int(32)
        len_val = self.emit_len(builder, self_val)
        # Decrement len
        new_len = builder.isub(len_val, Value(id=-1, name="one", type=i32))
        # Load data[len-1]
        data_ptr = builder.getfield(self_val, "data", self.FIELD_DATA, builder._ctx.get_ref(i32))
        elem = builder.getelem(data_ptr, new_len, i32)
        # Update len
        from flux.fir.instructions import SetField
        builder._current_block.instructions.append(
            SetField(self_val, "len", self.FIELD_LEN, new_len)
        )
        return elem

    def emit_get(self, builder: FIRBuilder, self_val: Value, index: Value) -> Value:
        i32 = builder._ctx.get_int(32)
        data_ptr = builder.getfield(self_val, "data", self.FIELD_DATA, builder._ctx.get_ref(i32))
        return builder.getelem(data_ptr, index, i32)

    def emit_set(self, builder: FIRBuilder, self_val: Value, index: Value, item: Value) -> None:
        i32 = builder._ctx.get_int(32)
        data_ptr = builder.getfield(self_val, "data", self.FIELD_DATA, builder._ctx.get_ref(i32))
        builder.setelem(data_ptr, index, item)


# ── Map (hash map) ─────────────────────────────────────────────────────────


class MapImpl(CollectionImpl):
    """Hash map with O(1) average lookup.

    FIR struct layout:
        - buckets: ref<i32>  (pointer to bucket storage)
        - size:    i32       (number of entries)
        - cap:     i32       (number of buckets)
    """

    name = "Map"
    description = "Hash map with O(1) average-case lookup."

    FIELD_BUCKETS = 0
    FIELD_SIZE = 1
    FIELD_CAP = 2

    def get_struct_type(self, ctx: TypeContext) -> FIRType:
        i32 = ctx.get_int(32)
        return ctx.get_struct("FluxMap", (
            ("buckets", ctx.get_ref(i32)),
            ("size", i32),
            ("cap", i32),
        ))

    def emit_alloc(self, builder: FIRBuilder, capacity: Value) -> Value:
        struct_type = self.get_struct_type(builder._ctx)
        ptr = builder.alloca(struct_type)
        builder.memset(ptr, 0, 12)
        return ptr

    def emit_len(self, builder: FIRBuilder, self_val: Value) -> Value:
        i32 = builder._ctx.get_int(32)
        return builder.getfield(self_val, "size", self.FIELD_SIZE, i32)

    def emit_push(self, builder: FIRBuilder, self_val: Value, item: Value) -> None:
        # Maps use insert semantics — delegate to a runtime call
        i32 = builder._ctx.get_int(32)
        builder.call("flux.map_insert", [self_val, item], return_type=None)

    def emit_pop(self, builder: FIRBuilder, self_val: Value) -> Optional[Value]:
        i32 = builder._ctx.get_int(32)
        builder.call("flux.map_remove_last", [self_val], return_type=i32)
        return Value(id=builder._next_value_id, name="map_pop_result", type=i32)

    def emit_get(self, builder: FIRBuilder, self_val: Value, index: Value) -> Value:
        i32 = builder._ctx.get_int(32)
        builder.call("flux.map_get", [self_val, index], return_type=i32)
        return Value(id=builder._next_value_id, name="map_get_result", type=i32)

    def emit_set(self, builder: FIRBuilder, self_val: Value, index: Value, item: Value) -> None:
        builder.call("flux.map_set", [self_val, index, item], return_type=None)


# ── Set (hash set) ─────────────────────────────────────────────────────────


class SetImpl(CollectionImpl):
    """Hash set with O(1) average membership test.

    FIR struct layout:
        - buckets: ref<i32>  (pointer to bucket storage)
        - size:    i32       (number of elements)
        - cap:     i32       (number of buckets)
    """

    name = "Set"
    description = "Hash set with O(1) average-case membership test."

    FIELD_BUCKETS = 0
    FIELD_SIZE = 1
    FIELD_CAP = 2

    def get_struct_type(self, ctx: TypeContext) -> FIRType:
        i32 = ctx.get_int(32)
        return ctx.get_struct("FluxSet", (
            ("buckets", ctx.get_ref(i32)),
            ("size", i32),
            ("cap", i32),
        ))

    def emit_alloc(self, builder: FIRBuilder, capacity: Value) -> Value:
        struct_type = self.get_struct_type(builder._ctx)
        ptr = builder.alloca(struct_type)
        builder.memset(ptr, 0, 12)
        return ptr

    def emit_len(self, builder: FIRBuilder, self_val: Value) -> Value:
        i32 = builder._ctx.get_int(32)
        return builder.getfield(self_val, "size", self.FIELD_SIZE, i32)

    def emit_push(self, builder: FIRBuilder, self_val: Value, item: Value) -> None:
        i32 = builder._ctx.get_int(32)
        builder.call("flux.set_insert", [self_val, item], return_type=None)

    def emit_pop(self, builder: FIRBuilder, self_val: Value) -> Optional[Value]:
        i32 = builder._ctx.get_int(32)
        builder.call("flux.set_remove", [self_val], return_type=i32)
        return Value(id=builder._next_value_id, name="set_pop_result", type=i32)

    def emit_get(self, builder: FIRBuilder, self_val: Value, index: Value) -> Value:
        i32 = builder._ctx.get_int(32)
        builder.call("flux.set_contains", [self_val, index], return_type=i32)
        return Value(id=builder._next_value_id, name="set_contains_result", type=i32)

    def emit_set(self, builder: FIRBuilder, self_val: Value, index: Value, item: Value) -> None:
        builder.call("flux.set_insert", [self_val, item], return_type=None)


# ── Queue (FIFO) ───────────────────────────────────────────────────────────


class QueueImpl(CollectionImpl):
    """First-in-first-out queue using a ring buffer.

    FIR struct layout:
        - data:   ref<i32>  (pointer to ring buffer)
        - head:   i32       (front index)
        - tail:   i32       (back index)
        - len:    i32       (current number of elements)
        - cap:    i32       (ring buffer capacity)
    """

    name = "Queue"
    description = "FIFO queue implemented as a ring buffer."

    FIELD_DATA = 0
    FIELD_HEAD = 1
    FIELD_TAIL = 2
    FIELD_LEN = 3
    FIELD_CAP = 4

    def get_struct_type(self, ctx: TypeContext) -> FIRType:
        i32 = ctx.get_int(32)
        return ctx.get_struct("FluxQueue", (
            ("data", ctx.get_ref(i32)),
            ("head", i32),
            ("tail", i32),
            ("len", i32),
            ("cap", i32),
        ))

    def emit_alloc(self, builder: FIRBuilder, capacity: Value) -> Value:
        struct_type = self.get_struct_type(builder._ctx)
        ptr = builder.alloca(struct_type)
        builder.memset(ptr, 0, 20)  # 5 x i32 = 20 bytes zeroed
        return ptr

    def emit_len(self, builder: FIRBuilder, self_val: Value) -> Value:
        i32 = builder._ctx.get_int(32)
        return builder.getfield(self_val, "len", self.FIELD_LEN, i32)

    def emit_push(self, builder: FIRBuilder, self_val: Value, item: Value) -> None:
        i32 = builder._ctx.get_int(32)
        builder.call("flux.queue_enqueue", [self_val, item], return_type=None)

    def emit_pop(self, builder: FIRBuilder, self_val: Value) -> Optional[Value]:
        i32 = builder._ctx.get_int(32)
        builder.call("flux.queue_dequeue", [self_val], return_type=i32)
        return Value(id=builder._next_value_id, name="queue_dequeue_result", type=i32)

    def emit_get(self, builder: FIRBuilder, self_val: Value, index: Value) -> Value:
        i32 = builder._ctx.get_int(32)
        builder.call("flux.queue_peek", [self_val, index], return_type=i32)
        return Value(id=builder._next_value_id, name="queue_peek_result", type=i32)

    def emit_set(self, builder: FIRBuilder, self_val: Value, index: Value, item: Value) -> None:
        builder.call("flux.queue_update", [self_val, index, item], return_type=None)


# ── Stack (LIFO) ───────────────────────────────────────────────────────────


class StackImpl(CollectionImpl):
    """Last-in-first-out stack.

    FIR struct layout:
        - data: ref<i32>  (pointer to element storage)
        - top:  i32       (index of next free slot / stack depth)
        - cap:  i32       (allocated capacity)
    """

    name = "Stack"
    description = "LIFO stack with O(1) push and pop."

    FIELD_DATA = 0
    FIELD_TOP = 1
    FIELD_CAP = 2

    def get_struct_type(self, ctx: TypeContext) -> FIRType:
        i32 = ctx.get_int(32)
        return ctx.get_struct("FluxStack", (
            ("data", ctx.get_ref(i32)),
            ("top", i32),
            ("cap", i32),
        ))

    def emit_alloc(self, builder: FIRBuilder, capacity: Value) -> Value:
        struct_type = self.get_struct_type(builder._ctx)
        ptr = builder.alloca(struct_type)
        builder.memset(ptr, 0, 12)  # 3 x i32 = 12 bytes zeroed
        return ptr

    def emit_len(self, builder: FIRBuilder, self_val: Value) -> Value:
        i32 = builder._ctx.get_int(32)
        return builder.getfield(self_val, "top", self.FIELD_TOP, i32)

    def emit_push(self, builder: FIRBuilder, self_val: Value, item: Value) -> None:
        i32 = builder._ctx.get_int(32)
        builder.call("flux.stack_push", [self_val, item], return_type=None)

    def emit_pop(self, builder: FIRBuilder, self_val: Value) -> Optional[Value]:
        i32 = builder._ctx.get_int(32)
        builder.call("flux.stack_pop", [self_val], return_type=i32)
        return Value(id=builder._next_value_id, name="stack_pop_result", type=i32)

    def emit_get(self, builder: FIRBuilder, self_val: Value, index: Value) -> Value:
        i32 = builder._ctx.get_int(32)
        builder.call("flux.stack_peek", [self_val, index], return_type=i32)
        return Value(id=builder._next_value_id, name="stack_peek_result", type=i32)

    def emit_set(self, builder: FIRBuilder, self_val: Value, index: Value, item: Value) -> None:
        builder.call("flux.stack_update", [self_val, index, item], return_type=None)


# ── Registry of all collections ────────────────────────────────────────────

STDLIB_COLLECTIONS: dict[str, CollectionImpl] = {
    "List": ListImpl(),
    "Map": MapImpl(),
    "Set": SetImpl(),
    "Queue": QueueImpl(),
    "Stack": StackImpl(),
}
