#!/usr/bin/env python3
"""
Fleet Context Inference Protocol — capability_parser.py

Parses CAPABILITY.toml files as defined in the Fleet Context Inference Protocol.
Validates format, required fields, and scoring ranges. Merges profiles from
multiple sources (git history + CAPABILITY.toml + code analysis). Detects
stale profiles based on last_active timestamps.

Part of the FLUX Bytecode VM Fleet Context Inference Protocol.
Format proposed by Oracle1 in the ISA Convergence Response (2026-04-12).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

from infer_context import ExpertiseProfile, DomainScore, ActivityLevel


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STALENESS_THRESHOLD_DAYS = 7
DORMANT_THRESHOLD_DAYS = 30

REQUIRED_AGENT_FIELDS = ["name", "type", "status"]
OPTIONAL_AGENT_FIELDS = [
    "role", "avatar", "home_repo", "last_active", "model",
    "flavor", "flux_enabled", "flux_isa_version", "flux_modes",
]

VALID_AGENT_TYPES = [
    "lighthouse", "vessel", "quartermaster", "worker",
    "specialist", "auditor", "coordinator", "navigator",
]

VALID_STATUSES = ["active", "idle", "offline", "sleeping", "maintenance"]

REQUIRED_CAPABILITY_FIELDS = ["confidence"]
OPTIONAL_CAPABILITY_FIELDS = ["description", "last_used", "tags", "repos"]

CONFIDENCE_MIN = 0.0
CONFIDENCE_MAX = 1.0
CONFIDENCE_DEFAULT = 0.5

# Sections that are recognized in a CAPABILITY.toml
KNOWN_TOP_LEVEL_SECTIONS = [
    "agent", "capabilities", "communication", "resources",
    "constraints", "associates", "domains", "specializations",
    "repos_maintained", "fleet", "meta",
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class ValidationSeverity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    """A single validation finding."""
    severity: ValidationSeverity
    field: str
    message: str

    def __str__(self) -> str:
        badge = {"error": "✗", "warning": "⚠", "info": "ℹ"}.get(
            self.severity.value, "?"
        )
        return f"  [{badge}] {self.field}: {self.message}"


@dataclass
class AgentInfo:
    """Parsed agent metadata section."""
    name: str = ""
    type: str = ""
    role: str = ""
    avatar: str = ""
    status: str = "unknown"
    home_repo: str = ""
    last_active: Optional[datetime] = None
    model: str = ""
    runtime: dict[str, Any] = field(default_factory=dict)

    @property
    def is_stale(self) -> bool:
        """True if last_active is more than STALENESS_THRESHOLD_DAYS ago."""
        if self.last_active is None:
            return True
        days_since = (datetime.now(timezone.utc) - self.last_active).days
        return days_since > STALENESS_THRESHOLD_DAYS

    @property
    def is_dormant(self) -> bool:
        """True if last_active is more than DORMANT_THRESHOLD_DAYS ago."""
        if self.last_active is None:
            return True
        days_since = (datetime.now(timezone.utc) - self.last_active).days
        return days_since > DORMANT_THRESHOLD_DAYS

    @property
    def staleness_days(self) -> int:
        """Days since last active, or a large number if unknown."""
        if self.last_active is None:
            return 9999
        return (datetime.now(timezone.utc) - self.last_active).days


@dataclass
class CapabilityEntry:
    """A single capability with confidence scoring."""
    name: str
    confidence: float = CONFIDENCE_DEFAULT
    description: str = ""
    last_used: Optional[datetime] = None
    tags: list[str] = field(default_factory=list)
    repos: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.confidence = max(CONFIDENCE_MIN, min(CONFIDENCE_MAX, self.confidence))


@dataclass
class CommunicationProfile:
    """Parsed communication preferences."""
    bottles: bool = False
    bottle_path: str = ""
    mud: bool = False
    mud_home: str = ""
    issues: bool = False
    pr_reviews: bool = False


@dataclass
class ResourceProfile:
    """Parsed resource constraints."""
    compute: str = "unknown"
    cpu_cores: int = 0
    ram_gb: int = 0
    storage_gb: int = 0
    cuda: bool = False
    languages: list[str] = field(default_factory=list)


@dataclass
class ParsedCapability:
    """Complete parsed representation of a CAPABILITY.toml file."""
    source_path: str = ""
    agent: AgentInfo = field(default_factory=AgentInfo)
    capabilities: dict[str, CapabilityEntry] = field(default_factory=dict)
    communication: CommunicationProfile = field(default_factory=CommunicationProfile)
    resources: ResourceProfile = field(default_factory=ResourceProfile)
    constraints: dict[str, Any] = field(default_factory=dict)
    associates: dict[str, Any] = field(default_factory=dict)
    raw_data: dict[str, Any] = field(default_factory=dict)
    validation_issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return all(
            i.severity != ValidationSeverity.ERROR for i in self.validation_issues
        )

    @property
    def domain_scores(self) -> dict[str, float]:
        """Return capabilities as domain->confidence mapping."""
        return {name: cap.confidence for name, cap in self.capabilities.items()}

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "source_path": self.source_path,
            "agent": {
                "name": self.agent.name,
                "type": self.agent.type,
                "role": self.agent.role,
                "status": self.agent.status,
                "home_repo": self.agent.home_repo,
                "last_active": self.agent.last_active.isoformat() if self.agent.last_active else None,
                "is_stale": self.agent.is_stale,
                "staleness_days": self.agent.staleness_days,
                "model": self.agent.model,
            },
            "capabilities": {
                name: {
                    "confidence": cap.confidence,
                    "description": cap.description,
                    "last_used": cap.last_used.isoformat() if cap.last_used else None,
                    "tags": cap.tags,
                    "repos": cap.repos,
                }
                for name, cap in self.capabilities.items()
            },
            "communication": asdict(self.communication),
            "resources": asdict(self.resources),
            "constraints": self.constraints,
            "associates": self.associates,
            "validation": {
                "is_valid": self.is_valid,
                "issues": [
                    {"severity": i.severity.value, "field": i.field, "message": i.message}
                    for i in self.validation_issues
                ],
            },
        }


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class CapabilityParser:
    """
    Parses and validates CAPABILITY.toml files according to the Fleet
    Context Inference Protocol specification.
    """

    def __init__(self, strict: bool = False):
        """
        Args:
            strict: If True, unknown sections/fields produce errors.
                    If False, they produce warnings.
        """
        self.strict = strict

    def parse_file(self, filepath: str) -> ParsedCapability:
        """Parse a CAPABILITY.toml file from disk."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"CAPABILITY.toml not found: {filepath}")

        with open(path, "rb") as f:
            raw = self._load_toml(f)

        return self.parse_toml(raw, source_path=str(path.resolve()))

    def parse_string(self, content: str, source_path: str = "<string>") -> ParsedCapability:
        """Parse CAPABILITY.toml content from a string."""
        import io
        raw = self._load_toml(io.BytesIO(content.encode("utf-8")))
        return self.parse_toml(raw, source_path=source_path)

    def parse_toml(self, data: dict[str, Any], source_path: str = "<dict>") -> ParsedCapability:
        """Parse an already-loaded TOML dictionary."""
        result = ParsedCapability(source_path=source_path, raw_data=data)

        # Parse agent section
        self._parse_agent(data, result)

        # Parse capabilities section
        self._parse_capabilities(data, result)

        # Parse communication section
        self._parse_communication(data, result)

        # Parse resources section
        self._parse_resources(data, result)

        # Parse constraints section
        self._parse_constraints(data, result)

        # Parse associates section
        self._parse_associates(data, result)

        # Validate unknown top-level sections
        self._validate_sections(data, result)

        return result

    def _load_toml(self, f) -> dict[str, Any]:
        """Load TOML data, with fallback error handling."""
        if tomllib is None:
            raise ImportError(
                "No TOML parser available. Install tomli: pip install tomli"
            )
        return tomllib.load(f)

    def _parse_agent(self, data: dict, result: ParsedCapability) -> None:
        """Parse the [agent] section."""
        agent_data = data.get("agent", {})
        if not isinstance(agent_data, dict):
            result.validation_issues.append(
                ValidationIssue(ValidationSeverity.ERROR, "agent", "Must be a table")
            )
            return

        agent = result.agent

        # Required fields
        for req in REQUIRED_AGENT_FIELDS:
            val = agent_data.get(req)
            if val is None or val == "":
                result.validation_issues.append(
                    ValidationIssue(
                        ValidationSeverity.ERROR, f"agent.{req}",
                        f"Required field '{req}' is missing or empty",
                    )
                )
            elif req == "name":
                agent.name = str(val)
            elif req == "type":
                agent.type = str(val)
                if agent.type not in VALID_AGENT_TYPES:
                    result.validation_issues.append(
                        ValidationIssue(
                            ValidationSeverity.WARNING, "agent.type",
                            f"Unknown agent type '{agent.type}'. "
                            f"Known: {VALID_AGENT_TYPES}",
                        )
                    )
            elif req == "status":
                agent.status = str(val)
                if agent.status not in VALID_STATUSES:
                    result.validation_issues.append(
                        ValidationIssue(
                            ValidationSeverity.WARNING, "agent.status",
                            f"Unknown status '{agent.status}'. Known: {VALID_STATUSES}",
                        )
                    )

        # Optional fields
        agent.role = str(agent_data.get("role", ""))
        agent.avatar = str(agent_data.get("avatar", ""))
        agent.home_repo = str(agent_data.get("home_repo", ""))
        agent.model = str(agent_data.get("model", ""))

        # Parse last_active timestamp
        last_active_raw = agent_data.get("last_active")
        if last_active_raw:
            agent.last_active = self._parse_timestamp(last_active_raw, "agent.last_active", result)

        # Parse runtime sub-table
        runtime_data = agent_data.get("runtime", {})
        if isinstance(runtime_data, dict):
            agent.runtime = runtime_data
            agent.runtime.setdefault("flavor", "")
            agent.runtime.setdefault("flux_enabled", False)
            agent.runtime.setdefault("flux_isa_version", "")
            agent.runtime.setdefault("flux_modes", [])

    def _parse_capabilities(self, data: dict, result: ParsedCapability) -> None:
        """Parse the [capabilities] section with nested sub-tables."""
        cap_data = data.get("capabilities", {})
        if not isinstance(cap_data, dict):
            if cap_data is not None:
                result.validation_issues.append(
                    ValidationIssue(ValidationSeverity.ERROR, "capabilities", "Must be a table")
                )
            return

        for cap_name, cap_values in cap_data.items():
            if not isinstance(cap_values, dict):
                result.validation_issues.append(
                    ValidationIssue(
                        ValidationSeverity.ERROR,
                        f"capabilities.{cap_name}",
                        "Each capability must be a table",
                    )
                )
                continue

            # Extract confidence
            confidence = cap_values.get("confidence", CONFIDENCE_DEFAULT)
            if not isinstance(confidence, (int, float)):
                result.validation_issues.append(
                    ValidationIssue(
                        ValidationSeverity.ERROR,
                        f"capabilities.{cap_name}.confidence",
                        f"Must be a number, got {type(confidence).__name__}",
                    )
                )
                confidence = CONFIDENCE_DEFAULT
            elif confidence < CONFIDENCE_MIN or confidence > CONFIDENCE_MAX:
                result.validation_issues.append(
                    ValidationIssue(
                        ValidationSeverity.WARNING,
                        f"capabilities.{cap_name}.confidence",
                        f"Value {confidence} outside range [{CONFIDENCE_MIN}, {CONFIDENCE_MAX}]. Clamped.",
                    )
                )
                confidence = max(CONFIDENCE_MIN, min(CONFIDENCE_MAX, confidence))

            # Parse last_used timestamp
            last_used = None
            last_used_raw = cap_values.get("last_used")
            if last_used_raw:
                last_used = self._parse_timestamp(
                    last_used_raw, f"capabilities.{cap_name}.last_used", result
                )

            entry = CapabilityEntry(
                name=cap_name,
                confidence=float(confidence),
                description=str(cap_values.get("description", "")),
                last_used=last_used,
                tags=list(cap_values.get("tags", [])),
                repos=list(cap_values.get("repos", [])),
            )
            result.capabilities[cap_name] = entry

    def _parse_communication(self, data: dict, result: ParsedCapability) -> None:
        """Parse the [communication] section."""
        comm_data = data.get("communication", {})
        if not isinstance(comm_data, dict):
            return

        result.communication = CommunicationProfile(
            bottles=bool(comm_data.get("bottles", False)),
            bottle_path=str(comm_data.get("bottle_path", "")),
            mud=bool(comm_data.get("mud", False)),
            mud_home=str(comm_data.get("mud_home", "")),
            issues=bool(comm_data.get("issues", False)),
            pr_reviews=bool(comm_data.get("pr_reviews", False)),
        )

    def _parse_resources(self, data: dict, result: ParsedCapability) -> None:
        """Parse the [resources] section."""
        res_data = data.get("resources", {})
        if not isinstance(res_data, dict):
            return

        result.resources = ResourceProfile(
            compute=str(res_data.get("compute", "unknown")),
            cpu_cores=int(res_data.get("cpu_cores", 0)),
            ram_gb=int(res_data.get("ram_gb", 0)),
            storage_gb=int(res_data.get("storage_gb", 0)),
            cuda=bool(res_data.get("cuda", False)),
            languages=list(res_data.get("languages", [])),
        )

    def _parse_constraints(self, data: dict, result: ParsedCapability) -> None:
        """Parse the [constraints] section."""
        const_data = data.get("constraints", {})
        if isinstance(const_data, dict):
            result.constraints = const_data

    def _parse_associates(self, data: dict, result: ParsedCapability) -> None:
        """Parse the [associates] section."""
        assoc_data = data.get("associates", {})
        if isinstance(assoc_data, dict):
            result.associates = assoc_data

    def _parse_timestamp(
        self, value: Any, field_path: str, result: ParsedCapability
    ) -> Optional[datetime]:
        """Parse various timestamp formats into a datetime."""
        if isinstance(value, datetime):
            return value

        s = str(value).strip()
        formats_to_try = [
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]
        for fmt in formats_to_try:
            try:
                dt = datetime.strptime(s, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue

        result.validation_issues.append(
            ValidationIssue(
                ValidationSeverity.WARNING,
                field_path,
                f"Cannot parse timestamp '{s}'. Expected ISO 8601.",
            )
        )
        return None

    def _validate_sections(self, data: dict, result: ParsedCapability) -> None:
        """Check for unknown top-level sections."""
        for key in data:
            if key not in KNOWN_TOP_LEVEL_SECTIONS:
                sev = ValidationSeverity.ERROR if self.strict else ValidationSeverity.WARNING
                result.validation_issues.append(
                    ValidationIssue(
                        sev, f"section.{key}",
                        f"Unknown top-level section '{key}'",
                    )
                )


# ---------------------------------------------------------------------------
# Profile Merger — merges git-inferred profiles with CAPABILITY.toml data
# ---------------------------------------------------------------------------

class ProfileMerger:
    """
    Merges capability profiles from multiple sources:
    1. Git history (from infer_context.py)
    2. CAPABILITY.toml (from capability_parser.py)
    3. Code analysis (manual/domain-specific additions)

    The merge strategy:
    - Self-reported confidence (CAPABILITY.toml) is weighted at 0.6
    - Git-inferred confidence is weighted at 0.4
    - When only one source exists, use it directly
    - Specialties and skill tags are unioned
    """

    def __init__(
        self,
        toml_weight: float = 0.6,
        git_weight: float = 0.4,
        code_weight: float = 0.5,
    ):
        self.toml_weight = toml_weight
        self.git_weight = git_weight
        self.code_weight = code_weight

    def merge(
        self,
        toml_profile: Optional[ParsedCapability] = None,
        git_profile: Optional[ExpertiseProfile] = None,
        code_domains: Optional[dict[str, float]] = None,
    ) -> dict[str, Any]:
        """
        Merge profiles from all available sources.

        Returns a unified capability dictionary suitable for fleet matching.
        """
        merged = {
            "agent_name": "",
            "domains": {},
            "specializations": [],
            "skill_tags": [],
            "last_active": None,
            "repos_maintained": {},
            "activity_level": ActivityLevel.DORMANT.value,
            "total_commits": 0,
            "communication": {},
            "resources": {},
            "sources_used": [],
            "merge_strategy": f"toml={self.toml_weight}, git={self.git_weight}, code={self.code_weight}",
        }

        # Determine agent name
        if toml_profile and toml_profile.agent.name:
            merged["agent_name"] = toml_profile.agent.name
        elif git_profile and git_profile.agent_name != "unknown":
            merged["agent_name"] = git_profile.agent_name

        # Merge domains
        all_domains: set[str] = set()
        if toml_profile:
            all_domains.update(toml_profile.capabilities.keys())
            merged["sources_used"].append("capability_toml")
        if git_profile:
            all_domains.update(git_profile.domain_scores.keys())
            merged["sources_used"].append("git_history")
        if code_domains:
            all_domains.update(code_domains.keys())
            merged["sources_used"].append("code_analysis")

        for domain in all_domains:
            toml_conf = 0.0
            git_conf = 0.0
            code_conf = 0.0
            toml_desc = ""
            git_desc = ""

            if toml_profile and domain in toml_profile.capabilities:
                cap = toml_profile.capabilities[domain]
                toml_conf = cap.confidence
                toml_desc = cap.description

            if git_profile and domain in git_profile.domain_scores:
                ds = git_profile.domain_scores[domain]
                git_conf = ds.confidence
                git_desc = f"Based on {ds.commit_count} commits, {ds.file_count} files"

            if code_domains and domain in code_domains:
                code_conf = code_domains[domain]

            # Weighted merge
            weights_used = []
            values = []
            if toml_conf > 0:
                weights_used.append(self.toml_weight)
                values.append(toml_conf)
            if git_conf > 0:
                weights_used.append(self.git_weight)
                values.append(git_conf)
            if code_conf > 0:
                weights_used.append(self.code_weight)
                values.append(code_conf)

            if weights_used:
                total_weight = sum(weights_used)
                merged_conf = sum(w * v for w, v in zip(weights_used, values)) / total_weight
            elif toml_conf > 0 or git_conf > 0:
                merged_conf = max(toml_conf, git_conf)
            else:
                merged_conf = 0.0

            merged["domains"][domain] = {
                "confidence": round(merged_conf, 3),
                "toml_confidence": round(toml_conf, 3),
                "git_confidence": round(git_conf, 3),
                "code_confidence": round(code_conf, 3),
                "description": toml_desc,
                "git_evidence": git_desc,
            }

        # Merge specializations
        specs = set()
        if git_profile:
            specs.update(git_profile.specialties)
        if toml_profile:
            for cap in toml_profile.capabilities.values():
                if cap.tags:
                    specs.update(cap.tags)
        if code_domains:
            specs.update(code_domains.keys())
        merged["specializations"] = sorted(specs)

        # Merge skill tags
        tags = set()
        if git_profile:
            tags.update(git_profile.skill_tags)
        if toml_profile:
            tags.update(toml_profile.resources.languages)
        merged["skill_tags"] = sorted(tags)

        # Merge last_active
        timestamps = []
        if toml_profile and toml_profile.agent.last_active:
            timestamps.append(toml_profile.agent.last_active)
        if git_profile and git_profile.activity.last_commit:
            timestamps.append(git_profile.activity.last_commit)
        if timestamps:
            merged["last_active"] = max(timestamps).isoformat()

        # Merge repos maintained
        repos: dict[str, int] = {}
        if git_profile:
            repos.update(git_profile.repos_maintained)
        if toml_profile and toml_profile.agent.home_repo:
            repos[toml_profile.agent.home_repo] = repos.get(toml_profile.agent.home_repo, 0)
        merged["repos_maintained"] = repos

        # Merge activity
        if git_profile:
            merged["activity_level"] = git_profile.activity.activity_level.value
            merged["total_commits"] = git_profile.total_commits
        elif toml_profile:
            if toml_profile.agent.is_dormant:
                merged["activity_level"] = ActivityLevel.DORMANT.value
            elif toml_profile.agent.is_stale:
                merged["activity_level"] = ActivityLevel.STALE.value
            else:
                merged["activity_level"] = ActivityLevel.ACTIVE.value

        # Merge communication
        if toml_profile:
            merged["communication"] = asdict(toml_profile.communication)

        # Merge resources
        if toml_profile:
            merged["resources"] = asdict(toml_profile.resources)

        return merged

    def detect_stale_profiles(
        self, profiles: list[dict[str, Any]], threshold_days: int = STALENESS_THRESHOLD_DAYS
    ) -> list[dict[str, Any]]:
        """
        Filter and annotate profiles that are stale (last_active > threshold).

        Returns list of stale profiles with staleness metadata.
        """
        stale = []
        for profile in profiles:
            last_active_str = profile.get("last_active")
            if not last_active_str:
                stale.append({
                    "agent": profile.get("agent_name", "unknown"),
                    "staleness_days": None,
                    "reason": "No last_active timestamp found",
                    "profile": profile,
                })
                continue

            try:
                last_active = datetime.fromisoformat(last_active_str)
                if last_active.tzinfo is None:
                    last_active = last_active.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                stale.append({
                    "agent": profile.get("agent_name", "unknown"),
                    "staleness_days": None,
                    "reason": f"Cannot parse last_active: {last_active_str}",
                    "profile": profile,
                })
                continue

            days_since = (datetime.now(timezone.utc) - last_active).days
            if days_since > threshold_days:
                stale.append({
                    "agent": profile.get("agent_name", "unknown"),
                    "staleness_days": days_since,
                    "reason": f"Last active {days_since} days ago (threshold: {threshold_days})",
                    "profile": profile,
                })

        return stale


# ---------------------------------------------------------------------------
# Batch Loader — loads CAPABILITY.toml from multiple vessel directories
# ---------------------------------------------------------------------------

class FleetCapabilityLoader:
    """Scans a fleet directory structure to find and parse all CAPABILITY.toml files."""

    CAPABILITY_FILENAME = "CAPABILITY.toml"

    def __init__(self, fleet_root: str, parser: Optional[CapabilityParser] = None):
        self.fleet_root = Path(fleet_root)
        self.parser = parser or CapabilityParser()

    def discover_toml_files(self) -> list[Path]:
        """Find all CAPABILITY.toml files under the fleet root."""
        results = []
        for path in self.fleet_root.rglob(self.CAPABILITY_FILENAME):
            results.append(path)
        return sorted(results)

    def load_all(self) -> list[ParsedCapability]:
        """Discover and parse all CAPABILITY.toml files."""
        toml_files = self.discover_toml_files()
        profiles = []
        for path in toml_files:
            print(f"  Loading: {path}")
            try:
                profile = self.parser.parse_file(str(path))
                profiles.append(profile)
            except Exception as e:
                print(f"  [ERROR] Failed to parse {path}: {e}", file=sys.stderr)
        return profiles

    def load_all_as_dicts(self) -> list[dict[str, Any]]:
        """Load all profiles and serialize to dictionaries."""
        return [p.to_dict() for p in self.load_all()]


# ---------------------------------------------------------------------------
# CLI interface
# ---------------------------------------------------------------------------

def main():
    """Command-line interface for the capability parser."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="capability_parser",
        description="Parse and validate CAPABILITY.toml files for the Fleet Context Inference Protocol.",
    )
    parser.add_argument(
        "files", nargs="*", help="CAPABILITY.toml files to parse.",
    )
    parser.add_argument(
        "--fleet-root", default=None,
        help="Scan a fleet directory for all CAPABILITY.toml files.",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Treat unknown fields as errors instead of warnings.",
    )
    parser.add_argument(
        "--check-stale", action="store_true",
        help="Check for stale profiles (last_active > 7 days).",
    )
    parser.add_argument(
        "--stale-threshold", type=int, default=STALENESS_THRESHOLD_DAYS,
        help=f"Days threshold for staleness (default: {STALENESS_THRESHOLD_DAYS}).",
    )
    parser.add_argument(
        "--output", default=None,
        help="Write combined JSON output to this file.",
    )

    args = parser.parse_args()
    cap_parser = CapabilityParser(strict=args.strict)

    profiles: list[ParsedCapability] = []

    # Load from individual files
    for filepath in args.files:
        print(f"📄 Parsing: {filepath}")
        profile = cap_parser.parse_file(filepath)
        profiles.append(profile)
        _print_validation(profile)

    # Load from fleet root
    if args.fleet_root:
        print(f"\n📂 Scanning fleet root: {args.fleet_root}")
        loader = FleetCapabilityLoader(args.fleet_root, parser=cap_parser)
        fleet_profiles = loader.load_all()
        profiles.extend(fleet_profiles)
        for p in fleet_profiles:
            _print_validation(p)

    # Stale check
    if args.check_stale and profiles:
        print(f"\n⏰ Staleness Check (threshold: {args.stale_threshold} days)")
        merger = ProfileMerger()
        dicts = [p.to_dict() for p in profiles]
        stale = merger.detect_stale_profiles(dicts, threshold_days=args.stale_threshold)
        if stale:
            for s in stale:
                days = s["staleness_days"]
                print(f"  ⚠ {s['agent']}: {days or '?'} days — {s['reason']}")
        else:
            print("  ✓ All profiles are fresh!")

    # Output
    if args.output:
        output_data = [p.to_dict() for p in profiles]
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)
        print(f"\n💾 Combined output saved: {args.output}")


def _print_validation(profile: ParsedCapability) -> None:
    """Print validation results for a parsed profile."""
    agent_name = profile.agent.name or "(unnamed)"
    valid = "✓ VALID" if profile.is_valid else "✗ INVALID"
    print(f"  Agent: {agent_name} — {valid}")
    for issue in profile.validation_issues:
        print(f"    {issue}")


if __name__ == "__main__":
    main()
