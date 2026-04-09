"""Register File — 64-register file for the FLUX Micro-VM.

Layout:
    R0  – R15 : 16 general-purpose integer registers
    F0  – F15 : 16 floating-point registers
    V0  – V15 : 16 SIMD/vector registers (128-bit bytearrays)

Special ABI aliases:
    R11 (SP)    : Stack pointer
    R12         : Region ID (implicit ABI)
    R13         : Trust token (implicit ABI)
    R14 (FP_REG): Frame pointer
    R15 (LR)    : Link register (return address)
"""

from __future__ import annotations

from typing import Optional


class RegisterFile:
    """64-register file: R0-R15 (general), F0-F15 (float), V0-V15 (vector)."""

    GP_COUNT = 16    # R0-R15
    FP_COUNT = 16    # F0-F15
    VEC_COUNT = 16   # V0-V15

    # Special register aliases (indices into the GP bank)
    SP = 11       # Stack pointer
    FP_REG = 14   # Frame pointer
    LR = 15       # Link register
    R12 = 12      # Region ID (implicit ABI)
    R13 = 13      # Trust token (implicit ABI)

    def __init__(self) -> None:
        self._gp: list[int] = [0] * self.GP_COUNT       # integers
        self._fp: list[float] = [0.0] * self.FP_COUNT    # floats
        self._vec: list[Optional[bytearray]] = [None] * self.VEC_COUNT  # SIMD 128-bit

    # ── General-purpose registers ──────────────────────────────────────────

    def read_gp(self, idx: int) -> int:
        """Read an integer general-purpose register."""
        if not 0 <= idx < self.GP_COUNT:
            raise IndexError(f"GP register index out of range: {idx}")
        return self._gp[idx]

    def write_gp(self, idx: int, value: int) -> None:
        """Write to an integer general-purpose register."""
        if not 0 <= idx < self.GP_COUNT:
            raise IndexError(f"GP register index out of range: {idx}")
        self._gp[idx] = int(value)

    # ── Floating-point registers ───────────────────────────────────────────

    def read_fp(self, idx: int) -> float:
        """Read a floating-point register."""
        if not 0 <= idx < self.FP_COUNT:
            raise IndexError(f"FP register index out of range: {idx}")
        return self._fp[idx]

    def write_fp(self, idx: int, value: float) -> None:
        """Write to a floating-point register."""
        if not 0 <= idx < self.FP_COUNT:
            raise IndexError(f"FP register index out of range: {idx}")
        self._fp[idx] = float(value)

    # ── Vector registers ───────────────────────────────────────────────────

    def read_vec(self, idx: int) -> bytes:
        """Read a SIMD vector register as bytes."""
        if not 0 <= idx < self.VEC_COUNT:
            raise IndexError(f"VEC register index out of range: {idx}")
        val = self._vec[idx]
        return bytes(val) if val is not None else b"\x00" * 16

    def write_vec(self, idx: int, value: bytes) -> None:
        """Write to a SIMD vector register (padded/truncated to 16 bytes)."""
        if not 0 <= idx < self.VEC_COUNT:
            raise IndexError(f"VEC register index out of range: {idx}")
        if len(value) < 16:
            buf = bytearray(16)
            buf[:len(value)] = value
            self._vec[idx] = buf
        elif len(value) == 16:
            self._vec[idx] = bytearray(value)
        else:
            self._vec[idx] = bytearray(value[:16])

    # ── SP / FP / LR convenience ──────────────────────────────────────────

    @property
    def sp(self) -> int:
        """Stack pointer (alias for R11)."""
        return self._gp[self.SP]

    @sp.setter
    def sp(self, val: int) -> None:
        self._gp[self.SP] = int(val)

    @property
    def fp(self) -> int:
        """Frame pointer (alias for R14)."""
        return self._gp[self.FP_REG]

    @fp.setter
    def fp(self, val: int) -> None:
        self._gp[self.FP_REG] = int(val)

    @property
    def lr(self) -> int:
        """Link register (alias for R15)."""
        return self._gp[self.LR]

    @lr.setter
    def lr(self, val: int) -> None:
        self._gp[self.LR] = int(val)

    # ── Snapshot / Restore ─────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Return a serializable snapshot for debugging / checkpointing."""
        return {
            "gp": list(self._gp),
            "fp": list(self._fp),
            "vec": [
                bytes(v) if v is not None else None
                for v in self._vec
            ],
        }

    def restore(self, snap: dict) -> None:
        """Restore register state from a previously taken snapshot."""
        gp = snap.get("gp")
        if gp is not None:
            assert len(gp) == self.GP_COUNT, "GP snapshot size mismatch"
            self._gp = [int(v) for v in gp]

        fp = snap.get("fp")
        if fp is not None:
            assert len(fp) == self.FP_COUNT, "FP snapshot size mismatch"
            self._fp = [float(v) for v in fp]

        vec = snap.get("vec")
        if vec is not None:
            assert len(vec) == self.VEC_COUNT, "VEC snapshot size mismatch"
            self._vec = [
                bytearray(v) if v is not None else None
                for v in vec
            ]

    # ── Repr ───────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        gp_vals = ", ".join(f"R{i}={self._gp[i]}" for i in range(self.GP_COUNT))
        return f"RegisterFile(gp=[{gp_vals}])"
