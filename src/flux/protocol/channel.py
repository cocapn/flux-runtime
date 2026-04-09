"""Communication channels for the FLUX agent protocol.

Channels provide different message routing patterns:

- **DirectChannel**: Point-to-point messaging between two specific agents.
- **BroadcastChannel**: One-to-many message delivery to all subscribers.
- **TopicChannel**: Publish/subscribe messaging with topic-based filtering.
"""

from __future__ import annotations

import enum
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set

from .message import MessageEnvelope, MessageKind


# ── Channel kinds ───────────────────────────────────────────────────────────


class ChannelKind(enum.IntEnum):
    """Type of communication channel."""
    DIRECT = 0x01
    BROADCAST = 0x02
    TOPIC = 0x03


# ── Message handler type ────────────────────────────────────────────────────

MessageHandler = Callable[[MessageEnvelope], None]


# ── Base channel ────────────────────────────────────────────────────────────


class Channel:
    """Base class for communication channels."""

    kind: ChannelKind = ChannelKind.DIRECT
    name: str = ""

    def send(self, message: MessageEnvelope) -> bool:
        """Send a message through this channel.

        Returns True if the message was accepted for delivery.
        """
        raise NotImplementedError

    def receive(self, agent: str, max_count: int = 0) -> List[MessageEnvelope]:
        """Receive pending messages for an agent.

        Parameters
        ----------
        agent : str
            The agent name to receive messages for.
        max_count : int
            Maximum messages to return (0 = all).

        Returns
        -------
        list[MessageEnvelope]
            List of received messages (delivery order).
        """
        raise NotImplementedError

    def subscribe(self, agent: str) -> None:
        """Subscribe an agent to this channel."""
        raise NotImplementedError

    def unsubscribe(self, agent: str) -> None:
        """Unsubscribe an agent from this channel."""
        raise NotImplementedError

    def pending_count(self, agent: str) -> int:
        """Return the number of pending messages for an agent."""
        raise NotImplementedError


# ── Direct channel (point-to-point) ────────────────────────────────────────


class DirectChannel(Channel):
    """Point-to-point channel between exactly two agents.

    Messages are buffered per-agent and delivered in FIFO order.
    """

    kind = ChannelKind.DIRECT

    def __init__(self, name: str = "direct", max_buffer: int = 1024) -> None:
        self.name = name
        self._max_buffer = max_buffer
        self._mailboxes: Dict[str, deque] = {}
        self._pairs: Dict[str, Set[str]] = {}  # agent → set of connected agents

    def connect(self, agent_a: str, agent_b: str) -> None:
        """Establish a bidirectional connection between two agents."""
        self._pairs.setdefault(agent_a, set()).add(agent_b)
        self._pairs.setdefault(agent_b, set()).add(agent_a)
        self._mailboxes.setdefault(agent_a, deque(maxlen=self._max_buffer))
        self._mailboxes.setdefault(agent_b, deque(maxlen=self._max_buffer))

    def is_connected(self, agent_a: str, agent_b: str) -> bool:
        """Check if two agents are connected."""
        return agent_b in self._pairs.get(agent_a, set())

    def send(self, message: MessageEnvelope) -> bool:
        """Send a message from sender to receiver (must be connected)."""
        sender = message.sender
        receiver = message.receiver

        if not self.is_connected(sender, receiver):
            return False

        mailbox = self._mailboxes.get(receiver)
        if mailbox is None:
            return False

        if len(mailbox) >= self._max_buffer:
            return False  # buffer full

        mailbox.append(message)
        return True

    def receive(self, agent: str, max_count: int = 0) -> List[MessageEnvelope]:
        """Drain the mailbox for the given agent."""
        mailbox = self._mailboxes.get(agent)
        if mailbox is None:
            return []

        if max_count <= 0:
            result = list(mailbox)
            mailbox.clear()
        else:
            result = []
            for _ in range(min(max_count, len(mailbox))):
                result.append(mailbox.popleft())
        return result

    def subscribe(self, agent: str) -> None:
        """Initialize a mailbox for the agent."""
        self._mailboxes.setdefault(agent, deque(maxlen=self._max_buffer))

    def unsubscribe(self, agent: str) -> None:
        """Remove agent's mailbox and connections."""
        self._mailboxes.pop(agent, None)
        # Remove from pairs
        for other in list(self._pairs.get(agent, set())):
            self._pairs.get(other, set()).discard(agent)
        self._pairs.pop(agent, None)

    def pending_count(self, agent: str) -> int:
        mailbox = self._mailboxes.get(agent)
        return len(mailbox) if mailbox else 0

    def connected_agents(self, agent: str) -> Set[str]:
        """Return the set of agents connected to the given agent."""
        return set(self._pairs.get(agent, set()))


# ── Broadcast channel (one-to-many) ────────────────────────────────────────


class BroadcastChannel(Channel):
    """One-to-many channel where a sender reaches all subscribers.

    All subscribers receive a copy of every message.
    """

    kind = ChannelKind.BROADCAST

    def __init__(self, name: str = "broadcast", max_buffer: int = 1024) -> None:
        self.name = name
        self._max_buffer = max_buffer
        self._subscribers: Set[str] = set()
        self._mailboxes: Dict[str, deque] = {}

    def send(self, message: MessageEnvelope) -> bool:
        """Broadcast a message to all subscribers except the sender."""
        if message.sender not in self._subscribers:
            return False

        delivered = False
        for subscriber in self._subscribers:
            if subscriber == message.sender:
                continue
            mailbox = self._mailboxes.get(subscriber)
            if mailbox is None:
                continue
            if len(mailbox) >= self._max_buffer:
                continue
            mailbox.append(message)
            delivered = True
        return delivered

    def receive(self, agent: str, max_count: int = 0) -> List[MessageEnvelope]:
        mailbox = self._mailboxes.get(agent)
        if mailbox is None:
            return []
        if max_count <= 0:
            result = list(mailbox)
            mailbox.clear()
        else:
            result = []
            for _ in range(min(max_count, len(mailbox))):
                result.append(mailbox.popleft())
        return result

    def subscribe(self, agent: str) -> None:
        self._subscribers.add(agent)
        self._mailboxes.setdefault(agent, deque(maxlen=self._max_buffer))

    def unsubscribe(self, agent: str) -> None:
        self._subscribers.discard(agent)
        self._mailboxes.pop(agent, None)

    def pending_count(self, agent: str) -> int:
        mailbox = self._mailboxes.get(agent)
        return len(mailbox) if mailbox else 0

    @property
    def subscriber_count(self) -> int:
        """Return the number of current subscribers."""
        return len(self._subscribers)

    @property
    def subscribers(self) -> Set[str]:
        """Return a copy of the current subscriber set."""
        return set(self._subscribers)


# ── Topic channel (pub/sub) ────────────────────────────────────────────────


class TopicChannel(Channel):
    """Publish/subscribe channel with topic-based message routing.

    Agents subscribe to specific topics and only receive messages
    published to those topics.
    """

    kind = ChannelKind.TOPIC

    def __init__(self, name: str = "topic", max_buffer: int = 1024) -> None:
        self.name = name
        self._max_buffer = max_buffer
        # topic → set of subscriber agents
        self._topic_subscribers: Dict[str, Set[str]] = {}
        # agent → set of subscribed topics
        self._agent_topics: Dict[str, Set[str]] = {}
        # (agent, topic) → message deque
        self._mailboxes: Dict[tuple, deque] = {}

    def publish(self, message: MessageEnvelope, topic: str) -> bool:
        """Publish a message to a specific topic.

        All agents subscribed to the topic receive a copy.
        """
        subscribers = self._topic_subscribers.get(topic, set())
        if message.sender not in subscribers:
            # Sender must be subscribed to publish
            subscribers_all = self._agent_topics.get(message.sender, set())
            if topic not in subscribers_all:
                return False

        delivered = False
        for subscriber in subscribers:
            if subscriber == message.sender:
                continue
            key = (subscriber, topic)
            mailbox = self._mailboxes.get(key)
            if mailbox is None:
                mailbox = deque(maxlen=self._max_buffer)
                self._mailboxes[key] = mailbox
            if len(mailbox) < self._max_buffer:
                mailbox.append(message)
                delivered = True
        return delivered

    def send(self, message: MessageEnvelope) -> bool:
        """Send a message — uses the 'topic' field from metadata."""
        topic = message.metadata.get("topic", "__default__")
        return self.publish(message, topic)

    def receive(
        self, agent: str, max_count: int = 0, topic: Optional[str] = None
    ) -> List[MessageEnvelope]:
        """Receive messages for an agent, optionally filtered by topic.

        If no topic is specified, returns messages from all subscribed topics.
        """
        if topic is not None:
            keys = [(agent, topic)]
        else:
            topics = self._agent_topics.get(agent, set())
            keys = [(agent, t) for t in topics]

        result = []
        for key in keys:
            mailbox = self._mailboxes.get(key)
            if mailbox is None:
                continue
            if max_count <= 0 or len(result) < max_count:
                count = max_count - len(result) if max_count > 0 else 0
                if count <= 0:
                    msgs = list(mailbox)
                    mailbox.clear()
                else:
                    msgs = []
                    for _ in range(min(count, len(mailbox))):
                        msgs.append(mailbox.popleft())
                result.extend(msgs)
        return result

    def subscribe(self, agent: str, topic: str = "") -> None:
        """Subscribe an agent to a topic (or all topics if empty)."""
        if topic:
            self._topic_subscribers.setdefault(topic, set()).add(agent)
            self._agent_topics.setdefault(agent, set()).add(topic)
        else:
            self._agent_topics.setdefault(agent, set())

    def unsubscribe(self, agent: str, topic: str = "") -> None:
        """Unsubscribe an agent from a topic (or all topics if empty)."""
        if topic:
            subs = self._topic_subscribers.get(topic, set())
            subs.discard(agent)
            agent_topics = self._agent_topics.get(agent, set())
            agent_topics.discard(topic)
            # Clean up mailbox
            self._mailboxes.pop((agent, topic), None)
        else:
            topics = self._agent_topics.pop(agent, set())
            for t in topics:
                subs = self._topic_subscribers.get(t, set())
                subs.discard(agent)
                self._mailboxes.pop((agent, t), None)

    def pending_count(self, agent: str) -> int:
        topics = self._agent_topics.get(agent, set())
        total = 0
        for t in topics:
            mailbox = self._mailboxes.get((agent, t))
            if mailbox:
                total += len(mailbox)
        return total

    def pending_count_topic(self, agent: str, topic: str) -> int:
        mailbox = self._mailboxes.get((agent, topic))
        return len(mailbox) if mailbox else 0

    @property
    def topics(self) -> Set[str]:
        """Return all active topics."""
        return set(self._topic_subscribers.keys())

    def topic_subscribers(self, topic: str) -> Set[str]:
        """Return all subscribers for a specific topic."""
        return set(self._topic_subscribers.get(topic, set()))
