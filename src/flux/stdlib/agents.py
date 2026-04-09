"""Agent standard library utilities for the FLUX runtime.

Provides FIR-level abstractions for agent registry operations, message
queues, and task scheduling.  These build on top of the A2A primitives
(Tell, Ask, TrustCheck) with higher-level semantics.
"""

from __future__ import annotations

from typing import Optional

from flux.fir.types import (
    FIRType, TypeContext, IntType, BoolType, StringType, AgentType,
)
from flux.fir.values import Value
from flux.fir.builder import FIRBuilder


# ── Base ────────────────────────────────────────────────────────────────────


class AgentFunction:
    """Base class for agent standard library functions."""

    name: str = ""
    description: str = ""

    def emit(self, builder: FIRBuilder, args: list[Value]) -> Optional[Value]:
        """Emit FIR instructions for this agent function."""
        raise NotImplementedError


# ── AgentRegistry ───────────────────────────────────────────────────────────


class AgentRegistryImpl(AgentFunction):
    """Agent registry for discovering and managing agent instances.

    Provides FIR-level operations for registration, lookup, and listing
    of agents within the FLUX runtime.
    """

    name = "AgentRegistry"
    description = "Agent registry for discovery and lifecycle management."

    def emit_register(self, builder: FIRBuilder, agent_name: Value) -> Value:
        """Register a new agent with the given name.

        Returns the agent's UUID as an i64 value.
        """
        i64 = builder._ctx.get_int(64)
        result = builder.call("flux.agent_register", [agent_name], return_type=i64)
        return result

    def emit_unregister(self, builder: FIRBuilder, agent_name: Value) -> None:
        """Unregister an agent by name."""
        builder.call("flux.agent_unregister", [agent_name], return_type=None)

    def emit_lookup(self, builder: FIRBuilder, agent_name: Value) -> Value:
        """Look up an agent by name, returning its UUID (or 0 if not found)."""
        i64 = builder._ctx.get_int(64)
        result = builder.call("flux.agent_lookup", [agent_name], return_type=i64)
        return result

    def emit_list(self, builder: FIRBuilder) -> Value:
        """List all registered agent names.

        Returns a reference to a list structure.
        """
        list_ref_type = builder._ctx.get_ref(builder._ctx.get_string())
        result = builder.call("flux.agent_list", [], return_type=list_ref_type)
        return result

    def emit_count(self, builder: FIRBuilder) -> Value:
        """Return the number of registered agents."""
        i32 = builder._ctx.get_int(32)
        result = builder.call("flux.agent_count", [], return_type=i32)
        return result

    def emit(self, builder: FIRBuilder, args: list[Value]) -> Value:
        """Default emit: list all agents."""
        return self.emit_list(builder)


# ── MessageQueue ────────────────────────────────────────────────────────────


class MessageQueueImpl(AgentFunction):
    """Per-agent message queue for async communication.

    Provides FIR-level operations for enqueueing, dequeueing, and
    peeking at messages in an agent's mailbox.
    """

    name = "MessageQueue"
    description = "Per-agent message queue for async A2A communication."

    def emit_send(
        self,
        builder: FIRBuilder,
        target: Value,
        message: Value,
        priority: Optional[Value] = None,
    ) -> Value:
        """Send a message to a target agent.

        Returns a boolean indicating success.
        """
        bool_t = builder._ctx.get_bool()
        args = [target, message]
        if priority is not None:
            args.append(priority)
        result = builder.call("flux.mq_send", args, return_type=bool_t)
        return result

    def emit_receive(self, builder: FIRBuilder, timeout_ms: Optional[Value] = None) -> Value:
        """Receive the next message from the queue.

        Returns the message payload as a string.
        """
        string_t = builder._ctx.get_string()
        args = []
        if timeout_ms is not None:
            args.append(timeout_ms)
        result = builder.call("flux.mq_receive", args, return_type=string_t)
        return result

    def emit_peek(self, builder: FIRBuilder) -> Value:
        """Peek at the next message without removing it."""
        string_t = builder._ctx.get_string()
        result = builder.call("flux.mq_peek", [], return_type=string_t)
        return result

    def emit_count(self, builder: FIRBuilder) -> Value:
        """Return the number of pending messages."""
        i32 = builder._ctx.get_int(32)
        result = builder.call("flux.mq_count", [], return_type=i32)
        return result

    def emit_drain(self, builder: FIRBuilder) -> Value:
        """Remove all messages from the queue, returning count removed."""
        i32 = builder._ctx.get_int(32)
        result = builder.call("flux.mq_drain", [], return_type=i32)
        return result

    def emit(self, builder: FIRBuilder, args: list[Value]) -> Value:
        """Default emit: receive next message."""
        return self.emit_receive(builder)


# ── TaskScheduler ───────────────────────────────────────────────────────────


class TaskSchedulerImpl(AgentFunction):
    """Task scheduler for coordinating agent work.

    Provides FIR-level operations for scheduling, canceling, and
    querying the status of tasks assigned to agents.
    """

    name = "TaskScheduler"
    description = "Task scheduler for coordinating agent work assignments."

    def emit_schedule(
        self,
        builder: FIRBuilder,
        agent_name: Value,
        task_data: Value,
        priority: Optional[Value] = None,
    ) -> Value:
        """Schedule a task for an agent.

        Returns the task ID as an i64.
        """
        i64 = builder._ctx.get_int(64)
        args = [agent_name, task_data]
        if priority is not None:
            args.append(priority)
        result = builder.call("flux.task_schedule", args, return_type=i64)
        return result

    def emit_cancel(self, builder: FIRBuilder, task_id: Value) -> Value:
        """Cancel a scheduled task.

        Returns a boolean indicating success.
        """
        bool_t = builder._ctx.get_bool()
        result = builder.call("flux.task_cancel", [task_id], return_type=bool_t)
        return result

    def emit_status(self, builder: FIRBuilder, task_id: Value) -> Value:
        """Get the status of a task.

        Returns an i32 status code: 0=pending, 1=running, 2=done, 3=failed.
        """
        i32 = builder._ctx.get_int(32)
        result = builder.call("flux.task_status", [task_id], return_type=i32)
        return result

    def emit_result(self, builder: FIRBuilder, task_id: Value) -> Value:
        """Get the result of a completed task.

        Returns the result as a string (or empty string if not done).
        """
        string_t = builder._ctx.get_string()
        result = builder.call("flux.task_result", [task_id], return_type=string_t)
        return result

    def emit_wait(self, builder: FIRBuilder, task_id: Value, timeout_ms: Optional[Value] = None) -> Value:
        """Wait for a task to complete, with optional timeout.

        Returns the status code.
        """
        i32 = builder._ctx.get_int(32)
        args = [task_id]
        if timeout_ms is not None:
            args.append(timeout_ms)
        result = builder.call("flux.task_wait", args, return_type=i32)
        return result

    def emit_pending_count(self, builder: FIRBuilder) -> Value:
        """Return the number of pending tasks."""
        i32 = builder._ctx.get_int(32)
        result = builder.call("flux.task_pending_count", [], return_type=i32)
        return result

    def emit(self, builder: FIRBuilder, args: list[Value]) -> Value:
        """Default emit: get pending count."""
        return self.emit_pending_count(builder)


# ── Registry of all agent functions ─────────────────────────────────────────

STDLIB_AGENTS: dict[str, AgentFunction] = {
    "AgentRegistry": AgentRegistryImpl(),
    "MessageQueue": MessageQueueImpl(),
    "TaskScheduler": TaskSchedulerImpl(),
}
