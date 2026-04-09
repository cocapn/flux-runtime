"""Linear Region Memory — capability-based memory management for the FLUX Micro-VM.

Each ``MemoryRegion`` is a contiguous block of owned memory with an access-
control list (owner + read-only borrowers).  The ``MemoryManager`` acts as a
region factory and provides stack helpers (push / pop) that operate on a
region's raw bytearray.
"""

from __future__ import annotations

import struct
from typing import Optional


# ── Memory Region ──────────────────────────────────────────────────────────


class MemoryRegion:
    """A contiguous block of memory with ownership semantics."""

    __slots__ = ("name", "data", "size", "owner", "borrowers")

    def __init__(self, name: str, size: int, owner: str = "") -> None:
        self.name = name
        self.data = bytearray(size)
        self.size = size
        self.owner = owner
        self.borrowers: list[str] = []  # read-only borrowers

    # ── Bulk read / write ─────────────────────────────────────────────────

    def read(self, offset: int, size: int = 1) -> bytes:
        """Read *size* bytes starting at *offset*.  Raises on out-of-bounds."""
        end = offset + size
        if offset < 0 or end > self.size:
            raise IndexError(
                f"MemoryRegion[{self.name!r}] read out of bounds: "
                f"offset={offset}, size={size}, region_size={self.size}"
            )
        return bytes(self.data[offset:end])

    def write(self, offset: int, data: bytes) -> None:
        """Write *data* starting at *offset*.  Raises on out-of-bounds."""
        end = offset + len(data)
        if offset < 0 or end > self.size:
            raise IndexError(
                f"MemoryRegion[{self.name!r}] write out of bounds: "
                f"offset={offset}, size={len(data)}, region_size={self.size}"
            )
        self.data[offset:end] = data

    # ── Typed helpers (little-endian) ──────────────────────────────────────

    def read_i32(self, offset: int) -> int:
        """Read a signed 32-bit integer (little-endian)."""
        raw = self.read(offset, 4)
        return struct.unpack("<i", raw)[0]

    def write_i32(self, offset: int, value: int) -> None:
        """Write a signed 32-bit integer (little-endian)."""
        self.write(offset, struct.pack("<i", value))

    def read_f32(self, offset: int) -> float:
        """Read a 32-bit IEEE 754 float (little-endian)."""
        raw = self.read(offset, 4)
        return struct.unpack("<f", raw)[0]

    def write_f32(self, offset: int, value: float) -> None:
        """Write a 32-bit IEEE 754 float (little-endian)."""
        self.write(offset, struct.pack("<f", value))

    # ── Repr ───────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"MemoryRegion(name={self.name!r}, size={self.size}, "
            f"owner={self.owner!r}, borrowers={self.borrowers!r})"
        )


# ── Memory Manager ─────────────────────────────────────────────────────────


class MemoryManager:
    """Manages linear memory regions for the VM."""

    def __init__(self, max_regions: int = 256) -> None:
        self._regions: dict[str, MemoryRegion] = {}
        self._max_regions = max_regions

    # ── Region lifecycle ───────────────────────────────────────────────────

    def create_region(self, name: str, size: int, owner: str) -> MemoryRegion:
        """Create and register a new memory region.  Returns the region."""
        if name in self._regions:
            raise ValueError(f"Region {name!r} already exists")
        if len(self._regions) >= self._max_regions:
            raise RuntimeError(
                f"Maximum number of regions ({self._max_regions}) exceeded"
            )
        region = MemoryRegion(name, size, owner)
        self._regions[name] = region
        return region

    def destroy_region(self, name: str) -> None:
        """Destroy a memory region by name."""
        if name not in self._regions:
            raise KeyError(f"Region {name!r} does not exist")
        del self._regions[name]

    def get_region(self, name: str) -> MemoryRegion:
        """Retrieve a memory region by name.  Raises ``KeyError`` if missing."""
        return self._regions[name]

    def transfer_region(self, name: str, new_owner: str) -> None:
        """Transfer ownership of a region to a new owner."""
        region = self.get_region(name)
        region.owner = new_owner

    def has_region(self, name: str) -> bool:
        """Return True if a region with the given name exists."""
        return name in self._regions

    # ── Stack helpers ──────────────────────────────────────────────────────

    @staticmethod
    def stack_push(value: int, region: MemoryRegion, sp: int) -> int:
        """Push a 32-bit value onto the stack region.

        The stack grows downward (sp is decremented before writing).
        Returns the new stack pointer value.
        """
        new_sp = sp - 4
        if new_sp < 0:
            raise MemoryError("Stack overflow")
        region.write_i32(new_sp, value)
        return new_sp

    @staticmethod
    def stack_pop(region: MemoryRegion, sp: int) -> tuple[int, int]:
        """Pop a 32-bit value from the stack region.

        Returns ``(value, new_sp)`` where *new_sp* is the restored pointer.
        """
        new_sp = sp + 4
        if new_sp > region.size:
            raise MemoryError("Stack underflow")
        value = region.read_i32(sp)
        return value, new_sp

    # ── Repr ───────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        names = ", ".join(sorted(self._regions.keys()))
        return f"MemoryManager(regions=[{names}])"
