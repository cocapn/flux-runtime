"""FLUX Agent Communication Protocol — typed messages, channels, and agent discovery.

This package provides a higher-level protocol layer on top of the binary
A2A message format.  It introduces:

- **Typed message envelopes** (Request, Response, Event, Error) with
  structured payloads and metadata.
- **Communication channels** (DirectChannel, BroadcastChannel, TopicChannel)
  for different message routing patterns.
- **Agent registry** for service discovery and capability-based routing.
- **Capability negotiation** and trust handshaking for secure agent interaction.
- **Message serialization** to/from bytecode-compatible binary format.
"""

from .message import (
    MessageKind,
    MessageEnvelope,
    Request,
    Response,
    Event,
    Error,
    MessageId,
)
from .channel import (
    Channel,
    DirectChannel,
    BroadcastChannel,
    TopicChannel,
)
from .registry import (
    AgentDescriptor,
    CapabilityDescriptor,
    AgentRegistry,
)
from .negotiation import (
    NegotiationState,
    CapabilityOffer,
    TrustHandshake,
    Negotiator,
)
from .serialization import (
    MessageSerializer,
    BinaryMessageCodec,
)

__all__ = [
    # Messages
    "MessageKind", "MessageEnvelope", "Request", "Response", "Event", "Error",
    "MessageId",
    # Channels
    "Channel", "DirectChannel", "BroadcastChannel", "TopicChannel",
    # Registry
    "AgentDescriptor", "CapabilityDescriptor", "AgentRegistry",
    # Negotiation
    "NegotiationState", "CapabilityOffer", "TrustHandshake", "Negotiator",
    # Serialization
    "MessageSerializer", "BinaryMessageCodec",
]
