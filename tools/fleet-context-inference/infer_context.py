#!/usr/bin/env python3
"""
Fleet Context Inference Protocol — infer_context.py

Scans vessel repos' git histories to build expertise profiles.
Reads commits, file paths, and code changes to produce capability
profiles with domain scores, specialty areas, and activity patterns.

Part of the FLUX Bytecode VM Fleet Context Inference Protocol.
Proposed by Oracle1 in the ISA Convergence Response (2026-04-12).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Domain taxonomy — maps file extensions, directories, keywords → domains
# ---------------------------------------------------------------------------

DOMAIN_TAXONOMY: dict[str, dict[str, list[str]]] = {
    "python": {
        "extensions": [".py", ".pyi", ".pyx", ".pxd"],
        "directories": ["python/", "py_src/", "src/"],
        "keywords": ["python", "pip", "poetry", "setuptools", "pytest"],
    },
    "rust": {
        "extensions": [".rs", ".toml"],
        "directories": ["src/", "examples/", "benches/"],
        "keywords": ["cargo", "rust", "rustc", "tokio", "serde"],
    },
    "typescript": {
        "extensions": [".ts", ".tsx", ".mts", ".cts"],
        "directories": ["src/", "lib/", "app/", "pages/"],
        "keywords": ["typescript", "tsc", "npm", "tsx", "next"],
    },
    "javascript": {
        "extensions": [".js", ".jsx", ".mjs", ".cjs"],
        "directories": ["src/", "lib/", "app/"],
        "keywords": ["javascript", "node", "npm", "webpack", "vite"],
    },
    "go": {
        "extensions": [".go"],
        "directories": ["cmd/", "pkg/", "internal/"],
        "keywords": ["golang", "go mod", "go run", "goroutine"],
    },
    "c": {
        "extensions": [".c", ".h", ".cpp", ".hpp", ".cc", ".cxx"],
        "directories": ["src/", "include/", "lib/"],
        "keywords": ["gcc", "clang", "makefile", "cmake", "libc"],
    },
    "cuda": {
        "extensions": [".cu", ".cuh", ".ptx"],
        "directories": ["kernels/", "cuda/", "gpu/"],
        "keywords": ["cuda", "nvcc", "cublas", "cudnn", "tensor core"],
    },
    "zig": {
        "extensions": [".zig"],
        "directories": ["src/", "lib/"],
        "keywords": ["zig", "zig build", "comptime"],
    },
    "testing": {
        "extensions": [".test.ts", ".test.js", "_test.py", "_test.rs", ".spec.ts"],
        "directories": ["tests/", "test/", "__tests__/", "spec/"],
        "keywords": ["test", "assert", "expect", "pytest", "jest", "mocha", "cargo test"],
    },
    "architecture": {
        "extensions": [".md", ".rst", ".txt"],
        "directories": ["docs/", "doc/", "specs/", "rfc/", "design/"],
        "keywords": ["architecture", "design", "spec", "RFC", "proposal", "protocol"],
    },
    "devops": {
        "extensions": [".yml", ".yaml", ".dockerfile", "Dockerfile"],
        "directories": [".github/", ".ci/", "deploy/", "infra/"],
        "keywords": ["docker", "kubernetes", "ci/cd", "terraform", "github actions"],
    },
    "bytecode_vm": {
        "extensions": [".flux", ".bytecode", ".bin", ".asm"],
        "directories": ["runtime/", "vm/", "bytecode/", "assembler/", "opcodes/"],
        "keywords": [
            "bytecode", "opcode", "instruction set", "VM", "register",
            "stack", "flux", "disassembler", "assembler", "interpreter",
        ],
    },
    "machine_learning": {
        "extensions": [".pt", ".onnx", ".safetensors", ".pkl"],
        "directories": ["model/", "models/", "ml/", "training/"],
        "keywords": ["neural", "transformer", "training", "inference", "model", "tensor"],
    },
    "web_development": {
        "extensions": [".html", ".css", ".scss", ".vue", ".svelte"],
        "directories": ["public/", "static/", "assets/", "components/"],
        "keywords": ["HTML", "CSS", "frontend", "react", "vue", "svelte", "tailwind"],
    },
    "database": {
        "extensions": [".sql", ".prisma", ".graphql"],
        "directories": ["migrations/", "db/", "schema/"],
        "keywords": ["SQL", "postgres", "mysql", "prisma", "migration", "schema"],
    },
    "security": {
        "extensions": [".pem", ".key", ".cert", ".sig"],
        "directories": ["security/", "auth/", "crypto/"],
        "keywords": ["encrypt", "decrypt", "hash", "token", "JWT", "OAuth", "trust"],
    },
    "networking": {
        "extensions": [".proto", ".thrift", ".graphql"],
        "directories": ["api/", "grpc/", "rest/", "websocket/"],
        "keywords": ["HTTP", "REST", "gRPC", "websocket", "TCP", "UDP", "socket"],
    },
    "evolution": {
        "extensions": [],
        "directories": ["evolution/", "evolve/", "genome/", "mutation/"],
        "keywords": [
            "mutation", "selection", "fitness", "genome", "evolution",
            "self-evolve", "genetic", "population", "crossover",
        ],
    },
    "fleet_coordination": {
        "extensions": [],
        "directories": ["fleet/", "coordination/", "dispatch/"],
        "keywords": [
            "fleet", "agent", "dispatch", "spawn", "vessel", "lighthouse",
            "bottle", "mausoleum", "quartermaster", "cocapn",
        ],
    },
}

# Specialty detection keywords — more specific than domains
SPECIALTY_KEYWORDS: dict[str, list[str]] = {
    "confidence_propagation": [
        "confidence", "bayesian fusion", "trust score", "decay curve",
        "uncertainty", "probabilistic",
    ],
    "isa_design": [
        "ISA", "instruction set", "opcode", "encoding", "register file",
        "instruction format", "addressing mode",
    ],
    "a2a_protocol": [
        "agent-to-agent", "A2A", "inter-agent", "message passing",
        "dispatch", "fleet communication",
    ],
    "memory_management": [
        "memory fabric", "forgetting curve", "working memory",
        "long-term memory", "cache layer", "eviction",
    ],
    "trust_scoring": [
        "trust", "reputation", "reliability score", "trust decay",
        "trust level", "yoke protocol",
    ],
    "debugging": [
        "debug", "trace", "witness mark", "forensic", "archaeology",
        "diagnostic", "assertion",
    ],
    "onboarding": [
        "onboarding", "bootcamp", "greenhorn", "getting started",
        "quickstart", "tutorial",
    ],
    "dsl_design": [
        "DSL", "parser", "compiler", "lexer", "tokenizer",
        "abstract syntax", "flux-ese",
    ],
    "knowledge_federation": [
        "knowledge federation", "knowledge graph", "federation",
        "registry", "knowledge base", "entry",
    ],
    "sandbox_runtime": [
        "sandbox", "isolation", "container", "jail",
        "security boundary", "execution environment",
    ],
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class ActivityLevel(Enum):
    DORMANT = "dormant"      # No activity in 30+ days
    STALE = "stale"          # No activity in 7-30 days
    ACTIVE = "active"        # Activity within 7 days
    HIGHLY_ACTIVE = "highly_active"  # Activity within 24 hours


@dataclass
class FileChange:
    """Represents a single file changed in a commit."""
    path: str
    extension: str
    added_lines: int = 0
    removed_lines: int = 0
    is_new_file: bool = False
    is_deleted: bool = False


@dataclass
class CommitRecord:
    """Parsed representation of a single git commit."""
    hash: str
    author: str
    author_email: str
    timestamp: datetime
    message: str
    message_subject: str
    files_changed: list[FileChange] = field(default_factory=list)
    total_additions: int = 0
    total_deletions: int = 0
    repo_path: str = ""

    @property
    def is_merge(self) -> bool:
        return "merge" in self.message_subject.lower().split()[:3]

    @property
    def domains_touched(self) -> list[str]:
        """Quick domain classification based on files and message."""
        touched = set()
        for fc in self.files_changed:
            for domain, rules in DOMAIN_TAXONOMY.items():
                if fc.extension in rules["extensions"]:
                    touched.add(domain)
                for d in rules["directories"]:
                    if fc.path.startswith(d):
                        touched.add(domain)
        return sorted(touched)


@dataclass
class DomainScore:
    """Expertise score for a single domain."""
    domain: str
    raw_score: float = 0.0
    commit_count: int = 0
    file_count: int = 0
    lines_changed: int = 0
    last_active: Optional[datetime] = None
    confidence: float = 0.0
    specializations: list[str] = field(default_factory=list)

    def compute_confidence(self) -> float:
        """Compute a 0-1 confidence based on evidence volume and recency."""
        if self.commit_count == 0:
            return 0.0

        # Volume factor (0-0.5): log-based to prevent saturation
        volume = min(0.5, 0.1 * (1 + (self.commit_count / 10) ** 0.5))

        # Breadth factor (0-0.2): number of files touched
        breadth = min(0.2, 0.02 * min(self.file_count, 10))

        # Depth factor (0-0.2): lines of code
        depth = min(0.2, 0.02 * (self.lines_changed / 100) ** 0.5)

        # Recency factor (0-0.1): how recently was this domain active
        recency = 0.0
        if self.last_active:
            days_since = (datetime.now(timezone.utc) - self.last_active).days
            recency = max(0.0, 0.1 * (1 - days_since / 30))

        self.confidence = round(min(1.0, volume + breadth + depth + recency), 3)
        return self.confidence


@dataclass
class ActivityPattern:
    """Patterns of when an agent is most active."""
    total_commits: int = 0
    commits_by_day_of_week: dict[str, int] = field(default_factory=lambda: {
        "mon": 0, "tue": 0, "wed": 0, "thu": 0, "fri": 0, "sat": 0, "sun": 0,
    })
    commits_by_hour: dict[int, int] = field(default_factory=dict)
    avg_commit_size: float = 0.0
    avg_files_per_commit: float = 0.0
    first_commit: Optional[datetime] = None
    last_commit: Optional[datetime] = None
    active_streak_days: int = 0
    longest_streak_days: int = 0

    @property
    def activity_level(self) -> ActivityLevel:
        if self.last_commit is None:
            return ActivityLevel.DORMANT
        days_since = (datetime.now(timezone.utc) - self.last_commit).days
        if days_since <= 1:
            return ActivityLevel.HIGHLY_ACTIVE
        elif days_since <= 7:
            return ActivityLevel.ACTIVE
        elif days_since <= 30:
            return ActivityLevel.STALE
        else:
            return ActivityLevel.DORMANT

    @property
    def peak_hour(self) -> Optional[int]:
        if not self.commits_by_hour:
            return None
        return max(self.commits_by_hour, key=self.commits_by_hour.get)

    @property
    def peak_day(self) -> Optional[str]:
        if not self.commits_by_day_of_week:
            return None
        return max(self.commits_by_day_of_week, key=self.commits_by_day_of_week.get)


@dataclass
class ExpertiseProfile:
    """Complete inferred expertise profile for a vessel/agent."""
    agent_name: str = "unknown"
    repos_scanned: list[str] = field(default_factory=list)
    total_commits: int = 0
    domain_scores: dict[str, DomainScore] = field(default_factory=dict)
    specialties: list[str] = field(default_factory=list)
    activity: ActivityPattern = field(default_factory=ActivityPattern)
    languages_used: dict[str, int] = field(default_factory=lambda: Counter())
    skill_tags: list[str] = field(default_factory=list)
    repos_maintained: dict[str, int] = field(default_factory=dict)
    profile_hash: str = ""
    inferred_at: str = ""

    def __post_init__(self):
        if not self.inferred_at:
            self.inferred_at = datetime.now(timezone.utc).isoformat()

    def compute_all_confidence(self) -> None:
        """Recompute confidence scores for all domains."""
        for ds in self.domain_scores.values():
            ds.compute_confidence()
        self._recompute_specialties()
        self._compute_skill_tags()
        self._compute_hash()

    def _recompute_specialties(self) -> None:
        """Detect specialties from high-confidence domains and keyword matches."""
        self.specialties = []
        for domain, score in self.domain_scores.items():
            if score.confidence >= 0.6:
                self.specialties.append(domain)

        # Check for specialty keywords in domain contexts
        # (would be populated from commit messages during scanning)

    def _compute_skill_tags(self) -> None:
        """Generate skill tags from profile data."""
        tags = set()
        for domain in self.domain_scores:
            tags.add(domain)

        # Map domain names to common skill tags
        domain_to_tag = {
            "python": "python",
            "rust": "rust",
            "typescript": "typescript",
            "javascript": "javascript",
            "go": "go",
            "c": "c",
            "cuda": "cuda",
            "zig": "zig",
            "testing": "testing",
            "architecture": "design",
            "devops": "devops",
            "bytecode_vm": "bytecode",
            "machine_learning": "ml",
            "web_development": "frontend",
            "database": "database",
            "security": "security",
            "networking": "networking",
            "evolution": "evolution",
            "fleet_coordination": "coordination",
        }
        for domain, tag in domain_to_tag.items():
            if domain in self.domain_scores and self.domain_scores[domain].confidence >= 0.3:
                tags.add(tag)

        self.skill_tags = sorted(tags)

    def _compute_hash(self) -> None:
        """Compute a content hash of the profile for cache invalidation."""
        def _serialize_domain(ds: DomainScore) -> dict:
            return {
                "confidence": ds.confidence,
                "commits": ds.commit_count,
                "files": ds.file_count,
                "lines": ds.lines_changed,
                "last_active": ds.last_active.isoformat() if ds.last_active else None,
            }
        content = json.dumps({
            "domains": {k: _serialize_domain(v) for k, v in self.domain_scores.items()},
            "total_commits": self.total_commits,
            "repos": self.repos_scanned,
        }, sort_keys=True)
        self.profile_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

    def top_domains(self, n: int = 5) -> list[tuple[str, float]]:
        """Return top N domains by confidence score."""
        scored = [(d, s.confidence) for d, s in self.domain_scores.items() if s.confidence > 0]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:n]

    def to_dict(self) -> dict[str, Any]:
        """Serialize profile to dictionary."""
        return {
            "agent_name": self.agent_name,
            "repos_scanned": self.repos_scanned,
            "total_commits": self.total_commits,
            "domains": {
                name: {
                    "confidence": ds.confidence,
                    "commit_count": ds.commit_count,
                    "file_count": ds.file_count,
                    "lines_changed": ds.lines_changed,
                    "last_active": ds.last_active.isoformat() if ds.last_active else None,
                    "specializations": ds.specializations,
                }
                for name, ds in self.domain_scores.items()
            },
            "specialties": self.specialties,
            "activity": {
                "total_commits": self.activity.total_commits,
                "activity_level": self.activity.activity_level.value,
                "peak_hour": self.activity.peak_hour,
                "peak_day": self.activity.peak_day,
                "first_commit": self.activity.first_commit.isoformat() if self.activity.first_commit else None,
                "last_commit": self.activity.last_commit.isoformat() if self.activity.last_commit else None,
                "avg_commit_size": round(self.activity.avg_commit_size, 1),
                "avg_files_per_commit": round(self.activity.avg_files_per_commit, 1),
            },
            "languages_used": dict(self.languages_used),
            "skill_tags": self.skill_tags,
            "repos_maintained": self.repos_maintained,
            "profile_hash": self.profile_hash,
            "inferred_at": self.inferred_at,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize profile to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        """Render profile as a markdown report."""
        lines = [
            f"# Expertise Profile: {self.agent_name}",
            "",
            f"**Profile Hash:** `{self.profile_hash}`",
            f"**Inferred At:** {self.inferred_at}",
            f"**Total Commits:** {self.total_commits}",
            f"**Repos Scanned:** {', '.join(self.repos_scanned) or 'none'}",
            "",
            "## Activity",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Activity Level | **{self.activity.activity_level.value}** |",
            f"| Peak Hour | {self.activity.peak_hour or 'N/A'}:00 UTC |",
            f"| Peak Day | {self.activity.peak_day or 'N/A'} |",
            f"| Avg Commit Size | {self.activity.avg_commit_size:.0f} lines |",
            f"| Avg Files/Commit | {self.activity.avg_files_per_commit:.1f} |",
            f"| First Commit | {self.activity.first_commit.strftime('%Y-%m-%d') if self.activity.first_commit else 'N/A'} |",
            f"| Last Commit | {self.activity.last_commit.strftime('%Y-%m-%d') if self.activity.last_commit else 'N/A'} |",
            "",
            "## Domain Expertise",
            "",
            "| Domain | Confidence | Commits | Files | Lines | Last Active |",
            "|--------|-----------|---------|-------|-------|-------------|",
        ]
        for domain, score in sorted(
            self.domain_scores.items(), key=lambda x: x[1].confidence, reverse=True
        ):
            if score.confidence > 0:
                la = score.last_active.strftime("%Y-%m-%d") if score.last_active else "N/A"
                lines.append(
                    f"| {domain} | {score.confidence:.2f} | {score.commit_count} "
                    f"| {score.file_count} | {score.lines_changed} | {la} |"
                )
        lines.append("")
        if self.specialties:
            lines.append("## Specialties")
            lines.append("")
            for s in self.specialties:
                lines.append(f"- **{s}**")
            lines.append("")
        if self.skill_tags:
            lines.append("## Skill Tags")
            lines.append("")
            lines.append("`" + "`, `".join(self.skill_tags) + "`")
            lines.append("")
        if self.languages_used:
            lines.append("## Languages Used")
            lines.append("")
            lines.append("| Language | Files |")
            lines.append("|----------|-------|")
            for lang, count in self.languages_used.most_common():
                lines.append(f"| {lang} | {count} |")
            lines.append("")
        if self.repos_maintained:
            lines.append("## Repos Maintained")
            lines.append("")
            lines.append("| Repo | Commits |")
            lines.append("|------|---------|")
            for repo, commits in sorted(
                self.repos_maintained.items(), key=lambda x: x[1], reverse=True
            ):
                lines.append(f"| {repo} | {commits} |")
            lines.append("")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Git History Scanner
# ---------------------------------------------------------------------------

class GitScanner:
    """Scans a git repository to extract commit history and file changes."""

    def __init__(self, repo_path: str, max_commits: int = 500, since_days: int = 90):
        """
        Args:
            repo_path: Absolute path to the git repository.
            max_commits: Maximum number of commits to process.
            since_days: Only look at commits from the last N days.
        """
        self.repo_path = Path(repo_path).resolve()
        self.max_commits = max_commits
        self.since_days = since_days
        self._validate_repo()

    def _validate_repo(self) -> None:
        """Verify the path is a valid git repository."""
        if not (self.repo_path / ".git").exists():
            raise ValueError(f"Not a git repository: {self.repo_path}")

    def _run_git(self, *args: str, timeout: int = 30) -> str:
        """Execute a git command and return stdout."""
        cmd = ["git", "-C", str(self.repo_path)] + list(args)
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, check=True,
            )
            return result.stdout
        except subprocess.TimeoutExpired:
            print(f"  [WARN] Git command timed out: {' '.join(args)}", file=sys.stderr)
            return ""
        except subprocess.CalledProcessError as e:
            print(f"  [WARN] Git command failed ({e.returncode}): {e.stderr.strip()}", file=sys.stderr)
            return ""

    def get_repo_name(self) -> str:
        """Extract repository name from the path."""
        return self.repo_path.name

    def scan_commits(self) -> list[CommitRecord]:
        """Scan git log and return parsed commit records."""
        since = (datetime.now(timezone.utc) - timedelta(days=self.since_days)).strftime("%Y-%m-%d")

        # Use a null-byte separator format for reliable parsing
        log_format = (
            "%H%x00%aN%x00%aE%x00%aI%x00%s%x00%b%x00"
        )
        raw = self._run_git(
            "log", f"--since={since}", f"-{self.max_commits}",
            "--format=" + log_format, "--numstat",
        )
        if not raw:
            return []

        return self._parse_log_output(raw)

    def _parse_log_output(self, raw: str) -> list[CommitRecord]:
        """Parse the raw git log output into CommitRecord objects."""
        commits: list[CommitRecord] = []
        entries = raw.split("\n\n")

        for entry in entries:
            if not entry.strip():
                continue

            parts = entry.split("\x00", 4)
            if len(parts) < 5:
                continue

            commit_hash, author, email, timestamp_str, rest = parts[:5]
            subject_body = rest.split("\x00", 1)[0]
            lines = subject_body.strip().split("\n")
            subject = lines[0] if lines else ""
            body = "\n".join(lines[1:]) if len(lines) > 1 else ""

            try:
                timestamp = datetime.fromisoformat(timestamp_str)
            except (ValueError, TypeError):
                timestamp = datetime.now(timezone.utc)

            record = CommitRecord(
                hash=commit_hash[:12],
                author=author.strip(),
                author_email=email.strip(),
                timestamp=timestamp,
                message=(subject + "\n" + body).strip(),
                message_subject=subject.strip(),
                repo_path=str(self.repo_path),
            )

            # Parse numstat lines (after the body)
            body_end = entry.find("\n\n")
            if body_end >= 0:
                stat_lines = entry[body_end:].strip().split("\n")
                for sl in stat_lines:
                    file_change = self._parse_numstat_line(sl)
                    if file_change:
                        record.files_changed.append(file_change)
                        record.total_additions += file_change.added_lines
                        record.total_deletions += file_change.removed_lines

            commits.append(record)

        return commits

    def _parse_numstat_line(self, line: str) -> Optional[FileChange]:
        """Parse a git numstat line: 'added\tdeleted\tfilename'."""
        parts = line.strip().split("\t")
        if len(parts) < 3:
            return None

        try:
            added = int(parts[0]) if parts[0] != "-" else 0
            removed = int(parts[1]) if parts[1] != "-" else 0
        except ValueError:
            return None

        filepath = parts[2]
        # Handle renames: '{old => new}/path'
        if "=>" in filepath:
            filepath = filepath.split("=>")[-1].strip().strip("}")

        ext = Path(filepath).suffix.lower()
        is_new = filepath.endswith("}")  # approximate detection

        return FileChange(
            path=filepath,
            extension=ext,
            added_lines=added,
            removed_lines=removed,
            is_new_file=is_new,
        )

    def get_file_tree(self) -> dict[str, list[str]]:
        """Get a snapshot of the repository file tree."""
        raw = self._run_git("ls-files")
        tree: dict[str, list[str]] = defaultdict(list)
        for line in raw.strip().split("\n"):
            if not line:
                continue
            ext = Path(line).suffix.lower()
            top_dir = line.split("/")[0] if "/" in line else "(root)"
            tree[top_dir].append(line)
        return dict(tree)


# ---------------------------------------------------------------------------
# Context Inferrer — builds ExpertiseProfile from git history
# ---------------------------------------------------------------------------

class ContextInferrer:
    """
    Main engine: scans repos, classifies commits, builds expertise profiles.
    Implements the Fleet Context Inference Protocol.
    """

    def __init__(self, agent_name: str = "unknown", max_commits_per_repo: int = 500):
        self.agent_name = agent_name
        self.max_commits_per_repo = max_commits_per_repo
        self._commit_buffer: list[CommitRecord] = []
        self._domain_accumulators: dict[str, dict[str, int]] = defaultdict(
            lambda: {"commits": 0, "files": 0, "lines": 0}
        )
        self._domain_last_active: dict[str, datetime] = {}
        self._languages: Counter = Counter()
        self._repos: dict[str, int] = {}
        self._specialty_hits: Counter = Counter()

    def scan_repo(self, repo_path: str, since_days: int = 90) -> list[CommitRecord]:
        """Scan a single repository and accumulate evidence."""
        print(f"  Scanning repo: {repo_path}")
        scanner = GitScanner(repo_path, max_commits=self.max_commits_per_repo, since_days=since_days)
        commits = scanner.scan_commits()
        repo_name = scanner.get_repo_name()
        self._repos[repo_name] = len(commits)

        for commit in commits:
            self._process_commit(commit, repo_name)

        print(f"    Found {len(commits)} commits in {repo_name}")
        return commits

    def scan_repos(self, repo_paths: list[str], since_days: int = 90) -> list[CommitRecord]:
        """Scan multiple repositories and accumulate evidence."""
        all_commits = []
        for repo_path in repo_paths:
            commits = self.scan_repo(repo_path, since_days=since_days)
            all_commits.extend(commits)
        return all_commits

    def _process_commit(self, commit: CommitRecord, repo_name: str) -> None:
        """Process a single commit: classify domains, update accumulators."""
        self._commit_buffer.append(commit)

        touched_domains = set()

        # Classify by files changed
        for fc in commit.files_changed:
            self._classify_file(fc, touched_domains)
            self._languages[fc.extension.lstrip(".")] += 1

        # Classify by commit message keywords
        msg_lower = commit.message.lower()
        for domain, rules in DOMAIN_TAXONOMY.items():
            for kw in rules["keywords"]:
                if kw.lower() in msg_lower:
                    touched_domains.add(domain)

        # Check specialty keywords
        for specialty, keywords in SPECIALTY_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in msg_lower:
                    self._specialty_hits[specialty] += 1
                    break

        # Update domain accumulators
        for domain in touched_domains:
            acc = self._domain_accumulators[domain]
            acc["commits"] += 1
            acc["files"] += len(commit.files_changed)
            acc["lines"] += commit.total_additions + commit.total_deletions

            # Update last active timestamp
            current = self._domain_last_active.get(domain)
            if current is None or commit.timestamp > current:
                self._domain_last_active[domain] = commit.timestamp

    def _classify_file(self, fc: FileChange, touched_domains: set[str]) -> None:
        """Classify a file change into domains."""
        for domain, rules in DOMAIN_TAXONOMY.items():
            if fc.extension in rules["extensions"]:
                touched_domains.add(domain)
            for d in rules["directories"]:
                if fc.path.startswith(d):
                    touched_domains.add(domain)

    def build_profile(self) -> ExpertiseProfile:
        """Build the final expertise profile from accumulated evidence."""
        profile = ExpertiseProfile(
            agent_name=self.agent_name,
            repos_scanned=list(self._repos.keys()),
            total_commits=len(self._commit_buffer),
            repos_maintained=dict(self._repos),
            languages_used=dict(self._languages.most_common()),
        )

        # Build domain scores
        for domain, acc in self._domain_accumulators.items():
            ds = DomainScore(
                domain=domain,
                commit_count=acc["commits"],
                file_count=acc["files"],
                lines_changed=acc["lines"],
                last_active=self._domain_last_active.get(domain),
            )
            ds.compute_confidence()

            # Attach relevant specialties
            for specialty, count in self._specialty_hits.most_common():
                if self._specialty_domain_match(specialty, domain):
                    if count >= 2:  # Require at least 2 mentions
                        ds.specializations.append(specialty)

            profile.domain_scores[domain] = ds

        # Build activity pattern
        if self._commit_buffer:
            commits_sorted = sorted(self._commit_buffer, key=lambda c: c.timestamp)
            profile.activity.total_commits = len(self._commit_buffer)
            profile.activity.first_commit = commits_sorted[0].timestamp
            profile.activity.last_commit = commits_sorted[-1].timestamp
            profile.activity.avg_commit_size = (
                sum(c.total_additions + c.total_deletions for c in self._commit_buffer)
                / len(self._commit_buffer)
            )
            profile.activity.avg_files_per_commit = (
                sum(len(c.files_changed) for c in self._commit_buffer)
                / len(self._commit_buffer)
            )

            day_map = {
                0: "mon", 1: "tue", 2: "wed", 3: "thu",
                4: "fri", 5: "sat", 6: "sun",
            }
            hour_counts: dict[int, int] = defaultdict(int)
            for c in self._commit_buffer:
                day_name = day_map.get(c.timestamp.weekday(), "mon")
                profile.activity.commits_by_day_of_week[day_name] += 1
                hour_counts[c.timestamp.hour] += 1
            profile.activity.commits_by_hour = dict(hour_counts)

            # Compute active streak
            profile.activity.active_streak_days = self._compute_active_streak(commits_sorted)
            profile.activity.longest_streak_days = self._compute_longest_streak(commits_sorted)

        # Finalize
        profile.compute_all_confidence()
        return profile

    def _specialty_domain_match(self, specialty: str, domain: str) -> bool:
        """Check if a specialty is related to a domain."""
        mapping = {
            "confidence_propagation": ["rust", "bytecode_vm", "security", "trust_scoring"],
            "isa_design": ["rust", "c", "bytecode_vm", "architecture"],
            "a2a_protocol": ["networking", "fleet_coordination", "bytecode_vm"],
            "memory_management": ["rust", "c", "bytecode_vm", "python"],
            "trust_scoring": ["security", "rust", "bytecode_vm"],
            "debugging": ["python", "rust", "testing"],
            "onboarding": ["architecture", "web_development", "devops"],
            "dsl_design": ["python", "rust", "typescript"],
            "knowledge_federation": ["python", "database", "architecture"],
            "sandbox_runtime": ["rust", "c", "devops", "security"],
        }
        related = mapping.get(specialty, [])
        return domain in related

    def _compute_active_streak(self, commits: list[CommitRecord]) -> int:
        """Compute the current active streak in days."""
        if not commits:
            return 0
        today = datetime.now(timezone.utc).date()
        days_seen: set[datetime.date] = set()
        for c in commits:
            days_seen.add(c.timestamp.date())

        streak = 0
        current = today
        while current in days_seen:
            streak += 1
            current -= timedelta(days=1)
        return streak

    def _compute_longest_streak(self, commits: list[CommitRecord]) -> int:
        """Compute the longest consecutive-day commit streak."""
        if not commits:
            return 0
        days_seen = sorted(set(c.timestamp.date() for c in commits))
        if not days_seen:
            return 0

        longest = 1
        current_streak = 1
        for i in range(1, len(days_seen)):
            if (days_seen[i] - days_seen[i - 1]).days == 1:
                current_streak += 1
                longest = max(longest, current_streak)
            else:
                current_streak = 1
        return longest


# ---------------------------------------------------------------------------
# Report Generator
# ---------------------------------------------------------------------------

class ReportGenerator:
    """Generates JSON and markdown reports from expertise profiles."""

    @staticmethod
    def save_json(profile: ExpertiseProfile, output_path: str) -> None:
        """Save profile as a JSON file."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(profile.to_json())
        print(f"  JSON report saved: {output_path}")

    @staticmethod
    def save_markdown(profile: ExpertiseProfile, output_path: str) -> None:
        """Save profile as a markdown report."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(profile.to_markdown())
        print(f"  Markdown report saved: {output_path}")

    @staticmethod
    def save_combined_report(
        profiles: list[ExpertiseProfile],
        json_path: str,
        markdown_path: str,
    ) -> None:
        """Save a fleet-wide combined report of all profiles."""
        # JSON
        combined_json = {
            "fleet_profiles": [p.to_dict() for p in profiles],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_agents": len(profiles),
        }
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(combined_json, f, indent=2)
        print(f"  Fleet JSON report saved: {json_path}")

        # Markdown
        md_lines = [
            "# Fleet Context Inference Report",
            "",
            f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
            f"**Total Agents Profiled:** {len(profiles)}",
            "",
        ]

        for profile in profiles:
            md_lines.append(f"## {profile.agent_name}")
            md_lines.append("")
            md_lines.append(f"**Activity:** {profile.activity.activity_level.value}")
            md_lines.append(f"**Commits:** {profile.total_commits}")
            top = profile.top_domains(3)
            md_lines.append(f"**Top Domains:** {', '.join(f'{d} ({c:.2f})' for d, c in top)}")
            if profile.skill_tags:
                md_lines.append(f"**Skills:** `{'`, `'.join(profile.skill_tags)}`")
            md_lines.append("")

        Path(markdown_path).parent.mkdir(parents=True, exist_ok=True)
        with open(markdown_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))
        print(f"  Fleet Markdown report saved: {markdown_path}")


# ---------------------------------------------------------------------------
# CLI interface
# ---------------------------------------------------------------------------

def main():
    """Command-line interface for the context inference protocol."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="infer_context",
        description="Fleet Context Inference Protocol — scan repos to infer agent expertise.",
    )
    parser.add_argument(
        "repos", nargs="+", help="Paths to git repositories to scan.",
    )
    parser.add_argument(
        "--agent-name", default=None, help="Agent name (default: inferred from repo).",
    )
    parser.add_argument(
        "--output-dir", default=".", help="Directory to write reports.",
    )
    parser.add_argument(
        "--format", choices=["json", "markdown", "both"], default="both",
        help="Output format (default: both).",
    )
    parser.add_argument(
        "--since-days", type=int, default=90,
        help="Only scan commits from the last N days (default: 90).",
    )
    parser.add_argument(
        "--max-commits", type=int, default=500,
        help="Max commits per repo (default: 500).",
    )

    args = parser.parse_args()

    # Determine agent name
    agent_name = args.agent_name
    if not agent_name:
        if len(args.repos) == 1:
            agent_name = Path(args.repos[0]).name.replace("-vessel", "").replace("-", " ").title()
        else:
            agent_name = "FleetAgent"

    print(f"🔍 Fleet Context Inference Protocol")
    print(f"   Agent: {agent_name}")
    print(f"   Repos: {len(args.repos)}")
    print(f"   Since: {args.since_days} days ago")
    print()

    # Run inference
    inferrer = ContextInferrer(agent_name=agent_name, max_commits_per_repo=args.max_commits)
    inferrer.scan_repos(args.repos, since_days=args.since_days)
    profile = inferrer.build_profile()

    # Output reports
    fmt = args.format
    base = os.path.join(args.output_dir, f"profile-{agent_name.lower().replace(' ', '-')}")

    if fmt in ("json", "both"):
        ReportGenerator.save_json(profile, f"{base}.json")
    if fmt in ("markdown", "both"):
        ReportGenerator.save_markdown(profile, f"{base}.md")

    # Print summary
    print()
    print("─── Profile Summary ───")
    print(f"  Agent:           {profile.agent_name}")
    print(f"  Total Commits:   {profile.total_commits}")
    print(f"  Activity Level:  {profile.activity.activity_level.value}")
    print(f"  Top Domains:     {profile.top_domains(3)}")
    print(f"  Skill Tags:      {profile.skill_tags}")
    print(f"  Profile Hash:    {profile.profile_hash}")
    print()


if __name__ == "__main__":
    main()
