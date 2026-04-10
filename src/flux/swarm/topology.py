"""Agent Topology — defines how agents connect to each other.

Supports five canonical topologies:
- HIERARCHICAL: tree with orchestrator → workers
- FLAT_MESH: everyone talks to everyone
- STAR: central hub with all agents connecting to it
- RING: pipeline with agent → agent → agent → ...
- BLACKBOARD: shared state, agents read/write

Provides methods for:
- Creating specific topologies (classmethod factories)
- Managing connections (connect, disconnect)
- Querying neighbors and paths
- BFS-based shortest path routing
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ── Topology Types ─────────────────────────────────────────────────────────

class SwarmTopology(Enum):
    """Canonical agent topology types."""
    HIERARCHICAL = "hierarchical"  # tree: orchestrator → workers
    FLAT_MESH = "flat_mesh"       # everyone talks to everyone
    STAR = "star"                  # central hub
    RING = "ring"                  # pipeline
    BLACKBOARD = "blackboard"      # shared state


# ── Topology ───────────────────────────────────────────────────────────────

class Topology:
    """Defines how agents connect to each other.

    Maintains an adjacency list of bidirectional connections between agents.
    Supports BFS-based shortest path routing.

    Attributes:
        type: The topology pattern type.
        connections: Mapping from agent_id to set of connected agent_ids.
    """

    def __init__(self, topology_type: SwarmTopology) -> None:
        self.type = topology_type
        self.connections: dict[str, set[str]] = {}

    # ── Connection Management ──────────────────────────────────────────

    def connect(self, agent_a: str, agent_b: str) -> None:
        """Create a bidirectional connection between two agents.

        Args:
            agent_a: First agent ID.
            agent_b: Second agent ID.
        """
        if agent_a == agent_b:
            return  # No self-loops
        self.connections.setdefault(agent_a, set()).add(agent_b)
        self.connections.setdefault(agent_b, set()).add(agent_a)

    def disconnect(self, agent_a: str, agent_b: str) -> None:
        """Remove a bidirectional connection between two agents.

        Args:
            agent_a: First agent ID.
            agent_b: Second agent ID.
        """
        if agent_a in self.connections:
            self.connections[agent_a].discard(agent_b)
        if agent_b in self.connections:
            self.connections[agent_b].discard(agent_a)

    def add_agent(self, agent_id: str) -> None:
        """Register an agent in the topology (no connections yet).

        Args:
            agent_id: Agent to register.
        """
        if agent_id not in self.connections:
            self.connections[agent_id] = set()

    def remove_agent(self, agent_id: str) -> None:
        """Remove an agent and all its connections.

        Args:
            agent_id: Agent to remove.
        """
        if agent_id in self.connections:
            neighbors = list(self.connections[agent_id])
            for neighbor in neighbors:
                self.connections[neighbor].discard(agent_id)
            del self.connections[agent_id]

    # ── Queries ────────────────────────────────────────────────────────

    def neighbors(self, agent_id: str) -> set[str]:
        """Get all agents connected to this one.

        Args:
            agent_id: Agent to query.

        Returns:
            Set of connected agent IDs.
        """
        return set(self.connections.get(agent_id, set()))

    def is_connected(self, agent_a: str, agent_b: str) -> bool:
        """Check if two agents are directly connected."""
        return agent_b in self.connections.get(agent_a, set())

    @property
    def agents(self) -> list[str]:
        """List of all agents in the topology."""
        return list(self.connections.keys())

    @property
    def edge_count(self) -> int:
        """Number of unique edges (undirected)."""
        total = sum(len(neighbors) for neighbors in self.connections.values())
        return total // 2  # Each edge counted twice (bidirectional)

    def degree(self, agent_id: str) -> int:
        """Number of connections for an agent."""
        return len(self.connections.get(agent_id, set()))

    def shortest_path(self, from_id: str, to_id: str) -> list[str]:
        """Find shortest communication path between two agents using BFS.

        Args:
            from_id: Source agent.
            to_id: Target agent.

        Returns:
            List of agent IDs forming the shortest path (inclusive),
            or empty list if no path exists.
        """
        if from_id not in self.connections or to_id not in self.connections:
            return []
        if from_id == to_id:
            return [from_id]

        # BFS
        visited: set[str] = {from_id}
        queue: deque[tuple[str, list[str]]] = deque([(from_id, [from_id])])

        while queue:
            current, path = queue.popleft()
            for neighbor in self.connections.get(current, set()):
                if neighbor == to_id:
                    return path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))

        return []  # No path found

    def path_length(self, from_id: str, to_id: str) -> int:
        """Get the length of the shortest path (number of hops)."""
        path = self.shortest_path(from_id, to_id)
        return max(0, len(path) - 1)

    def is_reachable(self, from_id: str, to_id: str) -> bool:
        """Check if one agent can reach another."""
        return len(self.shortest_path(from_id, to_id)) > 0

    # ── Factory Methods ────────────────────────────────────────────────

    @classmethod
    def hierarchical(cls, orchestrator: str, workers: list[str]) -> Topology:
        """Create a tree topology with orchestrator connected to all workers.

        Args:
            orchestrator: Central orchestrator agent ID.
            workers: List of worker agent IDs.

        Returns:
            Topology with hierarchical layout.
        """
        topo = cls(SwarmTopology.HIERARCHICAL)
        topo.add_agent(orchestrator)
        for worker in workers:
            topo.add_agent(worker)
            topo.connect(orchestrator, worker)
        return topo

    @classmethod
    def flat_mesh(cls, agents: list[str]) -> Topology:
        """Create a flat mesh where everyone connects to everyone.

        Args:
            agents: List of agent IDs.

        Returns:
            Topology with full mesh layout.
        """
        topo = cls(SwarmTopology.FLAT_MESH)
        for agent in agents:
            topo.add_agent(agent)
        for i in range(len(agents)):
            for j in range(i + 1, len(agents)):
                topo.connect(agents[i], agents[j])
        return topo

    @classmethod
    def star(cls, hub: str, spokes: list[str]) -> Topology:
        """Create a star topology with a central hub.

        Args:
            hub: Central hub agent ID.
            spokes: List of spoke agent IDs.

        Returns:
            Topology with star layout.
        """
        topo = cls(SwarmTopology.STAR)
        topo.add_agent(hub)
        for spoke in spokes:
            topo.add_agent(spoke)
            topo.connect(hub, spoke)
        return topo

    @classmethod
    def ring(cls, agents: list[str]) -> Topology:
        """Create a ring/pipeline topology.

        Each agent is connected to its predecessor and successor,
        forming a circular pipeline.

        Args:
            agents: List of agent IDs in pipeline order.

        Returns:
            Topology with ring layout.
        """
        topo = cls(SwarmTopology.RING)
        if len(agents) < 2:
            for agent in agents:
                topo.add_agent(agent)
            return topo

        for agent in agents:
            topo.add_agent(agent)
        for i in range(len(agents)):
            next_idx = (i + 1) % len(agents)
            topo.connect(agents[i], agents[next_idx])
        return topo

    @classmethod
    def blackboard(cls, agents: list[str]) -> Topology:
        """Create a blackboard topology (shared state access pattern).

        All agents can communicate with all others (backed by a shared
        state abstraction). Uses a full mesh as the physical topology.

        Args:
            agents: List of agent IDs.

        Returns:
            Topology with blackboard layout.
        """
        topo = cls(SwarmTopology.BLACKBOARD)
        for agent in agents:
            topo.add_agent(agent)
        for i in range(len(agents)):
            for j in range(i + 1, len(agents)):
                topo.connect(agents[i], agents[j])
        return topo

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize the topology to a dictionary.

        Returns:
            Dictionary with type, agents, edges, and adjacency info.
        """
        return {
            "type": self.type.value,
            "agents": self.agents,
            "edge_count": self.edge_count,
            "connections": {
                agent: sorted(neighbors)
                for agent, neighbors in sorted(self.connections.items())
            },
        }

    def __repr__(self) -> str:
        return (
            f"Topology({self.type.value}, agents={len(self.connections)}, "
            f"edges={self.edge_count})"
        )
