"""Agent registry for service discovery and capability-based routing.

The agent registry maintains a directory of known agents, their capabilities,
and provides lookup/routing functionality for the FLUX protocol layer.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


# ── Capability descriptor ───────────────────────────────────────────────────


@dataclass(frozen=True)
class CapabilityDescriptor:
    """Describes a single capability offered by an agent.

    Attributes
    ----------
    name : str
        Capability name (e.g., "compute.add", "file.read").
    version : str
        Semantic version string.
    params : tuple
        Tuple of parameter type descriptors.
    returns : tuple
        Tuple of return type descriptors.
    """

    name: str
    version: str = "1.0.0"
    params: tuple = ()
    returns: tuple = ()

    def matches(self, other: CapabilityDescriptor) -> bool:
        """Check if this capability matches another (name and version compatible)."""
        if self.name != other.name:
            return False
        # Simple version matching: exact match
        return self.version == other.version

    def __repr__(self) -> str:
        return f"Capability({self.name}@{self.version})"


# ── Agent descriptor ────────────────────────────────────────────────────────


@dataclass
class AgentDescriptor:
    """Full descriptor for a registered agent.

    Attributes
    ----------
    name : str
        Human-readable agent name.
    agent_id : str
        Unique agent identifier (UUID hex).
    capabilities : set
        Set of CapabilityDescriptor instances this agent offers.
    endpoints : dict
        Communication endpoints (name → address/URL).
    metadata : dict
        Arbitrary agent metadata.
    registered_at : float
        Unix timestamp of registration.
    last_seen : float
        Unix timestamp of last heartbeat.
    status : str
        Agent status: "active", "idle", "offline", "error".
    """

    name: str
    agent_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    capabilities: Set[CapabilityDescriptor] = field(default_factory=set)
    endpoints: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    registered_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    status: str = "active"

    def add_capability(self, cap: CapabilityDescriptor) -> None:
        """Register a capability for this agent."""
        self.capabilities.add(cap)

    def has_capability(self, name: str) -> bool:
        """Check if the agent offers a capability by name."""
        return any(c.name == name for c in self.capabilities)

    def get_capability(self, name: str) -> Optional[CapabilityDescriptor]:
        """Look up a capability by name, or None if not found."""
        for c in self.capabilities:
            if c.name == name:
                return c
        return None

    def heartbeat(self) -> None:
        """Update the last_seen timestamp."""
        self.last_seen = time.time()

    @property
    def capability_names(self) -> List[str]:
        """Return a sorted list of capability names."""
        return sorted(c.name for c in self.capabilities)

    @property
    def is_active(self) -> bool:
        """Check if the agent is currently active."""
        return self.status == "active"

    def __repr__(self) -> str:
        caps = ",".join(self.capability_names[:3])
        suffix = f"..." if len(self.capability_names) > 3 else ""
        return f"Agent({self.name}, caps=[{caps}{suffix}])"


# ── Agent registry ──────────────────────────────────────────────────────────


class AgentRegistry:
    """Central registry for agent discovery and capability-based routing.

    Supports:
    - Agent registration/unregistration
    - Capability-based agent lookup
    - Heartbeat tracking with expiry
    - Routing: find agents that can handle a given capability
    """

    def __init__(self, heartbeat_timeout: float = 300.0) -> None:
        self._agents: Dict[str, AgentDescriptor] = {}
        self._heartbeat_timeout = heartbeat_timeout

    # ── Registration ────────────────────────────────────────────────────

    def register(self, descriptor: AgentDescriptor) -> None:
        """Register an agent with the registry."""
        self._agents[descriptor.name] = descriptor

    def unregister(self, name: str) -> Optional[AgentDescriptor]:
        """Unregister an agent by name.  Returns the removed descriptor."""
        return self._agents.pop(name, None)

    def get(self, name: str) -> Optional[AgentDescriptor]:
        """Look up an agent by name."""
        return self._agents.get(name)

    def get_by_id(self, agent_id: str) -> Optional[AgentDescriptor]:
        """Look up an agent by its unique ID."""
        for desc in self._agents.values():
            if desc.agent_id == agent_id:
                return desc
        return None

    # ── Listing ─────────────────────────────────────────────────────────

    def list_agents(self, status: Optional[str] = None) -> List[AgentDescriptor]:
        """List all agents, optionally filtered by status."""
        agents = list(self._agents.values())
        if status is not None:
            agents = [a for a in agents if a.status == status]
        return agents

    def list_all_names(self) -> List[str]:
        """Return a list of all registered agent names."""
        return list(self._agents.keys())

    @property
    def count(self) -> int:
        """Return the number of registered agents."""
        return len(self._agents)

    # ── Capability-based lookup ─────────────────────────────────────────

    def find_by_capability(self, capability_name: str) -> List[AgentDescriptor]:
        """Find all agents that offer a given capability."""
        return [
            desc for desc in self._agents.values()
            if desc.has_capability(capability_name)
        ]

    def find_by_capabilities(
        self, capability_names: List[str]
    ) -> List[AgentDescriptor]:
        """Find all agents that offer ALL of the given capabilities."""
        cap_set = set(capability_names)
        return [
            desc for desc in self._agents.values()
            if cap_set.issubset(set(desc.capability_names))
        ]

    def route(self, capability_name: str) -> Optional[AgentDescriptor]:
        """Find the best agent to handle a capability.

        Strategy: pick the active agent with the most recent heartbeat.
        """
        candidates = self.find_by_capability(capability_name)
        active = [a for a in candidates if a.is_active]
        if not active:
            return None
        # Most recently seen
        return max(active, key=lambda a: a.last_seen)

    # ── Heartbeat management ────────────────────────────────────────────

    def heartbeat(self, name: str) -> bool:
        """Update heartbeat for a registered agent.  Returns False if unknown."""
        desc = self._agents.get(name)
        if desc is None:
            return False
        desc.heartbeat()
        return True

    def expire_stale(self) -> List[str]:
        """Mark agents with expired heartbeats as offline.

        Returns a list of names that were marked offline.
        """
        now = time.time()
        expired = []
        for name, desc in self._agents.items():
            if desc.status == "active" and (now - desc.last_seen) > self._heartbeat_timeout:
                desc.status = "offline"
                expired.append(name)
        return expired

    # ── Bulk operations ─────────────────────────────────────────────────

    def clear(self) -> None:
        """Remove all registered agents."""
        self._agents.clear()

    def all_capabilities(self) -> Set[str]:
        """Return the union of all capability names across all agents."""
        caps: Set[str] = set()
        for desc in self._agents.values():
            caps.update(desc.capability_names)
        return caps
