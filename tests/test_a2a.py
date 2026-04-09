"""Tests for the FLUX A2A Protocol Layer.

Covers:
- A2AMessage binary roundtrip (52-byte header)
- AgentId bytes roundtrip
- LocalTransport send/receive and multi-agent routing
- TrustEngine initial/success/failure/decay/revoke (INCREMENTS+2)
- AgentCoordinator trust-gated send
"""

import sys
import time
import uuid
from collections import deque

sys.path.insert(0, "src")

from flux.a2a.messages import A2AMessage
from flux.a2a.transport import LocalTransport
from flux.a2a.trust import TrustEngine, InteractionRecord, AgentProfile
from flux.a2a.coordinator import AgentCoordinator


# ── Helpers ───────────────────────────────────────────────────────────────

_pass = 0
_fail = 0


def _check(name: str, condition: bool) -> None:
    global _pass, _fail
    if condition:
        _pass += 1
        print(f"  ✓ {name}")
    else:
        _fail += 1
        print(f"  ✗ {name} FAILED")


def _section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ── 1. test_message_roundtrip ─────────────────────────────────────────────


def test_message_roundtrip() -> None:
    _section("test_message_roundtrip")

    sender = uuid.uuid4()
    receiver = uuid.uuid4()
    conv_id = uuid.uuid4()

    msg = A2AMessage(
        sender=sender,
        receiver=receiver,
        conversation_id=conv_id,
        in_reply_to=None,
        message_type=0x60,  # TELL
        priority=5,
        trust_token=12345,
        capability_token=67890,
        payload=b"hello world",
    )

    # Serialize → Deserialize roundtrip
    raw = msg.to_bytes()
    _check("header is 52 bytes for empty payload check", len(raw) - len(msg.payload) == 52)
    _check("total length = 52 + payload", len(raw) == 52 + len(b"hello world"))

    msg2 = A2AMessage.from_bytes(raw)
    _check("sender matches", msg2.sender == sender)
    _check("receiver matches", msg2.receiver == receiver)
    # conversation_id is compact (8 bytes) — first 8 bytes preserved
    _check("conversation_id first 8 bytes preserved", msg2.conversation_id.bytes[:8] == conv_id.bytes[:8])
    _check("in_reply_to is None", msg2.in_reply_to is None)
    _check("message_type matches", msg2.message_type == 0x60)
    _check("priority matches", msg2.priority == 5)
    _check("trust_token matches", msg2.trust_token == 12345)
    _check("capability_token matches", msg2.capability_token == 67890)
    _check("payload matches", msg2.payload == b"hello world")

    # Roundtrip with in_reply_to set
    reply_id = uuid.uuid4()
    msg3 = A2AMessage(
        sender=receiver,
        receiver=sender,
        conversation_id=conv_id,
        in_reply_to=reply_id,
        message_type=0x61,  # ASK
        priority=10,
        trust_token=99999,
        capability_token=11111,
        payload=b"\x00\x01\x02\xff",
    )
    raw3 = msg3.to_bytes()
    msg4 = A2AMessage.from_bytes(raw3)
    _check("in_reply_to is not None after roundtrip", msg4.in_reply_to is not None)
    _check("binary payload preserved", msg4.payload == b"\x00\x01\x02\xff")
    _check("message_type 0x61 preserved", msg4.message_type == 0x61)
    _check("priority 10 preserved", msg4.priority == 10)

    # Empty payload
    msg5 = A2AMessage(
        sender=sender,
        receiver=receiver,
        conversation_id=conv_id,
        in_reply_to=None,
        message_type=0x78,  # BARRIER
        priority=15,
        trust_token=0,
        capability_token=0,
        payload=b"",
    )
    raw5 = msg5.to_bytes()
    _check("empty payload → exactly 52 bytes", len(raw5) == 52)
    msg6 = A2AMessage.from_bytes(raw5)
    _check("empty payload deserialized", msg6.payload == b"")

    # Too-short buffer raises ValueError
    try:
        A2AMessage.from_bytes(b"\x00" * 10)
        _check("short buffer raises ValueError", False)
    except ValueError:
        _check("short buffer raises ValueError", True)


# ── 2. test_agent_id_bytes ───────────────────────────────────────────────


def test_agent_id_bytes() -> None:
    _section("test_agent_id_bytes")

    aid = uuid.uuid4()
    raw = aid.bytes
    _check("UUID bytes are 16 bytes", len(raw) == 16)

    # Reconstruct from bytes
    aid2 = uuid.UUID(bytes=raw)
    _check("UUID roundtrip from bytes", aid2 == aid)

    # Nil UUID
    nil = uuid.UUID(int=0)
    _check("nil UUID bytes all zeros", nil.bytes == b"\x00" * 16)
    _check("nil UUID roundtrip", uuid.UUID(bytes=nil.bytes) == nil)

    # Different UUIDs have different bytes
    aid3 = uuid.uuid4()
    _check("different UUIDs differ", aid.bytes != aid3.bytes)

    # bytes_le variant (used by some protocols)
    _check("bytes_le is also 16 bytes", len(aid.bytes_le) == 16)


# ── 3. test_transport_send_recv ──────────────────────────────────────────


def test_transport_send_recv() -> None:
    _section("test_transport_send_recv")

    transport = LocalTransport()
    alice = uuid.uuid4()
    bob = uuid.uuid4()

    transport.register(alice)
    transport.register(bob)

    _check("alice registered", transport.is_registered(alice))
    _check("bob registered", transport.is_registered(bob))
    _check("no pending for bob", transport.pending_count(bob) == 0)

    # Send a message from alice to bob
    msg = A2AMessage(
        sender=alice,
        receiver=bob,
        conversation_id=uuid.uuid4(),
        in_reply_to=None,
        message_type=0x60,
        priority=5,
        trust_token=500_000_000,
        capability_token=0,
        payload=b"ping",
    )
    delivered = transport.send(msg)
    _check("send returns True for registered receiver", delivered)
    _check("one pending for bob", transport.pending_count(bob) == 1)
    _check("none pending for alice", transport.pending_count(alice) == 0)

    # Receive
    msgs = transport.receive(bob)
    _check("received 1 message", len(msgs) == 1)
    _check("message payload correct", msgs[0].payload == b"ping")
    _check("mailbox cleared after receive", transport.pending_count(bob) == 0)

    # Second receive — empty
    msgs2 = transport.receive(bob)
    _check("second receive is empty", len(msgs2) == 0)

    # Send to unregistered agent
    charlie = uuid.uuid4()
    msg2 = A2AMessage(
        sender=alice,
        receiver=charlie,
        conversation_id=uuid.uuid4(),
        in_reply_to=None,
        message_type=0x60,
        priority=5,
        trust_token=0,
        capability_token=0,
        payload=b"",
    )
    _check("send to unregistered returns False", transport.send(msg2) is False)

    # Receive from unregistered agent — empty list
    msgs3 = transport.receive(charlie)
    _check("receive from unregistered returns empty", len(msgs3) == 0)

    # Unregister
    transport.unregister(alice)
    _check("alice unregistered", not transport.is_registered(alice))


# ── 4. test_transport_routing ───────────────────────────────────────────


def test_transport_routing() -> None:
    _section("test_transport_routing")

    transport = LocalTransport()
    agents = [uuid.uuid4() for _ in range(5)]
    for a in agents:
        transport.register(a)

    # Each agent sends to the next (modulo 5)
    for i in range(5):
        sender = agents[i]
        receiver = agents[(i + 1) % 5]
        msg = A2AMessage(
            sender=sender,
            receiver=receiver,
            conversation_id=uuid.uuid4(),
            in_reply_to=None,
            message_type=0x66,  # BROADCAST
            priority=0,
            trust_token=i * 100,
            capability_token=0,
            payload=f"from_{i}".encode(),
        )
        transport.send(msg)

    # Each agent should have exactly one message (from the previous agent)
    for i in range(5):
        target = agents[i]
        msgs = transport.receive(target)
        _check(f"agent {i} received 1 message", len(msgs) == 1)
        expected_sender = agents[(i - 1) % 5]
        _check(f"agent {i} message from correct sender", msgs[0].sender == expected_sender)
        _check(f"agent {i} payload correct", msgs[0].payload == f"from_{(i - 1) % 5}".encode())

    # All mailboxes should be empty now
    for i in range(5):
        _check(f"agent {i} mailbox empty after drain", transport.pending_count(agents[i]) == 0)

    # Multiple messages to same receiver
    transport.register(agents[0])  # re-register to clear
    for j in range(10):
        msg = A2AMessage(
            sender=agents[1],
            receiver=agents[0],
            conversation_id=uuid.uuid4(),
            in_reply_to=None,
            message_type=0x60,
            priority=5,
            trust_token=0,
            capability_token=0,
            payload=f"msg_{j}".encode(),
        )
        transport.send(msg)
    _check("10 messages queued for agent 0", transport.pending_count(agents[0]) == 10)
    all_msgs = transport.receive(agents[0])
    _check("received all 10 messages", len(all_msgs) == 10)


# ── 5. test_trust_initial ───────────────────────────────────────────────


def test_trust_initial() -> None:
    _section("test_trust_initial")

    engine = TrustEngine()

    # No interactions recorded → neutral
    trust = engine.compute_trust("alice", "bob")
    _check("initial trust is 0.5", abs(trust - 0.5) < 1e-9)

    _check("check_trust with threshold 0.5 passes", engine.check_trust("alice", "bob", 0.5))
    _check("check_trust with threshold 0.6 fails", not engine.check_trust("alice", "bob", 0.6))

    # Reverse direction also neutral
    trust_rev = engine.compute_trust("bob", "alice")
    _check("reverse initial trust is 0.5", abs(trust_rev - 0.5) < 1e-9)

    # get_profile returns None when no interactions
    _check("get_profile returns None initially", engine.get_profile("alice", "bob") is None)


# ── 6. test_trust_success_increases ─────────────────────────────────────


def test_trust_success_increases() -> None:
    _section("test_trust_success_increases")

    engine = TrustEngine()

    # Record 20 successful interactions
    for _ in range(20):
        engine.record_interaction("alice", "bob", success=True, latency_ms=5.0,
                                   capability_match=1.0, behavior_signature=1.0)

    trust = engine.compute_trust("alice", "bob")
    _check("trust > 0.5 after 20 successes", trust > 0.5)

    # Record many more successes to drive trust higher
    for _ in range(100):
        engine.record_interaction("alice", "bob", success=True, latency_ms=5.0,
                                   capability_match=1.0, behavior_signature=1.0)

    trust2 = engine.compute_trust("alice", "bob")
    _check("trust increased with more successes", trust2 > trust)
    _check("trust is high (> 0.8) after 120 successes", trust2 > 0.8)

    # Profile should exist
    profile = engine.get_profile("alice", "bob")
    _check("profile exists", profile is not None)
    _check("history has entries", len(profile.history) > 0)


# ── 7. test_trust_failure_decreases ─────────────────────────────────────


def test_trust_failure_decreases() -> None:
    _section("test_trust_failure_decreases")

    engine = TrustEngine()

    # First build up some trust
    for _ in range(20):
        engine.record_interaction("alice", "bob", success=True, latency_ms=5.0)

    trust_before = engine.compute_trust("alice", "bob")
    _check("trust is positive before failures", trust_before > 0.5)

    # Now record many failures
    for i in range(50):
        engine.record_interaction("alice", "bob", success=False, latency_ms=500.0,
                                   capability_match=0.1, behavior_signature=float(i % 7))

    trust_after = engine.compute_trust("alice", "bob")
    _check("trust decreased after failures", trust_after < trust_before)
    _check("trust is below 0.5 after failures", trust_after < 0.5)


# ── 8. test_trust_decay ─────────────────────────────────────────────────


def test_trust_decay() -> None:
    _section("test_trust_decay")

    engine = TrustEngine()

    # Record some interactions
    for _ in range(10):
        engine.record_interaction("alice", "bob", success=True, latency_ms=5.0,
                                   capability_match=1.0, behavior_signature=1.0)

    trust_fresh = engine.compute_trust("alice", "bob")
    _check("fresh trust is above neutral", trust_fresh > 0.5)

    # Manually age the interactions by modifying timestamps
    profile = engine.get_profile("alice", "bob")
    assert profile is not None
    now = time.time()
    aged_records = deque(maxlen=1000)
    for _ in range(10):
        aged_records.append(InteractionRecord(
            timestamp=now - 2000.0,  # 2000 seconds ago
            success=True,
            latency_ms=5.0,
            capability_match=1.0,
            behavior_signature=1.0,
        ))
    profile.history = aged_records

    trust_aged = engine.compute_trust("alice", "bob")
    _check("trust decayed over time", trust_aged < trust_fresh)
    _check("aged trust > 0 (not completely zero)", trust_aged > 0.0)


# ── 9. test_trust_revoke ────────────────────────────────────────────────


def test_trust_revoke() -> None:
    _section("test_trust_revoke")

    engine = TrustEngine()

    # Build up trust
    for _ in range(50):
        engine.record_interaction("alice", "bob", success=True, latency_ms=5.0,
                                   capability_match=1.0, behavior_signature=1.0)

    trust_before = engine.compute_trust("alice", "bob")
    _check("trust is high before revoke", trust_before > 0.7)

    # Revoke
    engine.revoke_trust("alice", "bob")

    trust_after = engine.compute_trust("alice", "bob")
    _check("trust is 0.5 (neutral) after revoke", abs(trust_after - 0.5) < 1e-9)

    # Profile should still exist but be empty
    profile = engine.get_profile("alice", "bob")
    _check("profile still exists after revoke", profile is not None)
    _check("history is empty after revoke", len(profile.history) == 0)

    # Revoke non-existent pair should not crash
    engine.revoke_trust("charlie", "dave")
    _check("revoke non-existent does not crash", True)


# ── 10. test_coordinator_trust_gate ─────────────────────────────────────


def test_coordinator_trust_gate() -> None:
    _section("test_coordinator_trust_gate")

    coord = AgentCoordinator(trust_threshold=0.3)
    coord.register_agent("alice")
    coord.register_agent("bob")

    # Normal send should work (initial trust = 0.5 >= 0.3)
    ok = coord.send_message("alice", "bob", 0x60, payload=b"hello")
    _check("normal send succeeds (trust 0.5 >= 0.3)", ok)
    msgs = coord.get_messages("bob")
    _check("bob received the message", len(msgs) == 1)
    _check("payload correct", msgs[0].payload == b"hello")

    # Lower trust by recording failures
    for i in range(80):
        coord.trust.record_interaction("alice", "bob", success=False,
                                        latency_ms=500.0 + i * 10.0,
                                        capability_match=0.05,
                                        behavior_signature=float(i % 7))

    trust = coord.trust.compute_trust("alice", "bob")
    _check("trust is low after failures", trust < 0.3)

    # Message should be blocked
    ok = coord.send_message("alice", "bob", 0x60, payload=b"blocked")
    _check("low trust blocks message", ok is False)
    _check("bob has 0 pending after blocked msg", coord.pending_count("bob") == 0)

    # Now record many successes to recover trust
    for _ in range(100):
        coord.trust.record_interaction("alice", "bob", success=True, latency_ms=5.0,
                                        capability_match=1.0, behavior_signature=1.0)

    trust_recovered = coord.trust.compute_trust("alice", "bob")
    _check("trust recovered above threshold", trust_recovered >= 0.3)

    # Message should now go through
    ok2 = coord.send_message("alice", "bob", 0x61, payload=b"allowed")
    _check("recovered trust allows message", ok2 is True)

    msgs2 = coord.get_messages("bob")
    _check("bob received the recovered message", len(msgs2) == 1)
    _check("payload is 'allowed'", msgs2[0].payload == b"allowed")

    # Send to unknown agent
    ok3 = coord.send_message("alice", "charlie", 0x60)
    _check("send to unknown returns False", ok3 is False)


# ── Run all tests ─────────────────────────────────────────────────────────


if __name__ == "__main__":
    print("=" * 60)
    print("  FLUX A2A Protocol Layer — Test Suite")
    print("=" * 60)

    test_message_roundtrip()
    test_agent_id_bytes()
    test_transport_send_recv()
    test_transport_routing()
    test_trust_initial()
    test_trust_success_increases()
    test_trust_failure_decreases()
    test_trust_decay()
    test_trust_revoke()
    test_coordinator_trust_gate()

    print(f"\n{'=' * 60}")
    print(f"  Results: {_pass} passed, {_fail} failed")
    print(f"{'=' * 60}")

    if _fail > 0:
        sys.exit(1)
    else:
        print("\n  All A2A tests passed!")
        sys.exit(0)
