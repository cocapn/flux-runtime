"""Research session tracking — seeds, iterations, reflections for ML-driven R&D.

Usage:
    session = ResearchSession("pong")
    session.begin_iteration(1, hypothesis="Raw bytecode approach is fastest for simple physics")
    # ... do work ...
    session.record_metrics(bytecode_size=128, cycles=340, memory_bytes=256)
    session.end_iteration(reflection="Raw bytecode works but register pressure is high. Consider SSA for complex expressions.")
    session.save()  # writes to research_log.jsonl
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# ── Directory Layout ─────────────────────────────────────────────────────────
# retro/research/
#   sessions/          — per-target JSONL logs
#   seeds/             — saved seed states
#   reflections/       — markdown reflection documents
#   artifacts/         — bytecode dumps, IR snapshots, traces

RESEARCH_ROOT = Path(__file__).parent


def _default_log_dir() -> Path:
    """Return the default directory for research logs."""
    d = RESEARCH_ROOT / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _default_seed_dir() -> Path:
    d = RESEARCH_ROOT / "seeds"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _default_reflection_dir() -> Path:
    d = RESEARCH_ROOT / "reflections"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Seed ──────────────────────────────────────────────────────────────────────


@dataclass
class Seed:
    """A deterministic seed for reproducibility.

    Tracks the RNG state, Python version, FLUX version, and any
    configuration that could affect reproducibility.
    """

    seed_id: str
    value: int
    created_at: str  # ISO 8601
    flux_version: str = "0.1.0"
    python_version: str = ""
    os_info: str = ""
    config: dict = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def generate(cls, target_name: str, iteration: int, config: dict | None = None) -> Seed:
        """Generate a new deterministic seed from target name + iteration."""
        import platform
        raw = f"{target_name}:{iteration}:{time.time_ns()}"
        value = int(hashlib.sha256(raw.encode()).hexdigest()[:16], 16)
        return cls(
            seed_id=f"{target_name}_iter{iteration}_{uuid.uuid4().hex[:8]}",
            value=value,
            created_at=datetime.now(timezone.utc).isoformat(),
            python_version=platform.python_version(),
            os_info=f"{platform.system()}-{platform.machine()}",
            config=config or {},
        )


# ── Metrics ───────────────────────────────────────────────────────────────────


@dataclass
class MetricSnapshot:
    """A point-in-time measurement of implementation characteristics."""

    timestamp: str  # ISO 8601
    bytecode_size: int = 0
    code_section_size: int = 0
    total_cycles: int = 0
    peak_memory_bytes: int = 0
    num_instructions: int = 0
    num_registers_used: int = 0
    num_basic_blocks: int = 0
    opcodes_used: list = field(default_factory=list)
    compile_time_ms: float = 0.0
    execution_time_ms: float = 0.0
    test_pass_rate: float = 0.0  # 0.0 to 1.0
    coverage_lines: float = 0.0  # 0.0 to 1.0
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ── Reflection ────────────────────────────────────────────────────────────────


@dataclass
class Reflection:
    """Structured reflection after an iteration.

    This is the key ML-ready data: what was tried, what happened,
    what was learned, and what should be tried next.
    """

    timestamp: str
    iteration: int
    target: str

    # What was the hypothesis/goal?
    hypothesis: str = ""

    # What actually happened?
    observations: list[str] = field(default_factory=list)

    # What metrics changed?
    metric_deltas: dict = field(default_factory=dict)  # metric_name -> delta

    # What worked well?
    successes: list[str] = field(default_factory=list)

    # What didn't work?
    failures: list[str] = field(default_factory=list)

    # What should be tried next?
    next_steps: list[str] = field(default_factory=list)

    # Open research questions
    open_questions: list[str] = field(default_factory=list)

    # Confidence in the approach (0.0-1.0)
    confidence: float = 0.5

    # Free-form notes for LLM reflection
    raw_notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_markdown(self) -> str:
        """Render as a readable markdown document for human review."""
        lines = [
            f"# Reflection: {self.target} — Iteration {self.iteration}",
            f"",
            f"**Date:** {self.timestamp}",
            f"**Hypothesis:** {self.hypothesis}",
            f"**Confidence:** {self.confidence:.0%}",
            f"",
            f"## Observations",
        ]
        for obs in self.observations:
            lines.append(f"- {obs}")
        lines.extend([
            f"",
            f"## What Worked",
        ])
        for s in self.successes:
            lines.append(f"- ✓ {s}")
        lines.extend([
            f"",
            f"## What Didn't Work",
        ])
        for f in self.failures:
            lines.append(f"- ✗ {f}")
        if self.metric_deltas:
            lines.extend([f"", f"## Metric Changes"])
            for k, v in self.metric_deltas.items():
                arrow = "+" if v > 0 else ""
                lines.append(f"- {k}: {arrow}{v}")
        lines.extend([
            f"",
            f"## Next Steps",
        ])
        for ns in self.next_steps:
            lines.append(f"- → {ns}")
        if self.open_questions:
            lines.extend([f"", f"## Open Research Questions"])
            for q in self.open_questions:
                lines.append(f"- ? {q}")
        if self.raw_notes:
            lines.extend([f"", f"## Raw Notes", f"", self.raw_notes])
        lines.append("")
        return "\n".join(lines)


# ── Iteration ─────────────────────────────────────────────────────────────────


@dataclass
class Iteration:
    """A single research iteration with seed, metrics, and reflection."""

    target: str
    iteration_number: int
    seed: Seed
    started_at: str
    ended_at: str = ""
    hypothesis: str = ""
    approach: str = ""  # "raw_bytecode", "fir_builder", "pipeline", "hybrid"
    metrics_before: Optional[MetricSnapshot] = None
    metrics_after: Optional[MetricSnapshot] = None
    reflection: Optional[Reflection] = None
    artifacts: list[str] = field(default_factory=list)  # paths to saved files
    status: str = "in_progress"  # "in_progress", "completed", "failed", "skipped"
    error: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        if d.get("metrics_before") and isinstance(d["metrics_before"], MetricSnapshot):
            d["metrics_before"] = d["metrics_before"].to_dict()
        if d.get("metrics_after") and isinstance(d["metrics_after"], MetricSnapshot):
            d["metrics_after"] = d["metrics_after"].to_dict()
        if d.get("reflection") and isinstance(d["reflection"], Reflection):
            d["reflection"] = d["reflection"].to_dict()
        if d.get("seed") and isinstance(d["seed"], Seed):
            d["seed"] = d["seed"].to_dict()
        return d

    def compute_deltas(self) -> dict:
        """Compute metric deltas between before and after snapshots."""
        if not self.metrics_before or not self.metrics_after:
            return {}
        before = self.metrics_before.to_dict()
        after = self.metrics_after.to_dict()
        deltas = {}
        for key in after:
            if key in ("timestamp", "extra", "opcodes_used"):
                continue
            if key in before and isinstance(after[key], (int, float)) and isinstance(before[key], (int, float)):
                deltas[key] = round(after[key] - before[key], 4)
        return deltas


# ── Research Session ──────────────────────────────────────────────────────────


class ResearchSession:
    """Manages a complete reverse-engineering research session.

    Each session targets one piece of software and tracks all iterations
    with full scientific rigor: seeds, metrics, reflections, artifacts.

    The session log is append-only (JSONL format) for safe concurrent writes
    and easy ML consumption.

    Usage::

        session = ResearchSession("pong")
        for i in range(1, 26):
            session.begin_iteration(
                i,
                hypothesis=f"Approach {i}: ...",
                approach="raw_bytecode",
            )
            # ... implementation work ...
            session.record_metrics_after(bytecode_size=128, total_cycles=340)
            session.end_iteration(
                reflection=Reflection(
                    timestamp=now(),
                    iteration=i,
                    target="pong",
                    hypothesis="...",
                    observations=["..."],
                    successes=["..."],
                    failures=["..."],
                    next_steps=["..."],
                    open_questions=["..."],
                    confidence=0.7,
                )
            )
        session.save()
    """

    def __init__(
        self,
        target: str,
        log_dir: Path | None = None,
        seed_dir: Path | None = None,
        reflection_dir: Path | None = None,
    ):
        self.target = target.lower().replace(" ", "_").replace("-", "_")
        self.session_id = f"{self.target}_{uuid.uuid4().hex[:12]}"
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.log_dir = log_dir or _default_log_dir()
        self.seed_dir = seed_dir or _default_seed_dir()
        self.reflection_dir = reflection_dir or _default_reflection_dir()

        self._current_iteration: Optional[Iteration] = None
        self._iterations: list[Iteration] = []
        self._config: dict = {}

    @property
    def log_path(self) -> Path:
        return self.log_dir / f"{self.target}.jsonl"

    @property
    def iteration_count(self) -> int:
        return len(self._iterations)

    def set_config(self, **kwargs: Any) -> None:
        """Set session-wide configuration (saved with each seed)."""
        self._config.update(kwargs)

    def begin_iteration(
        self,
        number: int,
        hypothesis: str = "",
        approach: str = "raw_bytecode",
        config: dict | None = None,
    ) -> Iteration:
        """Start a new research iteration."""
        merged_config = {**self._config, **(config or {})}
        seed = Seed.generate(self.target, number, merged_config)
        seed.notes = f"Iteration {number}: {hypothesis[:80]}"

        # Save seed
        seed_path = self.seed_dir / f"{seed.seed_id}.json"
        seed_path.write_text(json.dumps(seed.to_dict(), indent=2))

        iteration = Iteration(
            target=self.target,
            iteration_number=number,
            seed=seed,
            started_at=datetime.now(timezone.utc).isoformat(),
            hypothesis=hypothesis,
            approach=approach,
            status="in_progress",
        )

        self._current_iteration = iteration
        self._iterations.append(iteration)
        return iteration

    def record_metrics_before(self, **kwargs: Any) -> MetricSnapshot:
        """Record metrics before the iteration's changes."""
        snap = MetricSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            **kwargs,
        )
        if self._current_iteration:
            self._current_iteration.metrics_before = snap
        return snap

    def record_metrics_after(self, **kwargs: Any) -> MetricSnapshot:
        """Record metrics after the iteration's changes."""
        snap = MetricSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            **kwargs,
        )
        if self._current_iteration:
            self._current_iteration.metrics_after = snap
        return snap

    def add_artifact(self, path: str) -> None:
        """Record an artifact produced by this iteration."""
        if self._current_iteration:
            self._current_iteration.artifacts.append(path)

    def end_iteration(
        self,
        reflection: Reflection | None = None,
        status: str = "completed",
        error: str = "",
    ) -> Iteration:
        """Complete the current iteration with optional reflection."""
        if not self._current_iteration:
            raise RuntimeError("No iteration in progress. Call begin_iteration() first.")

        self._current_iteration.ended_at = datetime.now(timezone.utc).isoformat()
        self._current_iteration.status = status
        self._current_iteration.error = error

        if reflection:
            # Auto-fill metric deltas
            deltas = self._current_iteration.compute_deltas()
            reflection.metric_deltas = deltas
            self._current_iteration.reflection = reflection

            # Save reflection as markdown
            ref_path = (
                self.reflection_dir
                / f"{self.target}_iter{self._current_iteration.iteration_number}.md"
            )
            ref_path.write_text(reflection.to_markdown())

        # Append to JSONL log
        self._append_log(self._current_iteration)

        result = self._current_iteration
        self._current_iteration = None
        return result

    def save(self) -> None:
        """Save the full session summary."""
        if self._current_iteration:
            # Auto-complete any in-progress iteration
            self.end_iteration(
                status="auto_saved",
                reflection=Reflection(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    iteration=self._current_iteration.iteration_number,
                    target=self.target,
                    hypothesis=self._current_iteration.hypothesis,
                    observations=["Session auto-saved"],
                    next_steps=["Resume in next session"],
                    confidence=0.3,
                ),
            )

    def summary(self) -> str:
        """Generate a human-readable summary of the session."""
        lines = [
            f"Research Session: {self.target}",
            f"Session ID: {self.session_id}",
            f"Created: {self.created_at}",
            f"Iterations: {self.iteration_count}",
            f"Log: {self.log_path}",
            "",
        ]
        completed = [i for i in self._iterations if i.status == "completed"]
        if completed:
            best = max(completed, key=lambda i: i.reflection.confidence if i.reflection else 0)
            lines.extend([
                f"Best iteration: #{best.iteration_number} (confidence: "
                f"{best.reflection.confidence:.0%})" if best.reflection else "",
                f"Best approach: {best.approach}",
                "",
            ])

            lines.append("Iteration Log:")
            lines.append(f"  {'#':>3}  {'Approach':<16}  {'Status':<12}  {'Cycles':>8}  {'Bytes':>6}  {'Conf':>5}")
            lines.append(f"  {'─'*3}  {'─'*16}  {'─'*12}  {'─'*8}  {'─'*6}  {'─'*5}")
            for it in self._iterations:
                cycles = it.metrics_after.total_cycles if it.metrics_after else 0
                bsize = it.metrics_after.bytecode_size if it.metrics_after else 0
                conf = f"{it.reflection.confidence:.0%}" if it.reflection else "—"
                lines.append(
                    f"  {it.iteration_number:>3}  {it.approach:<16}  {it.status:<12}  "
                    f"{cycles:>8}  {bsize:>6}  {conf:>5}"
                )

        return "\n".join(lines)

    def _append_log(self, iteration: Iteration) -> None:
        """Append one iteration to the JSONL log file."""
        with open(self.log_path, "a") as f:
            f.write(json.dumps(iteration.to_dict()) + "\n")
