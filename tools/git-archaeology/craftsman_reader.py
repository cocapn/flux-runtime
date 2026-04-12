#!/usr/bin/env python3
"""
Git Archaeology: Craftsman's Reading Generator
================================================

Analyzes any repository's commit history and produces insights about where
attention was paid, what was hard, and what was fast.

Built on the Witness Marks protocol established by Oracle1 + JetsonClaw1.
"The repo IS the agent. Git IS the nervous system. Witness marks are how
the system remembers what it learned."

Usage:
    python craftsman_reader.py <repo_path> [options]
    python craftsman_reader.py <repo_path> --cross-repo <repo2> <repo3>
    python craftsman_reader.py <repo_path> --output report.md
    python craftsman_reader.py <repo_path> --since "2025-01-01" --until "2026-01-01"

Author: Fleet Agent — FLUX bytecode VM ecosystem
Protocol: WITNESS-MARKS-2026-04-12
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import textwrap
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONVENTIONAL_COMMIT_TYPES = [
    "feat", "fix", "docs", "style", "refactor", "perf", "test",
    "ci", "build", "chore", "revert",
]

CONVENTIONAL_COMMIT_PATTERN = re.compile(
    r"^(?P<type>" + "|".join(CONVENTIONAL_COMMIT_TYPES) + r")"
    r"(?:\((?P<scope>[^)]+)\))?"
    r"(?:!)?"
    r":\s*(?P<description>.+)$"
)

BODY_THRESHOLD = 50  # characters — commit body long enough to be a witness mark
MEGA_COMMIT_FILE_THRESHOLD = 20  # files changed — mega-commit flag
WITNESS_MARK_BODY_THRESHOLD = 50  # chars in body to count as a witness mark
ANTI_MARK_PATTERNS = [
    re.compile(r"^(update|updates?|stuff|things?|wip|fix|changes?|misc)$", re.IGNORECASE),
    re.compile(r"^(fix|add|update)\s+(typo|stuff|things?|comments?)$", re.IGNORECASE),
]

# Quality scoring weights
W_SCORE_TYPE_CONVENTIONAL = 15
W_SCORE_SCOPE_PRESENT = 10
W_SCORE_BODY_EXPLAINS_WHY = 20
W_SCORE_REFERENCES_ISSUE = 15
W_SCORE_ATOMIC_COMMITS = 15
W_SCORE_MESSAGE_LENGTH = 10
W_SCORE_NOT_MEGA = 15

# Heat map thresholds
HOT_SPOT_THRESHOLD_FILES = 5  # commits touching a file to be a hot spot
ATTENTION_DENSITY_WINDOW = 30  # days for rolling density calculation

# Output section dividers
SECTION_DIVIDER = "\n---\n"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class CommitType(str, Enum):
    FEAT = "feat"
    FIX = "fix"
    DOCS = "docs"
    STYLE = "style"
    REFACTOR = "refactor"
    PERF = "perf"
    TEST = "test"
    CI = "ci"
    BUILD = "build"
    CHORE = "chore"
    REVERT = "revert"
    OTHER = "other"


@dataclass
class ConventionalCommit:
    """Parsed conventional commit."""
    type: CommitType
    scope: Optional[str]
    description: str
    body: str
    raw_message: str


@dataclass
class FileChange:
    """A file touched in a commit."""
    path: str
    additions: int
    deletions: int


@dataclass
class CommitRecord:
    """A single commit with all parsed metadata."""
    hash: str
    short_hash: str
    author: str
    author_email: str
    date: datetime.datetime
    raw_message: str
    parsed: Optional[ConventionalCommit] = None
    files_changed: List[FileChange] = field(default_factory=list)
    num_files: int = 0
    total_additions: int = 0
    total_deletions: int = 0
    is_conventional: bool = False
    is_witness_mark: bool = False
    is_anti_mark: bool = False
    is_mega_commit: bool = False
    is_merge: bool = False
    is_force_push: bool = False
    references_issue: bool = False
    has_abandon_marker: bool = False
    craftsman_score: float = 0.0
    # Anti-mark reasons for reporting
    anti_mark_reasons: List[str] = field(default_factory=list)
    witness_mark_reasons: List[str] = field(default_factory=list)


@dataclass
class BranchInfo:
    """Information about a branch."""
    name: str
    head_hash: str
    author: str
    date: datetime.datetime
    commit_count: int = 0
    is_merged: bool = False
    is_orphan: bool = False
    age_days: float = 0.0
    divergence_count: int = 0


@dataclass
class HotSpot:
    """A file that receives disproportionate attention."""
    path: str
    commit_count: int
    total_additions: int
    total_deletions: int
    unique_authors: int
    attention_density: float  # avg commit msg length per touch


@dataclass
class VelocitySample:
    """A time-bucketed velocity measurement."""
    period_label: str
    commit_count: int
    files_touched: int
    lines_added: int
    lines_removed: int
    unique_authors: int
    avg_message_length: float
    conventional_ratio: float
    witness_mark_ratio: float


@dataclass
class RepoAnalysis:
    """Complete analysis result for one repository."""
    repo_path: str
    repo_name: str
    commits: List[CommitRecord] = field(default_factory=list)
    branches: List[BranchInfo] = field(default_factory=list)
    hot_spots: List[HotSpot] = field(default_factory=list)
    velocity_samples: List[VelocitySample] = field(default_factory=list)
    overall_craftsman_score: float = 0.0
    total_authors: int = 0
    date_range: Tuple[datetime.datetime, datetime.datetime] = (
        datetime.datetime.min, datetime.datetime.max
    )


# ---------------------------------------------------------------------------
# Git command helpers
# ---------------------------------------------------------------------------

class GitCommandError(Exception):
    """Raised when a git command fails."""
    pass


def git(repo_path: str, *args: str, check: bool = True) -> str:
    """Run a git command in the given repo and return stdout."""
    cmd = ["git", "-C", repo_path] + list(args)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except FileNotFoundError:
        raise GitCommandError("git is not installed or not on PATH")
    if check and result.returncode != 0:
        raise GitCommandError(
            f"git command failed: {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def git_log_format(repo_path: str, since: Optional[str] = None,
                   until: Optional[str] = None, branch: str = "HEAD") -> str:
    """Get commit log in a structured format."""
    args = [
        "log", branch,
        "--format=%H|%h|%an|%ae|%aI|%s%n%b%n---END_COMMIT---",
        "--no-merges",
    ]
    if since:
        args += ["--since", since]
    if until:
        args += ["--until", until]
    return git(repo_path, *args)


def git_log_merges(repo_path: str, since: Optional[str] = None,
                   until: Optional[str] = None) -> str:
    """Get merge commits."""
    args = [
        "log",
        "--merges",
        "--format=%H|%h|%an|%ae|%aI|%s%n%b%n---END_COMMIT---",
    ]
    if since:
        args += ["--since", since]
    if until:
        args += ["--until", until]
    return git(repo_path, *args)


def git_numstat(repo_path: str, commit_hash: str) -> str:
    """Get numstat (file changes with +/- lines) for a commit."""
    return git(repo_path, "show", "--numstat", "--format=", commit_hash)


def git_branches(repo_path: str) -> str:
    """List all branches with details."""
    return git(
        repo_path,
        "for-each-ref",
        "--sort=-committerdate",
        "--format=%(refname:short)|%(objectname:short)|%(authorname)|%(committerdate:iso)",
        "refs/heads/",
    )


def git_is_ancestor(repo_path: str, ancestor: str, descendant: str) -> bool:
    """Check if ancestor is an ancestor of descendant."""
    result = subprocess.run(
        ["git", "-C", repo_path, "merge-base", "--is-ancestor", ancestor, descendant],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode == 0


def git_rev_list_count(repo_path: str, ref1: str, ref2: str) -> int:
    """Count commits in ref1 not in ref2 (divergence)."""
    try:
        output = git(repo_path, "rev-list", "--count", f"{ref1}...{ref2}")
        return int(output.strip()) if output.strip() else 0
    except GitCommandError:
        return 0


# ---------------------------------------------------------------------------
# Parsing utilities
# ---------------------------------------------------------------------------

def parse_conventional_commit(message: str) -> Optional[ConventionalCommit]:
    """
    Parse a commit message into its conventional commit components.

    Returns None if the message doesn't follow the conventional commit format.
    """
    # First line is the subject
    lines = message.strip().split("\n")
    subject = lines[0].strip()

    match = CONVENTIONAL_COMMIT_PATTERN.match(subject)
    if not match:
        return None

    commit_type = match.group("type")
    scope = match.group("scope")
    description = match.group("description").strip()

    # Body is everything after the first blank line
    body_lines = []
    in_body = False
    for line in lines[1:]:
        if not in_body:
            if line.strip() == "":
                in_body = True
            continue
        # Stop at trailing metadata (Signed-off-by, Co-authored-by, etc.)
        if re.match(r"^(Signed-off-by|Co-authored-by|Acked-by|Reviewed-by| "
                     r"Relates-to|Refs|Fixes|Closes|Resolves)[: ]", line.strip()):
            break
        body_lines.append(line)

    body = "\n".join(body_lines).strip()

    try:
        type_enum = CommitType(commit_type)
    except ValueError:
        type_enum = CommitType.OTHER

    return ConventionalCommit(
        type=type_enum,
        scope=scope,
        description=description,
        body=body,
        raw_message=message,
    )


def parse_numstat(numstat_output: str) -> List[FileChange]:
    """Parse git numstat output into FileChange objects."""
    changes = []
    for line in numstat_output.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        additions = int(parts[0]) if parts[0] != "-" else 0
        deletions = int(parts[1]) if parts[1] != "-" else 0
        path = parts[2]
        # Handle renames: old_path => new_path
        if " => " in path:
            path = path.split(" => ")[1]
        changes.append(FileChange(path=path, additions=additions, deletions=deletions))
    return changes


def parse_commit_log(log_output: str) -> List[dict]:
    """Parse the structured git log output into raw commit dicts."""
    commits = []
    current = None

    for line in log_output.split("\n"):
        if line == "---END_COMMIT---":
            if current:
                commits.append(current)
            current = None
            continue

        if current is None and "|" in line:
            parts = line.split("|", 5)
            if len(parts) == 6:
                current = {
                    "hash": parts[0],
                    "short_hash": parts[1],
                    "author": parts[2],
                    "author_email": parts[3],
                    "date": parts[4],
                    "subject": parts[5],
                    "body": "",
                }
            continue

        if current is not None:
            if current["body"]:
                current["body"] += "\n" + line
            else:
                current["body"] = line

    return commits


def parse_branch_output(branch_output: str) -> List[dict]:
    """Parse for-each-ref branch output."""
    branches = []
    for line in branch_output.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("|", 3)
        if len(parts) == 4:
            branches.append({
                "name": parts[0],
                "head_hash": parts[1],
                "author": parts[2],
                "date": parts[3],
            })
    return branches


# ---------------------------------------------------------------------------
# Core analysis: Commit Analysis
# ---------------------------------------------------------------------------

def analyze_commit(raw: dict, repo_path: str) -> CommitRecord:
    """
    Build a fully-analyzed CommitRecord from raw git log data.
    """
    record = CommitRecord(
        hash=raw["hash"],
        short_hash=raw["short_hash"],
        author=raw["author"],
        author_email=raw["author_email"],
        date=datetime.datetime.fromisoformat(raw["date"]),
        raw_message=raw["subject"] + "\n" + raw["body"] if raw["body"] else raw["subject"],
    )

    # Parse conventional commit
    full_message = raw["subject"]
    if raw["body"]:
        full_message += "\n" + raw["body"]

    parsed = parse_conventional_commit(full_message)
    record.parsed = parsed
    record.is_conventional = parsed is not None

    # Get file-level stats
    try:
        numstat = git_numstat(repo_path, raw["hash"])
        record.files_changed = parse_numstat(numstat)
        record.num_files = len(record.files_changed)
        record.total_additions = sum(f.additions for f in record.files_changed)
        record.total_deletions = sum(f.deletions for f in record.files_changed)
    except GitCommandError:
        pass

    # --- Detect witness marks ---
    _detect_witness_marks(record, raw)

    # --- Detect anti-marks ---
    _detect_anti_marks(record, raw)

    # --- Score craftsman quality ---
    record.craftsman_score = _score_commit(record)

    return record


def _detect_witness_marks(record: CommitRecord, raw: dict) -> None:
    """
    Identify commits that serve as witness marks — detailed explanations
    of hard-won knowledge.
    """
    record.witness_mark_reasons = []

    # Long body explaining context
    body_len = len(raw.get("body", ""))
    if body_len > WITNESS_MARK_BODY_THRESHOLD:
        record.is_witness_mark = True
        record.witness_mark_reasons.append(
            f"detailed body ({body_len} chars)"
        )

    # References an issue, PR, or bottle
    full_msg = record.raw_message.lower()
    issue_patterns = [
        r"(?:fixes|closes|resolves|relates-to|refs?)\s+#\d+",
        r"#\d+",
        r"(?:issue|pr|pull request)\s+\d+",
        r"from-fleet/|for-fleet/|for-oracle",
        r"bottle",
    ]
    for pat in issue_patterns:
        if re.search(pat, full_msg):
            record.references_issue = True
            if not record.is_witness_mark:
                record.is_witness_mark = True
                record.witness_mark_reasons.append("references external context")
            break

    # Merge conflict resolution markers (detailed body mentioning conflicts)
    if "conflict" in full_msg and body_len > 30:
        if not record.is_witness_mark:
            record.is_witness_mark = True
            record.witness_mark_reasons.append("documents merge conflict resolution")

    # Explains WHY not just WHAT — body contains causal language
    causal_patterns = [
        r"because", r"since\b", r"reason\b", r"to prevent", r"to avoid",
        r"without this", r"this would", r"otherwise", r"needed to",
        r"the problem", r"root cause", r"discovered", r"turns out",
    ]
    if body_len > 20:
        for pat in causal_patterns:
            if re.search(pat, full_msg):
                if not record.is_witness_mark:
                    record.is_witness_mark = True
                    record.witness_mark_reasons.append("explains reasoning (WHY)")
                break

    # Abandon marker — explicitly marks a dead experiment
    abandon_patterns = [r"ABANDON", r"DEAD END", r"WONTFIX", r"REVERTED", r"rolled back"]
    for pat in abandon_patterns:
        if re.search(pat, full_msg):
            record.has_abandon_marker = True
            if not record.is_witness_mark:
                record.is_witness_mark = True
                record.witness_mark_reasons.append("marks abandoned experiment")
            break


def _detect_anti_marks(record: CommitRecord, raw: dict) -> None:
    """
    Identify anti-marks — commits that obscure rather than illuminate.
    """
    record.anti_mark_reasons = []

    subject = raw["subject"].strip()

    # Mega-commit: too many files
    if record.num_files > MEGA_COMMIT_FILE_THRESHOLD:
        record.is_mega_commit = True
        record.anti_mark_reasons.append(
            f"mega-commit: {record.num_files} files changed"
        )

    # Vague / misleading message
    for pat in ANTI_MARK_PATTERNS:
        if pat.match(subject):
            record.is_anti_mark = True
            record.anti_mark_reasons.append(f"vague message: '{subject}'")
            break

    # Long diff but short message — the message lies by omission
    total_lines = record.total_additions + record.total_deletions
    if total_lines > 100 and len(subject) < 20 and not record.is_conventional:
        record.is_anti_mark = True
        record.anti_mark_reasons.append(
            f"large change ({total_lines} lines) with terse message"
        )

    # "fix typo" that changes business logic
    is_typo_fix = re.search(r"typo\b", subject, re.IGNORECASE)
    if is_typo_fix and total_lines > 20:
        record.is_anti_mark = True
        record.anti_mark_reasons.append(
            "'fix typo' but changes {total_lines} lines — possibly misleading"
        )

    # Force-push detection: reset/rewrite indicators in message
    force_patterns = [r"force.?push", r"rebase", r"squash", r"rewrite"]
    for pat in force_patterns:
        if re.search(pat, record.raw_message.lower()):
            record.is_force_push = True
            if len(raw.get("body", "")) < 20:
                record.is_anti_mark = True
                record.anti_mark_reasons.append(
                    f"force-push/rewrite without documentation"
                )
            break


def _score_commit(record: CommitRecord) -> float:
    """
    Score a commit on craftsman quality (0-100).

    Based on the Craftsman's Git Protocol rules:
    Rule 1: Every commit tells a story (conventional format)
    Rule 2: Hard-won knowledge gets witness marks (body explains WHY)
    Rule 3: Experiments leave traces (abandon markers)
    Rule 4: README is the map (not directly scorable per commit)
    Rule 5: Tests are witness marks
    """
    score = 0.0

    # Conventional commit type
    if record.is_conventional:
        score += W_SCORE_TYPE_CONVENTIONAL
    else:
        # Partial credit for any structured first line
        if len(record.raw_message.split("\n")[0]) > 20:
            score += 5

    # Scope present
    if record.parsed and record.parsed.scope:
        score += W_SCORE_SCOPE_PRESENT

    # Body explains WHY (not just WHAT)
    if record.is_witness_mark:
        score += W_SCORE_BODY_EXPLAINS_WHY
    elif len(record.raw_message) > 100:
        score += 5  # partial credit for length

    # References issue or external context
    if record.references_issue:
        score += W_SCORE_REFERENCES_ISSUE

    # Atomic — few files, clear scope
    if record.num_files <= 3 and record.num_files > 0:
        score += W_SCORE_ATOMIC_COMMITS
    elif record.num_files <= 8:
        score += 8  # moderate credit
    elif record.num_files <= MEGA_COMMIT_FILE_THRESHOLD:
        score += 3  # minimal credit

    # Message length / quality
    subject_len = len(record.raw_message.split("\n")[0])
    if subject_len >= 40:
        score += W_SCORE_MESSAGE_LENGTH
    elif subject_len >= 20:
        score += 5

    # Not a mega-commit
    if not record.is_mega_commit:
        score += W_SCORE_NOT_MEGA

    # Penalty for anti-marks
    if record.is_anti_mark:
        score -= 15
    if record.is_mega_commit:
        score -= 10

    # Bonus for test commits
    if record.parsed and record.parsed.type == CommitType.TEST:
        score += 5

    # Bonus for abandon markers (Rule 3)
    if record.has_abandon_marker:
        score += 10

    return max(0.0, min(100.0, score))


# ---------------------------------------------------------------------------
# Core analysis: Branch lifecycle
# ---------------------------------------------------------------------------

def analyze_branches(repo_path: str) -> List[BranchInfo]:
    """
    Analyze all branches for lifecycle patterns — merged, orphaned, abandoned.
    """
    try:
        output = git_branches(repo_path)
    except GitCommandError:
        return []

    raw_branches = parse_branch_output(output)
    branches = []
    main_branch = "main"
    has_main = False

    # Detect main branch
    for rb in raw_branches:
        if rb["name"] in ("main", "master"):
            main_branch = rb["name"]
            has_main = True
            break

    for rb in raw_branches:
        if rb["name"] == main_branch:
            continue

        try:
            commit_date = datetime.datetime.fromisoformat(rb["date"])
        except (ValueError, TypeError):
            commit_date = datetime.datetime.now()

        age = (datetime.datetime.now() - commit_date).total_seconds() / 86400

        info = BranchInfo(
            name=rb["name"],
            head_hash=rb["head_hash"],
            author=rb["author"],
            date=commit_date,
            age_days=age,
        )

        # Check if merged into main
        if has_main:
            info.is_merged = git_is_ancestor(repo_path, rb["head_hash"], main_branch)

        # Count commits unique to this branch
        if has_main:
            info.divergence_count = git_rev_list_count(repo_path, rb["name"], main_branch)
            info.commit_count = info.divergence_count

        # Orphan detection: not merged, old, and has commits
        if not info.is_merged and age > 30 and info.commit_count > 0:
            info.is_orphan = True

        branches.append(info)

    return branches


# ---------------------------------------------------------------------------
# Core analysis: Hot spots & attention density
# ---------------------------------------------------------------------------

def compute_hot_spots(commits: List[CommitRecord]) -> List[HotSpot]:
    """
    Identify files that receive the most attention — "hot spots".

    These indicate complex, frequently-changed areas where the hard
    thinking likely happened.
    """
    file_data: Dict[str, dict] = defaultdict(lambda: {
        "commit_count": 0,
        "total_additions": 0,
        "total_deletions": 0,
        "authors": set(),
        "message_lengths": [],
    })

    for commit in commits:
        for fc in commit.files_changed:
            fd = file_data[fc.path]
            fd["commit_count"] += 1
            fd["total_additions"] += fc.additions
            fd["total_deletions"] += fc.deletions
            fd["authors"].add(commit.author)
            fd["message_lengths"].append(len(commit.raw_message))

    spots = []
    for path, data in file_data.items():
        msg_lens = data["message_lengths"]
        avg_msg_len = sum(msg_lens) / len(msg_lens) if msg_lens else 0.0

        spots.append(HotSpot(
            path=path,
            commit_count=data["commit_count"],
            total_additions=data["total_additions"],
            total_deletions=data["total_deletions"],
            unique_authors=len(data["authors"]),
            attention_density=avg_msg_len,
        ))

    # Sort by commit count descending
    spots.sort(key=lambda s: s.commit_count, reverse=True)
    return spots


def compute_velocity(
    commits: List[CommitRecord],
    bucket: str = "week",
) -> List[VelocitySample]:
    """
    Compute velocity metrics bucketed by time period.

    Buckets: 'day', 'week', 'month'
    """
    if not commits:
        return []

    # Determine bucket format
    if bucket == "day":
        fmt = "%Y-%m-%d"
    elif bucket == "week":
        fmt = "%Y-W%W"
    else:
        fmt = "%Y-%m"

    buckets: Dict[str, dict] = defaultdict(lambda: {
        "commit_count": 0,
        "files": set(),
        "lines_added": 0,
        "lines_removed": 0,
        "authors": set(),
        "message_lengths": [],
        "conventional_count": 0,
        "witness_mark_count": 0,
    })

    for commit in commits:
        key = commit.date.strftime(fmt)
        b = buckets[key]
        b["commit_count"] += 1
        b["lines_added"] += commit.total_additions
        b["lines_removed"] += commit.total_deletions
        b["authors"].add(commit.author)
        b["message_lengths"].append(len(commit.raw_message))
        if commit.is_conventional:
            b["conventional_count"] += 1
        if commit.is_witness_mark:
            b["witness_mark_count"] += 1
        for fc in commit.files_changed:
            b["files"].add(fc.path)

    samples = []
    for label, data in sorted(buckets.items()):
        n = data["commit_count"]
        msg_lens = data["message_lengths"]
        samples.append(VelocitySample(
            period_label=label,
            commit_count=n,
            files_touched=len(data["files"]),
            lines_added=data["lines_added"],
            lines_removed=data["lines_removed"],
            unique_authors=len(data["authors"]),
            avg_message_length=sum(msg_lens) / len(msg_lens) if msg_lens else 0.0,
            conventional_ratio=data["conventional_count"] / n if n else 0.0,
            witness_mark_ratio=data["witness_mark_count"] / n if n else 0.0,
        ))

    return samples


# ---------------------------------------------------------------------------
# Core analysis: Difficulty detection
# ---------------------------------------------------------------------------

def detect_difficulty_signals(commits: List[CommitRecord]) -> List[dict]:
    """
    Identify commits that represent hard work — long bodies, bug fixes,
    merge conflict resolutions, and other signals of difficulty.
    """
    signals = []

    for commit in commits:
        reasons = []

        # Long body (> 200 chars of explanation)
        body = commit.raw_message.split("\n", 1)[1] if "\n" in commit.raw_message else ""
        if len(body) > 200:
            reasons.append(f"long explanation ({len(body)} chars)")

        # Bug fix referencing issues
        if commit.parsed and commit.parsed.type == CommitType.FIX and commit.references_issue:
            reasons.append("bug fix with external reference — likely complex")

        # High churn file (many changes in one commit)
        if commit.total_additions + commit.total_deletions > 200:
            reasons.append(
                f"high churn ({commit.total_additions}+/{commit.total_deletions}-)"
            )

        # Multi-author file changes (suggests collaboration/friction)
        author_files: Dict[str, set] = defaultdict(set)
        for fc in commit.files_changed:
            author_files[commit.author].add(fc.path)
        # We need repo-wide data for true multi-author detection,
        # so we check commit metadata here

        # Merge conflict body mentions
        if "conflict" in commit.raw_message.lower():
            reasons.append("documents merge conflict resolution")

        # Performance commits (usually indicate hard optimization work)
        if commit.parsed and commit.parsed.type == CommitType.PERF:
            reasons.append("performance optimization — inherently hard")

        # Abandon markers (tried and failed)
        if commit.has_abandon_marker:
            reasons.append("abandoned experiment — dead end discovered")

        if reasons:
            signals.append({
                "commit": commit.short_hash,
                "subject": commit.raw_message.split("\n")[0],
                "author": commit.author,
                "date": commit.date.isoformat(),
                "difficulty_reasons": reasons,
                "score": len(reasons),
            })

    signals.sort(key=lambda s: s["score"], reverse=True)
    return signals


def detect_abandoned_experiments(
    commits: List[CommitRecord],
    branches: List[BranchInfo],
) -> List[dict]:
    """
    Find abandoned experiments — branches that diverge and never merge.
    Also looks for ABANDON markers in commit messages.
    """
    abandoned = []

    # Orphan branches
    for branch in branches:
        if branch.is_orphan:
            abandoned.append({
                "type": "orphan_branch",
                "name": branch.name,
                "author": branch.author,
                "age_days": round(branch.age_days, 1),
                "divergent_commits": branch.commit_count,
                "detail": (
                    f"Branch '{branch.name}' has {branch.commit_count} commits "
                    f"never merged into main ({branch.age_days:.0f} days old)"
                ),
            })

    # ABANDON markers in commit messages
    for commit in commits:
        if commit.has_abandon_marker:
            subject = commit.raw_message.split("\n")[0]
            body = commit.raw_message.split("\n", 1)[1] if "\n" in commit.raw_message else ""
            abandoned.append({
                "type": "abandon_marker",
                "commit": commit.short_hash,
                "subject": subject,
                "body_preview": body[:200],
                "author": commit.author,
                "date": commit.date.isoformat(),
                "detail": f"Commit {commit.short_hash} marks a dead end",
            })

    return abandoned


# ---------------------------------------------------------------------------
# Core analysis: Cross-repo
# ---------------------------------------------------------------------------

def cross_repo_analysis(
    analyses: List[RepoAnalysis],
) -> dict:
    """
    Given multiple repo analyses, produce cross-repo insights:
    - Which repos get more attention
    - Communication patterns (shared authors)
    - Comparative quality scores
    """
    if len(analyses) < 2:
        return {"note": "Need at least 2 repos for cross-repo analysis"}

    # Shared authors
    all_authors: Dict[str, List[str]] = defaultdict(list)
    repo_scores = []
    repo_commits = []

    for analysis in analyses:
        repo_scores.append({
            "repo": analysis.repo_name,
            "craftsman_score": round(analysis.overall_craftsman_score, 1),
        })
        repo_commits.append({
            "repo": analysis.repo_name,
            "total_commits": len(analysis.commits),
            "total_authors": analysis.total_authors,
        })
        authors = set(c.author for c in analysis.commits)
        for author in authors:
            all_authors[author].append(analysis.repo_name)

    # Find shared authors (cross-repo communication)
    shared_authors = {
        author: repos
        for author, repos in all_authors.items()
        if len(repos) > 1
    }

    # Comparative attention
    attention_ranking = sorted(
        repo_commits,
        key=lambda r: r["total_commits"],
        reverse=True,
    )

    # Quality ranking
    quality_ranking = sorted(
        repo_scores,
        key=lambda r: r["craftsman_score"],
        reverse=True,
    )

    return {
        "total_repos": len(analyses),
        "repo_scores": repo_scores,
        "repo_commits": repo_commits,
        "attention_ranking": attention_ranking,
        "quality_ranking": quality_ranking,
        "shared_authors": dict(shared_authors),
        "cross_repo_author_count": len(shared_authors),
    }


# ---------------------------------------------------------------------------
# Full repo analysis orchestrator
# ---------------------------------------------------------------------------

def analyze_repo(
    repo_path: str,
    since: Optional[str] = None,
    until: Optional[str] = None,
    include_merges: bool = False,
) -> RepoAnalysis:
    """
    Run all analyses on a single repository.
    """
    repo_path = os.path.abspath(repo_path)
    repo_name = os.path.basename(repo_path)

    analysis = RepoAnalysis(
        repo_path=repo_path,
        repo_name=repo_name,
    )

    # Validate it's a git repo
    if not os.path.isdir(os.path.join(repo_path, ".git")):
        print(f"Warning: {repo_path} does not appear to be a git repository.", file=sys.stderr)

    # 1. Parse commits
    print(f"  Parsing commit history for {repo_name}...", file=sys.stderr)
    log_output = git_log_format(repo_path, since=since, until=until)
    raw_commits = parse_commit_log(log_output)

    for raw in raw_commits:
        commit = analyze_commit(raw, repo_path)
        analysis.commits.append(commit)

    # Merge commits (optional, for merge conflict detection)
    if include_merges:
        merge_output = git_log_merges(repo_path, since=since, until=until)
        merge_raws = parse_commit_log(merge_output)
        for raw in merge_raws:
            commit = analyze_commit(raw, repo_path)
            commit.is_merge = True
            analysis.commits.append(commit)

    # Sort by date
    analysis.commits.sort(key=lambda c: c.date)

    if analysis.commits:
        analysis.date_range = (
            analysis.commits[0].date,
            analysis.commits[-1].date,
        )
        analysis.total_authors = len(set(c.author for c in analysis.commits))

    # 2. Analyze branches
    print(f"  Analyzing branch lifecycle...", file=sys.stderr)
    analysis.branches = analyze_branches(repo_path)

    # 3. Compute hot spots
    print(f"  Computing file hot spots...", file=sys.stderr)
    analysis.hot_spots = compute_hot_spots(analysis.commits)

    # 4. Compute velocity
    print(f"  Computing velocity metrics...", file=sys.stderr)
    analysis.velocity_samples = compute_velocity(analysis.commits)

    # 5. Overall craftsman score
    if analysis.commits:
        scores = [c.craftsman_score for c in analysis.commits]
        analysis.overall_craftsman_score = sum(scores) / len(scores)
    else:
        analysis.overall_craftsman_score = 0.0

    return analysis


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_markdown_report(
    analysis: RepoAnalysis,
    cross_repo: Optional[dict] = None,
) -> str:
    """
    Produce the full craftsman's reading as a markdown document.
    """
    sections = []

    # ---- Title & metadata ----
    sections.append(_section_title(analysis))
    sections.append(_section_summary(analysis))
    sections.append(_section_craftsman_scorecard(analysis))

    # ---- Velocity report ----
    sections.append(_section_velocity(analysis))

    # ---- Difficulty signals ----
    sections.append(_section_difficulty(analysis))

    # ---- Witness marks ----
    sections.append(_section_witness_marks(analysis))

    # ---- Anti-marks ----
    sections.append(_section_anti_marks(analysis))

    # ---- Hot spots / heat map ----
    sections.append(_section_heatmap(analysis))

    # ---- Branch lifecycle ----
    sections.append(_section_branches(analysis))

    # ---- Abandoned experiments ----
    sections.append(_section_abandoned(analysis))

    # ---- Narrative reading ----
    sections.append(_section_narrative(analysis))

    # ---- Cross-repo (if applicable) ----
    if cross_repo:
        sections.append(_section_cross_repo(cross_repo))

    return "\n".join(sections)


def _section_title(analysis: RepoAnalysis) -> str:
    """Generate the report title section."""
    start = analysis.date_range[0].strftime("%Y-%m-%d") if analysis.date_range[0] > datetime.datetime.min else "beginning"
    end = analysis.date_range[1].strftime("%Y-%m-%d") if analysis.date_range[1] < datetime.datetime.max else "now"
    return (
        f"# Git Archaeology: Craftsman's Reading\n\n"
        f"**Repository:** `{analysis.repo_name}`\n\n"
        f"**Path:** `{analysis.repo_path}`\n\n"
        f"**Period:** {start} to {end}\n\n"
        f"**Total commits:** {len(analysis.commits)}\n\n"
        f"**Contributors:** {analysis.total_authors}\n\n"
        f"**Analyzed:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        f"> *\"The repo IS the agent. Git IS the nervous system.\n"
        f"> Witness marks are how the system remembers what it learned.\"*\n"
    )


def _section_summary(analysis: RepoAnalysis) -> str:
    """Generate the executive summary section."""
    if not analysis.commits:
        return "## Summary\n\nNo commits found in the specified range.\n"

    conventional_count = sum(1 for c in analysis.commits if c.is_conventional)
    witness_count = sum(1 for c in analysis.commits if c.is_witness_mark)
    anti_count = sum(1 for c in analysis.commits if c.is_anti_mark)
    mega_count = sum(1 for c in analysis.commits if c.is_mega_commit)
    n = len(analysis.commits)

    # Type breakdown
    type_counts = Counter()
    for c in analysis.commits:
        if c.parsed:
            type_counts[c.parsed.type.value] += 1
        else:
            type_counts["other"] += 1

    # Scope coverage
    scopes = set()
    for c in analysis.commits:
        if c.parsed and c.parsed.scope:
            scopes.add(c.parsed.scope)

    # Lines of code
    total_added = sum(c.total_additions for c in analysis.commits)
    total_removed = sum(c.total_deletions for c in analysis.commits)

    type_rows = []
    for t, count in type_counts.most_common():
        bar = "#" * min(count, 40)
        type_rows.append(f"| `{t}` | {count:>4} | {count/n*100:>5.1f}% | {bar} |")

    return (
        f"## Executive Summary\n\n"
        f"| Metric | Value |\n"
        f"|--------|-------|\n"
        f"| Total commits | {n} |\n"
        f"| Conventional commits | {conventional_count} ({conventional_count/n*100:.1f}%) |\n"
        f"| Witness marks | {witness_count} ({witness_count/n*100:.1f}%) |\n"
        f"| Anti-marks | {anti_count} ({anti_count/n*100:.1f}%) |\n"
        f"| Mega-commits | {mega_count} |\n"
        f"| Unique scopes | {len(scopes)} |\n"
        f"| Total lines added | {total_added:,} |\n"
        f"| Total lines removed | {total_removed:,} |\n"
        f"| Net lines | {total_added - total_removed:+,} |\n\n"
        f"### Commit Type Distribution\n\n"
        f"| Type | Count | % | Visual |\n"
        f"|------|-------|---|--------|\n"
        + "\n".join(type_rows) + "\n"
    )


def _section_craftsman_scorecard(analysis: RepoAnalysis) -> str:
    """Generate the craftsman quality scorecard."""
    if not analysis.commits:
        return ""

    scores = [c.craftsman_score for c in analysis.commits]
    avg = analysis.overall_craftsman_score
    median = sorted(scores)[len(scores) // 2]

    # Grade
    if avg >= 80:
        grade = "A — Master Craftsman"
        emoji = "Award"
    elif avg >= 65:
        grade = "B — Skilled Artisan"
        emoji = "ThumbsUp"
    elif avg >= 50:
        grade = "C — Competent Worker"
        emoji = "Handshake"
    elif avg >= 35:
        grade = "D — Needs Improvement"
        emoji = "Warning"
    else:
        grade = "F — Vandal"
        emoji = "Alert"

    # Distribution buckets
    buckets = {"90-100": 0, "80-89": 0, "70-79": 0, "60-69": 0,
               "50-59": 0, "40-49": 0, "30-39": 0, "0-29": 0}
    for s in scores:
        if s >= 90: buckets["90-100"] += 1
        elif s >= 80: buckets["80-89"] += 1
        elif s >= 70: buckets["70-79"] += 1
        elif s >= 60: buckets["60-69"] += 1
        elif s >= 50: buckets["50-59"] += 1
        elif s >= 40: buckets["40-49"] += 1
        elif s >= 30: buckets["30-39"] += 1
        else: buckets["0-29"] += 1

    dist_rows = ""
    for bucket, count in buckets.items():
        if count > 0:
            bar = "#" * count
            dist_rows += f"| {bucket} | {count:>4} | {bar} |\n"

    # Top and bottom commits
    top_commits = sorted(analysis.commits, key=lambda c: c.craftsman_score, reverse=True)[:5]
    bottom_commits = sorted(analysis.commits, key=lambda c: c.craftsman_score)[:5]

    top_rows = ""
    for c in top_commits:
        subject = c.raw_message.split("\n")[0][:60]
        top_rows += f"| `{c.short_hash}` | {c.craftsman_score:>5.1f} | {subject} |\n"

    bottom_rows = ""
    for c in bottom_commits:
        subject = c.raw_message.split("\n")[0][:60]
        bottom_rows += f"| `{c.short_hash}` | {c.craftsman_score:>5.1f} | {subject} |\n"

    return (
        f"## Craftsman Scorecard\n\n"
        f"**Overall Score: {avg:.1f}/100 — {grade}**\n\n"
        f"| Statistic | Value |\n"
        f"|-----------|-------|\n"
        f"| Mean score | {avg:.1f} |\n"
        f"| Median score | {median:.1f} |\n"
        f"| Highest score | {max(scores):.1f} |\n"
        f"| Lowest score | {min(scores):.1f} |\n\n"
        f"### Score Distribution\n\n"
        f"| Range | Count | Visual |\n"
        f"|-------|-------|--------|\n"
        + dist_rows + "\n"
        f"### Top 5 Commits (Best Witness Marks)\n\n"
        f"| Commit | Score | Message |\n"
        f"|--------|-------|---------|\n"
        + top_rows + "\n"
        f"### Bottom 5 Commits (Need Improvement)\n\n"
        f"| Commit | Score | Message |\n"
        f"|--------|-------|---------|\n"
        + bottom_rows + "\n"
    )


def _section_velocity(analysis: RepoAnalysis) -> str:
    """Generate the velocity report."""
    if not analysis.velocity_samples:
        return "## Velocity Report\n\nNo velocity data available.\n"

    rows = ""
    for v in analysis.velocity_samples:
        conv_bar = "#" * int(v.conventional_ratio * 20)
        witness_bar = "#" * int(v.witness_mark_ratio * 20)
        rows += (
            f"| {v.period_label} | {v.commit_count:>3} | {v.files_touched:>3} | "
            f"{v.lines_added:>5} | {v.lines_removed:>5} | {v.unique_authors} | "
            f"{v.avg_message_length:>5.0f} | {conv_bar} | {witness_bar} |\n"
        )

    # Overall velocity stats
    total_days = (analysis.date_range[1] - analysis.date_range[0]).total_seconds() / 86400
    if total_days > 0:
        commits_per_day = len(analysis.commits) / total_days
        commits_per_hour = commits_per_day / 8  # assuming 8h work day
    else:
        commits_per_day = 0
        commits_per_hour = 0

    return (
        f"## Velocity Report\n\n"
        f"| Metric | Value |\n"
        f"|--------|-------|\n"
        f"| Analysis span | {total_days:.0f} days |\n"
        f"| Commits/day | {commits_per_day:.2f} |\n"
        f"| Commits/hour (8h day) | {commits_per_hour:.2f} |\n\n"
        f"| Period | Commits | Files | +Lines | -Lines | Authors | Avg Msg Len | Conv% | WM% |\n"
        f"|--------|---------|-------|--------|--------|---------|-------------|-------|-----|\n"
        + rows + "\n"
        f"*Conv% = conventional commit ratio, WM% = witness mark ratio*\n"
    )


def _section_difficulty(analysis: RepoAnalysis) -> str:
    """Generate the difficulty signals section."""
    signals = detect_difficulty_signals(analysis.commits)
    if not signals:
        return "## Difficulty Signals\n\nNo strong difficulty signals detected.\n"

    rows = ""
    for sig in signals[:15]:
        reasons_str = "; ".join(sig["difficulty_reasons"])
        rows += (
            f"| `{sig['commit']}` | {sig['subject'][:50]} | "
            f"{sig['author']} | {reasons_str} |\n"
        )

    return (
        f"## Difficulty Signals\n\n"
        f"These commits likely represent the hardest work — where attention\n"
        f"was most needed and knowledge was earned the hard way.\n\n"
        f"| Commit | Subject | Author | Signals |\n"
        f"|--------|---------|--------|---------|\n"
        + rows + "\n"
    )


def _section_witness_marks(analysis: RepoAnalysis) -> str:
    """Generate the witness marks section."""
    witness_commits = [c for c in analysis.commits if c.is_witness_mark]
    if not witness_commits:
        return "## Witness Marks\n\nNo witness marks detected. Consider improving commit messages.\n"

    # Group by type
    by_type = defaultdict(list)
    for c in witness_commits:
        t = c.parsed.type.value if c.parsed else "other"
        by_type[t].append(c)

    rows = ""
    for c in sorted(witness_commits, key=lambda c: c.date)[:20]:
        reasons = ", ".join(c.witness_mark_reasons[:3])
        subject = c.raw_message.split("\n")[0][:55]
        rows += f"| `{c.short_hash}` | {c.date.strftime('%Y-%m-%d')} | {subject} | {reasons} |\n"

    # Categorized summary
    cat_rows = ""
    for t, commits in sorted(by_type.items()):
        cat_rows += f"| `{t}` | {len(commits)} |\n"

    return (
        f"## Witness Marks\n\n"
        f"**{len(witness_commits)}** commits contain witness marks — detailed\n"
        f"explanations that help future agents understand what was hard and why.\n\n"
        f"### By Type\n\n"
        f"| Type | Count |\n"
        f"|------|-------|\n"
        + cat_rows + "\n"
        f"### Notable Witness Marks\n\n"
        f"| Commit | Date | Subject | Why It's a Mark |\n"
        f"|--------|------|---------|------------------|\n"
        + rows + "\n"
    )


def _section_anti_marks(analysis: RepoAnalysis) -> str:
    """Generate the anti-marks section."""
    anti_commits = [c for c in analysis.commits if c.is_anti_mark]
    if not anti_commits:
        return "## Anti-Marks\n\nNo anti-marks detected. Well done.\n"

    rows = ""
    for c in anti_commits[:15]:
        reasons = "; ".join(c.anti_mark_reasons)
        subject = c.raw_message.split("\n")[0][:50]
        rows += f"| `{c.short_hash}` | {subject} | {reasons} |\n"

    return (
        f"## Anti-Marks\n\n"
        f"**{len(anti_commits)}** commits flagged as anti-marks — they obscure\n"
        f"rather than illuminate. Future agents will struggle to understand these.\n\n"
        f"| Commit | Message | Issue |\n"
        f"|--------|---------|-------|\n"
        + rows + "\n"
    )


def _section_heatmap(analysis: RepoAnalysis) -> str:
    """Generate the file heat map section."""
    if not analysis.hot_spots:
        return "## File Heat Map\n\nNo file change data available.\n"

    # Top 20 hot spots
    top = analysis.hot_spots[:20]
    rows = ""
    max_commits = top[0].commit_count if top else 1
    for spot in top:
        bar = "#" * int(spot.commit_count / max_commits * 20)
        density_str = f"{spot.attention_density:.0f} chars"
        rows += (
            f"| `{spot.path}` | {spot.commit_count:>3} | "
            f"{spot.total_additions:>5}+ | {spot.total_deletions:>5}- | "
            f"{spot.unique_authors} | {density_str} | {bar} |\n"
        )

    # Attention density leaders (files with longest commit messages)
    density_leaders = sorted(
        [s for s in analysis.hot_spots if s.commit_count >= 2],
        key=lambda s: s.attention_density,
        reverse=True,
    )[:10]

    density_rows = ""
    for spot in density_leaders:
        density_rows += f"| `{spot.path}` | {spot.attention_density:.0f} | {spot.commit_count} |\n"

    return (
        f"## File Heat Map\n\n"
        f"Files changed most frequently — indicating complex, attention-heavy areas.\n\n"
        f"| File | Commits | +Lines | -Lines | Authors | Avg Msg | Heat |\n"
        f"|------|---------|--------|--------|---------|---------|------|\n"
        + rows + "\n"
        f"### Attention Density Leaders\n\n"
        f"Files with the longest average commit messages — where authors\n"
        f"left the most detailed explanations.\n\n"
        f"| File | Avg Msg Length | Commits |\n"
        f"|------|---------------|---------|\n"
        + density_rows + "\n"
    )


def _section_branches(analysis: RepoAnalysis) -> str:
    """Generate the branch lifecycle section."""
    if not analysis.branches:
        return "## Branch Lifecycle\n\nNo non-main branches found.\n"

    merged = [b for b in analysis.branches if b.is_merged]
    orphaned = [b for b in analysis.branches if b.is_orphan]
    active = [b for b in analysis.branches if not b.is_merged and not b.is_orphan]

    rows = ""
    for b in sorted(analysis.branches, key=lambda b: b.date, reverse=True)[:20]:
        status = "merged" if b.is_merged else ("ORPHAN" if b.is_orphan else "active")
        status_flag = "" if b.is_merged else ("!!" if b.is_orphan else "  ")
        rows += (
            f"| {status_flag} `{b.name}` | {b.author} | "
            f"{b.age_days:>6.0f}d | {b.commit_count:>3} | {status} |\n"
        )

    summary = (
        f"## Branch Lifecycle\n\n"
        f"| Metric | Count |\n"
        f"|--------|-------|\n"
        f"| Total branches | {len(analysis.branches)} |\n"
        f"| Merged | {len(merged)} |\n"
        f"| Active | {len(active)} |\n"
        f"| Orphaned | {len(orphaned)} |\n\n"
    )

    if orphaned:
        summary += (
            f"> **Warning:** {len(orphaned)} orphaned branch(es) detected.\n"
            f"> These branches have diverged but never merged. They may\n"
            f"> contain abandoned experiments or forgotten work.\n\n"
        )

    summary += (
        f"| Flag | Branch | Author | Age | Commits | Status |\n"
        f"|------|---------|--------|-----|---------|--------|\n"
        + rows + "\n"
        f"*!! = orphaned branch — consider closing or documenting*\n"
    )
    return summary


def _section_abandoned(analysis: RepoAnalysis) -> str:
    """Generate the abandoned experiments section."""
    abandoned = detect_abandoned_experiments(analysis.commits, analysis.branches)
    if not abandoned:
        return "## Abandoned Experiments\n\nNo abandoned experiments detected.\n"

    rows = ""
    for item in abandoned:
        if item["type"] == "orphan_branch":
            rows += (
                f"| Orphan Branch | `{item['name']}` | {item['author']} | "
                f"{item['age_days']}d | {item['divergent_commits']} commits |\n"
            )
        else:
            rows += (
                f"| ABANDON Commit | `{item['commit']}` | {item['author']} | "
                f"{item['date'][:10]} | {item['subject'][:50]} |\n"
            )

    return (
        f"## Abandoned Experiments\n\n"
        f"These are the dead ends and unmerged work. They are witness marks\n"
        f"in their own right — they tell future agents what paths were tried\n"
        f"and found wanting.\n\n"
        f"| Type | ID | Author | Date/Age | Detail |\n"
        f"|------|----|--------|----------|--------|\n"
        + rows + "\n"
    )


def _section_narrative(analysis: RepoAnalysis) -> str:
    """
    Generate a chronological craftsman's reading — a narrative of what
    happened in this repo, reading the witness marks.
    """
    if not analysis.commits:
        return "## Craftsman's Narrative\n\nNo commits to narrate.\n"

    # Phase detection: group commits into natural phases
    phases = _detect_phases(analysis.commits)
    narrative_parts = ["## Craftsman's Narrative\n"]
    narrative_parts.append(
        "A chronological reading of the repository's commit history,\n"
        "following the witness marks to understand what happened, what was\n"
        "hard, and where attention was paid.\n"
    )

    for i, phase in enumerate(phases):
        narrative_parts.append(f"### Phase {i+1}: {phase['label']}\n")
        narrative_parts.append(f"*{phase['start'].strftime('%Y-%m-%d')} to {phase['end'].strftime('%Y-%m-%d')}* ({len(phase['commits'])} commits)\n")

        # Key events
        key_events = _extract_key_events(phase["commits"])
        if key_events:
            for event in key_events:
                narrative_parts.append(f"- **{event['emoji']} {event['summary']}** ({event['commit']})")

        # Dominant type
        types = Counter()
        for c in phase["commits"]:
            if c.parsed:
                types[c.parsed.type.value] += 1
            else:
                types["other"] += 1
        dominant = types.most_common(1)
        if dominant:
            narrative_parts.append(
                f"\n*Primary activity: `{dominant[0][0]}` ({dominant[0][1]} commits)*"
            )

        # Quality note
        avg_score = sum(c.craftsman_score for c in phase["commits"]) / len(phase["commits"])
        narrative_parts.append(f"*Average craftsman score: {avg_score:.0f}/100*\n")

    return "\n".join(narrative_parts)


def _detect_phases(commits: List[CommitRecord], gap_days: float = 7.0) -> List[dict]:
    """
    Detect natural phases in commit history by finding gaps.
    A phase is a contiguous group of commits with no gap > gap_days.
    """
    if not commits:
        return []

    phases = []
    current_phase = {"commits": [commits[0]], "start": commits[0].date, "end": commits[0].date}

    for commit in commits[1:]:
        gap = (commit.date - current_phase["end"]).total_seconds() / 86400
        if gap > gap_days:
            current_phase["label"] = _label_phase(current_phase["commits"])
            phases.append(current_phase)
            current_phase = {"commits": [commit], "start": commit.date, "end": commit.date}
        else:
            current_phase["commits"].append(commit)
            current_phase["end"] = commit.date

    current_phase["label"] = _label_phase(current_phase["commits"])
    phases.append(current_phase)
    return phases


def _label_phase(commits: List[CommitRecord]) -> str:
    """Generate a human-readable label for a phase of commits."""
    if not commits:
        return "Empty phase"

    types = Counter()
    for c in commits:
        if c.parsed:
            types[c.parsed.type.value] += 1
        else:
            types["other"] += 1

    dominant = types.most_common(1)[0][0]

    labels = {
        "feat": "Feature Development",
        "fix": "Bug Fixing Sprint",
        "docs": "Documentation Effort",
        "refactor": "Refactoring Pass",
        "test": "Testing Sprint",
        "perf": "Performance Optimization",
        "ci": "CI/CD Infrastructure",
        "build": "Build System Changes",
        "chore": "Maintenance & Chores",
        "revert": "Reverting Changes",
        "other": "Mixed Activity",
    }

    scope_words = []
    for c in commits:
        if c.parsed and c.parsed.scope:
            scope_words.append(c.parsed.scope)

    if scope_words:
        top_scope = Counter(scope_words).most_common(1)[0][0]
        return f"{labels.get(dominant, dominant)} ({top_scope})"

    return labels.get(dominant, dominant)


def _extract_key_events(commits: List[CommitRecord]) -> List[dict]:
    """Extract the most notable events from a phase of commits."""
    events = []

    # Highest-scored commits
    top = sorted(commits, key=lambda c: c.craftsman_score, reverse=True)[:3]
    for c in top:
        if c.craftsman_score >= 70:
            subject = c.raw_message.split("\n")[0][:80]
            events.append({
                "emoji": "WITNESS MARK",
                "summary": subject,
                "commit": c.short_hash,
            })

    # Abandon markers
    for c in commits:
        if c.has_abandon_marker:
            subject = c.raw_message.split("\n")[0][:80]
            events.append({
                "emoji": "ABANDONED",
                "summary": subject,
                "commit": c.short_hash,
            })

    # Anti-marks (mega-commits)
    for c in commits:
        if c.is_mega_commit:
            subject = c.raw_message.split("\n")[0][:80]
            events.append({
                "emoji": "MEGA-COMMIT",
                "summary": f"{subject} ({c.num_files} files)",
                "commit": c.short_hash,
            })

    # Deduplicate
    seen = set()
    unique = []
    for e in events:
        if e["commit"] not in seen:
            seen.add(e["commit"])
            unique.append(e)

    return unique[:5]


def _section_cross_repo(cross_repo: dict) -> str:
    """Generate the cross-repo analysis section."""
    lines = [
        "## Cross-Repository Analysis\n",
        f"**{cross_repo['total_repos']}** repositories analyzed.\n",
    ]

    # Attention ranking
    lines.append("### Attention Ranking (by commit count)\n")
    lines.append("| Rank | Repository | Commits | Authors |")
    lines.append("|------|-----------|---------|---------|")
    for i, r in enumerate(cross_repo["attention_ranking"], 1):
        lines.append(f"| {i} | `{r['repo']}` | {r['total_commits']} | {r['total_authors']} |")

    # Quality ranking
    lines.append("\n### Quality Ranking (by craftsman score)\n")
    lines.append("| Rank | Repository | Score |")
    lines.append("|------|-----------|-------|")
    for i, r in enumerate(cross_repo["quality_ranking"], 1):
        lines.append(f"| {i} | `{r['repo']}` | {r['craftsman_score']}/100 |")

    # Shared authors
    shared = cross_repo.get("shared_authors", {})
    if shared:
        lines.append(f"\n### Cross-Repo Contributors ({len(shared)} shared authors)\n")
        lines.append("| Author | Repos |")
        lines.append("|--------|-------|")
        for author, repos in sorted(shared.items()):
            repos_str = ", ".join(f"`{r}`" for r in repos)
            lines.append(f"| {author} | {repos_str} |")
    else:
        lines.append("\n### Cross-Repo Contributors\n")
        lines.append("No shared authors detected across repositories.\n")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# JSON output (for programmatic consumption)
# ---------------------------------------------------------------------------

def generate_json_report(
    analysis: RepoAnalysis,
    cross_repo: Optional[dict] = None,
) -> str:
    """Generate a JSON report for programmatic consumption."""
    data = {
        "repo": analysis.repo_name,
        "repo_path": analysis.repo_path,
        "analyzed_at": datetime.datetime.now().isoformat(),
        "date_range": {
            "start": analysis.date_range[0].isoformat() if analysis.date_range[0] > datetime.datetime.min else None,
            "end": analysis.date_range[1].isoformat() if analysis.date_range[1] < datetime.datetime.max else None,
        },
        "summary": {
            "total_commits": len(analysis.commits),
            "total_authors": analysis.total_authors,
            "overall_craftsman_score": round(analysis.overall_craftsman_score, 2),
            "conventional_count": sum(1 for c in analysis.commits if c.is_conventional),
            "witness_mark_count": sum(1 for c in analysis.commits if c.is_witness_mark),
            "anti_mark_count": sum(1 for c in analysis.commits if c.is_anti_mark),
            "mega_commit_count": sum(1 for c in analysis.commits if c.is_mega_commit),
        },
        "difficulty_signals": detect_difficulty_signals(analysis.commits),
        "hot_spots": [
            {
                "path": s.path,
                "commit_count": s.commit_count,
                "additions": s.total_additions,
                "deletions": s.total_deletions,
                "authors": s.unique_authors,
                "attention_density": round(s.attention_density, 1),
            }
            for s in analysis.hot_spots[:20]
        ],
        "velocity": [
            {
                "period": v.period_label,
                "commits": v.commit_count,
                "files": v.files_touched,
                "lines_added": v.lines_added,
                "lines_removed": v.lines_removed,
                "authors": v.unique_authors,
                "avg_msg_length": round(v.avg_message_length, 1),
                "conventional_ratio": round(v.conventional_ratio, 3),
                "witness_mark_ratio": round(v.witness_mark_ratio, 3),
            }
            for v in analysis.velocity_samples
        ],
        "branches": [
            {
                "name": b.name,
                "author": b.author,
                "age_days": round(b.age_days, 1),
                "commits": b.commit_count,
                "is_merged": b.is_merged,
                "is_orphan": b.is_orphan,
            }
            for b in analysis.branches
        ],
        "abandoned_experiments": detect_abandoned_experiments(analysis.commits, analysis.branches),
        "top_witness_marks": [
            {
                "hash": c.short_hash,
                "subject": c.raw_message.split("\n")[0],
                "author": c.author,
                "date": c.date.isoformat(),
                "reasons": c.witness_mark_reasons,
                "score": round(c.craftsman_score, 1),
            }
            for c in sorted(analysis.commits, key=lambda c: c.craftsman_score, reverse=True)[:10]
        ],
    }

    if cross_repo:
        data["cross_repo"] = cross_repo

    return json.dumps(data, indent=2, default=str)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="craftsman_reader",
        description=(
            "Git Archaeology: Craftsman's Reading Generator. "
            "Analyzes repository commit history and produces insights about "
            "where attention was paid, what was hard, and what was fast. "
            "Built on the Witness Marks protocol (Oracle1 + JetsonClaw1)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              # Analyze current repo
              python craftsman_reader.py .

              # Analyze with date range
              python craftsman_reader.py ./my-repo --since 2025-01-01 --until 2026-01-01

              # Output to file
              python craftsman_reader.py ./my-repo --output report.md

              # JSON output for programmatic use
              python craftsman_reader.py ./my-repo --format json --output analysis.json

              # Cross-repo analysis
              python craftsman_reader.py ./repo1 --cross-repo ./repo2 ./repo3

              # Include merge commits
              python craftsman_reader.py ./repo1 --include-merges

              # Velocity bucketed by month
              python craftsman_reader.py ./repo1 --velocity-bucket month
        """),
    )

    parser.add_argument(
        "repo_path",
        help="Path to the git repository to analyze",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--since",
        help="Only include commits after this date (git date format)",
    )
    parser.add_argument(
        "--until",
        help="Only include commits before this date (git date format)",
    )
    parser.add_argument(
        "--cross-repo",
        nargs="+",
        metavar="REPO",
        help="Additional repo paths for cross-repo analysis",
    )
    parser.add_argument(
        "--include-merges",
        action="store_true",
        help="Include merge commits in the analysis",
    )
    parser.add_argument(
        "--velocity-bucket",
        choices=["day", "week", "month"],
        default="week",
        help="Time bucket for velocity report (default: week)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress progress messages to stderr",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.quiet:
        print("Git Archaeology: Craftsman's Reading Generator", file=sys.stderr)
        print(f"Protocol: WITNESS-MARKS-2026-04-12", file=sys.stderr)
        print(f"{'=' * 50}", file=sys.stderr)

    # Validate repo path
    repo_path = os.path.abspath(args.repo_path)
    if not os.path.isdir(repo_path):
        print(f"Error: '{repo_path}' is not a directory.", file=sys.stderr)
        return 1

    # Analyze primary repo
    if not args.quiet:
        print(f"\n[1] Analyzing primary repository: {os.path.basename(repo_path)}", file=sys.stderr)

    analysis = analyze_repo(
        repo_path,
        since=args.since,
        until=args.until,
        include_merges=args.include_merges,
    )

    # Cross-repo analysis
    cross_repo = None
    if args.cross_repo:
        additional_analyses = [analysis]
        for i, path in enumerate(args.cross_repo, 2):
            if not args.quiet:
                print(f"\n[{i}] Analyzing additional repository: {os.path.basename(path)}", file=sys.stderr)
            try:
                extra = analyze_repo(path, since=args.since, until=args.until)
                additional_analyses.append(extra)
            except Exception as e:
                print(f"Warning: Failed to analyze {path}: {e}", file=sys.stderr)

        if len(additional_analyses) > 1:
            if not args.quiet:
                print(f"\n[*] Running cross-repo analysis...", file=sys.stderr)
            cross_repo = cross_repo_analysis(additional_analyses)

    # Generate report
    if args.format == "json":
        report = generate_json_report(analysis, cross_repo)
    else:
        report = generate_markdown_report(analysis, cross_repo)

    # Output
    if args.output:
        output_path = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
        with open(output_path, "w") as f:
            f.write(report)
        if not args.quiet:
            print(f"\nReport written to: {output_path}", file=sys.stderr)
    else:
        print(report)

    if not args.quiet:
        print(f"\nAnalysis complete. Craftsman score: {analysis.overall_craftsman_score:.1f}/100", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
