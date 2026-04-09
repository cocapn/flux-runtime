"""A2A Message Transport — In-process local delivery with mailbox semantics.

Each registered agent gets a FIFO mailbox.  Messages are appended on
``send`` and drained on ``receive``.  No persistence, no networking —
purely synchronous delivery within a single Python process.

Agent identifiers are ``uuid.UUID`` instances (128-bit), matching the
A2A protocol layer.
"""

from __future__ import annotations

from collections import deque
from typing import Deque

from flux.a2a.messages import A2AMessage
import uuid


class LocalTransport:
    """In-process message delivery (zero-copy for same-VM agents).

    Each registered agent gets a mailbox (a ``deque``).  Messages are
    appended on :meth:`send` and drained on :meth:`receive`.
    """

    def __init__(self) -> None:
        self._mailboxes: dict[uuid.UUID, Deque[A2AMessage]] = {}

    # ── Registration ──────────────────────────────────────────────────────

    def register(self, agent_id: uuid.UUID) -> None:
        """Create an empty mailbox for *agent_id*.

        Re-registering an existing agent clears its mailbox.
        """
        self._mailboxes[agent_id] = deque()

    def unregister(self, agent_id: uuid.UUID) -> None:
        """Remove an agent's mailbox entirely."""
        self._mailboxes.pop(agent_id, None)

    # ── Send / Receive ────────────────────────────────────────────────────

    def send(self, message: A2AMessage) -> bool:
        """Deliver *message* to the receiver's mailbox.

        Returns ``True`` if the receiver is registered, ``False`` otherwise.
        """
        target = message.receiver
        if target in self._mailboxes:
            self._mailboxes[target].append(message)
            return True
        return False

    def receive(self, agent_id: uuid.UUID) -> list[A2AMessage]:
        """Return **and clear** the mailbox for *agent_id*.

        If the agent is not registered, returns an empty list.
        """
        mailbox = self._mailboxes.get(agent_id)
        if mailbox is None:
            return []
        msgs = list(mailbox)
        mailbox.clear()
        return msgs

    # ── Queries ───────────────────────────────────────────────────────────

    def pending_count(self, agent_id: uuid.UUID) -> int:
        """Return the number of undelivered messages in the mailbox."""
        mailbox = self._mailboxes.get(agent_id)
        return len(mailbox) if mailbox is not None else 0

    def is_registered(self, agent_id: uuid.UUID) -> bool:
        """Check whether *agent_id* has a mailbox."""
        return agent_id in self._mailboxes

    def registered_agents(self) -> list[uuid.UUID]:
        """Return a list of all registered agent IDs."""
        return list(self._mailboxes.keys())
