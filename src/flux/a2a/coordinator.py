"""Agent Coordinator — Orchestrates multiple agents within a single VM.

Ties together :class:`LocalTransport` for message delivery and
:class:`TrustEngine` for trust-gated communication.  Agents are
identified by string names; internally each is assigned a ``uuid.UUID``
for the A2A protocol layer.

Message flow:

    agent_a.send_message("bob", TELL, payload=b"hi")
        → trust check (compute_trust >= threshold)
        → build A2AMessage
        → transport.send(message)
        → message lands in bob's mailbox
        → agent_b.get_messages("bob") drains the mailbox
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import uuid

from flux.a2a.messages import A2AMessage
from flux.a2a.transport import LocalTransport
from flux.a2a.trust import TrustEngine


class AgentCoordinator:
    """Coordinates multiple agents running in the same VM.

    Parameters
    ----------
    trust_threshold : float
        Minimum trust score required for message delivery (default 0.3).
    """

    def __init__(self, trust_threshold: float = 0.3) -> None:
        self._agents: Dict[str, Dict[str, Any]] = {}
        self.trust: TrustEngine = TrustEngine()
        self.transport: LocalTransport = LocalTransport()
        self.trust_threshold: float = trust_threshold

    # ── Agent Registration ────────────────────────────────────────────────

    def register_agent(
        self, agent_id: str, interpreter: Any = None
    ) -> uuid.UUID:
        """Register an agent with an optional VM interpreter.

        Parameters
        ----------
        agent_id : str
            Logical name for the agent.
        interpreter : Any, optional
            A :class:`flux.vm.interpreter.Interpreter` instance, or None.

        Returns
        -------
        uuid.UUID
            The generated UUID for this agent (used in A2A headers).
        """
        aid = uuid.uuid4()
        self.transport.register(aid)
        self._agents[agent_id] = {
            "uuid": aid,
            "interpreter": interpreter,
        }
        return aid

    def unregister_agent(self, agent_id: str) -> None:
        """Remove an agent from the coordinator."""
        info = self._agents.pop(agent_id, None)
        if info is not None:
            self.transport.unregister(info["uuid"])

    # ── Messaging ─────────────────────────────────────────────────────────

    def send_message(
        self,
        sender: str,
        receiver: str,
        msg_type: int,
        payload: bytes = b"",
        priority: int = 5,
        in_reply_to: Optional[uuid.UUID] = None,
    ) -> bool:
        """Send an A2A message between registered agents.

        The message is only delivered if the trust score from *sender*
        to *receiver* meets the configured threshold.

        Parameters
        ----------
        sender : str
            Name of the sending agent.
        receiver : str
            Name of the receiving agent.
        msg_type : int
            A2A message type (0x60–0x7B).
        payload : bytes
            Application-level payload.
        priority : int
            Delivery priority 0–15.
        in_reply_to : uuid.UUID, optional
            UUID this message is replying to.

        Returns
        -------
        bool
            ``True`` if the message was delivered, ``False`` if blocked
            by the trust gate or if either agent is unknown.
        """
        # Trust gate
        trust = self.trust.compute_trust(sender, receiver)
        if trust < self.trust_threshold:
            return False

        sender_info = self._agents.get(sender)
        receiver_info = self._agents.get(receiver)
        if sender_info is None or receiver_info is None:
            return False

        msg = A2AMessage(
            sender=sender_info["uuid"],
            receiver=receiver_info["uuid"],
            conversation_id=uuid.uuid4(),
            in_reply_to=in_reply_to,
            message_type=msg_type,
            priority=priority,
            trust_token=int(trust * 1e9),
            capability_token=0,
            payload=payload,
        )

        delivered = self.transport.send(msg)
        if delivered:
            # Record positive interaction on success
            self.trust.record_interaction(sender, receiver, True, 0.1)
        return delivered

    def get_messages(self, agent_id: str) -> List[A2AMessage]:
        """Drain the mailbox for *agent_id* and return all pending messages."""
        info = self._agents.get(agent_id)
        if info is None:
            return []
        return self.transport.receive(info["uuid"])

    def pending_count(self, agent_id: str) -> int:
        """Return the number of pending messages for *agent_id*."""
        info = self._agents.get(agent_id)
        if info is None:
            return 0
        return self.transport.pending_count(info["uuid"])

    # ── Queries ───────────────────────────────────────────────────────────

    def get_agent_uuid(self, agent_name: str) -> Optional[uuid.UUID]:
        """Return the UUID for a named agent, or ``None``."""
        info = self._agents.get(agent_name)
        return info["uuid"] if info else None

    def registered_agents(self) -> List[str]:
        """Return a list of all registered agent names."""
        return list(self._agents.keys())
