"""Security module tests."""

import math
import struct
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from flux.security.capabilities import CapabilityToken, CapabilityRegistry, Permission
from flux.security.resource_limits import ResourceLimits, ResourceMonitor
from flux.security.sandbox import Sandbox, SandboxManager
from flux.vm.interpreter import Interpreter, VMA2AError
from flux.bytecode.opcodes import Op
from flux.a2a.trust import TrustEngine


def _make_format_g(data: bytes) -> bytes:
    """Wrap *data* in a Format G variable-length instruction prefix."""
    length = len(data)
    return bytes([length & 0xFF, (length >> 8) & 0xFF]) + data


def _cap_grant_bytes(cap_id: int) -> bytes:
    """Build a CAP_GRANT instruction that grants *cap_id* (no HALT)."""
    return bytes([Op.CAP_GRANT]) + _make_format_g(struct.pack('<I', cap_id))


def _cap_require_bytes(cap_id: int) -> bytes:
    """Build a CAP_REQUIRE instruction that requires *cap_id* (no HALT)."""
    return bytes([Op.CAP_REQUIRE]) + _make_format_g(struct.pack('<I', cap_id))


def _cap_revoke_bytes(cap_id: int) -> bytes:
    """Build a CAP_REVOKE instruction that revokes *cap_id* (no HALT)."""
    return bytes([Op.CAP_REVOKE]) + _make_format_g(struct.pack('<I', cap_id))


def test_capability_creation_and_validation():
    t = CapabilityToken.create("agent-1", "memory.heap", Permission.READ | Permission.WRITE)
    assert t.agent_id == "agent-1"
    assert t.resource == "memory.heap"
    assert t.is_valid()
    assert t.has_permission(Permission.READ)
    assert not t.has_permission(Permission.NETWORK)
    print("  PASS test_capability_creation_and_validation")


def test_capability_expiry():
    t = CapabilityToken.create("agent-1", "mem", Permission.READ, ttl_seconds=0.01)
    time.sleep(0.02)
    assert not t.is_valid()
    print("  PASS test_capability_expiry")


def test_capability_derivation():
    parent = CapabilityToken.create("agent-1", "fs", Permission.READ | Permission.WRITE)
    child = parent.derive(Permission.READ, "data")
    assert child.resource == "fs.data"
    assert child.has_permission(Permission.READ)
    assert not child.has_permission(Permission.WRITE)
    print("  PASS test_capability_derivation")


def test_registry_grant_revoke():
    reg = CapabilityRegistry()
    t = reg.grant("agent-1", "io", Permission.READ)
    assert reg.check(t)
    reg.revoke(t)
    assert not reg.check(t)
    print("  PASS test_registry_grant_revoke")


def test_resource_monitor():
    limits = ResourceLimits(max_cycles=100)
    mon = ResourceMonitor(limits)
    assert mon.check("max_cycles", 50)
    assert mon.consume("max_cycles", 50)
    assert not mon.consume("max_cycles", 51)
    mon.release("max_cycles", 50)
    assert mon.check("max_cycles", 51)
    print("  PASS test_resource_monitor")


def test_sandbox_lifecycle():
    mgr = SandboxManager()
    sb = mgr.create_sandbox("a1")
    assert mgr.get_sandbox("a1") is sb
    assert "a1" in mgr.list_sandboxes()
    assert mgr.destroy_sandbox("a1")
    assert "a1" not in mgr.list_sandboxes()
    print("  PASS test_sandbox_lifecycle")


# ── Issue #15: Bytecode Verification ──────────────────────────────────────


def test_empty_bytecode_raises():
    """Feeding empty bytes to the VM must raise ValueError."""
    vm = Interpreter(b"")
    try:
        vm.execute()
        assert False, "Expected ValueError for empty bytecode"
    except ValueError as e:
        assert "empty" in str(e).lower()
    print("  PASS test_empty_bytecode_raises")


def test_oversized_bytecode_raises():
    """Bytecode larger than 1 MB must raise ValueError."""
    huge = b'\x00' * (Interpreter.MAX_BYTECODE_SIZE + 1)
    vm = Interpreter(huge)
    try:
        vm.execute()
        assert False, "Expected ValueError for oversized bytecode"
    except ValueError as e:
        assert "exceeds" in str(e).lower()
    print("  PASS test_oversized_bytecode_raises")


def test_valid_bytecode_passes_verification():
    """Normal bytecode (NOP + HALT) must pass verification."""
    vm = Interpreter(bytes([Op.NOP, Op.HALT]))
    cycles = vm.execute()
    assert cycles == 2
    print("  PASS test_valid_bytecode_passes_verification")


# ── Issue #16: CAP Opcode Enforcement ─────────────────────────────────────


def test_cap_require_without_grant_raises():
    """CAP_REQUIRE for an ungranted capability must raise VMA2AError."""
    bytecode = _cap_require_bytes(42) + bytes([Op.HALT])
    vm = Interpreter(bytecode)
    try:
        vm.execute()
        assert False, "Expected VMA2AError for ungranted capability"
    except VMA2AError as e:
        assert "not granted" in str(e)
    print("  PASS test_cap_require_without_grant_raises")


def test_cap_grant_then_require_succeeds():
    """CAP_GRANT followed by CAP_REQUIRE for the same cap must succeed."""
    bytecode = _cap_grant_bytes(42) + _cap_require_bytes(42) + bytes([Op.HALT])
    vm = Interpreter(bytecode)
    vm.execute()
    assert 42 in vm.capabilities
    print("  PASS test_cap_grant_then_require_succeeds")


def test_cap_revoke_then_require_raises():
    """CAP_REVOKE followed by CAP_REQUIRE for the same cap must raise."""
    bytecode = _cap_grant_bytes(7) + _cap_revoke_bytes(7) + _cap_require_bytes(7) + bytes([Op.HALT])
    vm = Interpreter(bytecode)
    try:
        vm.execute()
        assert False, "Expected VMA2AError after revocation"
    except VMA2AError as e:
        assert "not granted" in str(e)
    print("  PASS test_cap_revoke_then_require_raises")


def test_capabilities_cleared_on_reset():
    """VM reset must clear the capability set."""
    bytecode = _cap_grant_bytes(1) + bytes([Op.HALT])
    vm = Interpreter(bytecode)
    vm.execute()
    assert 1 in vm.capabilities
    vm.reset()
    assert len(vm.capabilities) == 0
    print("  PASS test_capabilities_cleared_on_reset")


# ── Issue #17: NaN Trust Poison ───────────────────────────────────────────


def test_nan_capability_match_raises():
    """NaN capability_match must raise ValueError."""
    engine = TrustEngine()
    try:
        engine.record_interaction("a", "b", True, 50.0, capability_match=float('nan'))
        assert False, "Expected ValueError for NaN capability_match"
    except ValueError as e:
        assert "nan" in str(e).lower()
    print("  PASS test_nan_capability_match_raises")


def test_nan_behavior_signature_raises():
    """NaN behavior_signature must raise ValueError."""
    engine = TrustEngine()
    try:
        engine.record_interaction("a", "b", True, 50.0, behavior_signature=float('nan'))
        assert False, "Expected ValueError for NaN behavior_signature"
    except ValueError as e:
        assert "nan" in str(e).lower()
    print("  PASS test_nan_behavior_signature_raises")


def test_nan_latency_raises():
    """NaN latency_ms must raise ValueError."""
    engine = TrustEngine()
    try:
        engine.record_interaction("a", "b", True, float('nan'))
        assert False, "Expected ValueError for NaN latency_ms"
    except ValueError as e:
        assert "nan" in str(e).lower()
    print("  PASS test_nan_latency_raises")


def test_nan_threshold_raises():
    """NaN threshold in check_trust must raise ValueError."""
    engine = TrustEngine()
    try:
        engine.check_trust("a", "b", float('nan'))
        assert False, "Expected ValueError for NaN threshold"
    except ValueError as e:
        assert "nan" in str(e).lower()
    print("  PASS test_nan_threshold_raises")


def test_out_of_range_capability_match_clamped():
    """capability_match > 1.0 must be clamped to 1.0, < 0.0 clamped to 0.0."""
    engine = TrustEngine()
    engine.record_interaction("a", "b", True, 10.0, capability_match=2.5)
    profile = engine.get_profile("a", "b")
    assert profile is not None
    assert profile.history[-1].capability_match == 1.0

    engine.record_interaction("a", "b", True, 10.0, capability_match=-0.5)
    assert profile.history[-1].capability_match == 0.0
    print("  PASS test_out_of_range_capability_match_clamped")


def test_out_of_range_threshold_clamped():
    """check_trust threshold > 1.0 must be clamped; < 0.0 clamped."""
    engine = TrustEngine()
    # No interactions → neutral trust 0.5
    # Threshold 2.0 clamped to 1.0 → 0.5 < 1.0 → False
    assert engine.check_trust("a", "b", 2.0) is False
    # Threshold -1.0 clamped to 0.0 → 0.5 >= 0.0 → True
    assert engine.check_trust("a", "b", -1.0) is True
    print("  PASS test_out_of_range_threshold_clamped")


def test_valid_trust_operations_still_work():
    """Normal trust operations should still produce correct results."""
    engine = TrustEngine()
    engine.record_interaction("a", "b", True, 10.0, 0.9)
    engine.record_interaction("a", "b", True, 15.0, 0.8)
    trust = engine.compute_trust("a", "b")
    assert 0.0 <= trust <= 1.0, f"Trust {trust} out of range"
    assert trust > 0.5, f"Trust {trust} should be above neutral after successes"
    print("  PASS test_valid_trust_operations_still_work")


if __name__ == "__main__":
    test_capability_creation_and_validation()
    test_capability_expiry()
    test_capability_derivation()
    test_registry_grant_revoke()
    test_resource_monitor()
    test_sandbox_lifecycle()
    # Issue #15
    test_empty_bytecode_raises()
    test_oversized_bytecode_raises()
    test_valid_bytecode_passes_verification()
    # Issue #16
    test_cap_require_without_grant_raises()
    test_cap_grant_then_require_succeeds()
    test_cap_revoke_then_require_raises()
    test_capabilities_cleared_on_reset()
    # Issue #17
    test_nan_capability_match_raises()
    test_nan_behavior_signature_raises()
    test_nan_latency_raises()
    test_nan_threshold_raises()
    test_out_of_range_capability_match_clamped()
    test_out_of_range_threshold_clamped()
    test_valid_trust_operations_still_work()
    print("All security tests passed!")
