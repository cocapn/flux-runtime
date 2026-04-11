"""
FLUX A2A Protocol Primitives — Rich multi-agent coordination patterns.

WHY THIS MODULE EXISTS:
The flux-runtime A2A layer (messages.py, transport.py, trust.py) provides
binary message passing and trust management — the transport and security
infrastructure. But it lacks the HIGH-LEVEL coordination patterns that
agents actually need: parallel exploration, agent inheritance, collaborative
traversal, structured discourse, result combination, and self-reflection.

These primitives were originally designed in flux-a2a-prototype (a research
repo with 13K LOC, 184+ tests, built by Super Z + Babel across a single
session). This module adopts them into flux-runtime with simplifications:
- FUTS type system removed (deferred to Phase 2)
- Cross-language bridge removed (deferred to Phase 2)
- Core dataclass structure preserved with $schema versioning
- All primitives remain JSON-serializable (to_dict/from_dict)

DESIGN PRINCIPLES:
1. Every primitive carries confidence (0.0-1.0) — uncertainty is first-class
2. Every primitive has a meta dict — extensibility without schema breakage
3. Every primitive has a $schema field — forward/backward compatibility
4. Unknown fields go into meta, not errors — backward compatible
5. These primitives expand to core Signal ops at compile time — no new VM opcodes needed

RELATIONSHIP TO SIGNAL LANGUAGE:
The SignalCompiler (signal_compiler.py) compiles Signal JSON → FLUX bytecode.
Protocol primitives (branch, fork, co_iterate, discuss, synthesize, reflect)
are high-level constructs that the compiler CAN recognize and expand.

Current state: the SignalCompiler does NOT yet recognize these primitives.
Integration requires adding compilation rules in signal_compiler.py that
expand each primitive to a sequence of core Signal operations.

See: flux-spec/SIGNAL.md (sections 9-13) for the formal specification.
See: KNOWLEDGE/public/a2a-integration-architecture.md for the integration plan.

Author: Super Z (Cartographer)
Date: 2026-04-12
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


# ===========================================================================
# Enums
# ===========================================================================

class BranchStrategy(str, Enum):
    """How branch sub-paths execute."""
    PARALLEL = "parallel"       # All branches run concurrently
    SEQUENTIAL = "sequential"   # Branches run in order
    COMPETITIVE = "competitive" # First to complete wins, others cancelled


class MergeStrategy(str, Enum):
    """How branch/fork results are combined."""
    CONSENSUS = "consensus"
    VOTE = "vote"
    BEST = "best"
    ALL = "all"
    WEIGHTED_CONFIDENCE = "weighted_confidence"
    FIRST_COMPLETE = "first_complete"
    LAST_WRITER_WINS = "last_writer_wins"
    CUSTOM = "custom"


class ForkOnComplete(str, Enum):
    """What to do when a forked agent finishes."""
    COLLECT = "collect"   # Store result
    DISCARD = "discard"   # Drop result
    SIGNAL = "signal"     # Notify parent
    MERGE = "merge"       # Merge back into parent


class ForkConflictMode(str, Enum):
    """How to resolve conflicts between fork and parent."""
    PARENT_WINS = "parent_wins"
    CHILD_WINS = "child_wins"
    NEGOTIATE = "negotiate"


class SharedStateMode(str, Enum):
    """How co-iterating agents share state."""
    CONFLICT = "conflict"       # Fail on write conflict
    MERGE = "merge"             # Auto-merge writes
    PARTITIONED = "partitioned" # Each agent gets a partition
    ISOLATED = "isolated"       # No shared state


class DiscussFormat(str, Enum):
    """Format for agent discussions."""
    DEBATE = "debate"
    BRAINSTORM = "brainstorm"
    REVIEW = "review"
    NEGOTIATE = "negotiate"
    PEER_REVIEW = "peer_review"


class SynthesisMethod(str, Enum):
    """Method for combining multiple results."""
    MAP_REDUCE = "map_reduce"
    ENSEMBLE = "ensemble"
    CHAIN = "chain"
    VOTE = "vote"
    WEIGHTED_MERGE = "weighted_merge"
    BEST_EFFORT = "best_effort"


class ReflectTarget(str, Enum):
    """What to reflect on."""
    STRATEGY = "strategy"
    PROGRESS = "progress"
    UNCERTAINTY = "uncertainty"
    CONFIDENCE = "confidence"
    ALL = "all"


# ===========================================================================
# Helpers
# ===========================================================================

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))

def _uuid() -> str:
    return str(uuid.uuid4())


# ===========================================================================
# 1. Branch — Parallel Exploration
# ===========================================================================

@dataclass
class BranchBody:
    """One arm of a branch primitive."""
    label: str = ""
    weight: float = 1.0
    body: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 1.0
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.weight = _clamp(self.weight)
        self.confidence = _clamp(self.confidence)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"label": self.label, "weight": self.weight, "body": self.body}
        if self.confidence < 1.0:
            d["confidence"] = self.confidence
        if self.meta:
            d["meta"] = self.meta
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BranchBody:
        return cls(
            label=data.get("label", ""),
            weight=data.get("weight", 1.0),
            body=data.get("body", []),
            confidence=data.get("confidence", 1.0),
            meta=data.get("meta", {}),
        )


@dataclass
class BranchPrimitive:
    """
    Spawn parallel (or sequential/competitive) exploration paths.

    COOPERATION PATTERN: Parallel Divergence + Convergence.
    Multiple agents explore different approaches, then merge the best result.

    COMPILATION: Expands to FORK (0x58) per branch + JOIN (0x59) + MERGE (0x57).
    The compiler emits one FORK per branch body, then JOIN to synchronize,
    then MERGE with the specified strategy.

    JSON schema:
      {
        "op": "branch",
        "$schema": "flux.a2a.branch/v1",
        "id": "optional-uuid",
        "strategy": "parallel|sequential|competitive",
        "branches": [{"label": "A", "body": [...]}],
        "merge": {"strategy": "weighted_confidence", "timeout_ms": 30000}
      }
    """
    id: str = ""
    strategy: str = BranchStrategy.PARALLEL.value
    branches: list[BranchBody] = field(default_factory=list)
    merge_strategy: str = MergeStrategy.WEIGHTED_CONFIDENCE.value
    merge_timeout_ms: int = 30000
    merge_fallback: str = MergeStrategy.FIRST_COMPLETE.value
    confidence: float = 1.0
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = _uuid()
        self.confidence = _clamp(self.confidence)
        self.branches = [
            b if isinstance(b, BranchBody) else BranchBody.from_dict(b)
            for b in self.branches
        ]

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "op": "branch",
            "$schema": "flux.a2a.branch/v1",
            "id": self.id,
            "strategy": self.strategy,
            "branches": [b.to_dict() for b in self.branches],
            "merge": {
                "strategy": self.merge_strategy,
                "timeout_ms": self.merge_timeout_ms,
                "fallback": self.merge_fallback,
            },
        }
        if self.confidence < 1.0:
            d["confidence"] = self.confidence
        if self.meta:
            d["meta"] = self.meta
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BranchPrimitive:
        merge = data.get("merge", {})
        return cls(
            id=data.get("id", ""),
            strategy=data.get("strategy", BranchStrategy.PARALLEL.value),
            branches=[BranchBody.from_dict(b) for b in data.get("branches", [])],
            merge_strategy=merge.get("strategy", MergeStrategy.WEIGHTED_CONFIDENCE.value),
            merge_timeout_ms=merge.get("timeout_ms", 30000),
            merge_fallback=merge.get("fallback", MergeStrategy.FIRST_COMPLETE.value),
            confidence=data.get("confidence", 1.0),
            meta=data.get("meta", {}),
        )


# ===========================================================================
# 2. Fork — Agent Inheritance
# ===========================================================================

@dataclass
class ForkMutation:
    """How a fork differs from its parent."""
    type: str = "strategy"  # prompt | context | strategy | capability
    changes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "changes": self.changes}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ForkMutation:
        return cls(type=data.get("type", "strategy"), changes=data.get("changes", {}))


@dataclass
class ForkInherit:
    """Fine-grained control over what a fork inherits from its parent."""
    state: list[str] = field(default_factory=list)  # Empty = all
    context: bool = True
    trust_graph: bool = False
    message_history: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "context": self.context,
            "trust_graph": self.trust_graph,
            "message_history": self.message_history,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ForkInherit:
        return cls(
            state=data.get("state", []),
            context=data.get("context", True),
            trust_graph=data.get("trust_graph", False),
            message_history=data.get("message_history", False),
        )


@dataclass
class ForkPrimitive:
    """
    Create a child agent that inherits specified state from the parent.

    COOPERATION PATTERN: Refit and Propagate.
    Take what works (parent state) and adapt it (mutations) for a new purpose.

    COMPILATION: Expands to state serialization + FORK (0x58) + body ops + JOIN (0x59).

    JSON schema:
      {
        "op": "fork",
        "$schema": "flux.a2a.fork/v1",
        "id": "optional-uuid",
        "inherit": {"state": ["x", "y"], "context": true},
        "mutations": [{"type": "strategy", "changes": {...}}],
        "on_complete": "merge",
        "conflict_mode": "negotiate"
      }
    """
    id: str = ""
    inherit: ForkInherit = field(default_factory=ForkInherit)
    mutations: list[ForkMutation] = field(default_factory=list)
    on_complete: str = ForkOnComplete.MERGE.value
    conflict_mode: str = ForkConflictMode.NEGOTIATE.value
    confidence: float = 1.0
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = _uuid()
        self.confidence = _clamp(self.confidence)
        if not isinstance(self.inherit, ForkInherit):
            self.inherit = ForkInherit.from_dict(self.inherit) if isinstance(self.inherit, dict) else ForkInherit()
        self.mutations = [
            m if isinstance(m, ForkMutation) else ForkMutation.from_dict(m)
            for m in self.mutations
        ]

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "op": "fork",
            "$schema": "flux.a2a.fork/v1",
            "id": self.id,
            "inherit": self.inherit.to_dict(),
            "mutations": [m.to_dict() for m in self.mutations],
            "on_complete": self.on_complete,
            "conflict_mode": self.conflict_mode,
        }
        if self.confidence < 1.0:
            d["confidence"] = self.confidence
        if self.meta:
            d["meta"] = self.meta
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ForkPrimitive:
        return cls(
            id=data.get("id", ""),
            inherit=data.get("inherit", {}),
            mutations=data.get("mutations", []),
            on_complete=data.get("on_complete", ForkOnComplete.MERGE.value),
            conflict_mode=data.get("conflict_mode", ForkConflictMode.NEGOTIATE.value),
            confidence=data.get("confidence", 1.0),
            meta=data.get("meta", {}),
        )


# ===========================================================================
# 3. CoIterate — Multi-Agent Shared Traversal
# ===========================================================================

@dataclass
class CoIteratePrimitive:
    """
    Multiple agents traverse the same program simultaneously.

    COOPERATION PATTERN: Collaborative Traversal.
    Like pair programming but with N agents. Each traverses the same operations
    but may produce different results. Conflict resolution determines how
    divergent writes are handled.

    COMPILATION: Expands to parallel FORK (one per agent) + shared state monitor
    + convergence check loop + final MERGE.

    JSON schema:
      {
        "op": "co_iterate",
        "$schema": "flux.a2a.co_iterate/v1",
        "id": "optional-uuid",
        "agents": ["agent1", "agent2"],
        "shared_state_mode": "merge",
        "conflict_resolution": "vote",
        "convergence": {"metric": "agreement", "threshold": 0.95}
      }
    """
    id: str = ""
    agents: list[str] = field(default_factory=list)
    shared_state_mode: str = SharedStateMode.MERGE.value
    conflict_resolution: str = "vote"  # priority | vote | last_writer | reject | branch
    convergence_metric: str = "agreement"  # agreement | confidence_delta | value_stability
    convergence_threshold: float = 0.95
    merge_type: str = "trust_weighted"  # sequential_consensus | parallel_merge | majority_vote
    confidence: float = 1.0
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = _uuid()
        self.confidence = _clamp(self.confidence)
        self.convergence_threshold = _clamp(self.convergence_threshold, 0.0, 1.0)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "op": "co_iterate",
            "$schema": "flux.a2a.co_iterate/v1",
            "id": self.id,
            "agents": self.agents,
            "shared_state_mode": self.shared_state_mode,
            "conflict_resolution": self.conflict_resolution,
            "convergence": {
                "metric": self.convergence_metric,
                "threshold": self.convergence_threshold,
            },
        }
        if self.confidence < 1.0:
            d["confidence"] = self.confidence
        if self.meta:
            d["meta"] = self.meta
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CoIteratePrimitive:
        conv = data.get("convergence", {})
        return cls(
            id=data.get("id", ""),
            agents=data.get("agents", []),
            shared_state_mode=data.get("shared_state_mode", SharedStateMode.MERGE.value),
            conflict_resolution=data.get("conflict_resolution", "vote"),
            convergence_metric=conv.get("metric", "agreement"),
            convergence_threshold=conv.get("threshold", 0.95),
            merge_type=data.get("merge_type", "trust_weighted"),
            confidence=data.get("confidence", 1.0),
            meta=data.get("meta", {}),
        )


# ===========================================================================
# 4. Discuss — Structured Agent Discourse
# ===========================================================================

@dataclass
class Participant:
    """A participant in a discussion."""
    agent: str = ""
    stance: str = "neutral"  # pro | con | neutral | devil's_advocate | moderator
    role: str = ""  # Optional role description

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"agent": self.agent, "stance": self.stance}
        if self.role:
            d["role"] = self.role
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Participant:
        return cls(agent=data.get("agent", ""), stance=data.get("stance", "neutral"), role=data.get("role", ""))


@dataclass
class DiscussPrimitive:
    """
    Facilitate structured multi-agent discussion.

    COOPERATION PATTERN: Structured Debate.
    Agents take turns presenting arguments. The discussion terminates when
    a consensus condition is met (unanimous agreement, majority, timeout, etc.)

    COMPILATION: Expands to a message round-robin loop (TELL for each turn,
    ASK for responses) + consensus check + result SYNTHESIZE.

    This is the most complex primitive — it orchestrates actual inter-agent
    communication at the protocol level, not just bytecode.

    JSON schema:
      {
        "op": "discuss",
        "$schema": "flux.a2a.discuss/v1",
        "id": "optional-uuid",
        "format": "peer_review",
        "topic": "Should we use binary or JSON for A2A?",
        "participants": [{"agent": "oracle1", "stance": "pro"}],
        "turn_order": "round_robin",
        "until": {"condition": "consensus", "max_rounds": 5}
      }
    """
    id: str = ""
    format: str = DiscussFormat.PEER_REVIEW.value
    topic: str = ""
    participants: list[Participant] = field(default_factory=list)
    turn_order: str = "round_robin"  # round_robin | priority | free_for_all | moderated
    until_condition: str = "consensus"  # consensus | timeout | rounds | majority
    max_rounds: int = 5
    confidence: float = 1.0
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = _uuid()
        self.confidence = _clamp(self.confidence)
        self.participants = [
            p if isinstance(p, Participant) else Participant.from_dict(p)
            for p in self.participants
        ]

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "op": "discuss",
            "$schema": "flux.a2a.discuss/v1",
            "id": self.id,
            "format": self.format,
            "topic": self.topic,
            "participants": [p.to_dict() for p in self.participants],
            "turn_order": self.turn_order,
            "until": {
                "condition": self.until_condition,
                "max_rounds": self.max_rounds,
            },
        }
        if self.confidence < 1.0:
            d["confidence"] = self.confidence
        if self.meta:
            d["meta"] = self.meta
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscussPrimitive:
        until = data.get("until", {})
        return cls(
            id=data.get("id", ""),
            format=data.get("format", DiscussFormat.PEER_REVIEW.value),
            topic=data.get("topic", ""),
            participants=data.get("participants", []),
            turn_order=data.get("turn_order", "round_robin"),
            until_condition=until.get("condition", "consensus"),
            max_rounds=until.get("max_rounds", 5),
            confidence=data.get("confidence", 1.0),
            meta=data.get("meta", {}),
        )


# ===========================================================================
# 5. Synthesize — Result Combination
# ===========================================================================

@dataclass
class SynthesisSource:
    """Input source for synthesis."""
    type: str = "variable"  # branch_result | fork_result | discuss_result | external | variable
    ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "ref": self.ref}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SynthesisSource:
        return cls(type=data.get("type", "variable"), ref=data.get("ref", ""))


@dataclass
class SynthesizePrimitive:
    """
    Combine multiple results into a unified output.

    COOPERATION PATTERN: Convergence.
    After parallel exploration, combine results using a reduction strategy.

    COMPILATION: Expands to AWAIT (all sources) + reduction loop
    (add/merge/vote operations depending on method) + final LET.

    JSON schema:
      {
        "op": "synthesize",
        "$schema": "flux.a2a.synthesize/v1",
        "method": "map_reduce",
        "sources": [{"type": "branch_result", "ref": "exploration"}],
        "output_type": "decision",
        "confidence_mode": "propagate"
      }
    """
    id: str = ""
    method: str = SynthesisMethod.MAP_REDUCE.value
    sources: list[SynthesisSource] = field(default_factory=list)
    output_type: str = "decision"  # code | spec | question | decision | summary | value
    confidence_mode: str = "propagate"  # propagate | min | max | average
    confidence: float = 1.0
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = _uuid()
        self.confidence = _clamp(self.confidence)
        self.sources = [
            s if isinstance(s, SynthesisSource) else SynthesisSource.from_dict(s)
            for s in self.sources
        ]

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "op": "synthesize",
            "$schema": "flux.a2a.synthesize/v1",
            "id": self.id,
            "method": self.method,
            "sources": [s.to_dict() for s in self.sources],
            "output_type": self.output_type,
            "confidence_mode": self.confidence_mode,
        }
        if self.confidence < 1.0:
            d["confidence"] = self.confidence
        if self.meta:
            d["meta"] = self.meta
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SynthesizePrimitive:
        return cls(
            id=data.get("id", ""),
            method=data.get("method", SynthesisMethod.MAP_REDUCE.value),
            sources=data.get("sources", []),
            output_type=data.get("output_type", "decision"),
            confidence_mode=data.get("confidence_mode", "propagate"),
            confidence=data.get("confidence", 1.0),
            meta=data.get("meta", {}),
        )


# ===========================================================================
# 6. Reflect — Meta-Cognition
# ===========================================================================

@dataclass
class ReflectPrimitive:
    """
    Enable an agent to reason about its own state and strategy.

    COOPERATION PATTERN: Audit and Converge (meta-level).
    The agent examines its own process, identifies weaknesses, and adjusts.

    COMPILATION: Expands to self-assessment computations (CMP on internal
    registers) + conditional BRANCH for strategy adjustment.

    This is the most important primitive for fleet learning. It enables
    agents to improve their own behavior based on experience.

    JSON schema:
      {
        "op": "reflect",
        "$schema": "flux.a2a.reflect/v1",
        "target": "strategy",
        "method": "introspection",
        "output": "adjustment",
        "confidence": 0.7
      }
    """
    id: str = ""
    target: str = ReflectTarget.STRATEGY.value
    method: str = "introspection"  # introspection | benchmark | comparison | statistical
    output: str = "adjustment"  # adjustment | question | branch | log | signal
    confidence: float = 1.0
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = _uuid()
        self.confidence = _clamp(self.confidence)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "op": "reflect",
            "$schema": "flux.a2a.reflect/v1",
            "id": self.id,
            "target": self.target,
            "method": self.method,
            "output": self.output,
        }
        if self.confidence < 1.0:
            d["confidence"] = self.confidence
        if self.meta:
            d["meta"] = self.meta
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReflectPrimitive:
        return cls(
            id=data.get("id", ""),
            target=data.get("target", ReflectTarget.STRATEGY.value),
            method=data.get("method", "introspection"),
            output=data.get("output", "adjustment"),
            confidence=data.get("confidence", 1.0),
            meta=data.get("meta", {}),
        )


# ===========================================================================
# Registry — look up primitive class by operation name
# ===========================================================================

PRIMITIVE_REGISTRY: dict[str, type] = {
    "branch": BranchPrimitive,
    "fork": ForkPrimitive,
    "co_iterate": CoIteratePrimitive,
    "discuss": DiscussPrimitive,
    "synthesize": SynthesizePrimitive,
    "reflect": ReflectPrimitive,
}


def parse_primitive(data: dict[str, Any]) -> Any:
    """
    Parse a JSON dict into the appropriate protocol primitive.

    WHY: The SignalCompiler needs to recognize protocol primitives in a
    Signal program and expand them to core ops. This function provides
    the parsing entry point.

    Usage:
        prim = parse_primitive({"op": "branch", "branches": [...]})
        # Returns BranchPrimitive instance

    Unknown ops return None (not an error — they might be core Signal ops
        handled by the compiler directly).
    """
    op_name = data.get("op", "")
    cls = PRIMITIVE_REGISTRY.get(op_name)
    if cls is None:
        return None
    return cls.from_dict(data)
