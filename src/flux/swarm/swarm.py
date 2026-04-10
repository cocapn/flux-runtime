"""Swarm Orchestrator — manages groups of collaborating FLUX agents.

The Swarm ties together:
- Agent management (spawn, despawn)
- Message routing (broadcast, scatter, reduce)
- Synchronization (barrier)
- Deadlock detection
- Evolution (parallel agent evolution)
- Topology optimization
- Comprehensive reporting
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .agent import (
    AgentRole,
    AgentTask,
    FluxAgent,
    TrustProfile,
)
from .deadlock import DeadlockDetector, DeadlockReport, DeadlockSeverity
from .message_bus import AgentMessage, MessageBus
from .topology import SwarmTopology, Topology


# ── Report Types ───────────────────────────────────────────────────────────

@dataclass
class SwarmReport:
    """Comprehensive report of swarm state."""
    name: str = ""
    topology_type: str = ""
    agent_count: int = 0
    total_messages: int = 0
    total_tasks_completed: int = 0
    total_tasks_failed: int = 0
    agents: list[dict] = field(default_factory=list)
    topology: dict = field(default_factory=dict)
    deadlock_reports: list[dict] = field(default_factory=list)
    uptime_seconds: float = 0.0


@dataclass
class SwarmEvolutionReport:
    """Report from evolving the swarm."""
    generations_run: int = 0
    agents_evolved: int = 0
    role_changes: list[dict] = field(default_factory=list)
    total_time_ns: int = 0


@dataclass
class TopologyChange:
    """Suggested topology change based on communication patterns."""
    description: str = ""
    change_type: str = ""  # "add_edge", "remove_edge", "restructure"
    agents_involved: list[str] = field(default_factory=list)
    confidence: float = 0.0


# ── Swarm ──────────────────────────────────────────────────────────────────

class Swarm:
    """Manages a group of collaborating FLUX agents.

    Provides:
    - Agent lifecycle (spawn, despawn)
    - Message routing (broadcast, scatter, reduce)
    - Synchronization (barrier)
    - Deadlock detection
    - Parallel evolution
    - Topology optimization
    - Comprehensive reporting

    Args:
        name: Human-readable name for this swarm.
        topology: The initial agent topology.
    """

    def __init__(self, name: str, topology: Topology) -> None:
        self.name = name
        self.topology = topology
        self.agents: dict[str, FluxAgent] = {}
        self.message_bus = MessageBus()
        self.deadlock_detector = DeadlockDetector()
        self._barrier_events: dict[str, set[str]] = {}
        self.created_at: float = time.time()
        self._topology_changes: list[TopologyChange] = []

    # ── Agent Lifecycle ────────────────────────────────────────────────

    def spawn(
        self,
        agent_id: str,
        role: AgentRole = AgentRole.GENERAL,
    ) -> FluxAgent:
        """Create and register a new agent in the swarm.

        Args:
            agent_id: Unique identifier for the agent.
            role: Initial agent role.

        Returns:
            The newly created FluxAgent.

        Raises:
            ValueError: If agent_id is already registered.
        """
        if agent_id in self.agents:
            raise ValueError(f"Agent '{agent_id}' already exists in swarm '{self.name}'")

        agent = FluxAgent(agent_id=agent_id, role=role)
        self.agents[agent_id] = agent

        # Register with message bus
        self.message_bus.register(agent_id)

        # Add to topology if not already present
        if agent_id not in self.topology.connections:
            self.topology.add_agent(agent_id)

        return agent

    def despawn(self, agent_id: str) -> Optional[FluxAgent]:
        """Remove an agent from the swarm.

        Args:
            agent_id: Agent to remove.

        Returns:
            The removed agent, or None if not found.
        """
        agent = self.agents.pop(agent_id, None)
        if agent is None:
            return None

        # Unregister from message bus
        self.message_bus.unregister(agent_id)

        # Remove from topology
        self.topology.remove_agent(agent_id)

        return agent

    def get_agent(self, agent_id: str) -> Optional[FluxAgent]:
        """Get an agent by ID.

        Args:
            agent_id: Agent to look up.

        Returns:
            FluxAgent or None if not found.
        """
        return self.agents.get(agent_id)

    # ── Messaging ──────────────────────────────────────────────────────

    def broadcast(self, sender_id: str, message: AgentMessage) -> int:
        """Send a message to all agents connected to the sender in the topology.

        Args:
            sender_id: Sending agent ID.
            message: Message to broadcast.

        Returns:
            Number of agents that received the message.
        """
        if sender_id not in self.agents:
            return 0

        neighbors = self.topology.neighbors(sender_id)
        delivered = 0

        for neighbor_id in neighbors:
            if neighbor_id in self.agents:
                msg = AgentMessage(
                    sender=sender_id,
                    receiver=neighbor_id,
                    msg_type=message.msg_type,
                    payload=dict(message.payload),
                    topic=message.topic,
                    priority=message.priority,
                )
                if self.message_bus.send(
                    sender_id, neighbor_id, msg.payload, msg.msg_type, msg.priority
                ):
                    delivered += 1
                    # Record wait for deadlock detection
                    self.deadlock_detector.record_wait(sender_id, neighbor_id)

        return delivered

    def scatter(
        self, sender_id: str, message: AgentMessage, targets: list[str]
    ) -> int:
        """Send a message to specific target agents.

        Args:
            sender_id: Sending agent ID.
            message: Message to send.
            targets: List of target agent IDs.

        Returns:
            Number of agents that received the message.
        """
        if sender_id not in self.agents:
            return 0

        delivered = 0
        for target_id in targets:
            if target_id in self.agents and target_id != sender_id:
                msg = AgentMessage(
                    sender=sender_id,
                    receiver=target_id,
                    msg_type=message.msg_type,
                    payload=dict(message.payload),
                    priority=message.priority,
                )
                if self.message_bus.send(
                    sender_id, target_id, msg.payload, msg.msg_type, msg.priority
                ):
                    delivered += 1
                    self.deadlock_detector.record_wait(sender_id, target_id)

        return delivered

    def reduce(
        self,
        coordinator_id: str,
        reducer: Callable[[list[Any]], Any],
        timeout: float = 30.0,
    ) -> Optional[Any]:
        """Collect results from all agents and reduce.

        Each agent contributes its current stats. The reducer function
        combines these into a single result.

        Args:
            coordinator_id: Agent coordinating the reduce operation.
            reducer: Function that takes a list of values and returns one.
            timeout: Maximum time to wait (unused in sync implementation).

        Returns:
            Reduced result, or None if coordinator not found.
        """
        if coordinator_id not in self.agents:
            return None

        values = []
        for agent_id, agent in self.agents.items():
            values.append(agent.get_stats())

        try:
            return reducer(values)
        except Exception:
            return None

    # ── Synchronization ────────────────────────────────────────────────

    def barrier(
        self,
        barrier_id: str,
        participant_ids: list[str],
    ) -> bool:
        """Synchronization point — wait for all participants to arrive.

        In this synchronous implementation, barrier succeeds immediately
        if all participants are registered.

        Args:
            barrier_id: Unique barrier identifier.
            participant_ids: List of agent IDs that must participate.

        Returns:
            True if all participants have arrived at the barrier.
        """
        if barrier_id not in self._barrier_events:
            self._barrier_events[barrier_id] = set()

        arrived = self._barrier_events[barrier_id]

        # Mark all participants as arrived
        for pid in participant_ids:
            if pid in self.agents:
                arrived.add(pid)

        # Check if all participants have arrived
        all_registered = all(pid in self.agents for pid in participant_ids)
        all_arrived = all(pid in arrived for pid in participant_ids)

        return all_registered and all_arrived

    def clear_barrier(self, barrier_id: str) -> None:
        """Clear a barrier event."""
        self._barrier_events.pop(barrier_id, None)

    # ── Deadlock Detection ─────────────────────────────────────────────

    def check_deadlocks(self) -> list[DeadlockReport]:
        """Run deadlock detection on pending A2A operations.

        Returns:
            List of DeadlockReports for any detected issues.
        """
        # Clear previous wait records that have been resolved
        # (agents that have no pending messages)
        for agent_id in list(self.deadlock_detector._wait_graph.keys()):
            if agent_id in self.agents:
                pending = self.message_bus.pending_count(agent_id)
                if pending == 0:
                    self.deadlock_detector.record_release(agent_id)

        message_log = self.message_bus.get_log()
        return self.deadlock_detector.check_deadlocks(message_log)

    # ── Evolution ──────────────────────────────────────────────────────

    def evolve_swarm(self, generations: int = 3) -> SwarmEvolutionReport:
        """Evolve all agents in parallel, then optimize topology.

        Each agent runs its own local evolution (specialization analysis)
        based on accumulated profiling data.

        Args:
            generations: Number of evolution generations per agent.

        Returns:
            SwarmEvolutionReport with evolution results.
        """
        start = time.monotonic_ns()
        report = SwarmEvolutionReport()
        report.generations_run = generations

        for agent_id, agent in self.agents.items():
            old_role = agent.role
            agent.evolve(generations)
            new_role = agent.role
            report.agents_evolved += 1

            if old_role != new_role:
                report.role_changes.append({
                    "agent_id": agent_id,
                    "old_role": old_role.value,
                    "new_role": new_role.value,
                })

        report.total_time_ns = time.monotonic_ns() - start

        # After evolution, optimize topology
        change = self.optimize_topology()
        if change.confidence > 0.0:
            self._topology_changes.append(change)

        return report

    # ── Topology Optimization ──────────────────────────────────────────

    def optimize_topology(self) -> TopologyChange:
        """Analyze communication patterns and suggest topology improvements.

        Looks at:
        - Agents that communicate frequently → suggest direct connection
        - Agents with high degree → potential bottleneck
        - Agents forming cliques → suggest sub-grouping

        Returns:
            TopologyChange with suggestion (may have confidence=0.0 if no change needed).
        """
        message_log = self.message_bus.get_log(limit=200)
        if not message_log:
            return TopologyChange(
                description="No messages to analyze.",
                confidence=0.0,
            )

        # Count message frequency between agent pairs
        from collections import Counter

        pair_counts: Counter[tuple[str, str]] = Counter()
        for msg in message_log:
            if msg.sender and msg.receiver and msg.sender != msg.receiver:
                pair = tuple(sorted([msg.sender, msg.receiver]))
                pair_counts[pair] += 1

        if not pair_counts:
            return TopologyChange(
                description="No direct messages to analyze.",
                confidence=0.0,
            )

        # Find the most communicating pair that isn't directly connected
        most_common = pair_counts.most_common(1)[0]
        pair, count = most_common

        if count >= 5 and not self.topology.is_connected(pair[0], pair[1]):
            confidence = min(1.0, count / 20.0)
            return TopologyChange(
                description=(
                    f"Agents '{pair[0]}' and '{pair[1]}' communicate frequently "
                    f"({count} messages) but are not directly connected. "
                    f"Consider adding a direct edge."
                ),
                change_type="add_edge",
                agents_involved=list(pair),
                confidence=confidence,
            )

        # Check for bottleneck agents (high degree)
        max_degree = max(self.topology.degree(a) for a in self.topology.agents) if self.topology.agents else 0
        avg_degree = (
            sum(self.topology.degree(a) for a in self.topology.agents) / len(self.topology.agents)
            if self.topology.agents else 0
        )

        if avg_degree > 0 and max_degree > avg_degree * 2.5:
            bottleneck_agents = [
                a for a in self.topology.agents
                if self.topology.degree(a) == max_degree
            ]
            if bottleneck_agents:
                return TopologyChange(
                    description=(
                        f"Agent '{bottleneck_agents[0]}' has degree {max_degree} "
                        f"(avg={avg_degree:.1f}). Consider splitting or adding "
                        f"parallel paths to reduce bottleneck."
                    ),
                    change_type="restructure",
                    agents_involved=bottleneck_agents,
                    confidence=0.6,
                )

        return TopologyChange(
            description="Current topology appears well-suited for communication patterns.",
            confidence=0.0,
        )

    # ── Reporting ──────────────────────────────────────────────────────

    def get_swarm_report(self) -> SwarmReport:
        """Generate a comprehensive report of swarm state.

        Returns:
            SwarmReport with all swarm metrics.
        """
        deadlock_reports = self.check_deadlocks()

        return SwarmReport(
            name=self.name,
            topology_type=self.topology.type.value,
            agent_count=len(self.agents),
            total_messages=self.message_bus.total_messages,
            total_tasks_completed=sum(
                a.get_stats()["tasks_completed"] for a in self.agents.values()
            ),
            total_tasks_failed=sum(
                a.get_stats()["tasks_failed"] for a in self.agents.values()
            ),
            agents=[a.get_stats() for a in self.agents.values()],
            topology=self.topology.to_dict(),
            deadlock_reports=[
                {
                    "severity": r.severity.value,
                    "is_deadlock": r.is_deadlock,
                    "is_livelock": r.is_livelock,
                    "description": r.description,
                    "cycle": r.cycle,
                }
                for r in deadlock_reports
            ],
            uptime_seconds=time.time() - self.created_at,
        )

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def agent_count(self) -> int:
        """Number of agents in the swarm."""
        return len(self.agents)

    @property
    def uptime_seconds(self) -> float:
        """Seconds since the swarm was created."""
        return time.time() - self.created_at

    def __repr__(self) -> str:
        return (
            f"Swarm({self.name!r}, topology={self.topology.type.value}, "
            f"agents={self.agent_count})"
        )
