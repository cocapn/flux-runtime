"""Tests for the FLUX Agent Communication Protocol.

Covers:
- Message envelopes: Request, Response, Event, Error creation and reply
- MessageId roundtrip (hex, bytes)
- DirectChannel: connect, send, receive, disconnect
- BroadcastChannel: subscribe, broadcast, unsubscribe
- TopicChannel: subscribe to topics, publish, receive by topic
- AgentRegistry: register, lookup, capability search, routing, heartbeat
- Capability negotiation: offers, acceptance, rejection, expiry
- Trust handshaking: initiate, challenge, respond, accept/reject
- Binary message serialization roundtrip
- Batch encoding/decoding
"""

import sys
import time
import pytest

sys.path.insert(0, "src")

from flux.protocol.message import (
    MessageKind, MessageEnvelope, MessageId,
    Request, Response, Event, Error,
)
from flux.protocol.channel import (
    Channel, DirectChannel, BroadcastChannel, TopicChannel, ChannelKind,
)
from flux.protocol.registry import (
    AgentDescriptor, CapabilityDescriptor, AgentRegistry,
)
from flux.protocol.negotiation import (
    NegotiationState, CapabilityOffer, TrustHandshake, Negotiator,
)
from flux.protocol.serialization import (
    BinaryMessageCodec, HEADER_SIZE, PROTOCOL_MAGIC,
)


# ════════════════════════════════════════════════════════════════════════════
# Message Tests
# ════════════════════════════════════════════════════════════════════════════


class TestMessageId:
    """Tests for MessageId."""

    def test_default_creation(self):
        """MessageId creates a UUID by default."""
        mid = MessageId()
        assert mid.value is not None
        assert len(mid.to_bytes()) == 16

    def test_from_bytes_roundtrip(self):
        """MessageId roundtrips through bytes."""
        mid = MessageId()
        raw = mid.to_bytes()
        mid2 = MessageId.from_bytes(raw)
        assert mid2.value == mid.value

    def test_from_hex_roundtrip(self):
        """MessageId roundtrips through hex string."""
        mid = MessageId()
        hex_str = mid.value.hex
        mid2 = MessageId.from_hex(hex_str)
        assert mid2.value == mid.value

    def test_from_bytes_invalid_length(self):
        """MessageId.from_bytes raises ValueError for wrong length."""
        with pytest.raises(ValueError, match="16 bytes"):
            MessageId.from_bytes(b"\x00" * 8)

    def test_repr(self):
        """MessageId repr is informative."""
        mid = MessageId()
        assert "MessageId" in repr(mid)


class TestMessageEnvelope:
    """Tests for the base message envelope."""

    def test_default_creation(self):
        """MessageEnvelope creates with defaults."""
        env = MessageEnvelope(sender="alice", receiver="bob")
        assert env.sender == "alice"
        assert env.receiver == "bob"
        assert env.kind == MessageKind.EVENT
        assert env.payload == {}
        assert env.metadata == {}
        assert len(env.conversation_id) > 0

    def test_kind_properties(self):
        """Kind properties work correctly."""
        req = MessageEnvelope(kind=MessageKind.REQUEST)
        assert req.is_request
        assert not req.is_response
        assert not req.is_error

        resp = MessageEnvelope(kind=MessageKind.RESPONSE)
        assert not resp.is_request
        assert resp.is_response

        err = MessageEnvelope(kind=MessageKind.ERROR)
        assert not resp.is_error
        assert err.is_error

    def test_reply_creates_response(self):
        """reply() creates a Response with swapped sender/receiver."""
        env = MessageEnvelope(sender="alice", receiver="bob")
        reply = env.reply({"result": 42})

        assert reply.sender == "bob"
        assert reply.receiver == "alice"
        assert reply.kind == MessageKind.RESPONSE
        assert reply.payload == {"result": 42}
        assert reply.conversation_id == env.conversation_id
        assert "in_reply_to" in reply.metadata

    def test_as_error_creates_error(self):
        """as_error() creates an Error envelope."""
        env = MessageEnvelope(sender="alice", receiver="bob")
        err = env.as_error(code=500, message="Internal error", details="stack trace")

        assert isinstance(err, Error)
        assert err.sender == "bob"
        assert err.receiver == "alice"
        assert err.error_code == 500
        assert err.error_message == "Internal error"
        assert err.error_details == "stack trace"

    def test_to_dict(self):
        """to_dict produces a serializable dictionary."""
        env = MessageEnvelope(
            sender="alice", receiver="bob",
            payload={"key": "value"},
            metadata={"trace": "abc123"},
        )
        d = env.to_dict()

        assert d["sender"] == "alice"
        assert d["receiver"] == "bob"
        assert d["kind"] == int(MessageKind.EVENT)
        assert d["payload"] == {"key": "value"}
        assert d["metadata"] == {"trace": "abc123"}
        assert "id" in d
        assert "conversation_id" in d
        assert "timestamp" in d


class TestRequest:
    """Tests for Request messages."""

    def test_create_factory(self):
        """Request.create() produces a valid request."""
        req = Request.create(
            sender="alice", receiver="bob",
            method="compute.add",
            payload={"a": 1, "b": 2},
            timeout_ms=5000,
        )
        assert req.is_request
        assert req.method == "compute.add"
        assert req.payload == {"a": 1, "b": 2}
        assert req.timeout_ms == 5000
        assert req.expects_reply is True

    def test_kind_auto_set(self):
        """Request.__post_init__ sets kind to REQUEST."""
        req = Request(sender="a", receiver="b")
        assert req.kind == MessageKind.REQUEST


class TestResponse:
    """Tests for Response messages."""

    def test_create_factory(self):
        """Response.create() creates a reply to a request."""
        req = Request.create(sender="alice", receiver="bob", method="add")
        resp = Response.create(req, payload={"result": 3}, success=True)

        assert resp.is_response
        assert resp.sender == "bob"
        assert resp.receiver == "alice"
        assert resp.conversation_id == req.conversation_id
        assert resp.success is True

    def test_create_failure(self):
        """Response.create() with success=False."""
        req = Request.create(sender="a", receiver="b", method="x")
        resp = Response.create(req, payload={"error": "not found"}, success=False)

        assert resp.success is False


class TestEvent:
    """Tests for Event messages."""

    def test_create_factory(self):
        """Event.create() produces a valid event."""
        evt = Event.create(
            sender="monitor",
            event_type="heartbeat",
            payload={"status": "ok"},
        )
        assert evt.kind == MessageKind.EVENT
        assert evt.event_type == "heartbeat"
        assert evt.sender == "monitor"

    def test_broadcast_event_no_receiver(self):
        """Broadcast events have empty receiver."""
        evt = Event.create(sender="monitor", event_type="alert")
        assert evt.receiver == ""


class TestError:
    """Tests for Error messages."""

    def test_create_factory(self):
        """Error.create() produces a structured error."""
        err = Error.create(
            error_code=404,
            error_message="Not Found",
            sender="server",
            receiver="client",
            details="Resource does not exist",
        )
        assert err.is_error
        assert err.error_code == 404
        assert err.error_message == "Not Found"
        assert err.error_details == "Resource does not exist"
        assert err.payload["code"] == 404

    def test_auto_populates_payload(self):
        """Error auto-populates payload from code/message/details."""
        err = Error(error_code=500, error_message="Server Error")
        assert err.payload["code"] == 500
        assert err.payload["message"] == "Server Error"
        assert err.payload["details"] == ""


# ════════════════════════════════════════════════════════════════════════════
# Channel Tests
# ════════════════════════════════════════════════════════════════════════════


class TestDirectChannel:
    """Tests for point-to-point direct channels."""

    def test_connect_and_send(self):
        """Connected agents can exchange messages."""
        ch = DirectChannel("test")
        ch.connect("alice", "bob")

        msg = MessageEnvelope(sender="alice", receiver="bob", payload={"hi": True})
        ok = ch.send(msg)
        assert ok is True

        msgs = ch.receive("bob")
        assert len(msgs) == 1
        assert msgs[0].payload == {"hi": True}

    def test_send_disconnected_returns_false(self):
        """Sending to a disconnected agent returns False."""
        ch = DirectChannel("test")
        ch.subscribe("alice")
        ch.subscribe("bob")

        msg = MessageEnvelope(sender="alice", receiver="bob")
        ok = ch.send(msg)
        assert ok is False

    def test_bidirectional(self):
        """Messages flow both ways in a connected pair."""
        ch = DirectChannel("test")
        ch.connect("alice", "bob")

        ch.send(MessageEnvelope(sender="alice", receiver="bob", payload={"dir": "a2b"}))
        ch.send(MessageEnvelope(sender="bob", receiver="alice", payload={"dir": "b2a"}))

        assert len(ch.receive("bob")) == 1
        assert len(ch.receive("alice")) == 1

    def test_receive_empty_mailbox(self):
        """Receiving from an empty mailbox returns empty list."""
        ch = DirectChannel("test")
        ch.connect("alice", "bob")
        assert ch.receive("bob") == []

    def test_receive_max_count(self):
        """receive(max_count) limits returned messages."""
        ch = DirectChannel("test")
        ch.connect("alice", "bob")

        for i in range(5):
            ch.send(MessageEnvelope(sender="alice", receiver="bob", payload={"n": i}))

        msgs = ch.receive("bob", max_count=3)
        assert len(msgs) == 3
        assert ch.pending_count("bob") == 2

    def test_unsubscribe(self):
        """Unsubscribing removes the agent's mailbox."""
        ch = DirectChannel("test")
        ch.connect("alice", "bob")

        ch.unsubscribe("bob")
        assert ch.pending_count("bob") == 0
        assert not ch.is_connected("alice", "bob")

    def test_connected_agents(self):
        """connected_agents returns the set of connected agents."""
        ch = DirectChannel("test")
        ch.connect("alice", "bob")
        ch.connect("alice", "charlie")

        agents = ch.connected_agents("alice")
        assert "bob" in agents
        assert "charlie" in agents
        assert "alice" not in agents

    def test_buffer_full(self):
        """Sending to a full buffer returns False."""
        ch = DirectChannel("test", max_buffer=3)
        ch.connect("alice", "bob")

        for i in range(3):
            ok = ch.send(MessageEnvelope(sender="alice", receiver="bob", payload={"i": i}))
            assert ok is True

        # Fourth message should fail
        ok = ch.send(MessageEnvelope(sender="alice", receiver="bob"))
        assert ok is False


class TestBroadcastChannel:
    """Tests for one-to-many broadcast channels."""

    def test_subscribe_and_broadcast(self):
        """All subscribers receive broadcast messages."""
        ch = BroadcastChannel("test")
        ch.subscribe("alice")
        ch.subscribe("bob")
        ch.subscribe("charlie")

        msg = MessageEnvelope(sender="alice", receiver="", payload={"alert": True})
        ok = ch.send(msg)
        assert ok is True

        # bob and charlie should get the message; alice should not
        assert len(ch.receive("bob")) == 1
        assert len(ch.receive("charlie")) == 1
        assert len(ch.receive("alice")) == 0

    def test_non_subscriber_cannot_send(self):
        """Only subscribers can send broadcasts."""
        ch = BroadcastChannel("test")
        ch.subscribe("bob")

        msg = MessageEnvelope(sender="stranger", receiver="", payload={})
        ok = ch.send(msg)
        assert ok is False

    def test_unsubscribe(self):
        """Unsubscribed agents no longer receive messages."""
        ch = BroadcastChannel("test")
        ch.subscribe("alice")
        ch.subscribe("bob")

        ch.unsubscribe("bob")

        msg = MessageEnvelope(sender="alice", receiver="", payload={})
        ch.send(msg)

        assert len(ch.receive("bob")) == 0

    def test_subscriber_count(self):
        """subscriber_count reflects current subscriptions."""
        ch = BroadcastChannel("test")
        assert ch.subscriber_count == 0

        ch.subscribe("alice")
        ch.subscribe("bob")
        assert ch.subscriber_count == 2

        ch.unsubscribe("alice")
        assert ch.subscriber_count == 1

    def test_subscribers_property(self):
        """subscribers returns a copy of the subscriber set."""
        ch = BroadcastChannel("test")
        ch.subscribe("alice")
        ch.subscribe("bob")

        subs = ch.subscribers
        assert subs == {"alice", "bob"}
        # Mutating the copy doesn't affect the channel
        subs.add("charlie")
        assert ch.subscriber_count == 2


class TestTopicChannel:
    """Tests for topic-based pub/sub channels."""

    def test_subscribe_and_publish(self):
        """Agents subscribed to a topic receive published messages."""
        ch = TopicChannel("test")
        ch.subscribe("alice", "alerts")
        ch.subscribe("bob", "alerts")

        msg = MessageEnvelope(
            sender="alice", receiver="",
            payload={"msg": "fire"},
            metadata={"topic": "alerts"},
        )
        ok = ch.send(msg)
        assert ok is True

        msgs = ch.receive("bob")
        assert len(msgs) == 1
        assert msgs[0].payload["msg"] == "fire"

    def test_topic_isolation(self):
        """Messages on one topic don't leak to another topic."""
        ch = TopicChannel("test")
        ch.subscribe("alice", "alerts")
        ch.subscribe("bob", "alerts")
        ch.subscribe("bob", "news")

        ch.send(MessageEnvelope(
            sender="alice", receiver="",
            payload={}, metadata={"topic": "alerts"},
        ))

        assert len(ch.receive("bob", topic="news")) == 0
        assert len(ch.receive("bob", topic="alerts")) == 1

    def test_publish_by_method(self):
        """publish() method works with explicit topic."""
        ch = TopicChannel("test")
        ch.subscribe("alice", "alerts")
        ch.subscribe("bob", "alerts")

        msg = MessageEnvelope(sender="alice", receiver="", payload={})
        ok = ch.publish(msg, "alerts")
        assert ok is True

        assert len(ch.receive("bob")) == 1

    def test_unsubscribe_from_topic(self):
        """Unsubscribing from a topic stops message delivery."""
        ch = TopicChannel("test")
        ch.subscribe("bob", "alerts")
        ch.unsubscribe("bob", "alerts")

        ch.send(MessageEnvelope(
            sender="alice", receiver="",
            payload={}, metadata={"topic": "alerts"},
        ))

        assert len(ch.receive("bob")) == 0

    def test_topics_property(self):
        """topics returns all active topics."""
        ch = TopicChannel("test")
        ch.subscribe("alice", "alerts")
        ch.subscribe("bob", "news")
        ch.subscribe("charlie", "alerts")

        assert ch.topics == {"alerts", "news"}

    def test_topic_subscribers(self):
        """topic_subscribers returns subscribers for a specific topic."""
        ch = TopicChannel("test")
        ch.subscribe("alice", "alerts")
        ch.subscribe("bob", "alerts")
        ch.subscribe("charlie", "news")

        assert ch.topic_subscribers("alerts") == {"alice", "bob"}
        assert ch.topic_subscribers("news") == {"charlie"}

    def test_pending_count_topic(self):
        """pending_count_topic returns count for a specific topic."""
        ch = TopicChannel("test")
        ch.subscribe("alice", "alerts")
        ch.subscribe("bob", "alerts")
        ch.subscribe("bob", "news")

        for _ in range(3):
            ch.publish(
                MessageEnvelope(sender="alice", receiver="", payload={}),
                "alerts",
            )

        assert ch.pending_count_topic("bob", "alerts") == 3
        assert ch.pending_count_topic("bob", "news") == 0

    def test_receive_all_topics(self):
        """receive() without topic returns messages from all subscribed topics."""
        ch = TopicChannel("test")
        ch.subscribe("alice", "alerts")
        ch.subscribe("bob", "alerts")
        ch.subscribe("bob", "news")
        ch.subscribe("charlie", "news")

        ch.publish(MessageEnvelope(sender="alice", receiver="", payload={"t": "alert"}), "alerts")
        ch.publish(MessageEnvelope(sender="charlie", receiver="", payload={"t": "news"}), "news")

        msgs = ch.receive("bob")
        assert len(msgs) == 2


# ════════════════════════════════════════════════════════════════════════════
# Registry Tests
# ════════════════════════════════════════════════════════════════════════════


class TestAgentDescriptor:
    """Tests for AgentDescriptor."""

    def test_add_and_check_capability(self):
        """Capabilities can be added and checked."""
        desc = AgentDescriptor(name="agent1")
        cap = CapabilityDescriptor(name="compute.add", version="1.0.0")
        desc.add_capability(cap)

        assert desc.has_capability("compute.add")
        assert not desc.has_capability("compute.mul")

    def test_get_capability(self):
        """get_capability returns the descriptor or None."""
        desc = AgentDescriptor(name="agent1")
        cap = CapabilityDescriptor(name="file.read", version="2.0.0")
        desc.add_capability(cap)

        found = desc.get_capability("file.read")
        assert found is not None
        assert found.version == "2.0.0"

        assert desc.get_capability("file.write") is None

    def test_capability_names(self):
        """capability_names returns sorted list."""
        desc = AgentDescriptor(name="agent1")
        desc.add_capability(CapabilityDescriptor(name="zebra"))
        desc.add_capability(CapabilityDescriptor(name="alpha"))
        desc.add_capability(CapabilityDescriptor(name="mid"))

        assert desc.capability_names == ["alpha", "mid", "zebra"]

    def test_is_active(self):
        """is_active checks the status field."""
        desc = AgentDescriptor(name="agent1", status="active")
        assert desc.is_active

        desc.status = "offline"
        assert not desc.is_active

    def test_heartbeat(self):
        """heartbeat updates last_seen."""
        desc = AgentDescriptor(name="agent1")
        old = desc.last_seen
        time.sleep(0.01)
        desc.heartbeat()
        assert desc.last_seen > old


class TestAgentRegistry:
    """Tests for AgentRegistry."""

    def test_register_and_get(self):
        """Agents can be registered and retrieved."""
        reg = AgentRegistry()
        desc = AgentDescriptor(name="agent1")
        reg.register(desc)

        found = reg.get("agent1")
        assert found is not None
        assert found.name == "agent1"

    def test_unregister(self):
        """Agents can be unregistered."""
        reg = AgentRegistry()
        desc = AgentDescriptor(name="agent1")
        reg.register(desc)

        removed = reg.unregister("agent1")
        assert removed is not None
        assert reg.get("agent1") is None

    def test_get_by_id(self):
        """Agents can be looked up by UUID."""
        reg = AgentRegistry()
        desc = AgentDescriptor(name="agent1", agent_id="custom-id-123")
        reg.register(desc)

        found = reg.get_by_id("custom-id-123")
        assert found is not None
        assert found.name == "agent1"

    def test_list_agents(self):
        """list_agents returns all registered agents."""
        reg = AgentRegistry()
        reg.register(AgentDescriptor(name="a", status="active"))
        reg.register(AgentDescriptor(name="b", status="idle"))
        reg.register(AgentDescriptor(name="c", status="offline"))

        assert len(reg.list_agents()) == 3
        assert len(reg.list_agents(status="active")) == 1
        assert len(reg.list_agents(status="idle")) == 1

    def test_find_by_capability(self):
        """find_by_capability returns matching agents."""
        reg = AgentRegistry()
        a = AgentDescriptor(name="a")
        a.add_capability(CapabilityDescriptor(name="compute"))
        b = AgentDescriptor(name="b")
        b.add_capability(CapabilityDescriptor(name="file"))
        b.add_capability(CapabilityDescriptor(name="compute"))
        reg.register(a)
        reg.register(b)

        result = reg.find_by_capability("compute")
        assert len(result) == 2
        names = {d.name for d in result}
        assert names == {"a", "b"}

    def test_find_by_multiple_capabilities(self):
        """find_by_capabilities returns agents with ALL given capabilities."""
        reg = AgentRegistry()
        a = AgentDescriptor(name="a")
        a.add_capability(CapabilityDescriptor(name="compute"))
        a.add_capability(CapabilityDescriptor(name="file"))
        b = AgentDescriptor(name="b")
        b.add_capability(CapabilityDescriptor(name="compute"))
        reg.register(a)
        reg.register(b)

        result = reg.find_by_capabilities(["compute", "file"])
        assert len(result) == 1
        assert result[0].name == "a"

    def test_route_picks_most_recent(self):
        """route() picks the most recently active agent with the capability."""
        reg = AgentRegistry()
        a = AgentDescriptor(name="a", status="active")
        a.add_capability(CapabilityDescriptor(name="compute"))
        b = AgentDescriptor(name="b", status="active")
        b.add_capability(CapabilityDescriptor(name="compute"))
        reg.register(a)
        reg.register(b)

        b.heartbeat()  # b is more recent
        routed = reg.route("compute")
        assert routed is not None
        assert routed.name == "b"

    def test_route_returns_none_if_no_match(self):
        """route() returns None if no agent has the capability."""
        reg = AgentRegistry()
        assert reg.route("nonexistent") is None

    def test_heartbeat(self):
        """heartbeat() updates an agent's last_seen."""
        reg = AgentRegistry()
        desc = AgentDescriptor(name="agent1")
        reg.register(desc)

        assert reg.heartbeat("agent1") is True
        assert reg.heartbeat("unknown") is False

    def test_expire_stale(self):
        """expire_stale marks agents with old heartbeats as offline."""
        reg = AgentRegistry(heartbeat_timeout=0.01)  # 10ms
        desc = AgentDescriptor(name="agent1", status="active")
        # Set last_seen to the past
        desc.last_seen = time.time() - 1.0
        reg.register(desc)

        expired = reg.expire_stale()
        assert "agent1" in expired
        assert reg.get("agent1").status == "offline"

    def test_all_capabilities(self):
        """all_capabilities returns the union of all capability names."""
        reg = AgentRegistry()
        a = AgentDescriptor(name="a")
        a.add_capability(CapabilityDescriptor(name="compute"))
        a.add_capability(CapabilityDescriptor(name="file"))
        b = AgentDescriptor(name="b")
        b.add_capability(CapabilityDescriptor(name="compute"))
        b.add_capability(CapabilityDescriptor(name="net"))
        reg.register(a)
        reg.register(b)

        caps = reg.all_capabilities()
        assert caps == {"compute", "file", "net"}

    def test_clear(self):
        """clear() removes all agents."""
        reg = AgentRegistry()
        reg.register(AgentDescriptor(name="a"))
        reg.register(AgentDescriptor(name="b"))
        reg.clear()
        assert reg.count == 0


class TestCapabilityDescriptor:
    """Tests for CapabilityDescriptor."""

    def test_matches_same_name_and_version(self):
        """Matching descriptors match."""
        a = CapabilityDescriptor(name="compute.add", version="1.0.0")
        b = CapabilityDescriptor(name="compute.add", version="1.0.0")
        assert a.matches(b)

    def test_no_match_different_name(self):
        """Different names don't match."""
        a = CapabilityDescriptor(name="compute.add", version="1.0.0")
        b = CapabilityDescriptor(name="compute.mul", version="1.0.0")
        assert not a.matches(b)

    def test_no_match_different_version(self):
        """Different versions don't match."""
        a = CapabilityDescriptor(name="compute.add", version="1.0.0")
        b = CapabilityDescriptor(name="compute.add", version="2.0.0")
        assert not a.matches(b)

    def test_frozen(self):
        """CapabilityDescriptor is frozen (hashable)."""
        cap = CapabilityDescriptor(name="x", version="1.0.0")
        s = {cap}
        assert len(s) == 1


# ════════════════════════════════════════════════════════════════════════════
# Negotiation Tests
# ════════════════════════════════════════════════════════════════════════════


class TestCapabilityOffer:
    """Tests for CapabilityOffer."""

    def test_default_creation(self):
        """CapabilityOffer creates with defaults."""
        offer = CapabilityOffer(
            agent_name="alice",
            capabilities=[CapabilityDescriptor(name="compute")],
        )
        assert offer.agent_name == "alice"
        assert len(offer.capabilities) == 1
        assert offer.trust_level == 0.3
        assert not offer.is_expired

    def test_matches_requirement(self):
        """matches_requirement checks capability names."""
        offer = CapabilityOffer(
            agent_name="alice",
            capabilities=[
                CapabilityDescriptor(name="compute"),
                CapabilityDescriptor(name="file"),
            ],
        )
        assert offer.matches_requirement("compute")
        assert offer.matches_requirement("file")
        assert not offer.matches_requirement("net")

    def test_expired(self):
        """Offer with past expiry is expired."""
        offer = CapabilityOffer(
            agent_name="alice",
            capabilities=[],
            expires_at=time.time() - 10,
        )
        assert offer.is_expired


class TestTrustHandshake:
    """Tests for TrustHandshake."""

    def test_lifecycle(self):
        """Handshake proceeds through the expected states."""
        hs = TrustHandshake()
        assert hs.state == NegotiationState.IDLE
        assert not hs.is_complete

        hs.initiate("alice", "bob", trust_level=0.7)
        assert hs.state == NegotiationState.PROPOSED
        assert hs.initiator == "alice"
        assert hs.responder == "bob"
        assert hs.trust_level == 0.7

        hs.challenge("nonce-123")
        assert hs.state == NegotiationState.COUNTER_PROPOSED
        assert hs.nonce == "nonce-123"

        hs.respond("proof-456")
        assert hs.proof == "proof-456"

        hs.accept()
        assert hs.state == NegotiationState.ACCEPTED
        assert hs.is_complete
        assert hs.completed_at > 0

    def test_reject(self):
        """Handshake can be rejected."""
        hs = TrustHandshake()
        hs.initiate("alice", "bob")
        hs.challenge("nonce")
        hs.respond("proof")

        hs.reject("invalid proof")
        assert hs.state == NegotiationState.REJECTED
        assert hs.error == "invalid proof"
        assert hs.is_complete

    def test_invalid_transitions(self):
        """Invalid state transitions raise ValueError."""
        hs = TrustHandshake()

        with pytest.raises(ValueError):
            hs.challenge("nonce")  # not proposed yet

        with pytest.raises(ValueError):
            hs.respond("proof")  # not counter-proposed

    def test_expire(self):
        """Handshake can be expired."""
        hs = TrustHandshake()
        hs.initiate("alice", "bob")
        hs.expire()
        assert hs.state == NegotiationState.EXPIRED
        assert hs.is_complete

    def test_fail(self):
        """Handshake can be failed."""
        hs = TrustHandshake()
        hs.initiate("alice", "bob")
        hs.fail("network error")
        assert hs.state == NegotiationState.FAILED
        assert hs.error == "network error"

    def test_duration(self):
        """duration reports elapsed time."""
        hs = TrustHandshake()
        hs.initiate("alice", "bob")
        hs.challenge("nonce-123")
        hs.respond("proof-456")
        hs.accept()

        assert hs.duration >= 0


class TestNegotiator:
    """Tests for Negotiator."""

    def test_create_and_accept_offer(self):
        """Offers can be created and accepted."""
        neg = Negotiator()
        offer = neg.create_offer(
            agent_name="alice",
            capabilities=[CapabilityDescriptor(name="compute")],
        )

        assert neg.active_offers == 1
        ok = neg.accept_offer(offer.offer_id, "bob")
        assert ok is True
        assert neg.total_agreements == 1

    def test_reject_offer(self):
        """Offers can be rejected."""
        neg = Negotiator()
        offer = neg.create_offer(
            agent_name="alice",
            capabilities=[],
        )

        ok = neg.reject_offer(offer.offer_id)
        assert ok is True
        assert neg.active_offers == 0

    def test_cannot_accept_own_offer(self):
        """An agent cannot accept its own offer."""
        neg = Negotiator()
        offer = neg.create_offer(agent_name="alice", capabilities=[])

        ok = neg.accept_offer(offer.offer_id, "alice")
        assert ok is False

    def test_cannot_accept_expired_offer(self):
        """Expired offers cannot be accepted."""
        neg = Negotiator()
        offer = neg.create_offer(agent_name="alice", capabilities=[])
        offer.expires_at = time.time() - 10  # expired

        ok = neg.accept_offer(offer.offer_id, "bob")
        assert ok is False

    def test_expire_offers(self):
        """expire_offers removes expired offers."""
        neg = Negotiator(offer_ttl=0.01)
        offer = neg.create_offer(agent_name="alice", capabilities=[])
        time.sleep(0.02)

        expired = neg.expire_offers()
        assert len(expired) == 1
        assert offer.offer_id in expired
        assert neg.active_offers == 0

    def test_handshake_lifecycle(self):
        """Handshake can be initiated and completed."""
        neg = Negotiator()
        hs = neg.initiate_handshake("alice", "bob", 0.7)

        hs.challenge("nonce")
        hs.respond("proof")
        ok = neg.complete_handshake(hs.handshake_id)
        assert ok is True
        assert neg.total_agreements == 1

    def test_trust_level_between_agents(self):
        """get_trust_level reflects agreements."""
        neg = Negotiator()
        neg.initiate_handshake("alice", "bob", 0.8)

        assert neg.get_trust_level("alice", "bob") == 0.0

        neg.create_offer(
            agent_name="alice",
            capabilities=[],
            trust_level=0.6,
        )
        neg.accept_offer(list(neg._offers.keys())[0], "bob")

        assert neg.get_trust_level("alice", "bob") == 0.6

    def test_has_agreement(self):
        """has_agreement checks bidirectionally."""
        neg = Negotiator()
        assert not neg.has_agreement("alice", "bob")

        neg.create_offer(agent_name="alice", capabilities=[])
        neg.accept_offer(list(neg._offers.keys())[0], "bob")

        assert neg.has_agreement("alice", "bob")
        assert neg.has_agreement("bob", "alice")

    def test_clear(self):
        """clear() resets all state."""
        neg = Negotiator()
        neg.create_offer(agent_name="a", capabilities=[])
        neg.initiate_handshake("a", "b")
        neg.clear()

        assert neg.active_offers == 0
        assert neg.active_handshakes == 0
        assert neg.total_agreements == 0


# ════════════════════════════════════════════════════════════════════════════
# Serialization Tests
# ════════════════════════════════════════════════════════════════════════════


class TestBinaryMessageCodec:
    """Tests for the binary message codec."""

    def test_roundtrip_request(self):
        """Request roundtrips through binary serialization."""
        codec = BinaryMessageCodec()
        req = Request.create(
            sender="alice", receiver="bob",
            method="compute.add",
            payload={"a": 42, "b": 58},
            timeout_ms=5000,
        )

        data = codec.serialize(req)
        assert len(data) >= HEADER_SIZE

        decoded = codec.deserialize(data)
        assert decoded.sender == "alice"
        assert decoded.receiver == "bob"
        assert decoded.kind == MessageKind.REQUEST
        assert decoded.conversation_id == req.conversation_id
        assert decoded.payload == {"a": 42, "b": 58}
        assert isinstance(decoded, Request)
        assert decoded.method == "compute.add"

    def test_roundtrip_response(self):
        """Response roundtrips through binary serialization."""
        codec = BinaryMessageCodec()
        req = Request.create(sender="alice", receiver="bob", method="add")
        resp = Response.create(req, payload={"result": 100}, success=True)

        data = codec.serialize(resp)
        decoded = codec.deserialize(data)

        assert isinstance(decoded, Response)
        assert decoded.sender == "bob"
        assert decoded.receiver == "alice"
        assert decoded.success is True
        assert decoded.payload == {"result": 100}

    def test_roundtrip_event(self):
        """Event roundtrips through binary serialization."""
        codec = BinaryMessageCodec()
        evt = Event.create(
            sender="monitor",
            event_type="heartbeat",
            payload={"status": "ok"},
        )

        data = codec.serialize(evt)
        decoded = codec.deserialize(data)

        assert isinstance(decoded, Event)
        assert decoded.sender == "monitor"
        assert decoded.event_type == "heartbeat"

    def test_roundtrip_error(self):
        """Error roundtrips through binary serialization."""
        codec = BinaryMessageCodec()
        err = Error.create(
            error_code=500,
            error_message="Internal Server Error",
            sender="server",
            receiver="client",
            details="Stack overflow",
        )

        data = codec.serialize(err)
        decoded = codec.deserialize(data)

        assert isinstance(decoded, Error)
        assert decoded.error_code == 500
        assert decoded.error_message == "Internal Server Error"
        assert decoded.error_details == "Stack overflow"

    def test_empty_sender_receiver(self):
        """Empty sender/receiver roundtrip correctly."""
        codec = BinaryMessageCodec()
        env = MessageEnvelope(sender="", receiver="", payload={})

        data = codec.serialize(env)
        decoded = codec.deserialize(data)
        assert decoded.sender == ""
        assert decoded.receiver == ""

    def test_short_buffer_raises(self):
        """Short buffer raises ValueError."""
        codec = BinaryMessageCodec()
        with pytest.raises(ValueError, match="at least"):
            codec.deserialize(b"\x00" * 10)

    def test_invalid_magic_raises(self):
        """Invalid magic bytes raise ValueError."""
        codec = BinaryMessageCodec()
        bad_data = b"XXXX" + b"\x00" * (HEADER_SIZE - 4)
        with pytest.raises(ValueError, match="Invalid magic"):
            codec.deserialize(bad_data)

    def test_metadata_preserved(self):
        """Metadata is preserved through roundtrip."""
        codec = BinaryMessageCodec()
        env = MessageEnvelope(
            sender="alice", receiver="bob",
            payload={"data": 1},
            metadata={"trace_id": "abc", "priority": 10},
        )

        data = codec.serialize(env)
        decoded = codec.deserialize(data)

        assert decoded.metadata["trace_id"] == "abc"
        assert decoded.metadata["priority"] == 10

    def test_batch_encode_decode(self):
        """Multiple messages can be batch-encoded and decoded."""
        codec = BinaryMessageCodec()
        msgs = [
            Request.create(sender="a", receiver="b", method="m1", payload={"i": i})
            for i in range(5)
        ]

        data = BinaryMessageCodec.encode_message_batch(msgs)
        decoded = BinaryMessageCodec.decode_message_batch(data)

        assert len(decoded) == 5
        for i, msg in enumerate(decoded):
            assert msg.sender == "a"
            assert msg.receiver == "b"
            assert msg.payload["i"] == i

    def test_batch_empty(self):
        """Empty batch roundtrips correctly."""
        data = BinaryMessageCodec.encode_message_batch([])
        decoded = BinaryMessageCodec.decode_message_batch(data)
        assert decoded == []

    def test_batch_with_malformed_skipped(self):
        """Malformed messages in a batch are skipped."""
        codec = BinaryMessageCodec()
        msgs = [
            Request.create(sender="a", receiver="b", method="ok"),
        ]
        batch = BinaryMessageCodec.encode_message_batch(msgs)
        # Append garbage after a valid length prefix
        import struct
        garbage = struct.pack("<I", 20) + b"\xff" * 20
        combined = batch + garbage

        decoded = BinaryMessageCodec.decode_message_batch(combined)
        # At least the valid message should be recovered
        assert len(decoded) >= 1
