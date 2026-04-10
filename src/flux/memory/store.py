"""Persistent Memory Store — four-tier memory for the FLUX system.

Tiers:
- HOT (in-memory): Current session data, instant access
- WARM (JSON file): Last N sessions, fast load
- COLD (JSON archive): Full history, indexed queries
- FROZEN (archive dir): Compressed snapshots, long-term retention

The forgetting curve (Ebbinghaus-inspired):
- Access recency boost: recently used items are promoted to hotter tiers
- Decay timer: items not accessed decay toward colder tiers
- Hard delete: items below minimum relevance are permanently deleted
"""

from __future__ import annotations

import json
import os
import shutil
import time
import gzip
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


# ── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class MemoryEntry:
    """A single item in the memory store."""
    key: str
    value: Any
    tier: str = "hot"          # hot, warm, cold, frozen
    created_at: float = 0.0
    last_accessed: float = 0.0
    access_count: int = 0
    ttl: int = 0               # 0 = no expiry (seconds)
    relevance: float = 1.0     # 0.0-1.0, decays over time

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()
        if self.last_accessed == 0.0:
            self.last_accessed = time.time()

    def touch(self) -> None:
        """Update last_accessed and increment access_count."""
        self.last_accessed = time.time()
        self.access_count += 1

    def decay_relevance(self, half_life: float = 3600.0) -> float:
        """Apply exponential decay to relevance. Returns new relevance."""
        age = time.time() - self.last_accessed
        self.relevance = max(0.0, self.relevance * (0.5 ** (age / half_life)))
        return self.relevance

    def is_expired(self) -> bool:
        """Check if this entry has exceeded its TTL."""
        if self.ttl == 0:
            return False  # 0 means no expiry
        if self.ttl < 0:
            return True   # negative means immediately expired
        return (time.time() - self.created_at) > self.ttl

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "tier": self.tier,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "ttl": self.ttl,
            "relevance": self.relevance,
        }

    @classmethod
    def from_dict(cls, data: dict) -> MemoryEntry:
        return cls(**data)


TIER_ORDER = {"hot": 0, "warm": 1, "cold": 2, "frozen": 3}


@dataclass
class MemoryStats:
    """Statistics about memory usage across tiers."""
    hot_count: int = 0
    warm_count: int = 0
    cold_count: int = 0
    frozen_count: int = 0
    total_count: int = 0
    expired_count: int = 0
    low_relevance_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


# ── Memory Store ─────────────────────────────────────────────────────────────

class MemoryStore:
    """Four-tier persistent memory for the FLUX system.

    Tiers:
    - HOT (in-memory): Current session data, instant access
    - WARM (JSON file): Last N sessions, fast load
    - COLD (JSON archive): Full history, indexed queries
    - FROZEN (archive dir): Compressed snapshots, long-term retention

    The forgetting curve (Ebbinghaus-inspired):
    - Access recency boost: recently used items are promoted to hotter tiers
    - Decay timer: items not accessed decay toward colder tiers
    - Hard delete: items below minimum relevance are permanently deleted
    """

    MAX_WARM_ENTRIES = 500
    MAX_COLD_ENTRIES = 5000
    DECAY_HALF_LIFE = 3600.0     # 1 hour
    MIN_RELEVANCE = 0.01
    ARCHIVE_BATCH_SIZE = 100

    def __init__(self, base_path: str = ".flux/memory"):
        self.base_path = base_path
        self._hot: dict[str, MemoryEntry] = {}
        self._warm_cache: dict[str, MemoryEntry] = {}
        self._cold_cache: dict[str, MemoryEntry] = {}
        self._warm_path = os.path.join(base_path, "warm.json")
        self._cold_path = os.path.join(base_path, "cold.json")
        self._frozen_path = os.path.join(base_path, "archive")

    # ── Lifecycle ───────────────────────────────────────────────────────

    def startup(self) -> None:
        """Load warm and cold caches from disk on startup."""
        os.makedirs(self.base_path, exist_ok=True)
        os.makedirs(self._frozen_path, exist_ok=True)
        self._warm_cache = self._load_json_file(self._warm_path)
        self._cold_cache = self._load_json_file(self._cold_path)

    def shutdown(self) -> None:
        """Persist warm and cold caches to disk on shutdown."""
        self._save_json_file(self._warm_path, self._warm_cache)
        self._save_json_file(self._cold_path, self._cold_cache)

    # ── Store / Retrieve ────────────────────────────────────────────────

    def store(self, key: str, value: Any, tier: str = "hot",
              ttl: int = 0) -> None:
        """Store a value at the given tier.

        Args:
            key: Unique identifier for this memory.
            value: The data to store (must be JSON-serializable for warm+).
            tier: Target tier ("hot", "warm", "cold", "frozen").
            ttl: Time-to-live in seconds (0 = no expiry).
        """
        tier = tier.lower()
        if tier not in TIER_ORDER:
            raise ValueError(f"Invalid tier: {tier!r}. Must be one of {list(TIER_ORDER)}")

        entry = MemoryEntry(
            key=key,
            value=value,
            tier=tier,
            ttl=ttl,
        )

        # Remove from any other tier first
        for store in (self._hot, self._warm_cache, self._cold_cache):
            store.pop(key, None)

        if tier == "hot":
            self._hot[key] = entry
        elif tier == "warm":
            self._warm_cache[key] = entry
            self._trim_warm()
        elif tier == "cold":
            self._cold_cache[key] = entry
            self._trim_cold()
        elif tier == "frozen":
            self._save_frozen_entry(key, value)

    def retrieve(self, key: str) -> Optional[Any]:
        """Search hot → warm → cold → frozen for a key.

        Returns the value if found, None otherwise.
        Accesses promote the item (updates last_accessed).
        """
        # HOT
        entry = self._hot.get(key)
        if entry is not None:
            if entry.is_expired():
                del self._hot[key]
                return None
            entry.touch()
            return entry.value

        # WARM
        entry = self._warm_cache.get(key)
        if entry is not None:
            if entry.is_expired():
                del self._warm_cache[key]
                return None
            entry.touch()
            return entry.value

        # COLD
        entry = self._cold_cache.get(key)
        if entry is not None:
            if entry.is_expired():
                del self._cold_cache[key]
                return None
            entry.touch()
            return entry.value

        # FROZEN — read from compressed archive file
        value = self._load_frozen_entry(key)
        if value is not None:
            return value

        return None

    # ── Tier Promotion / Decay ──────────────────────────────────────────

    def promote(self, key: str) -> None:
        """Move item to a hotter tier.

        frozen → cold → warm → hot. No-op if already hot or not found.
        """
        # Check each tier from coldest to hottest
        for src_tier, src_store in [
            ("frozen", None),
            ("cold", self._cold_cache),
            ("warm", self._warm_cache),
        ]:
            entry = None
            value = None

            if src_tier == "frozen":
                value = self._load_frozen_entry(key)
                if value is not None:
                    entry = MemoryEntry(key=key, value=value, tier="frozen")
                    # Remove frozen file after promotion
                    self._remove_frozen_entry(key)
            else:
                entry = src_store.pop(key, None) if src_store else None
                value = entry.value if entry else None

            if entry is not None and value is not None:
                dest_tier = self._hotter_tier(src_tier)
                self.store(key, value, tier=dest_tier)
                return

    def _hotter_tier(self, tier: str) -> str:
        """Get the next hotter tier."""
        order = TIER_ORDER[tier]
        if order <= 0:
            return tier
        for name, idx in TIER_ORDER.items():
            if idx == order - 1:
                return name
        return tier

    def decay(self) -> int:
        """Run decay cycle on all tiers. Returns number of items demoted.

        For each entry:
        1. Apply exponential decay to relevance.
        2. If relevance drops below threshold, demote to next colder tier.
        3. If already frozen or expired, delete permanently.
        """
        demoted = 0
        now = time.time()

        # Decay hot entries
        to_demote_hot = []
        for key, entry in list(self._hot.items()):
            entry.decay_relevance(self.DECAY_HALF_LIFE)
            if entry.is_expired():
                del self._hot[key]
                demoted += 1
            elif entry.relevance < self.MIN_RELEVANCE:
                to_demote_hot.append((key, entry))

        for key, entry in to_demote_hot:
            del self._hot[key]
            self.store(key, entry.value, tier="warm")
            demoted += 1

        # Decay warm entries
        to_demote_warm = []
        for key, entry in list(self._warm_cache.items()):
            entry.decay_relevance(self.DECAY_HALF_LIFE)
            if entry.is_expired():
                del self._warm_cache[key]
                demoted += 1
            elif entry.relevance < self.MIN_RELEVANCE:
                to_demote_warm.append((key, entry))

        for key, entry in to_demote_warm:
            del self._warm_cache[key]
            self.store(key, entry.value, tier="cold")
            demoted += 1

        # Decay cold entries
        to_demote_cold = []
        for key, entry in list(self._cold_cache.items()):
            entry.decay_relevance(self.DECAY_HALF_LIFE)
            if entry.is_expired():
                del self._cold_cache[key]
                demoted += 1
            elif entry.relevance < self.MIN_RELEVANCE:
                to_demote_cold.append((key, entry))

        for key, entry in to_demote_cold:
            del self._cold_cache[key]
            self._save_frozen_entry(key, entry.value)
            demoted += 1

        return demoted

    # ── Archive / Frozen ────────────────────────────────────────────────

    def archive(self) -> int:
        """Archive cold items to frozen storage.

        Moves all cold entries to compressed frozen files.
        Returns number of items archived.
        """
        count = len(self._cold_cache)
        if count == 0:
            return 0

        for key, entry in list(self._cold_cache.items()):
            self._save_frozen_entry(key, entry.value)

        self._cold_cache.clear()
        return count

    def _save_frozen_entry(self, key: str, value: Any) -> None:
        """Save a single entry to frozen (compressed JSON) storage."""
        safe_key = self._safe_filename(key)
        filepath = os.path.join(self._frozen_path, f"{safe_key}.json.gz")
        data = {
            "key": key,
            "value": value,
            "created_at": time.time(),
        }
        with gzip.open(filepath, "wt", encoding="utf-8") as f:
            json.dump(data, f)

    def _load_frozen_entry(self, key: str) -> Optional[Any]:
        """Load a single entry from frozen storage."""
        safe_key = self._safe_filename(key)
        filepath = os.path.join(self._frozen_path, f"{safe_key}.json.gz")
        if not os.path.exists(filepath):
            return None
        try:
            with gzip.open(filepath, "rt", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("value")
        except (json.JSONDecodeError, OSError):
            return None

    def _remove_frozen_entry(self, key: str) -> None:
        """Remove a frozen entry file."""
        safe_key = self._safe_filename(key)
        filepath = os.path.join(self._frozen_path, f"{safe_key}.json.gz")
        if os.path.exists(filepath):
            os.remove(filepath)

    @staticmethod
    def _safe_filename(key: str) -> str:
        """Convert a key to a safe filename."""
        import hashlib
        # Use hash for long keys, but preserve short readable keys
        if len(key) < 64 and all(c.isalnum() or c in "._-" for c in key):
            return key
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    # ── Query ───────────────────────────────────────────────────────────

    def query(self, pattern: str, tier: str = "all") -> list[dict]:
        """Search across memory tiers by key pattern.

        Args:
            pattern: Substring to match against keys (case-insensitive).
            tier: Which tier to search ("hot", "warm", "cold", "frozen", "all").

        Returns:
            List of dicts with key, value, tier, relevance, access_count.
        """
        results: list[dict] = []
        pattern_lower = pattern.lower()

        def _matches(key: str) -> bool:
            return pattern_lower in key.lower()

        if tier in ("hot", "all"):
            for key, entry in self._hot.items():
                if _matches(key) and not entry.is_expired():
                    results.append({
                        "key": entry.key,
                        "value": entry.value,
                        "tier": "hot",
                        "relevance": entry.relevance,
                        "access_count": entry.access_count,
                    })

        if tier in ("warm", "all"):
            for key, entry in self._warm_cache.items():
                if _matches(key) and not entry.is_expired():
                    results.append({
                        "key": entry.key,
                        "value": entry.value,
                        "tier": "warm",
                        "relevance": entry.relevance,
                        "access_count": entry.access_count,
                    })

        if tier in ("cold", "all"):
            for key, entry in self._cold_cache.items():
                if _matches(key) and not entry.is_expired():
                    results.append({
                        "key": entry.key,
                        "value": entry.value,
                        "tier": "cold",
                        "relevance": entry.relevance,
                        "access_count": entry.access_count,
                    })

        if tier in ("frozen", "all"):
            if os.path.exists(self._frozen_path):
                for fname in os.listdir(self._frozen_path):
                    if fname.endswith(".json.gz"):
                        try:
                            fpath = os.path.join(self._frozen_path, fname)
                            with gzip.open(fpath, "rt", encoding="utf-8") as f:
                                data = json.load(f)
                            if _matches(data.get("key", "")):
                                results.append({
                                    "key": data.get("key", ""),
                                    "value": data.get("value"),
                                    "tier": "frozen",
                                    "relevance": 0.0,
                                    "access_count": 0,
                                })
                        except (json.JSONDecodeError, OSError):
                            continue

        return results

    # ── Stats ───────────────────────────────────────────────────────────

    def stats(self) -> MemoryStats:
        """Get memory usage statistics across all tiers."""
        expired = 0
        low_rel = 0

        for store in (self._hot, self._warm_cache, self._cold_cache):
            for entry in store.values():
                if entry.is_expired():
                    expired += 1
                if entry.relevance < self.MIN_RELEVANCE:
                    low_rel += 1

        frozen_count = 0
        if os.path.exists(self._frozen_path):
            frozen_count = len([
                f for f in os.listdir(self._frozen_path)
                if f.endswith(".json.gz")
            ])

        total = (
            len(self._hot) +
            len(self._warm_cache) +
            len(self._cold_cache) +
            frozen_count
        )

        return MemoryStats(
            hot_count=len(self._hot),
            warm_count=len(self._warm_cache),
            cold_count=len(self._cold_cache),
            frozen_count=frozen_count,
            total_count=total,
            expired_count=expired,
            low_relevance_count=low_rel,
        )

    # ── Forget / Clear ──────────────────────────────────────────────────

    def forget(self, key: str) -> bool:
        """Permanently delete a key from all tiers.

        Returns True if the key was found and deleted.
        """
        found = False

        if key in self._hot:
            del self._hot[key]
            found = True

        if key in self._warm_cache:
            del self._warm_cache[key]
            found = True

        if key in self._cold_cache:
            del self._cold_cache[key]
            found = True

        if self._remove_frozen_entry_safe(key):
            found = True

        return found

    def _remove_frozen_entry_safe(self, key: str) -> bool:
        """Try to remove a frozen entry. Returns True if it existed."""
        safe_key = self._safe_filename(key)
        filepath = os.path.join(self._frozen_path, f"{safe_key}.json.gz")
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False

    def clear_tier(self, tier: str) -> int:
        """Clear all entries from a specific tier. Returns count cleared."""
        tier = tier.lower()
        if tier == "hot":
            count = len(self._hot)
            self._hot.clear()
            return count
        elif tier == "warm":
            count = len(self._warm_cache)
            self._warm_cache.clear()
            return count
        elif tier == "cold":
            count = len(self._cold_cache)
            self._cold_cache.clear()
            return count
        elif tier == "frozen":
            if os.path.exists(self._frozen_path):
                files = [
                    f for f in os.listdir(self._frozen_path)
                    if f.endswith(".json.gz")
                ]
                for fname in files:
                    os.remove(os.path.join(self._frozen_path, fname))
                return len(files)
            return 0
        else:
            raise ValueError(f"Invalid tier: {tier!r}")

    # ── Internal ────────────────────────────────────────────────────────

    def _load_json_file(self, path: str) -> dict[str, MemoryEntry]:
        """Load entries from a JSON file."""
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                key: MemoryEntry.from_dict(entry)
                for key, entry in data.items()
            }
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_json_file(self, path: str, entries: dict[str, MemoryEntry]) -> None:
        """Save entries to a JSON file."""
        data = {
            key: entry.to_dict()
            for key, entry in entries.items()
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    def _trim_warm(self) -> None:
        """Evict lowest-relevance entries from warm cache if over capacity."""
        if len(self._warm_cache) <= self.MAX_WARM_ENTRIES:
            return
        sorted_entries = sorted(
            self._warm_cache.items(),
            key=lambda x: x[1].relevance,
        )
        excess = len(self._warm_cache) - self.MAX_WARM_ENTRIES
        for key, _ in sorted_entries[:excess]:
            del self._warm_cache[key]

    def _trim_cold(self) -> None:
        """Evict lowest-relevance entries from cold cache if over capacity."""
        if len(self._cold_cache) <= self.MAX_COLD_ENTRIES:
            return
        sorted_entries = sorted(
            self._cold_cache.items(),
            key=lambda x: x[1].relevance,
        )
        excess = len(self._cold_cache) - self.MAX_COLD_ENTRIES
        for key, _ in sorted_entries[:excess]:
            del self._cold_cache[key]
