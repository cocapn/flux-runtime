"""FLUX A2A Protocol Layer — Agent-to-Agent communication primitives.

This package provides:
- ``messages``  — Binary A2A message types (A2AMessage with 52-byte header)
- ``transport``  — Local in-process message delivery (LocalTransport)
- ``trust``      — INCREMENTS+2 trust engine (TrustEngine, InteractionRecord, AgentProfile)
- ``coordinator`` — Multi-agent orchestration (AgentCoordinator)
"""

from flux.a2a.messages import A2AMessage
from flux.a2a.transport import LocalTransport
from flux.a2a.trust import InteractionRecord, AgentProfile, TrustEngine
from flux.a2a.coordinator import AgentCoordinator

__all__ = [
    # Messages
    "A2AMessage",
    # Transport
    "LocalTransport",
    # Trust
    "InteractionRecord",
    "AgentProfile",
    "TrustEngine",
    # Coordinator
    "AgentCoordinator",
]
