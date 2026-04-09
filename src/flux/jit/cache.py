"""JIT code cache with LRU eviction.

Provides a cache for JIT-compiled functions, keyed by a hash of the
function's IR. When the cache is full, the least-recently-used entry
is evicted.
"""

from __future__ import annotations

import hashlib
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A single entry in the JIT code cache."""
    key: str
    value: Any
    hit_count: int = 0
    size_bytes: int = 0


class JITCache:
    """LRU cache for JIT-compiled code.

    Entries are keyed by a hash string (typically SHA-256 of the function's
    IR representation). The cache supports a maximum number of entries;
    when full, the least-recently-used entry is evicted.

    Args:
        max_size: Maximum number of entries to keep. Defaults to 64.
        max_memory_bytes: Optional maximum memory budget in bytes.
    """

    def __init__(
        self,
        max_size: int = 64,
        max_memory_bytes: Optional[int] = None,
    ) -> None:
        self._max_size = max_size
        self._max_memory_bytes = max_memory_bytes
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._total_hits: int = 0
        self._total_misses: int = 0
        self._total_evictions: int = 0

    def _check_memory_budget(self) -> None:
        """Evict entries until we're within the memory budget."""
        if self._max_memory_bytes is None:
            return
        while self._total_memory() > self._max_memory_bytes and self._cache:
            self._evict_lru()

    def _evict_lru(self) -> Optional[str]:
        """Evict the least-recently-used entry."""
        if not self._cache:
            return None
        key, _ = self._cache.popitem(last=False)
        self._total_evictions += 1
        logger.debug("JIT cache evicted: %s", key)
        return key

    def _total_memory(self) -> int:
        """Return total memory used by cached entries."""
        return sum(e.size_bytes for e in self._cache.values())

    @staticmethod
    def compute_key(data: bytes) -> str:
        """Compute a cache key from raw bytes using SHA-256.

        Args:
            data: Raw bytes to hash (e.g., serialized FIR).

        Returns:
            Hexadecimal hash string.
        """
        return hashlib.sha256(data).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Look up a cached entry.

        Moves the entry to the most-recently-used position on hit.

        Args:
            key: Cache key string.

        Returns:
            Cached value, or None on miss.
        """
        entry = self._cache.get(key)
        if entry is not None:
            entry.hit_count += 1
            self._cache.move_to_end(key)
            self._total_hits += 1
            return entry.value
        self._total_misses += 1
        return None

    def put(self, key: str, value: Any, size_bytes: int = 0) -> None:
        """Insert or update a cache entry.

        If the key already exists, updates the value and moves to MRU.
        If the cache is full, evicts the LRU entry first.

        Args:
            key: Cache key string.
            value: Value to cache.
            size_bytes: Estimated memory size of the cached value.
        """
        if key in self._cache:
            # Update existing entry
            entry = self._cache[key]
            entry.value = value
            entry.size_bytes = size_bytes
            self._cache.move_to_end(key)
        else:
            # Evict if at capacity
            while len(self._cache) >= self._max_size:
                self._evict_lru()

            self._cache[key] = CacheEntry(
                key=key,
                value=value,
                size_bytes=size_bytes,
            )

        self._check_memory_budget()

    def invalidate(self, key: str) -> bool:
        """Remove a specific entry from the cache.

        Returns:
            True if the entry was found and removed, False otherwise.
        """
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> int:
        """Clear all entries from the cache.

        Returns:
            Number of entries that were cleared.
        """
        count = len(self._cache)
        self._cache.clear()
        return count

    def contains(self, key: str) -> bool:
        """Check if a key is in the cache without updating LRU order."""
        return key in self._cache

    @property
    def size(self) -> int:
        """Current number of cached entries."""
        return len(self._cache)

    @property
    def hit_rate(self) -> float:
        """Cache hit rate as a fraction (0.0 to 1.0)."""
        total = self._total_hits + self._total_misses
        return self._total_hits / total if total > 0 else 0.0

    @property
    def stats(self) -> dict[str, int | float]:
        """Cache statistics."""
        return {
            "size": self.size,
            "max_size": self._max_size,
            "hits": self._total_hits,
            "misses": self._total_misses,
            "evictions": self._total_evictions,
            "hit_rate": self.hit_rate,
            "memory_bytes": self._total_memory(),
        }

    def __repr__(self) -> str:
        return (
            f"JITCache(size={self.size}/{self._max_size}, "
            f"hit_rate={self.hit_rate:.2%})"
        )
