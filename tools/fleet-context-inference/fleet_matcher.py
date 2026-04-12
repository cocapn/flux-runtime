#!/usr/bin/env python3
"""
Fleet Context Inference Protocol — fleet_matcher.py

Given a task description, finds the best-matching agent from the fleet.
Uses capability profiles + recent activity + domain expertise to rank agents.

Scoring Algorithm:
    match_score = domain_match * 0.4 + recent_activity * 0.3 + historical_success * 0.3

Implements skill tag matching (python, rust, cuda, design, etc.) and
outputs ranked agent recommendations with match scores and reasoning.

Part of the FLUX Bytecode VM Fleet Context Inference Protocol.
"""

from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

from capability_parser import (
    ProfileMerger,
    ParsedCapability,
    ActivityLevel,
)


# ---------------------------------------------------------------------------
# Constants & Configuration
# ---------------------------------------------------------------------------

# Core scoring weights (must sum to 1.0)
DOMAIN_MATCH_WEIGHT = 0.4
RECENT_ACTIVITY_WEIGHT = 0.3
HISTORICAL_SUCCESS_WEIGHT = 0.3

# Bonus multipliers
SPECIALIZATION_BONUS = 0.08
SKILL_TAG_EXACT_BONUS = 0.10
RESOURCE_MATCH_BONUS = 0.05
STALENESS_PENALTY = 0.15
COMMUNICATION_BONUS = 0.03
TRUST_BONUS_WEIGHT = 0.05

# Domain keyword mapping for task matching
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "python": ["python", "pip", "pytest", "flask", "django", "pandas", "numpy"],
    "rust": ["rust", "cargo", "crate", "tokio", "serde", "rustc"],
    "typescript": ["typescript", "ts", "tsx", "react", "next.js", "node"],
    "javascript": ["javascript", "js", "jsx", "node", "npm", "webpack"],
    "go": ["go", "golang", "goroutine", "go mod", "gin"],
    "c": ["c language", "gcc", "clang", "c++", "cpp", "makefile"],
    "cuda": ["cuda", "gpu", "jetson", "tensor core", "nvcc", "cublas"],
    "zig": ["zig", "zig build", "comptime"],
    "testing": ["test", "testing", "assert", "pytest", "jest", "coverage", "tdd"],
    "architecture": [
        "architecture", "design", "spec", "RFC", "system design",
        "planning", "roadmap",
    ],
    "devops": [
        "docker", "kubernetes", "CI/CD", "deploy", "terraform",
        "github actions", "infrastructure",
    ],
    "bytecode_vm": [
        "bytecode", "opcode", "VM", "interpreter", "assembler",
        "disassembler", "register", "stack machine", "instruction set",
        "flux",
    ],
    "machine_learning": [
        "neural", "model", "training", "inference", "transformer",
        "tensor", "deep learning", "ML",
    ],
    "web_development": [
        "HTML", "CSS", "frontend", "web", "UI", "component",
        "tailwind", "responsive",
    ],
    "database": ["database", "SQL", "postgres", "prisma", "migration", "schema"],
    "security": [
        "security", "encrypt", "decrypt", "auth", "JWT", "token",
        "crypto", "trust",
    ],
    "networking": ["HTTP", "REST", "API", "gRPC", "websocket", "TCP", "socket"],
    "evolution": [
        "mutation", "selection", "fitness", "genome", "evolution",
        "genetic", "self-evolve",
    ],
    "fleet_coordination": [
        "fleet", "agent", "dispatch", "spawn", "vessel", "lighthouse",
        "coordination", "orchestration",
    ],
    "research": [
        "research", "paper", "arXiv", "analysis", "survey", "benchmark",
        "study", "experiment",
    ],
    "design": ["design", "UI", "UX", "layout", "visual", "graphic", "icon"],
    "documentation": [
        "docs", "documentation", "README", "guide", "tutorial",
        "onboarding", "handbook",
    ],
}

# Skill tags that can be extracted from task descriptions
SKILL_TAG_PATTERNS: dict[str, re.Pattern] = {
    tag: re.compile(rf"\b{re.escape(tag)}\b", re.IGNORECASE)
    for tag in [
        "python", "rust", "typescript", "javascript", "go", "c", "cuda",
        "zig", "testing", "docker", "kubernetes", "react", "vue", "svelte",
        "node", "flask", "django", "sql", "graphql", "redis", "mongodb",
        "tensorflow", "pytorch", "design", "frontend", "backend", "api",
        "devops", "security", "networking", "database", "ml", "bytecode",
        "asm", "assembly", "embedded", "arm64", "gpu", "fpga",
    ]
}

# Resource requirement patterns
RESOURCE_PATTERNS: dict[str, re.Pattern] = {
    "cuda": re.compile(r"\b(cuda|gpu|tensor.?core|jetson|nvcc|cuda\.|cublas)\b", re.IGNORECASE),
    "high_ram": re.compile(r"\b(high.?ram|large.?memory|big.?memory|24gb|32gb|64gb)\b", re.IGNORECASE),
    "high_cpu": re.compile(r"\b(high.?cpu|multi.?core|parallel|compute.?intensive)\b", re.IGNORECASE),
    "storage": re.compile(r"\b(large.?storage|storage.?intensive|big.?data)\b", re.IGNORECASE),
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TaskDescription:
    """Parsed representation of a task to be matched against agents."""
    raw: str = ""
    title: str = ""
    description: str = ""
    required_domains: list[str] = field(default_factory=list)
    required_skills: list[str] = field(default_factory=list)
    required_resources: list[str] = field(default_factory=list)
    priority: str = "normal"  # low, normal, high, critical
    estimated_hours: float = 0.0
    complexity: str = "medium"  # low, medium, high

    @classmethod
    def from_string(cls, task_string: str) -> "TaskDescription":
        """Parse a free-text task description into structured requirements."""
        task = cls(raw=task_string)

        # Split title and description if formatted
        lines = task_string.strip().split("\n")
        if lines:
            task.title = lines[0].strip().lstrip("#").strip()
            if len(lines) > 1:
                task.description = "\n".join(lines[1:]).strip()
            else:
                task.description = task_string.strip()

        # Extract domain requirements from keywords
        task_lower = task_string.lower()
        for domain, keywords in DOMAIN_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in task_lower:
                    task.required_domains.append(domain)
                    break

        # Extract skill tags
        for tag, pattern in SKILL_TAG_PATTERNS.items():
            if pattern.search(task_string):
                task.required_skills.append(tag)

        # Extract resource requirements
        for resource, pattern in RESOURCE_PATTERNS.items():
            if pattern.search(task_string):
                task.required_resources.append(resource)

        # Deduplicate
        task.required_domains = list(dict.fromkeys(task.required_domains))
        task.required_skills = list(dict.fromkeys(task.required_skills))
        task.required_resources = list(dict.fromkeys(task.required_resources))

        return task


@dataclass
class AgentMatchScore:
    """Detailed scoring breakdown for a single agent-task match."""
    agent_name: str
    overall_score: float = 0.0
    domain_match_score: float = 0.0
    recent_activity_score: float = 0.0
    historical_success_score: float = 0.0
    specialization_bonus: float = 0.0
    skill_tag_bonus: float = 0.0
    resource_bonus: float = 0.0
    staleness_penalty: float = 0.0
    communication_bonus: float = 0.0
    trust_bonus: float = 0.0
    matched_domains: list[str] = field(default_factory=list)
    matched_skills: list[str] = field(default_factory=list)
    missing_domains: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)

    @property
    def rank_label(self) -> str:
        if self.overall_score >= 0.85:
            return "★★★ EXCELLENT"
        elif self.overall_score >= 0.65:
            return "★★ GOOD"
        elif self.overall_score >= 0.45:
            return "★ FAIR"
        else:
            return "○ MARGINAL"

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "overall_score": round(self.overall_score, 4),
            "rank_label": self.rank_label,
            "breakdown": {
                "domain_match": round(self.domain_match_score, 4),
                "recent_activity": round(self.recent_activity_score, 4),
                "historical_success": round(self.historical_success_score, 4),
                "specialization_bonus": round(self.specialization_bonus, 4),
                "skill_tag_bonus": round(self.skill_tag_bonus, 4),
                "resource_bonus": round(self.resource_bonus, 4),
                "staleness_penalty": round(self.staleness_penalty, 4),
                "communication_bonus": round(self.communication_bonus, 4),
                "trust_bonus": round(self.trust_bonus, 4),
            },
            "matched_domains": self.matched_domains,
            "matched_skills": self.matched_skills,
            "missing_domains": self.missing_domains,
            "missing_skills": self.missing_skills,
            "reasoning": self.reasoning,
        }


@dataclass
class MatchResult:
    """Complete result of a fleet matching operation."""
    task: TaskDescription
    matches: list[AgentMatchScore] = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    @property
    def best_match(self) -> Optional[AgentMatchScore]:
        return self.matches[0] if self.matches else None

    @property
    def top_n(self, n: int = 3) -> list[AgentMatchScore]:
        return self.matches[:n]

    def to_markdown(self) -> str:
        """Render match results as a markdown report."""
        lines = [
            "# Fleet Task Matching Report",
            "",
            f"**Generated:** {self.timestamp}",
            f"**Task:** {self.task.title or '(untitled)'}",
            "",
        ]
        if self.task.required_domains:
            lines.append(f"**Required Domains:** {', '.join(self.task.required_domains)}")
        if self.task.required_skills:
            lines.append(f"**Required Skills:** `{'`, `'.join(self.task.required_skills)}`")
        if self.task.required_resources:
            lines.append(f"**Required Resources:** {', '.join(self.task.required_resources)}")
        lines.append("")

        if not self.matches:
            lines.append("⚠ **No matching agents found.**")
            return "\n".join(lines)

        lines.append("## Ranked Matches")
        lines.append("")

        for rank, match in enumerate(self.matches, 1):
            lines.append(f"### {rank}. {match.agent_name} — {match.rank_label}")
            lines.append("")
            lines.append(f"| Component | Score |")
            lines.append(f"|-----------|-------|")
            lines.append(f"| **Overall** | **{match.overall_score:.3f}** |")
            lines.append(f"| Domain Match | {match.domain_match_score:.3f} |")
            lines.append(f"| Recent Activity | {match.recent_activity_score:.3f} |")
            lines.append(f"| Historical Success | {match.historical_success_score:.3f} |")
            lines.append(f"| Specialization Bonus | +{match.specialization_bonus:.3f} |")
            lines.append(f"| Skill Tag Bonus | +{match.skill_tag_bonus:.3f} |")
            lines.append(f"| Resource Bonus | +{match.resource_bonus:.3f} |")
            lines.append(f"| Staleness Penalty | -{match.staleness_penalty:.3f} |")
            lines.append(f"| Communication Bonus | +{match.communication_bonus:.3f} |")
            lines.append(f"| Trust Bonus | +{match.trust_bonus:.3f} |")
            lines.append("")

            if match.matched_domains:
                lines.append(f"✓ Matched domains: {', '.join(match.matched_domains)}")
            if match.matched_skills:
                lines.append(f"✓ Matched skills: `{'`, `'.join(match.matched_skills)}`")
            if match.missing_domains:
                lines.append(f"✗ Missing domains: {', '.join(match.missing_domains)}")
            if match.missing_skills:
                lines.append(f"✗ Missing skills: `{'`, `'.join(match.missing_skills)}`")
            lines.append("")

            if match.reasoning:
                lines.append("**Reasoning:**")
                for r in match.reasoning:
                    lines.append(f"  - {r}")
                lines.append("")

        return "\n".join(lines)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps({
            "task": {
                "raw": self.task.raw,
                "title": self.task.title,
                "required_domains": self.task.required_domains,
                "required_skills": self.task.required_skills,
                "required_resources": self.task.required_resources,
            },
            "timestamp": self.timestamp,
            "matches": [m.to_dict() for m in self.matches],
        }, indent=indent)


# ---------------------------------------------------------------------------
# Historical Success Tracker
# ---------------------------------------------------------------------------

class HistoricalSuccessTracker:
    """
    Tracks historical task completion success rates for agents.
    In a real fleet deployment, this would be backed by a persistent store.
    For now, operates in-memory with optional JSON persistence.
    """

    def __init__(self, data_path: Optional[str] = None):
        self.data_path = data_path
        self._records: dict[str, dict[str, Any]] = {}
        if data_path and Path(data_path).exists():
            self._load()

    def record_outcome(
        self,
        agent_name: str,
        task_domain: str,
        success: bool,
        quality_score: float = 1.0,
    ) -> None:
        """Record the outcome of a task assigned to an agent."""
        if agent_name not in self._records:
            self._records[agent_name] = {
                "total_tasks": 0,
                "successful": 0,
                "domain_success": {},
            }
        rec = self._records[agent_name]
        rec["total_tasks"] += 1
        if success:
            rec["successful"] += 1

        if task_domain not in rec["domain_success"]:
            rec["domain_success"][task_domain] = {"total": 0, "success": 0}
        ds = rec["domain_success"][task_domain]
        ds["total"] += 1
        if success:
            ds["success"] += 1

        self._save()

    def get_success_rate(self, agent_name: str, domain: Optional[str] = None) -> float:
        """Get the success rate for an agent, optionally filtered by domain."""
        rec = self._records.get(agent_name)
        if not rec:
            return 0.5  # Neutral prior for unknown agents

        if domain:
            ds = rec["domain_success"].get(domain)
            if ds and ds["total"] >= 3:
                return ds["success"] / ds["total"]

        # Fall back to overall rate
        if rec["total_tasks"] >= 3:
            return rec["successful"] / rec["total_tasks"]

        return 0.5  # Not enough data

    def get_task_count(self, agent_name: str) -> int:
        """Get total tasks completed by an agent."""
        return self._records.get(agent_name, {}).get("total_tasks", 0)

    def _load(self) -> None:
        if self.data_path:
            try:
                with open(self.data_path, "r", encoding="utf-8") as f:
                    self._records = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._records = {}

    def _save(self) -> None:
        if self.data_path:
            Path(self.data_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(self._records, f, indent=2)


# ---------------------------------------------------------------------------
# Fleet Matcher — core scoring engine
# ---------------------------------------------------------------------------

class FleetMatcher:
    """
    Given a task description, finds the best-matching agent from the fleet.

    Scoring formula:
        match_score = (domain_match * 0.4
                     + recent_activity * 0.3
                     + historical_success * 0.3)
                     + bonuses - penalties

    All component scores are normalized to [0, 1] before weighting.
    """

    def __init__(
        self,
        agent_profiles: list[dict[str, Any]],
        success_tracker: Optional[HistoricalSuccessTracker] = None,
        weights: Optional[dict[str, float]] = None,
    ):
        """
        Args:
            agent_profiles: List of merged agent capability dictionaries
                           (output of ProfileMerger.merge()).
            success_tracker: Historical success data. Uses neutral priors if None.
            weights: Custom scoring weights. Defaults to the protocol standard.
        """
        self.profiles = {
            p.get("agent_name", f"agent-{i}"): p
            for i, p in enumerate(agent_profiles)
        }
        self.tracker = success_tracker or HistoricalSuccessTracker()

        if weights:
            self.w = weights
        else:
            self.w = {
                "domain": DOMAIN_MATCH_WEIGHT,
                "activity": RECENT_ACTIVITY_WEIGHT,
                "success": HISTORICAL_SUCCESS_WEIGHT,
            }
        # Verify weights sum to 1.0
        total = sum(self.w.values())
        if abs(total - 1.0) > 0.01:
            print(
                f"  [WARN] Scoring weights sum to {total:.2f}, expected 1.0",
                file=sys.stderr,
            )

    def match(
        self,
        task: str | TaskDescription,
        top_n: int = 5,
        min_score: float = 0.0,
    ) -> MatchResult:
        """
        Match a task against all known agents and return ranked results.

        Args:
            task: Task description as string or TaskDescription.
            top_n: Maximum number of results to return.
            min_score: Minimum score threshold for inclusion.

        Returns:
            MatchResult with ranked agent recommendations.
        """
        if isinstance(task, str):
            task = TaskDescription.from_string(task)

        scores: list[AgentMatchScore] = []
        for agent_name, profile in self.profiles.items():
            score = self._score_agent(agent_name, profile, task)
            if score.overall_score >= min_score:
                scores.append(score)

        # Sort by overall score descending
        scores.sort(key=lambda s: s.overall_score, reverse=True)
        scores = scores[:top_n]

        return MatchResult(task=task, matches=scores)

    def _score_agent(
        self, agent_name: str, profile: dict[str, Any], task: TaskDescription
    ) -> AgentMatchScore:
        """Compute the full scoring breakdown for one agent vs. one task."""
        score = AgentMatchScore(agent_name=agent_name)

        # --- 1. Domain Match Score (0-1) ---
        score.domain_match_score = self._compute_domain_match(profile, task, score)

        # --- 2. Recent Activity Score (0-1) ---
        score.recent_activity_score = self._compute_activity_score(profile, task, score)

        # --- 3. Historical Success Score (0-1) ---
        score.historical_success_score = self._compute_success_score(profile, task, score)

        # --- Apply staleness penalty ---
        score.staleness_penalty = self._compute_staleness_penalty(profile, score)

        # --- Compute bonuses ---
        score.specialization_bonus = self._compute_specialization_bonus(profile, task, score)
        score.skill_tag_bonus = self._compute_skill_tag_bonus(profile, task, score)
        score.resource_bonus = self._compute_resource_bonus(profile, task, score)
        score.communication_bonus = self._compute_communication_bonus(profile, score)
        score.trust_bonus = self._compute_trust_bonus(profile, score)

        # --- Final score ---
        raw = (
            score.domain_match_score * self.w["domain"]
            + score.recent_activity_score * self.w["activity"]
            + score.historical_success_score * self.w["success"]
        )
        adjusted = raw + score.specialization_bonus + score.skill_tag_bonus
        adjusted += score.resource_bonus + score.communication_bonus + score.trust_bonus
        adjusted -= score.staleness_penalty

        score.overall_score = max(0.0, min(1.0, adjusted))

        # Track matched and missing
        agent_domains = set(profile.get("domains", {}).keys())
        agent_skills = set(profile.get("skill_tags", []))
        score.matched_domains = sorted(agent_domains & set(task.required_domains))
        score.matched_skills = sorted(agent_skills & set(task.required_skills))
        score.missing_domains = sorted(set(task.required_domains) - agent_domains)
        score.missing_skills = sorted(set(task.required_skills) - agent_skills)

        return score

    def _compute_domain_match(
        self, profile: dict, task: TaskDescription, score: AgentMatchScore
    ) -> float:
        """
        Compute domain match score (0-1).
        Measures how well the agent's domains cover the task's requirements.
        """
        if not task.required_domains:
            score.reasoning.append("No specific domains required — neutral domain score.")
            return 0.5  # Neutral when no domains required

        agent_domains = profile.get("domains", {})
        total_score = 0.0

        for domain in task.required_domains:
            domain_data = agent_domains.get(domain, {})
            confidence = domain_data.get("confidence", 0.0)

            # Use the git-inferred confidence if it's higher (evidence-based)
            git_conf = domain_data.get("git_confidence", 0.0)
            effective = max(confidence, git_conf * 0.8)  # Trust self-report slightly more

            total_score += effective

        avg_score = total_score / len(task.required_domains)
        score.reasoning.append(
            f"Domain match: {avg_score:.2f} across {len(task.required_domains)} required domains"
        )
        return min(1.0, avg_score)

    def _compute_activity_score(
        self, profile: dict, task: TaskDescription, score: AgentMatchScore
    ) -> float:
        """
        Compute recent activity score (0-1).
        Based on activity level, commit recency, and consistency.
        """
        level_str = profile.get("activity_level", "dormant")

        # Base score from activity level
        level_scores = {
            "highly_active": 1.0,
            "active": 0.75,
            "stale": 0.3,
            "dormant": 0.05,
        }
        base = level_scores.get(level_str, 0.2)

        # Boost from total commits (logarithmic)
        total_commits = profile.get("total_commits", 0)
        commit_boost = min(0.2, 0.05 * math.log1p(total_commits / 10))

        result = min(1.0, base + commit_boost)
        score.reasoning.append(f"Activity: {level_str} (base={base:.2f}, commits={total_commits})")
        return result

    def _compute_success_score(
        self, profile: dict, task: TaskDescription, score: AgentMatchScore
    ) -> float:
        """
        Compute historical success score (0-1).
        Uses the HistoricalSuccessTracker with neutral priors.
        """
        agent_name = score.agent_name

        # Get overall success rate
        overall_rate = self.tracker.get_success_rate(agent_name)

        # Get domain-specific rates for required domains
        domain_rates = []
        for domain in task.required_domains:
            rate = self.tracker.get_success_rate(agent_name, domain)
            domain_rates.append(rate)

        if domain_rates:
            # Weight domain-specific rates more heavily
            combined = 0.4 * overall_rate + 0.6 * (sum(domain_rates) / len(domain_rates))
        else:
            combined = overall_rate

        # Task count confidence boost (more history = more trust)
        task_count = self.tracker.get_task_count(agent_name)
        confidence_factor = min(1.0, task_count / 20)  # Full trust at 20+ tasks

        result = 0.5 * (1 - confidence_factor) + combined * confidence_factor
        score.reasoning.append(
            f"Historical success: {overall_rate:.2f} overall, "
            f"{len(domain_rates)} domain-specific rates, "
            f"{task_count} tasks recorded"
        )
        return result

    def _compute_staleness_penalty(
        self, profile: dict, score: AgentMatchScore
    ) -> float:
        """Compute staleness penalty based on how long since the agent was active."""
        last_active_str = profile.get("last_active")
        if not last_active_str:
            return STALENESS_PENALTY  # Max penalty for unknown

        try:
            last_active = datetime.fromisoformat(last_active_str)
            if last_active.tzinfo is None:
                last_active = last_active.replace(tzinfo=timezone.utc)
            days_since = (datetime.now(timezone.utc) - last_active).days
        except (ValueError, TypeError):
            return STALENESS_PENALTY * 0.5

        if days_since <= 1:
            return 0.0
        elif days_since <= 3:
            return STALENESS_PENALTY * 0.1
        elif days_since <= 7:
            return STALENESS_PENALTY * 0.3
        elif days_since <= 14:
            return STALENESS_PENALTY * 0.6
        else:
            return STALENESS_PENALTY

    def _compute_specialization_bonus(
        self, profile: dict, task: TaskDescription, score: AgentMatchScore
    ) -> float:
        """Bonus for agents with specializations matching the task."""
        agent_specs = set(profile.get("specializations", []))
        if not agent_specs or not task.required_domains:
            return 0.0

        overlap = agent_specs & set(task.required_domains)
        if overlap:
            bonus = min(SPECIALIZATION_BONUS * len(overlap), SPECIALIZATION_BONUS * 2)
            score.reasoning.append(f"Specialization bonus: +{bonus:.3f} for {sorted(overlap)}")
            return bonus
        return 0.0

    def _compute_skill_tag_bonus(
        self, profile: dict, task: TaskDescription, score: AgentMatchScore
    ) -> float:
        """Bonus for exact skill tag matches."""
        agent_skills = set(profile.get("skill_tags", []))
        if not task.required_skills or not agent_skills:
            return 0.0

        overlap = agent_skills & set(task.required_skills)
        if overlap:
            bonus = min(SKILL_TAG_EXACT_BONUS * len(overlap), SKILL_TAG_EXACT_BONUS * 3)
            score.reasoning.append(f"Skill tag bonus: +{bonus:.3f} for {sorted(overlap)}")
            return bonus
        return 0.0

    def _compute_resource_bonus(
        self, profile: dict, task: TaskDescription, score: AgentMatchScore
    ) -> float:
        """Bonus when agent has resources the task requires."""
        resources = profile.get("resources", {})
        bonus = 0.0

        for req in task.required_resources:
            if req == "cuda" and resources.get("cuda", False):
                bonus += RESOURCE_MATCH_BONUS
                score.reasoning.append("Resource bonus: agent has CUDA available")
            elif req == "high_ram" and resources.get("ram_gb", 0) >= 16:
                bonus += RESOURCE_MATCH_BONUS
                score.reasoning.append(f"Resource bonus: agent has {resources.get('ram_gb', 0)}GB RAM")
            elif req == "high_cpu" and resources.get("cpu_cores", 0) >= 4:
                bonus += RESOURCE_MATCH_BONUS
                score.reasoning.append(f"Resource bonus: agent has {resources.get('cpu_cores', 0)} CPU cores")

        return min(bonus, RESOURCE_MATCH_BONUS * 3)

    def _compute_communication_bonus(
        self, profile: dict, score: AgentMatchScore
    ) -> float:
        """Bonus for agents with active communication channels."""
        comm = profile.get("communication", {})
        channels = sum([
            comm.get("bottles", False),
            comm.get("mud", False),
            comm.get("issues", False),
            comm.get("pr_reviews", False),
        ])
        if channels >= 2:
            score.reasoning.append(f"Communication bonus: {channels} channels active")
            return COMMUNICATION_BONUS
        return 0.0

    def _compute_trust_bonus(
        self, profile: dict, score: AgentMatchScore
    ) -> float:
        """Bonus based on trust relationships from associates section."""
        # Trust is handled via HistoricalSuccessTracker in real deployment
        # Here we provide a small bonus for agents with trust data
        task_count = self.tracker.get_task_count(score.agent_name)
        if task_count >= 5:
            return TRUST_BONUS_WEIGHT
        return 0.0


# ---------------------------------------------------------------------------
# Fleet Matcher CLI
# ---------------------------------------------------------------------------

def main():
    """Command-line interface for fleet task matching."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="fleet_matcher",
        description="Match tasks to the best agents in the fleet using capability profiles.",
    )
    parser.add_argument(
        "--profiles", required=True,
        help="Path to a JSON file containing merged agent profiles (array).",
    )
    parser.add_argument(
        "--task", required=True,
        help="Task description string to match against agents.",
    )
    parser.add_argument(
        "--task-file", default=None,
        help="Read task description from a file.",
    )
    parser.add_argument(
        "--top-n", type=int, default=5,
        help="Number of top matches to return (default: 5).",
    )
    parser.add_argument(
        "--min-score", type=float, default=0.0,
        help="Minimum score threshold (default: 0.0).",
    )
    parser.add_argument(
        "--format", choices=["text", "json", "markdown"], default="text",
        help="Output format (default: text).",
    )
    parser.add_argument(
        "--output", default=None,
        help="Write results to a file.",
    )

    args = parser.parse_args()

    # Load profiles
    with open(args.profiles, "r", encoding="utf-8") as f:
        profiles = json.load(f)
    if not isinstance(profiles, list):
        print("Error: profiles file must contain a JSON array.", file=sys.stderr)
        sys.exit(1)
    print(f"📋 Loaded {len(profiles)} agent profiles from {args.profiles}")

    # Load task
    if args.task_file:
        with open(args.task_file, "r", encoding="utf-8") as f:
            task_text = f.read().strip()
    else:
        task_text = args.task

    print(f"🎯 Task: {task_text[:80]}{'...' if len(task_text) > 80 else ''}")
    print()

    # Match
    matcher = FleetMatcher(profiles)
    result = matcher.match(task_text, top_n=args.top_n, min_score=args.min_score)

    # Output
    if args.format == "json":
        output = result.to_json()
    elif args.format == "markdown":
        output = result.to_markdown()
    else:
        output = _format_text(result)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"💾 Results saved: {args.output}")
    else:
        print(output)


def _format_text(result: MatchResult) -> str:
    """Format match results as readable text."""
    lines = [
        "═══════════════════════════════════════════════════",
        "  FLEET TASK MATCHING RESULTS",
        "═══════════════════════════════════════════════════",
        "",
        f"  Task: {result.task.title or result.task.raw[:60]}",
        f"  Generated: {result.timestamp}",
        "",
    ]

    if not result.matches:
        lines.append("  ⚠ No matching agents found.")
        return "\n".join(lines)

    for rank, match in enumerate(result.matches, 1):
        lines.append(f"  ┌─ #{rank} {match.agent_name}  {match.rank_label}")
        lines.append(f"  │  Overall Score: {match.overall_score:.4f}")
        lines.append(f"  │  Domain Match:  {match.domain_match_score:.4f} × {DOMAIN_MATCH_WEIGHT}")
        lines.append(f"  │  Activity:      {match.recent_activity_score:.4f} × {RECENT_ACTIVITY_WEIGHT}")
        lines.append(f"  │  Success Hist:  {match.historical_success_score:.4f} × {HISTORICAL_SUCCESS_WEIGHT}")
        if match.specialization_bonus > 0:
            lines.append(f"  │  + Spec Bonus:  {match.specialization_bonus:.4f}")
        if match.skill_tag_bonus > 0:
            lines.append(f"  │  + Skill Bonus: {match.skill_tag_bonus:.4f}")
        if match.resource_bonus > 0:
            lines.append(f"  │  + Res Bonus:   {match.resource_bonus:.4f}")
        if match.staleness_penalty > 0:
            lines.append(f"  │  - Stale Pen:   {match.staleness_penalty:.4f}")
        if match.matched_domains:
            lines.append(f"  │  Domains ✓: {', '.join(match.matched_domains)}")
        if match.matched_skills:
            lines.append(f"  │  Skills ✓:  {'  '.join(match.matched_skills)}")
        if match.missing_domains:
            lines.append(f"  │  Missing ✗: {', '.join(match.missing_domains)}")
        lines.append(f"  └───────────────────────────────────")
        lines.append("")

        for reason in match.reasoning:
            lines.append(f"    → {reason}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    main()
