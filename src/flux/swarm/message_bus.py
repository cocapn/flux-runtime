"""Inter-Agent Message Bus — routes messages between agents in the swarm.

Provides a lightweight in-process message bus with:
- Direct point-to-point messaging
- Topic-based pub/sub
- Message logging for livelock/deadlock analysis
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional


# ── Message Types ─────────────────────────────────────────────────────────

@dataclass
class AgentMessage:
    """A high-level message between swarm agents.

    Attributes:
        sender: Agent ID of the sender.
        receiver: Agent ID of the receiver (None for broadcast).
        topic: Topic string for pub/sub (None for direct messages).
        msg_type: Message type identifier (e.g. "request", "response", "event").
        payload: Arbitrary message payload (dict).
        conversation_id: UUID grouping related messages.
        timestamp: Unix timestamp when the message was created.
        priority: Delivery priority (0–15, higher = more urgent).
    """
    sender: str
    receiver: Optional[str] = None
    topic: Optional[str] = None
    msg_type: str = "request"
    payload: dict = field(default_factory=dict)
    conversation_id: str = ""
    timestamp: float = 0.0
    priority: int = 5

    def __post_init__(self):
        if self.conversation_id == "":
            self.conversation_id = str(uuid.uuid4())
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    @property
    def is_broadcast(self) -> bool:
        """True if this message is a broadcast (no specific receiver)."""
        return self.receiver is None

    @property
    def is_pubsub(self) -> bool:
        """True if this message targets a topic."""
        return self.topic is not None

    def summary(self) -> str:
        """Brief human-readable summary."""
        target = self.topic or self.receiver or "broadcast"
        return (
            f"{self.sender}→{target} "
            f"[{self.msg_type}] "
            f"payload_keys={list(self.payload.keys())}"
        )

    def __repr__(self) -> str:
        return (
            f"AgentMessage(from={self.sender!r}, to={self.receiver!r}, "
            f"topic={self.topic!r}, type={self.msg_type!r}, "
            f"conv={self.conversation_id[:8]})"
        )


# ── Message Bus ───────────────────────────────────────────────────────────

class MessageBus:
    """Routes messages between agents in the swarm.

    Supports three communication patterns:
    - **Direct**: send(from_id, to_id, payload) — point-to-point
    - **Broadcast**: publish(from_id, topic, payload) — one-to-many via topics
    - **Scatter**: send to multiple specific targets

    Each agent has an asyncio.Queue for message delivery.
    """

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[AgentMessage]] = {}
        self._subscriptions: dict[str, set[str]] = defaultdict(set)  # topic → set of agent_ids
        self._message_log: list[AgentMessage] = []
        self._message_count: int = 0

    # ── Registration ───────────────────────────────────────────────────

    def register(self, agent_id: str) -> None:
        """Register an agent's message queue.

        Args:
            agent_id: Unique identifier for the agent.
        """
        if agent_id not in self._queues:
            self._queues[agent_id] = asyncio.Queue()

    def unregister(self, agent_id: str) -> None:
        """Remove an agent and all its subscriptions."""
        self._queues.pop(agent_id, None)
        # Remove from all topic subscriptions
        for topic in list(self._subscriptions.keys()):
            self._subscriptions[topic].discard(agent_id)
            if not self._subscriptions[topic]:
                del self._subscriptions[topic]

    # ── Direct Messaging ───────────────────────────────────────────────

    def send(
        self,
        from_id: str,
        to_id: str,
        payload: dict,
        msg_type: str = "request",
        priority: int = 5,
    ) -> bool:
        """Send a direct message from one agent to another.

        Args:
            from_id: Sender agent ID.
            to_id: Receiver agent ID.
            payload: Message payload dictionary.
            msg_type: Type of message ("request", "response", "event").
            priority: Delivery priority 0–15.

        Returns:
            True if delivered, False if receiver not registered.
        """
        if to_id not in self._queues:
            return False

        msg = AgentMessage(
            sender=from_id,
            receiver=to_id,
            msg_type=msg_type,
            payload=payload,
            priority=priority,
        )

        self._log_message(msg)
        self._queues[to_id].put_nowait(msg)
        self._message_count += 1
        return True

    # ── Pub/Sub ────────────────────────────────────────────────────────

    def subscribe(self, agent_id: str, topic: str) -> None:
        """Subscribe an agent to a topic.

        Args:
            agent_id: Agent to subscribe.
            topic: Topic name to subscribe to.
        """
        self._subscriptions[topic].add(agent_id)

    def unsubscribe(self, agent_id: str, topic: str) -> None:
        """Unsubscribe an agent from a topic."""
        if topic in self._subscriptions:
            self._subscriptions[topic].discard(agent_id)
            if not self._subscriptions[topic]:
                del self._subscriptions[topic]

    def publish(
        self,
        from_id: str,
        topic: str,
        payload: dict,
        msg_type: str = "event",
        priority: int = 5,
    ) -> int:
        """Publish a message to a topic.

        Args:
            from_id: Publisher agent ID.
            topic: Topic to publish to.
            payload: Message payload.
            msg_type: Message type.
            priority: Priority.

        Returns:
            Number of subscribers notified.
        """
        subscribers = self._subscriptions.get(topic, set())
        if not subscribers:
            return 0

        delivered = 0
        for agent_id in subscribers:
            msg = AgentMessage(
                sender=from_id,
                receiver=agent_id,
                topic=topic,
                msg_type=msg_type,
                payload=payload,
                priority=priority,
            )
            self._log_message(msg)
            if agent_id in self._queues:
                self._queues[agent_id].put_nowait(msg)
                delivered += 1

        self._message_count += delivered
        return delivered

    # ── Drain ──────────────────────────────────────────────────────────

    def drain(self, agent_id: str) -> list[AgentMessage]:
        """Get all pending messages for an agent.

        Args:
            agent_id: Agent whose messages to drain.

        Returns:
            List of pending AgentMessages.
        """
        if agent_id not in self._queues:
            return []

        messages: list[AgentMessage] = []
        queue = self._queues[agent_id]
        while not queue.empty():
            try:
                messages.append(queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return messages

    def pending_count(self, agent_id: str) -> int:
        """Get the number of pending messages for an agent."""
        if agent_id not in self._queues:
            return 0
        return self._queues[agent_id].qsize()

    # ── Queries ────────────────────────────────────────────────────────

    @property
    def registered_agents(self) -> list[str]:
        """List of registered agent IDs."""
        return list(self._queues.keys())

    @property
    def topics(self) -> list[str]:
        """List of active topics."""
        return list(self._subscriptions.keys())

    def subscribers(self, topic: str) -> set[str]:
        """Get subscribers for a topic."""
        return set(self._subscriptions.get(topic, set()))

    @property
    def total_messages(self) -> int:
        """Total number of messages sent through this bus."""
        return self._message_count

    def get_log(self, limit: int = 100) -> list[AgentMessage]:
        """Get recent message log entries."""
        return self._message_log[-limit:]

    # ── Internals ──────────────────────────────────────────────────────

    def _log_message(self, msg: AgentMessage) -> None:
        """Append a message to the log."""
        self._message_log.append(msg)
        # Keep log bounded to prevent memory issues
        if len(self._message_log) > 10_000:
            self._message_log = self._message_log[-5_000:]

    def clear_log(self) -> None:
        """Clear the message log."""
        self._message_log.clear()

    def __repr__(self) -> str:
        return (
            f"MessageBus(agents={len(self._queues)}, "
            f"topics={len(self._subscriptions)}, "
            f"messages={self._message_count})"
        )
