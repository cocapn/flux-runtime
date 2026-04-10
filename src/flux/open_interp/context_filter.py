"""
Contextual Conflict Filter — prevents false positives from scoped contradictions.

Seed's Attack: Two entries in different contexts (medical vs adverse interaction)
look contradictory but aren't. This filter checks scope before flagging.

Fix: Add context_tag awareness to contradiction detection.
"""
import re
from typing import Optional, List
from dataclasses import dataclass


@dataclass
class ScopedEntry:
    """An entry with an explicit context scope."""
    name: str
    pattern: str
    context_tag: str = "general"  # general, medical, maritime, financial, etc.
    domain: str = "default"
    
    def shares_scope(self, other: 'ScopedEntry') -> bool:
        """Two entries share scope if their context tags overlap."""
        if self.context_tag == "general" or other.context_tag == "general":
            return True  # general scope conflicts with everything
        return self.context_tag == other.context_tag


class ContextualConflictFilter:
    """
    Filters contradiction candidates by context scope before expensive analysis.
    
    Prevents false positives from entries in different domains that look
    contradictory but describe different facets of reality.
    """
    
    def __init__(self):
        self._scope_whitelist: List[tuple] = []  # (tag_a, tag_b) pairs that CAN conflict
        self._scope_blacklist: List[tuple] = []  # (tag_a, tag_b) pairs that CANNOT conflict
    
    def should_check(self, entry_a: ScopedEntry, entry_b: ScopedEntry) -> bool:
        """Should these two entries be checked for contradictions?"""
        # Blacklist overrides
        for tag_a, tag_b in self._scope_blacklist:
            if (entry_a.context_tag == tag_a and entry_b.context_tag == tag_b) or \
               (entry_a.context_tag == tag_b and entry_b.context_tag == tag_a):
                return False
        # Whitelist
        for tag_a, tag_b in self._scope_whitelist:
            if (entry_a.context_tag == tag_a and entry_b.context_tag == tag_b) or \
               (entry_a.context_tag == tag_b and entry_b.context_tag == tag_a):
                return True
        # Default: shared scope
        return entry_a.shares_scope(entry_b)
    
    def add_whitelist(self, tag_a: str, tag_b: str):
        """Explicitly allow cross-scope checking between two tags."""
        self._scope_whitelist.append((tag_a, tag_b))
    
    def add_blacklist(self, tag_a: str, tag_b: str):
        """Explicitly prevent cross-scope checking between two tags."""
        self._scope_blacklist.append((tag_a, tag_b))
