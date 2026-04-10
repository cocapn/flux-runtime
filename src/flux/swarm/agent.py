"""FluxAgent — autonomous agent within the FLUX swarm runtime.

Each agent has:
- Its own module container (nested in the swarm)
- Its own profiler (tracks what it does)
- Its own tile registry (its local vocabulary)
- Access to the shared A2A bus
- A role/specialization (evolves over time)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from flux.adaptive.profiler import AdaptiveProfiler, HeatLevel
from flux.modules.container import ModuleContainer
from flux.modules.granularity import Granularity
from flux.tiles.registry import TileRegistry

from .message_bus import AgentMessage


# ── Agent Role ─────────────────────────────────────────────────────────────

class AgentRole(Enum):
    """Agent specialization roles.

    Agents evolve their role based on profiling data:
    - GENERAL: Default, no specialization yet
    - SPECIALIST_COMPUTE: Fast path executor (C+SIMD) — lots of computation
    - SPECIALIST_COORDINATOR: A2A routing, orchestration — lots of messaging
    - SPECIALIST_EXPLORER: Creative, experimental — lots of diverse work
    - SPECIALIST_MEMORY: Data management, caching — lots of state
    - SPECIALIST_IO: Input/output, side effects — lots of I/O
    """
    GENERAL = "general"
    SPECIALIST_COMPUTE = "compute"
    SPECIALIST_COORDINATOR = "coordinator"
    SPECIALIST_EXPLORER = "explorer"
    SPECIALIST_MEMORY = "memory"
    SPECIALIST_IO = "io"


# ── Trust Profile ──────────────────────────────────────────────────────────

@dataclass
class TrustProfile:
    """Tracks an agent's trust relationships and behavioral metrics.

    Attributes:
        trust_score: Overall trust score [0.0, 1.0].
        successful_interactions: Count of successful interactions.
        failed_interactions: Count of failed interactions.
        avg_latency_ms: Average message processing latency.
        capabilities: Set of declared capability strings.
    """
    trust_score: float = 0.5
    successful_interactions: int = 0
    failed_interactions: int = 0
    avg_latency_ms: float = 0.0
    capabilities: set[str] = field(default_factory=set)

    @property
    def total_interactions(self) -> int:
        """Total number of interactions."""
        return self.successful_interactions + self.failed_interactions

    @property
    def success_rate(self) -> float:
        """Fraction of interactions that were successful."""
        if self.total_interactions == 0:
            return 0.5  # Neutral
        return self.successful_interactions / self.total_interactions

    def record_success(self, latency_ms: float = 0.0) -> None:
        """Record a successful interaction."""
        self.successful_interactions += 1
        self._update_latency(latency_ms)
        self._update_trust()

    def record_failure(self, latency_ms: float = 0.0) -> None:
        """Record a failed interaction."""
        self.failed_interactions += 1
        self._update_latency(latency_ms)
        self._update_trust()

    def add_capability(self, cap: str) -> None:
        """Add a capability."""
        self.capabilities.add(cap)

    def has_capability(self, cap: str) -> bool:
        """Check if agent has a capability."""
        return cap in self.capabilities

    def _update_latency(self, latency_ms: float) -> None:
        """Update running average latency."""
        total = self.total_interactions
        if total <= 1:
            self.avg_latency_ms = latency_ms
        else:
            self.avg_latency_ms = (
                self.avg_latency_ms * (total - 1) + latency_ms
            ) / total

    def _update_trust(self) -> None:
        """Recalculate trust score based on interaction history."""
        if self.total_interactions == 0:
            self.trust_score = 0.5
            return
        # Exponential moving average weighted toward success rate
        self.trust_score = 0.7 * self.success_rate + 0.3 * (1.0 - self.avg_latency_ms / 1000.0)
        self.trust_score = max(0.0, min(1.0, self.trust_score))

    def __repr__(self) -> str:
        return (
            f"TrustProfile(score={self.trust_score:.2f}, "
            f"success_rate={self.success_rate:.2f}, "
            f"interactions={self.total_interactions})"
        )


# ── Task Types ─────────────────────────────────────────────────────────────

@dataclass
class AgentTask:
    """A task to be executed by an agent.

    Attributes:
        task_id: Unique task identifier.
        task_type: Type of task (e.g. "compute", "route", "explore").
        payload: Task-specific data.
        priority: Task priority (0–15).
        source_agent: Agent that created this task.
    """
    task_id: str
    task_type: str = "compute"
    payload: dict = field(default_factory=dict)
    priority: int = 5
    source_agent: str = ""


@dataclass
class AgentResult:
    """Result of a task execution.

    Attributes:
        task_id: ID of the completed task.
        success: Whether the task succeeded.
        result: Result data.
        error: Error message if failed.
        duration_ns: Execution time in nanoseconds.
    """
    task_id: str
    success: bool = True
    result: dict = field(default_factory=dict)
    error: str = ""
    duration_ns: int = 0


# ── FluxAgent ──────────────────────────────────────────────────────────────

class FluxAgent:
    """An autonomous agent that runs within the FLUX runtime.

    Each agent has:
    - Its own module container (nested in the swarm)
    - Its own profiler (tracks what it does)
    - Its own tile registry (its local vocabulary)
    - Access to the shared A2A bus
    - A role/specialization (evolves over time)

    Args:
        agent_id: Unique identifier for this agent.
        role: Initial role/specialization.
    """

    def __init__(
        self,
        agent_id: str,
        role: AgentRole = AgentRole.GENERAL,
    ) -> None:
        self.agent_id = agent_id
        self.role = role

        # Agent's own module container (nested in swarm)
        self.module_container = ModuleContainer(
            name=agent_id,
            granularity=Granularity.CARRIAGE,
        )

        # Local tile registry (starts empty, can share with swarm)
        self.local_registry = TileRegistry()

        # Profiler tracking what this agent does
        self.profiler = AdaptiveProfiler()

        # Trust profile for this agent
        self.trust_profile = TrustProfile()

        # Capabilities
        self.capabilities: set[str] = set()

        # Task tracking
        self._tasks_completed: int = 0
        self._tasks_failed: int = 0
        self._messages_sent: int = 0
        self._messages_received: int = 0
        self._a2a_operations: int = 0
        self._io_operations: int = 0
        self._memory_operations: int = 0
        self._compute_operations: int = 0
        self._explore_operations: int = 0
        self._total_operations: int = 0

        # Evolution tracking
        self.generation: int = 0
        self.created_at: float = time.time()
        self.last_active: float = time.time()

    # ── Message Handling ───────────────────────────────────────────────

    def receive(self, message: AgentMessage) -> None:
        """Handle an incoming A2A message.

        Records the message for profiling and updates trust metrics.

        Args:
            message: The incoming message.
        """
        self._messages_received += 1
        self._a2a_operations += 1
        self.last_active = time.time()

        # Record in profiler as an A2A operation
        self.profiler.record_call(
            f"a2a.receive.{message.sender}",
            duration_ns=0,
        )

    def send(self, target_id: str, message: AgentMessage) -> AgentMessage:
        """Create and prepare an outgoing A2A message.

        Args:
            target_id: Target agent ID.
            message: Message to send (will have sender/receiver set).

        Returns:
            The prepared message with sender/receiver fields populated.
        """
        message.sender = self.agent_id
        message.receiver = target_id
        self._messages_sent += 1
        self._a2a_operations += 1
        self.last_active = time.time()
        return message

    # ── Task Execution ─────────────────────────────────────────────────

    def execute_task(self, task: AgentTask) -> AgentResult:
        """Execute a task and return results.

        Tracks the execution for profiling and specialization purposes.

        Args:
            task: The task to execute.

        Returns:
            AgentResult with the outcome.
        """
        start = time.time_ns()
        self.last_active = time.time()

        try:
            # Record the task as a profiler sample
            self.profiler.record_call(
                f"task.{task.task_type}",
                duration_ns=0,
            )

            # Classify the task by type for specialization tracking
            self._total_operations += 1
            if task.task_type in ("compute", "math", "numeric", "sort", "filter"):
                self._compute_operations += 1
            elif task.task_type in ("route", "coordinate", "delegate", "dispatch"):
                self._a2a_operations += 1
            elif task.task_type in ("explore", "search", "discover", "creative"):
                self._explore_operations += 1
            elif task.task_type in ("store", "cache", "retrieve", "memory"):
                self._memory_operations += 1
            elif task.task_type in ("read", "write", "print", "log", "io"):
                self._io_operations += 1

            duration_ns = time.time_ns() - start
            self._tasks_completed += 1

            return AgentResult(
                task_id=task.task_id,
                success=True,
                result={"task_type": task.task_type, "agent": self.agent_id},
                duration_ns=duration_ns,
            )

        except Exception as e:
            duration_ns = time.time_ns() - start
            self._tasks_failed += 1
            return AgentResult(
                task_id=task.task_id,
                success=False,
                error=str(e),
                duration_ns=duration_ns,
            )

    # ── Specialization ─────────────────────────────────────────────────

    def specialize(self) -> AgentRole:
        """Determine optimal specialization based on profiling.

        Analyzes the agent's execution history to determine which role
        best fits its observed behavior:

        - Lots of fast computation → SPECIALIST_COMPUTE
        - Lots of A2A messaging → SPECIALIST_COORDINATOR
        - Creative/exploratory work → SPECIALIST_EXPLORER
        - Data management → SPECIALIST_MEMORY
        - I/O operations → SPECIALIST_IO

        Returns:
            The recommended AgentRole.
        """
        total = self._total_operations

        if total == 0:
            return AgentRole.GENERAL

        # Compute fractions
        compute_frac = self._compute_operations / total
        a2a_frac = self._a2a_operations / total
        io_frac = self._io_operations / total
        memory_frac = self._memory_operations / total
        explore_frac = self._explore_operations / total

        # Thresholds for specialization
        if compute_frac >= 0.5:
            return AgentRole.SPECIALIST_COMPUTE
        elif a2a_frac >= 0.5:
            return AgentRole.SPECIALIST_COORDINATOR
        elif io_frac >= 0.4:
            return AgentRole.SPECIALIST_IO
        elif memory_frac >= 0.4:
            return AgentRole.SPECIALIST_MEMORY
        elif explore_frac >= 0.5:
            # Explorer: creative, diverse tasks
            return AgentRole.SPECIALIST_EXPLORER
        elif compute_frac < 0.2 and a2a_frac < 0.2:
            # Lots of diverse, non-focused work → explorer
            return AgentRole.SPECIALIST_EXPLORER

        return AgentRole.GENERAL

    def apply_specialization(self) -> AgentRole:
        """Analyze and apply specialization, updating the role.

        Returns:
            The new role.
        """
        new_role = self.specialize()
        self.role = new_role
        return new_role

    # ── Evolution ──────────────────────────────────────────────────────

    def evolve(self, generations: int = 3) -> None:
        """Run local evolution on this agent's state.

        This updates the agent's specialization based on accumulated
        profiling data and increments the generation counter.

        Args:
            generations: Number of evolution steps to simulate.
        """
        for _ in range(generations):
            self.generation += 1
            self.apply_specialization()

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def total_tasks(self) -> int:
        """Total tasks attempted."""
        return self._tasks_completed + self._tasks_failed

    @property
    def task_success_rate(self) -> float:
        """Fraction of tasks that succeeded."""
        if self.total_tasks == 0:
            return 0.5
        return self._tasks_completed / self.total_tasks

    @property
    def uptime_seconds(self) -> float:
        """Seconds since this agent was created."""
        return time.time() - self.created_at

    def get_stats(self) -> dict:
        """Get comprehensive agent statistics."""
        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "generation": self.generation,
            "tasks_completed": self._tasks_completed,
            "tasks_failed": self._tasks_failed,
            "task_success_rate": self.task_success_rate,
            "messages_sent": self._messages_sent,
            "messages_received": self._messages_received,
            "a2a_operations": self._a2a_operations,
            "io_operations": self._io_operations,
            "memory_operations": self._memory_operations,
            "compute_operations": self._compute_operations,
            "trust_score": self.trust_profile.trust_score,
            "uptime_seconds": self.uptime_seconds,
            "modules": len(self.module_container.cards),
            "tiles": self.local_registry.count,
        }

    def __repr__(self) -> str:
        return (
            f"FluxAgent({self.agent_id!r}, role={self.role.value}, "
            f"tasks={self.total_tasks}, gen={self.generation})"
        )
