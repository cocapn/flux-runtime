"""Capability negotiation and trust handshaking for the FLUX agent protocol.

When two agents need to communicate, they must first negotiate shared
capabilities and establish a trust relationship.  This module provides:

- **CapabilityOffer**: A proposal of capabilities an agent is willing to share.
- **TrustHandshake**: A multi-step protocol for establishing trust between agents.
- **Negotiator**: High-level API for managing the negotiation lifecycle.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .registry import CapabilityDescriptor, AgentDescriptor


# ── Negotiation states ──────────────────────────────────────────────────────


class NegotiationState(enum.IntEnum):
    """States in the capability negotiation lifecycle."""
    IDLE = 0
    PROPOSED = 1
    COUNTER_PROPOSED = 2
    ACCEPTED = 3
    REJECTED = 4
    EXPIRED = 5
    FAILED = 6


# ── Capability offer ────────────────────────────────────────────────────────


@dataclass
class CapabilityOffer:
    """A proposal of capabilities an agent offers to share.

    Attributes
    ----------
    offer_id : str
        Unique identifier for this offer.
    agent_name : str
        Name of the offering agent.
    capabilities : list
        List of CapabilityDescriptor instances being offered.
    requirements : list
        List of capability names the offering agent requires from the counterparty.
    trust_level : float
        Minimum trust level required (0.0–1.0).
    expires_at : float
        Unix timestamp when this offer expires.
    metadata : dict
        Additional negotiation metadata.
    """

    offer_id: str = ""
    agent_name: str = ""
    capabilities: List[CapabilityDescriptor] = field(default_factory=list)
    requirements: List[str] = field(default_factory=list)
    trust_level: float = 0.3
    expires_at: float = 0.0
    metadata: Dict[str, dict] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.offer_id:
            import uuid
            self.offer_id = uuid.uuid4().hex[:16]
        if not self.expires_at:
            self.expires_at = time.time() + 300.0  # 5 minutes default

    @property
    def is_expired(self) -> bool:
        """Check if this offer has expired."""
        return time.time() > self.expires_at

    @property
    def capability_names(self) -> List[str]:
        """Return names of offered capabilities."""
        return [c.name for c in self.capabilities]

    def matches_requirement(self, cap_name: str) -> bool:
        """Check if a capability name is in the offer."""
        return cap_name in self.capability_names


# ── Trust handshake ─────────────────────────────────────────────────────────


@dataclass
class TrustHandshake:
    """A multi-step trust handshake between two agents.

    The handshake proceeds through these steps:
    1. **Initiate**: Agent A sends a handshake request to Agent B.
    2. **Challenge**: Agent B responds with a challenge (nonce).
    3. **Response**: Agent A responds with proof (signed nonce).
    4. **Complete**: Agent B verifies and either accepts or rejects.

    Attributes
    ----------
    handshake_id : str
        Unique identifier for this handshake.
    initiator : str
        Name of the initiating agent.
    responder : str
        Name of the responding agent.
    state : NegotiationState
        Current state of the handshake.
    trust_level : float
        Agreed-upon trust level.
    nonce : str
        Challenge nonce sent by the responder.
    proof : str
        Proof of identity provided by the initiator.
    error : str
        Error message if the handshake failed.
    created_at : float
        Unix timestamp of handshake creation.
    completed_at : float
        Unix timestamp when the handshake completed.
    """

    handshake_id: str = ""
    initiator: str = ""
    responder: str = ""
    state: NegotiationState = NegotiationState.IDLE
    trust_level: float = 0.0
    nonce: str = ""
    proof: str = ""
    error: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.handshake_id:
            import uuid
            self.handshake_id = uuid.uuid4().hex[:16]

    def initiate(self, initiator: str, responder: str, trust_level: float = 0.5) -> None:
        """Start a new handshake."""
        self.initiator = initiator
        self.responder = responder
        self.trust_level = trust_level
        self.state = NegotiationState.PROPOSED
        self.created_at = time.time()

    def challenge(self, nonce: str) -> None:
        """Respond with a challenge nonce (step 2)."""
        if self.state != NegotiationState.PROPOSED:
            raise ValueError(f"Cannot challenge in state {self.state.name}")
        self.nonce = nonce
        self.state = NegotiationState.COUNTER_PROPOSED

    def respond(self, proof: str) -> None:
        """Provide proof of identity (step 3)."""
        if self.state != NegotiationState.COUNTER_PROPOSED:
            raise ValueError(f"Cannot respond in state {self.state.name}")
        self.proof = proof

    def accept(self) -> None:
        """Accept the handshake (step 4 — success)."""
        if self.state != NegotiationState.COUNTER_PROPOSED:
            raise ValueError(f"Cannot accept in state {self.state.name}")
        self.state = NegotiationState.ACCEPTED
        self.completed_at = time.time()

    def reject(self, reason: str = "") -> None:
        """Reject the handshake (step 4 — failure)."""
        self.state = NegotiationState.REJECTED
        self.error = reason
        self.completed_at = time.time()

    def expire(self) -> None:
        """Mark the handshake as expired."""
        self.state = NegotiationState.EXPIRED
        self.completed_at = time.time()

    def fail(self, error: str) -> None:
        """Mark the handshake as failed due to an error."""
        self.state = NegotiationState.FAILED
        self.error = error
        self.completed_at = time.time()

    @property
    def is_complete(self) -> bool:
        """Check if the handshake has reached a terminal state."""
        return self.state in (
            NegotiationState.ACCEPTED,
            NegotiationState.REJECTED,
            NegotiationState.EXPIRED,
            NegotiationState.FAILED,
        )

    @property
    def duration(self) -> float:
        """Time elapsed for the handshake (0 if not complete)."""
        if self.completed_at <= 0:
            return time.time() - self.created_at
        return self.completed_at - self.created_at


# ── Negotiator ──────────────────────────────────────────────────────────────


class Negotiator:
    """High-level capability negotiator.

    Manages the lifecycle of capability offers and trust handshakes
    between agents.
    """

    def __init__(
        self,
        default_trust_level: float = 0.3,
        offer_ttl: float = 300.0,
        handshake_timeout: float = 60.0,
    ) -> None:
        self._default_trust = default_trust_level
        self._offer_ttl = offer_ttl
        self._handshake_timeout = handshake_timeout
        self._offers: Dict[str, CapabilityOffer] = {}
        self._handshakes: Dict[str, TrustHandshake] = {}
        self._agreements: Dict[tuple, float] = {}  # (agent_a, agent_b) → trust_level

    # ── Offer management ────────────────────────────────────────────────

    def create_offer(
        self,
        agent_name: str,
        capabilities: List[CapabilityDescriptor],
        requirements: Optional[List[str]] = None,
        trust_level: Optional[float] = None,
    ) -> CapabilityOffer:
        """Create a new capability offer from an agent."""
        offer = CapabilityOffer(
            agent_name=agent_name,
            capabilities=capabilities,
            requirements=requirements or [],
            trust_level=trust_level or self._default_trust,
            expires_at=time.time() + self._offer_ttl,
        )
        self._offers[offer.offer_id] = offer
        return offer

    def get_offer(self, offer_id: str) -> Optional[CapabilityOffer]:
        """Look up an offer by ID."""
        return self._offers.get(offer_id)

    def accept_offer(self, offer_id: str, accepting_agent: str) -> bool:
        """Accept a capability offer.

        Returns True if the offer was valid and accepted.
        """
        offer = self._offers.get(offer_id)
        if offer is None:
            return False
        if offer.is_expired:
            return False
        if offer.agent_name == accepting_agent:
            return False  # cannot accept own offer
        # Record agreement
        key = (offer.agent_name, accepting_agent)
        self._agreements[key] = max(
            self._agreements.get(key, 0.0), offer.trust_level
        )
        return True

    def reject_offer(self, offer_id: str) -> bool:
        """Reject a capability offer.  Returns True if the offer existed."""
        return self._offers.pop(offer_id, None) is not None

    def expire_offers(self) -> List[str]:
        """Remove all expired offers.  Returns list of expired offer IDs."""
        expired = []
        for oid, offer in self._offers.items():
            if offer.is_expired:
                expired.append(oid)
        for oid in expired:
            del self._offers[oid]
        return expired

    # ── Handshake management ────────────────────────────────────────────

    def initiate_handshake(
        self,
        initiator: str,
        responder: str,
        trust_level: float = 0.5,
    ) -> TrustHandshake:
        """Start a new trust handshake."""
        hs = TrustHandshake()
        hs.initiate(initiator, responder, trust_level)
        self._handshakes[hs.handshake_id] = hs
        return hs

    def get_handshake(self, handshake_id: str) -> Optional[TrustHandshake]:
        """Look up a handshake by ID."""
        return self._handshakes.get(handshake_id)

    def complete_handshake(self, handshake_id: str) -> bool:
        """Complete a handshake by accepting it.

        Returns True if the handshake was in the correct state.
        """
        hs = self._handshakes.get(handshake_id)
        if hs is None:
            return False
        if hs.state != NegotiationState.COUNTER_PROPOSED:
            return False
        hs.accept()
        # Record the trust agreement
        key = (hs.initiator, hs.responder)
        self._agreements[key] = max(
            self._agreements.get(key, 0.0), hs.trust_level
        )
        return True

    def expire_handshakes(self) -> List[str]:
        """Expire all handshakes that have exceeded the timeout.

        Returns a list of expired handshake IDs.
        """
        now = time.time()
        expired = []
        for hid, hs in self._handshakes.items():
            if not hs.is_complete and (now - hs.created_at) > self._handshake_timeout:
                hs.expire()
                expired.append(hid)
        return expired

    # ── Agreement queries ───────────────────────────────────────────────

    def get_trust_level(self, agent_a: str, agent_b: str) -> float:
        """Get the agreed trust level between two agents."""
        key = (agent_a, agent_b)
        return self._agreements.get(key, 0.0)

    def has_agreement(self, agent_a: str, agent_b: str) -> bool:
        """Check if two agents have a trust agreement."""
        return (agent_a, agent_b) in self._agreements or (agent_b, agent_a) in self._agreements

    # ── Statistics ──────────────────────────────────────────────────────

    @property
    def active_offers(self) -> int:
        """Number of active (non-expired) offers."""
        return sum(1 for o in self._offers.values() if not o.is_expired)

    @property
    def active_handshakes(self) -> int:
        """Number of active (non-terminal) handshakes."""
        return sum(1 for h in self._handshakes.values() if not h.is_complete)

    @property
    def total_agreements(self) -> int:
        """Total number of trust agreements."""
        return len(self._agreements)

    def clear(self) -> None:
        """Clear all offers, handshakes, and agreements."""
        self._offers.clear()
        self._handshakes.clear()
        self._agreements.clear()
