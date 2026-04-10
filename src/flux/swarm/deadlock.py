"""Deadlock Detection — detects deadlocks and livelocks in agent communication.

Uses a wait-for graph (WFG) to detect circular dependencies (deadlocks)
and pattern analysis to detect livelocks (repeated message cycles).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .message_bus import AgentMessage


# ── Types ──────────────────────────────────────────────────────────────────

class DeadlockSeverity(Enum):
    """Severity of a detected deadlock."""
    NONE = "none"
    LOW = "low"          # Two-agent deadlock, easy to resolve
    MEDIUM = "medium"    # Multi-agent deadlock
    HIGH = "high"        # Large cycle or repeated deadlock
    CRITICAL = "critical"  # System-wide deadlock


@dataclass
class DeadlockReport:
    """Report of a detected deadlock or livelock."""
    severity: DeadlockSeverity = DeadlockSeverity.NONE
    cycle: list[str] = field(default_factory=list)
    is_deadlock: bool = False
    is_livelock: bool = False
    description: str = ""

    @property
    def has_issue(self) -> bool:
        """True if a deadlock or livelock was detected."""
        return self.is_deadlock or self.is_livelock


@dataclass
class DeadlockResolution:
    """Suggested resolution for a deadlock."""
    description: str = ""
    yield_agent: str = ""         # Agent that should yield
    reason: str = ""
    priority: str = ""            # Which agent to prioritize


# ── Deadlock Detector ──────────────────────────────────────────────────────

class DeadlockDetector:
    """Detects deadlocks and livelocks in agent communication.

    Deadlock detection uses a wait-for graph (WFG):
    - Nodes are agents
    - Edge A→B means agent A is waiting for agent B
    - A cycle in the WFG indicates a deadlock

    Livelock detection analyzes message history for repeated patterns:
    - Two agents bouncing the same task back and forth
    - Repeated delegation without progress
    """

    def __init__(self) -> None:
        self._wait_graph: dict[str, set[str]] = defaultdict(set)
        self._livelock_counters: dict[str, int] = defaultdict(int)
        self._livelock_threshold: int = 5  # repeated messages before flagging
        self._message_fingerprints: dict[str, dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )

    # ── Wait Graph Management ──────────────────────────────────────────

    def record_wait(self, waiter: str, waited_for: str) -> None:
        """Record that *waiter* is waiting for *waited_for*.

        Args:
            waiter: Agent that is waiting.
            waited_for: Agent being waited for.
        """
        self._wait_graph[waiter].add(waited_for)

    def record_release(self, agent: str) -> None:
        """Record that *agent* is no longer waiting for anything.

        Args:
            agent: Agent that has finished waiting.
        """
        if agent in self._wait_graph:
            self._wait_graph[agent].clear()

    def record_release_pair(self, waiter: str, waited_for: str) -> None:
        """Record that *waiter* is no longer waiting for *waited_for*."""
        if waiter in self._wait_graph:
            self._wait_graph[waiter].discard(waited_for)
            if not self._wait_graph[waiter]:
                del self._wait_graph[waiter]

    def clear(self) -> None:
        """Clear the entire wait graph."""
        self._wait_graph.clear()

    # ── Deadlock Detection ─────────────────────────────────────────────

    def detect_cycle(self) -> Optional[list[str]]:
        """Find a cycle in the wait graph (deadlock).

        Uses DFS-based three-color cycle detection.

        Returns:
            A list of agent IDs forming the cycle, or None if no cycle exists.
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {node: WHITE for node in self._wait_graph}
        parent: dict[str, Optional[str]] = {}

        def dfs(node: str) -> Optional[list[str]]:
            color[node] = GRAY
            for neighbor in self._wait_graph.get(node, set()):
                if neighbor not in color:
                    # Neighbor not in graph — skip
                    continue
                if color[neighbor] == GRAY:
                    # Found cycle — reconstruct path
                    cycle = [neighbor, node]
                    curr: Optional[str] = node
                    while curr is not None and curr != neighbor:
                        curr = parent.get(curr)
                        if curr is None:
                            break
                        cycle.append(curr)
                    return cycle
                if color[neighbor] == WHITE:
                    parent[neighbor] = node
                    result = dfs(neighbor)
                    if result:
                        return result
            color[node] = BLACK
            return None

        for node in list(self._wait_graph.keys()):
            if color[node] == WHITE:
                result = dfs(node)
                if result:
                    return result
        return None

    # ── Livelock Detection ─────────────────────────────────────────────

    def detect_livelock(self, agent_id: str, history: list[AgentMessage]) -> bool:
        """Detect if an agent is in a livelock (repeating the same messages).

        Analyzes message history for patterns where an agent sends the same
        payload to the same target repeatedly without making progress.

        Args:
            agent_id: Agent to check.
            history: Recent message history from this agent.

        Returns:
            True if livelock is suspected.
        """
        if not history:
            return False

        # Count occurrences of (receiver, msg_type, payload_hash) tuples
        from collections import Counter

        fingerprints: list[str] = []
        for msg in history:
            if msg.sender == agent_id:
                # Create a fingerprint of the message
                fp = f"{msg.receiver}:{msg.msg_type}:{self._hash_payload(msg.payload)}"
                fingerprints.append(fp)
                self._message_fingerprints[agent_id][fp] += 1

        if not fingerprints:
            return False

        # Check if the same pattern repeats
        counts = Counter(fingerprints)
        max_count = max(counts.values()) if counts else 0

        return max_count >= self._livelock_threshold

    def detect_livelock_pair(
        self, agent_a: str, agent_b: str, history: list[AgentMessage]
    ) -> bool:
        """Detect if two agents are in a mutual livelock (bouncing messages).

        Args:
            agent_a: First agent.
            agent_b: Second agent.
            history: Recent message history.

        Returns:
            True if the two agents appear to be in a livelock.
        """
        a_to_b = 0
        b_to_a = 0

        for msg in history[-20:]:  # Look at last 20 messages
            if msg.sender == agent_a and msg.receiver == agent_b:
                a_to_b += 1
            elif msg.sender == agent_b and msg.receiver == agent_a:
                b_to_a += 1

        # If both directions have been used recently, check for alternation
        if a_to_b < 3 and b_to_a < 3:
            return False

        # Check alternation pattern
        last_20 = history[-20:]
        alternations = 0
        for i in range(1, len(last_20)):
            prev = last_20[i - 1]
            curr = last_20[i]
            if (
                prev.sender == agent_a and prev.receiver == agent_b
                and curr.sender == agent_b and curr.receiver == agent_a
            ):
                alternations += 1
            elif (
                prev.sender == agent_b and prev.receiver == agent_a
                and curr.sender == agent_a and curr.receiver == agent_b
            ):
                alternations += 1

        return alternations >= self._livelock_threshold

    # ── Resolution ─────────────────────────────────────────────────────

    def suggest_resolution(self, cycle: list[str]) -> DeadlockResolution:
        """Suggest how to resolve a deadlock.

        The agent with the lowest trust (or alphabetically first if no
        trust data is available) should yield.

        Args:
            cycle: List of agent IDs forming the deadlock cycle.

        Returns:
            DeadlockResolution with suggestion.
        """
        if not cycle:
            return DeadlockResolution(
                description="No cycle detected.",
                reason="Empty cycle provided.",
            )

        # Alphabetical first agent yields (simple deterministic strategy)
        sorted_agents = sorted(cycle)
        yield_agent = sorted_agents[0]
        priority_agent = sorted_agents[-1]

        return DeadlockResolution(
            description=(
                f"Deadlock detected in cycle: {' → '.join(cycle + [cycle[0]])}. "
                f"Agent '{yield_agent}' should yield to break the cycle."
            ),
            yield_agent=yield_agent,
            reason=(
                f"Agent '{yield_agent}' is selected to yield based on "
                f"deterministic ordering. Agent '{priority_agent}' retains priority."
            ),
            priority=priority_agent,
        )

    # ── Comprehensive Check ────────────────────────────────────────────

    def check_deadlocks(
        self, message_log: Optional[list[AgentMessage]] = None
    ) -> list[DeadlockReport]:
        """Run comprehensive deadlock and livelock detection.

        Args:
            message_log: Optional message history for livelock detection.

        Returns:
            List of DeadlockReports for all detected issues.
        """
        reports: list[DeadlockReport] = []

        # Check for deadlocks (cycles in WFG)
        cycle = self.detect_cycle()
        if cycle:
            severity = self._cycle_severity(len(cycle))
            reports.append(DeadlockReport(
                severity=severity,
                cycle=cycle,
                is_deadlock=True,
                is_livelock=False,
                description=f"Deadlock: circular wait among {len(cycle)} agents.",
            ))

        # Check for livelocks in message history
        if message_log:
            for agent_id in set(msg.sender for msg in message_log):
                agent_history = [
                    msg for msg in message_log
                    if msg.sender == agent_id or msg.receiver == agent_id
                ]
                if self.detect_livelock(agent_id, message_log):
                    reports.append(DeadlockReport(
                        severity=DeadlockSeverity.MEDIUM,
                        is_deadlock=False,
                        is_livelock=True,
                        description=f"Livelock suspected for agent '{agent_id}': repeated message patterns.",
                    ))

        if not reports:
            reports.append(DeadlockReport(
                severity=DeadlockSeverity.NONE,
                description="No deadlocks or livelocks detected.",
            ))

        return reports

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def wait_graph(self) -> dict[str, set[str]]:
        """Snapshot of the current wait-for graph."""
        return {k: set(v) for k, v in self._wait_graph.items()}

    @property
    def agent_count(self) -> int:
        """Number of agents in the wait graph."""
        return len(self._wait_graph)

    # ── Internals ──────────────────────────────────────────────────────

    @staticmethod
    def _hash_payload(payload: dict) -> str:
        """Create a simple hash of a payload for fingerprinting."""
        try:
            return str(sorted(payload.items()))
        except TypeError:
            return str(payload)

    @staticmethod
    def _cycle_severity(cycle_length: int) -> DeadlockSeverity:
        """Determine severity based on cycle size."""
        if cycle_length == 2:
            return DeadlockSeverity.LOW
        elif cycle_length <= 4:
            return DeadlockSeverity.MEDIUM
        elif cycle_length <= 6:
            return DeadlockSeverity.HIGH
        else:
            return DeadlockSeverity.CRITICAL

    def __repr__(self) -> str:
        return (
            f"DeadlockDetector(agents={self.agent_count}, "
            f"edges={sum(len(v) for v in self._wait_graph.values())})"
        )
