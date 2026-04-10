"""
Term Obituary — Graceful vocabulary death.

When a term is deprecated, it doesn't just disappear. It gets an obituary:
what it meant, why it died, what replaced it, and a migration path.

Dead terms leave tombstones. But tombstones are just hashes.
Obituaries are the stories that help living agents understand the change.

Usage:
    from flux.open_interp.term_obituary import Obituary, TermCemetery
    obit = Obituary(term="old_name", reason="superseded", replacement="new_name")
    cemetery = TermCemetery()
    cemetery.bury(obit)
    cemetery.migration_report()
"""

import time
import json
import os
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from enum import Enum


class DeathReason(Enum):
    SUPERSEDED = "superseded"       # Replaced by better term
    MERGED = "merged"               # Combined with another term
    SPLIT = "split"                 # Split into multiple terms
    AMBIGUOUS = "ambiguous"         # Too vague, caused confusion
    INCORRECT = "incorrect"         # Factually wrong
    OBSOLETE = "obsolete"           # Domain no longer relevant
    RESTRUCTURED = "restructured"   # Architecture change made it unnecessary


@dataclass
class Obituary:
    """A record of a vocabulary term's death."""
    term: str
    reason: DeathReason
    replacement: Optional[str] = None
    migration_notes: str = ""
    old_definition: str = ""
    old_pattern: str = ""
    old_bytecode: str = ""
    died_at: float = field(default_factory=time.time)
    version: str = ""
    
    @property
    def has_replacement(self) -> bool:
        return self.replacement is not None and self.replacement != ""
    
    def to_dict(self) -> dict:
        return {
            "term": self.term,
            "reason": self.reason.value,
            "replacement": self.replacement,
            "migration_notes": self.migration_notes,
            "old_definition": self.old_definition,
            "old_pattern": self.old_pattern,
            "died_at": self.died_at,
            "version": self.version,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Obituary':
        return cls(
            term=data["term"],
            reason=DeathReason(data["reason"]),
            replacement=data.get("replacement"),
            migration_notes=data.get("migration_notes", ""),
            old_definition=data.get("old_definition", ""),
            old_pattern=data.get("old_pattern", ""),
            died_at=data.get("died_at", time.time()),
            version=data.get("version", ""),
        )


class TermCemetery:
    """
    The graveyard of deprecated vocabulary terms.
    
    Every dead term gets an obituary. Other agents can consult
    the cemetery to understand why terms changed and how to migrate.
    """
    
    def __init__(self, path: Optional[str] = None):
        self.obituaries: Dict[str, Obituary] = {}
        self.path = path
        if path and os.path.exists(path):
            self.load(path)
    
    def bury(self, obituary: Obituary) -> None:
        """Record a term's death."""
        self.obituaries[obituary.term] = obituary
        if self.path:
            self.save(self.path)
    
    def exhume(self, term: str) -> Optional[Obituary]:
        """Look up a dead term's obituary."""
        return self.obituaries.get(term)
    
    def is_dead(self, term: str) -> bool:
        """Check if a term has been deprecated."""
        return term in self.obituaries
    
    def get_replacement(self, term: str) -> Optional[str]:
        """Get the replacement for a dead term."""
        obit = self.obituaries.get(term)
        return obit.replacement if obit else None
    
    def migration_map(self) -> Dict[str, str]:
        """Get a mapping of dead terms to their replacements."""
        return {
            term: obit.replacement
            for term, obit in self.obituaries.items()
            if obit.has_replacement
        }
    
    def migration_report(self) -> str:
        """Generate a human-readable migration report."""
        if not self.obituaries:
            return "No deprecated terms."
        
        lines = ["# Term Migration Report\n"]
        for term, obit in sorted(self.obituaries.items()):
            replacement = obit.replacement or "(none)"
            lines.append(f"## {term}")
            lines.append(f"- Reason: {obit.reason.value}")
            lines.append(f"- Replacement: {replacement}")
            if obit.migration_notes:
                lines.append(f"- Notes: {obit.migration_notes}")
            lines.append("")
        
        return "\n".join(lines)
    
    def rewrite_guide(self, text: str) -> str:
        """
        Rewrite text that uses deprecated terms.
        Replaces dead terms with their living replacements.
        """
        for term, obit in self.obituaries.items():
            if obit.has_replacement:
                text = text.replace(term, obit.replacement)
        return text
    
    def stats(self) -> dict:
        """Cemetery statistics."""
        reasons = {}
        for obit in self.obituaries.values():
            r = obit.reason.value
            reasons[r] = reasons.get(r, 0) + 1
        return {
            "total_dead": len(self.obituaries),
            "with_replacement": sum(1 for o in self.obituaries.values() if o.has_replacement),
            "orphaned": sum(1 for o in self.obituaries.values() if not o.has_replacement),
            "by_reason": reasons,
        }
    
    def save(self, path: str) -> None:
        """Save cemetery to JSON file."""
        data = {term: obit.to_dict() for term, obit in self.obituaries.items()}
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load(self, path: str) -> None:
        """Load cemetery from JSON file."""
        with open(path, 'r') as f:
            data = json.load(f)
        self.obituaries = {
            term: Obituary.from_dict(obit_data)
            for term, obit_data in data.items()
        }
