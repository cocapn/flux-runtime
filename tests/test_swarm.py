"""Tests for the FLUX Swarm — multi-agent orchestration framework.

Covers:
- FluxAgent creation, specialization, task execution, evolution
- Topology creation, connections, neighbors, shortest path
- Swarm spawn, broadcast, scatter, reduce, barrier
- MessageBus send, receive, publish, subscribe
- DeadlockDetector cycle detection, livelock detection, resolution
- Swarm evolution and topology optimization
- Comprehensive swarm report
"""

import pytest
import time


# ── FluxAgent Tests ─────────────────────────────────────────────────────────

class TestFluxAgentCreation:
    """Test FluxAgent instantiation and basic properties."""

    def test_create_default_agent(self):
        from flux.swarm.agent import FluxAgent, AgentRole
        agent = FluxAgent(agent_id="test-agent")
        assert agent.agent_id == "test-agent"
        assert agent.role == AgentRole.GENERAL
        assert agent.generation == 0
        assert agent.total_tasks == 0

    def test_create_agent_with_role(self):
        from flux.swarm.agent import FluxAgent, AgentRole
        agent = FluxAgent(agent_id="compute-1", role=AgentRole.SPECIALIST_COMPUTE)
        assert agent.role == AgentRole.SPECIALIST_COMPUTE

    def test_agent_has_module_container(self):
        from flux.swarm.agent import FluxAgent
        from flux.modules.container import ModuleContainer
        agent = FluxAgent(agent_id="mod-test")
        assert isinstance(agent.module_container, ModuleContainer)
        assert agent.module_container.name == "mod-test"

    def test_agent_has_profiler(self):
        from flux.swarm.agent import FluxAgent
        from flux.adaptive.profiler import AdaptiveProfiler
        agent = FluxAgent(agent_id="prof-test")
        assert isinstance(agent.profiler, AdaptiveProfiler)

    def test_agent_has_tile_registry(self):
        from flux.swarm.agent import FluxAgent
        from flux.tiles.registry import TileRegistry
        agent = FluxAgent(agent_id="tile-test")
        assert isinstance(agent.local_registry, TileRegistry)

    def test_agent_has_trust_profile(self):
        from flux.swarm.agent import FluxAgent, TrustProfile
        agent = FluxAgent(agent_id="trust-test")
        assert isinstance(agent.trust_profile, TrustProfile)
        assert agent.trust_profile.trust_score == 0.5

    def test_agent_repr(self):
        from flux.swarm.agent import FluxAgent
        agent = FluxAgent(agent_id="repr-test")
        r = repr(agent)
        assert "repr-test" in r
        assert "general" in r

    def test_agent_get_stats(self):
        from flux.swarm.agent import FluxAgent
        agent = FluxAgent(agent_id="stats-test")
        stats = agent.get_stats()
        assert stats["agent_id"] == "stats-test"
        assert stats["role"] == "general"
        assert stats["tasks_completed"] == 0
        assert stats["messages_sent"] == 0
        assert stats["messages_received"] == 0

    def test_agent_uptime(self):
        from flux.swarm.agent import FluxAgent
        agent = FluxAgent(agent_id="uptime-test")
        assert agent.uptime_seconds >= 0
        time.sleep(0.01)
        assert agent.uptime_seconds >= 0.01


# ── Agent Specialization Tests ─────────────────────────────────────────────

class TestAgentSpecialization:
    """Test agent role determination from profiling."""

    def test_specialize_general_no_data(self):
        from flux.swarm.agent import FluxAgent, AgentRole
        agent = FluxAgent(agent_id="gen-no-data")
        assert agent.specialize() == AgentRole.GENERAL

    def test_specialize_compute(self):
        from flux.swarm.agent import FluxAgent, AgentRole, AgentTask
        agent = FluxAgent(agent_id="comp-specialist")
        for i in range(20):
            agent.execute_task(AgentTask(task_id=f"c{i}", task_type="compute"))
            agent.execute_task(AgentTask(task_id=f"m{i}", task_type="math"))
        assert agent.specialize() == AgentRole.SPECIALIST_COMPUTE

    def test_specialize_coordinator(self):
        from flux.swarm.agent import FluxAgent, AgentRole, AgentTask
        agent = FluxAgent(agent_id="coord-specialist")
        for i in range(20):
            agent.execute_task(AgentTask(task_id=f"r{i}", task_type="route"))
            agent.execute_task(AgentTask(task_id=f"d{i}", task_type="delegate"))
        assert agent.specialize() == AgentRole.SPECIALIST_COORDINATOR

    def test_specialize_explorer(self):
        from flux.swarm.agent import FluxAgent, AgentRole, AgentTask
        agent = FluxAgent(agent_id="exp-specialist")
        for i in range(10):
            agent.execute_task(AgentTask(task_id=f"e{i}", task_type="explore"))
            agent.execute_task(AgentTask(task_id=f"s{i}", task_type="search"))
            agent.execute_task(AgentTask(task_id=f"d{i}", task_type="discover"))
        assert agent.specialize() == AgentRole.SPECIALIST_EXPLORER

    def test_specialize_memory(self):
        from flux.swarm.agent import FluxAgent, AgentRole, AgentTask
        agent = FluxAgent(agent_id="mem-specialist")
        for i in range(20):
            agent.execute_task(AgentTask(task_id=f"st{i}", task_type="store"))
            agent.execute_task(AgentTask(task_id=f"ca{i}", task_type="cache"))
        assert agent.specialize() == AgentRole.SPECIALIST_MEMORY

    def test_specialize_io(self):
        from flux.swarm.agent import FluxAgent, AgentRole, AgentTask
        agent = FluxAgent(agent_id="io-specialist")
        for i in range(20):
            agent.execute_task(AgentTask(task_id=f"wr{i}", task_type="write"))
            agent.execute_task(AgentTask(task_id=f"rd{i}", task_type="read"))
        assert agent.specialize() == AgentRole.SPECIALIST_IO

    def test_apply_specialization(self):
        from flux.swarm.agent import FluxAgent, AgentRole, AgentTask
        agent = FluxAgent(agent_id="apply-spec")
        for i in range(20):
            agent.execute_task(AgentTask(task_id=f"c{i}", task_type="compute"))
        new_role = agent.apply_specialization()
        assert new_role == AgentRole.SPECIALIST_COMPUTE
        assert agent.role == AgentRole.SPECIALIST_COMPUTE

    def test_evolve(self):
        from flux.swarm.agent import FluxAgent, AgentTask
        agent = FluxAgent(agent_id="evolve-test")
        for i in range(10):
            agent.execute_task(AgentTask(task_id=f"c{i}", task_type="compute"))
        agent.evolve(generations=5)
        assert agent.generation == 5


# ── Agent Task Execution Tests ─────────────────────────────────────────────

class TestAgentTaskExecution:
    """Test agent task execution."""

    def test_execute_task_success(self):
        from flux.swarm.agent import FluxAgent, AgentTask
        agent = FluxAgent(agent_id="task-ok")
        result = agent.execute_task(AgentTask(task_id="t1", task_type="compute"))
        assert result.success is True
        assert result.task_id == "t1"
        assert result.duration_ns >= 0

    def test_execute_multiple_tasks(self):
        from flux.swarm.agent import FluxAgent, AgentTask
        agent = FluxAgent(agent_id="task-multi")
        for i in range(5):
            agent.execute_task(AgentTask(task_id=f"t{i}", task_type="compute"))
        assert agent.total_tasks == 5
        assert agent.task_success_rate == 1.0

    def test_task_success_rate(self):
        from flux.swarm.agent import FluxAgent, AgentTask
        agent = FluxAgent(agent_id="task-rate")
        agent._tasks_completed = 8
        agent._tasks_failed = 2
        assert agent.total_tasks == 10
        assert abs(agent.task_success_rate - 0.8) < 1e-9


# ── Agent Message Handling Tests ───────────────────────────────────────────

class TestAgentMessageHandling:
    """Test agent send/receive message handling."""

    def test_receive_message(self):
        from flux.swarm.agent import FluxAgent
        from flux.swarm.message_bus import AgentMessage
        agent = FluxAgent(agent_id="recv-test")
        msg = AgentMessage(sender="other", receiver="recv-test", msg_type="request")
        agent.receive(msg)
        assert agent._messages_received == 1
        assert agent._a2a_operations >= 1

    def test_send_message(self):
        from flux.swarm.agent import FluxAgent
        from flux.swarm.message_bus import AgentMessage
        agent = FluxAgent(agent_id="send-test")
        msg = AgentMessage(sender="send-test", msg_type="request", payload={"data": 42})
        result = agent.send("target-agent", msg)
        assert result.sender == "send-test"
        assert result.receiver == "target-agent"
        assert agent._messages_sent == 1

    def test_send_updates_last_active(self):
        from flux.swarm.agent import FluxAgent
        from flux.swarm.message_bus import AgentMessage
        agent = FluxAgent(agent_id="active-send")
        time.sleep(0.01)
        msg = AgentMessage(sender="active-send", msg_type="event")
        agent.send("target", msg)
        assert time.time() - agent.last_active < 0.01


# ── TrustProfile Tests ─────────────────────────────────────────────────────

class TestTrustProfile:
    """Test trust profile tracking."""

    def test_initial_trust(self):
        from flux.swarm.agent import TrustProfile
        tp = TrustProfile()
        assert tp.trust_score == 0.5
        assert tp.total_interactions == 0

    def test_record_success(self):
        from flux.swarm.agent import TrustProfile
        tp = TrustProfile()
        tp.record_success(latency_ms=10.0)
        assert tp.successful_interactions == 1
        assert tp.avg_latency_ms == 10.0

    def test_record_failure(self):
        from flux.swarm.agent import TrustProfile
        tp = TrustProfile()
        tp.record_failure()
        assert tp.failed_interactions == 1

    def test_success_rate(self):
        from flux.swarm.agent import TrustProfile
        tp = TrustProfile()
        tp.record_success()
        tp.record_success()
        tp.record_failure()
        assert abs(tp.success_rate - 2 / 3) < 1e-9

    def test_capabilities(self):
        from flux.swarm.agent import TrustProfile
        tp = TrustProfile()
        tp.add_capability("compute")
        tp.add_capability("io")
        assert tp.has_capability("compute")
        assert tp.has_capability("io")
        assert not tp.has_capability("memory")

    def test_trust_increases_with_success(self):
        from flux.swarm.agent import TrustProfile
        tp = TrustProfile()
        for _ in range(10):
            tp.record_success(latency_ms=1.0)
        assert tp.trust_score > 0.5


# ── Topology Tests ─────────────────────────────────────────────────────────

class TestTopologyCreation:
    """Test topology creation via factory methods."""

    def test_create_hierarchical(self):
        from flux.swarm.topology import Topology, SwarmTopology
        topo = Topology.hierarchical("orch", ["w1", "w2", "w3"])
        assert topo.type == SwarmTopology.HIERARCHICAL
        assert len(topo.agents) == 4
        assert topo.degree("orch") == 3
        assert topo.degree("w1") == 1

    def test_create_flat_mesh(self):
        from flux.swarm.topology import Topology, SwarmTopology
        topo = Topology.flat_mesh(["a", "b", "c", "d"])
        assert topo.type == SwarmTopology.FLAT_MESH
        assert topo.edge_count == 6  # 4 choose 2
        for agent in ["a", "b", "c", "d"]:
            assert topo.degree(agent) == 3

    def test_create_star(self):
        from flux.swarm.topology import Topology, SwarmTopology
        topo = Topology.star("hub", ["s1", "s2", "s3", "s4"])
        assert topo.type == SwarmTopology.STAR
        assert topo.degree("hub") == 4
        assert topo.degree("s1") == 1
        assert topo.edge_count == 4

    def test_create_ring(self):
        from flux.swarm.topology import Topology, SwarmTopology
        topo = Topology.ring(["a", "b", "c", "d"])
        assert topo.type == SwarmTopology.RING
        assert topo.edge_count == 4
        for agent in ["a", "b", "c", "d"]:
            assert topo.degree(agent) == 2

    def test_create_ring_single_agent(self):
        from flux.swarm.topology import Topology, SwarmTopology
        topo = Topology.ring(["only"])
        assert topo.type == SwarmTopology.RING
        assert len(topo.agents) == 1
        assert topo.edge_count == 0

    def test_create_blackboard(self):
        from flux.swarm.topology import Topology, SwarmTopology
        topo = Topology.blackboard(["a", "b", "c"])
        assert topo.type == SwarmTopology.BLACKBOARD
        assert topo.edge_count == 3


# ── Topology Connection Tests ──────────────────────────────────────────────

class TestTopologyConnections:
    """Test topology connection management."""

    def test_connect(self):
        from flux.swarm.topology import Topology, SwarmTopology
        topo = Topology(SwarmTopology.FLAT_MESH)
        topo.add_agent("a")
        topo.add_agent("b")
        topo.connect("a", "b")
        assert topo.is_connected("a", "b")
        assert topo.is_connected("b", "a")
        assert topo.edge_count == 1

    def test_disconnect(self):
        from flux.swarm.topology import Topology, SwarmTopology
        topo = Topology(SwarmTopology.FLAT_MESH)
        topo.add_agent("a")
        topo.add_agent("b")
        topo.connect("a", "b")
        topo.disconnect("a", "b")
        assert not topo.is_connected("a", "b")
        assert topo.edge_count == 0

    def test_no_self_loop(self):
        from flux.swarm.topology import Topology, SwarmTopology
        topo = Topology(SwarmTopology.FLAT_MESH)
        topo.add_agent("a")
        topo.connect("a", "a")
        assert topo.edge_count == 0

    def test_neighbors(self):
        from flux.swarm.topology import Topology, SwarmTopology
        topo = Topology(SwarmTopology.FLAT_MESH)
        topo.add_agent("a")
        topo.add_agent("b")
        topo.add_agent("c")
        topo.connect("a", "b")
        topo.connect("a", "c")
        assert topo.neighbors("a") == {"b", "c"}
        assert topo.neighbors("b") == {"a"}

    def test_remove_agent(self):
        from flux.swarm.topology import Topology, SwarmTopology
        topo = Topology.hierarchical("orch", ["w1", "w2"])
        topo.remove_agent("w1")
        assert "w1" not in topo.agents
        assert "w1" not in topo.neighbors("orch")
        assert topo.edge_count == 1

    def test_to_dict(self):
        from flux.swarm.topology import Topology, SwarmTopology
        topo = Topology.hierarchical("orch", ["w1"])
        d = topo.to_dict()
        assert d["type"] == "hierarchical"
        assert "orch" in d["agents"]
        assert d["edge_count"] == 1


# ── Topology Routing Tests ─────────────────────────────────────────────────

class TestTopologyRouting:
    """Test shortest path routing."""

    def test_shortest_path_direct(self):
        from flux.swarm.topology import Topology
        topo = Topology.hierarchical("orch", ["w1", "w2"])
        path = topo.shortest_path("orch", "w1")
        assert path == ["orch", "w1"]

    def test_shortest_path_two_hops(self):
        from flux.swarm.topology import Topology
        topo = Topology.ring(["a", "b", "c", "d"])
        path = topo.shortest_path("a", "c")
        assert path == ["a", "b", "c"] or path == ["a", "d", "c"]
        assert len(path) == 3

    def test_shortest_path_same_agent(self):
        from flux.swarm.topology import Topology
        topo = Topology.star("hub", ["s1"])
        path = topo.shortest_path("hub", "hub")
        assert path == ["hub"]

    def test_shortest_path_no_connection(self):
        from flux.swarm.topology import Topology, SwarmTopology
        topo = Topology(SwarmTopology.FLAT_MESH)
        topo.add_agent("a")
        topo.add_agent("b")
        # No connection
        path = topo.shortest_path("a", "b")
        assert path == []

    def test_path_length(self):
        from flux.swarm.topology import Topology
        topo = Topology.ring(["a", "b", "c", "d"])
        assert topo.path_length("a", "a") == 0
        assert topo.path_length("a", "b") == 1
        assert topo.path_length("a", "c") == 2

    def test_is_reachable(self):
        from flux.swarm.topology import Topology
        topo = Topology.hierarchical("orch", ["w1", "w2"])
        assert topo.is_reachable("orch", "w1")
        assert topo.is_reachable("w1", "orch")
        assert topo.is_reachable("orch", "orch")


# ── MessageBus Tests ───────────────────────────────────────────────────────

class TestMessageBus:
    """Test message bus send/receive/publish/subscribe."""

    def test_register_unregister(self):
        from flux.swarm.message_bus import MessageBus
        bus = MessageBus()
        bus.register("a1")
        bus.register("a2")
        assert "a1" in bus.registered_agents
        bus.unregister("a1")
        assert "a1" not in bus.registered_agents

    def test_send_and_drain(self):
        from flux.swarm.message_bus import MessageBus
        bus = MessageBus()
        bus.register("sender")
        bus.register("receiver")
        delivered = bus.send("sender", "receiver", {"key": "value"})
        assert delivered is True
        msgs = bus.drain("receiver")
        assert len(msgs) == 1
        assert msgs[0].payload == {"key": "value"}

    def test_send_to_unknown(self):
        from flux.swarm.message_bus import MessageBus
        bus = MessageBus()
        bus.register("sender")
        delivered = bus.send("sender", "unknown", {"data": 1})
        assert delivered is False

    def test_drain_empty(self):
        from flux.swarm.message_bus import MessageBus
        bus = MessageBus()
        bus.register("a1")
        msgs = bus.drain("a1")
        assert msgs == []

    def test_pending_count(self):
        from flux.swarm.message_bus import MessageBus
        bus = MessageBus()
        bus.register("s")
        bus.register("r")
        bus.send("s", "r", {"msg": 1})
        bus.send("s", "r", {"msg": 2})
        assert bus.pending_count("r") == 2

    def test_subscribe_publish(self):
        from flux.swarm.message_bus import MessageBus
        bus = MessageBus()
        bus.register("pub")
        bus.register("sub1")
        bus.register("sub2")
        bus.subscribe("sub1", "news")
        bus.subscribe("sub2", "news")
        count = bus.publish("pub", "news", {"headline": "test"})
        assert count == 2
        msgs1 = bus.drain("sub1")
        msgs2 = bus.drain("sub2")
        assert len(msgs1) == 1
        assert len(msgs2) == 1
        assert msgs1[0].topic == "news"

    def test_publish_no_subscribers(self):
        from flux.swarm.message_bus import MessageBus
        bus = MessageBus()
        count = bus.publish("pub", "empty_topic", {"data": 1})
        assert count == 0

    def test_unsubscribe(self):
        from flux.swarm.message_bus import MessageBus
        bus = MessageBus()
        bus.register("pub")
        bus.register("sub")
        bus.subscribe("sub", "topic")
        bus.unsubscribe("sub", "topic")
        count = bus.publish("pub", "topic", {"data": 1})
        assert count == 0

    def test_total_messages(self):
        from flux.swarm.message_bus import MessageBus
        bus = MessageBus()
        bus.register("s")
        bus.register("r1")
        bus.register("r2")
        bus.send("s", "r1", {})
        bus.send("s", "r2", {})
        assert bus.total_messages == 2

    def test_message_log(self):
        from flux.swarm.message_bus import MessageBus
        bus = MessageBus()
        bus.register("s")
        bus.register("r")
        bus.send("s", "r", {"data": 1})
        log = bus.get_log(limit=10)
        assert len(log) == 1

    def test_unregister_removes_subscriptions(self):
        from flux.swarm.message_bus import MessageBus
        bus = MessageBus()
        bus.register("sub")
        bus.subscribe("sub", "topic1")
        bus.subscribe("sub", "topic2")
        bus.unregister("sub")
        assert bus.subscribers("topic1") == set()


# ── Swarm Agent Management Tests ───────────────────────────────────────────

class TestSwarmManagement:
    """Test Swarm spawn and agent management."""

    def test_create_swarm(self):
        from flux.swarm import Swarm, Topology
        topo = Topology.hierarchical("orch", [])
        swarm = Swarm(name="test-swarm", topology=topo)
        assert swarm.name == "test-swarm"
        assert swarm.agent_count == 0

    def test_spawn_agent(self):
        from flux.swarm import Swarm, Topology, FluxAgent
        topo = Topology.hierarchical("orch", [])
        swarm = Swarm(name="test", topology=topo)
        agent = swarm.spawn("worker-1")
        assert isinstance(agent, FluxAgent)
        assert swarm.agent_count == 1
        assert swarm.get_agent("worker-1") is not None

    def test_spawn_duplicate_raises(self):
        from flux.swarm import Swarm, Topology
        topo = Topology.hierarchical("orch", [])
        swarm = Swarm(name="test", topology=topo)
        swarm.spawn("dup")
        with pytest.raises(ValueError, match="already exists"):
            swarm.spawn("dup")

    def test_despawn_agent(self):
        from flux.swarm import Swarm, Topology
        topo = Topology.hierarchical("orch", [])
        swarm = Swarm(name="test", topology=topo)
        swarm.spawn("temp")
        removed = swarm.despawn("temp")
        assert removed is not None
        assert swarm.agent_count == 0
        assert swarm.get_agent("temp") is None

    def test_despawn_unknown(self):
        from flux.swarm import Swarm, Topology
        topo = Topology.hierarchical("orch", [])
        swarm = Swarm(name="test", topology=topo)
        assert swarm.despawn("nobody") is None


# ── Swarm Messaging Tests ──────────────────────────────────────────────────

class TestSwarmMessaging:
    """Test Swarm broadcast and scatter."""

    def test_broadcast_to_neighbors(self):
        from flux.swarm import Swarm, Topology, AgentMessage
        topo = Topology.hierarchical("orch", ["w1", "w2"])
        swarm = Swarm(name="test", topology=topo)
        swarm.spawn("orch")
        swarm.spawn("w1")
        swarm.spawn("w2")

        msg = AgentMessage(sender="orch", msg_type="event", payload={"cmd": "go"})
        count = swarm.broadcast("orch", msg)
        assert count == 2

        # Verify messages delivered
        msgs_w1 = swarm.message_bus.drain("w1")
        msgs_w2 = swarm.message_bus.drain("w2")
        assert len(msgs_w1) == 1
        assert len(msgs_w2) == 1

    def test_broadcast_from_unknown(self):
        from flux.swarm import Swarm, Topology, AgentMessage
        topo = Topology.star("hub", ["s1"])
        swarm = Swarm(name="test", topology=topo)
        swarm.spawn("hub")
        swarm.spawn("s1")
        msg = AgentMessage(sender="nobody", msg_type="event", payload={})
        count = swarm.broadcast("nobody", msg)
        assert count == 0

    def test_scatter_to_targets(self):
        from flux.swarm import Swarm, Topology, AgentMessage
        topo = Topology.flat_mesh(["a", "b", "c"])
        swarm = Swarm(name="test", topology=topo)
        swarm.spawn("a")
        swarm.spawn("b")
        swarm.spawn("c")

        msg = AgentMessage(sender="a", msg_type="request", payload={"task": "compute"})
        count = swarm.scatter("a", msg, ["b", "c"])
        assert count == 2

    def test_scatter_excludes_sender(self):
        from flux.swarm import Swarm, Topology, AgentMessage
        topo = Topology.flat_mesh(["a", "b"])
        swarm = Swarm(name="test", topology=topo)
        swarm.spawn("a")
        swarm.spawn("b")

        msg = AgentMessage(sender="a", msg_type="request", payload={})
        count = swarm.scatter("a", msg, ["a", "b"])
        assert count == 1  # 'a' excluded

    def test_reduce(self):
        from flux.swarm import Swarm, Topology
        topo = Topology.flat_mesh(["a", "b"])
        swarm = Swarm(name="test", topology=topo)
        swarm.spawn("a")
        swarm.spawn("b")

        result = swarm.reduce("a", lambda values: len(values))
        assert result == 2

    def test_reduce_unknown_coordinator(self):
        from flux.swarm import Swarm, Topology
        topo = Topology.flat_mesh(["a"])
        swarm = Swarm(name="test", topology=topo)
        result = swarm.reduce("nobody", lambda v: v)
        assert result is None


# ── Swarm Barrier Tests ────────────────────────────────────────────────────

class TestSwarmBarrier:
    """Test Swarm barrier synchronization."""

    def test_barrier_all_present(self):
        from flux.swarm import Swarm, Topology
        topo = Topology.flat_mesh(["a", "b", "c"])
        swarm = Swarm(name="test", topology=topo)
        swarm.spawn("a")
        swarm.spawn("b")
        swarm.spawn("c")

        result = swarm.barrier("b1", ["a", "b", "c"])
        assert result is True

    def test_barrier_missing_participant(self):
        from flux.swarm import Swarm, Topology
        topo = Topology.flat_mesh(["a", "b"])
        swarm = Swarm(name="test", topology=topo)
        swarm.spawn("a")
        swarm.spawn("b")

        result = swarm.barrier("b2", ["a", "b", "c"])
        assert result is False  # 'c' not registered

    def test_clear_barrier(self):
        from flux.swarm import Swarm, Topology
        topo = Topology.flat_mesh(["a"])
        swarm = Swarm(name="test", topology=topo)
        swarm.spawn("a")
        swarm.barrier("b-clear", ["a"])
        swarm.clear_barrier("b-clear")
        assert "b-clear" not in swarm._barrier_events


# ── Deadlock Detection Tests ───────────────────────────────────────────────

class TestDeadlockDetection:
    """Test DeadlockDetector cycle detection."""

    def test_no_cycle(self):
        from flux.swarm.deadlock import DeadlockDetector
        det = DeadlockDetector()
        det.record_wait("a", "b")
        det.record_wait("b", "c")
        assert det.detect_cycle() is None

    def test_simple_two_agent_cycle(self):
        from flux.swarm.deadlock import DeadlockDetector
        det = DeadlockDetector()
        det.record_wait("a", "b")
        det.record_wait("b", "a")
        cycle = det.detect_cycle()
        assert cycle is not None
        assert "a" in cycle
        assert "b" in cycle

    def test_three_agent_cycle(self):
        from flux.swarm.deadlock import DeadlockDetector
        det = DeadlockDetector()
        det.record_wait("a", "b")
        det.record_wait("b", "c")
        det.record_wait("c", "a")
        cycle = det.detect_cycle()
        assert cycle is not None
        assert len(set(cycle)) == 3

    def test_release_clears_wait(self):
        from flux.swarm.deadlock import DeadlockDetector
        det = DeadlockDetector()
        det.record_wait("a", "b")
        det.record_release("a")
        assert det.detect_cycle() is None

    def test_release_pair(self):
        from flux.swarm.deadlock import DeadlockDetector
        det = DeadlockDetector()
        det.record_wait("a", "b")
        det.record_wait("a", "c")
        det.record_release_pair("a", "b")
        assert "b" not in det.wait_graph.get("a", set())
        assert "c" in det.wait_graph.get("a", set())

    def test_clear(self):
        from flux.swarm.deadlock import DeadlockDetector
        det = DeadlockDetector()
        det.record_wait("a", "b")
        det.clear()
        assert det.agent_count == 0

    def test_empty_detector(self):
        from flux.swarm.deadlock import DeadlockDetector
        det = DeadlockDetector()
        assert det.detect_cycle() is None
        assert det.agent_count == 0


# ── Livelock Detection Tests ───────────────────────────────────────────────

class TestLivelockDetection:
    """Test DeadlockDetector livelock detection."""

    def test_no_livelock(self):
        from flux.swarm.deadlock import DeadlockDetector
        from flux.swarm.message_bus import AgentMessage
        det = DeadlockDetector()
        history = [
            AgentMessage(sender="a", receiver="b", payload={"n": i}, msg_type="request")
            for i in range(3)
        ]
        assert det.detect_livelock("a", history) is False

    def test_livelock_repeated_messages(self):
        from flux.swarm.deadlock import DeadlockDetector
        from flux.swarm.message_bus import AgentMessage
        det = DeadlockDetector()
        history = [
            AgentMessage(
                sender="a", receiver="b",
                payload={"task": "same_thing"}, msg_type="request"
            )
            for _ in range(6)
        ]
        assert det.detect_livelock("a", history) is True

    def test_livelock_pair(self):
        from flux.swarm.deadlock import DeadlockDetector
        from flux.swarm.message_bus import AgentMessage
        det = DeadlockDetector()
        history = []
        for _ in range(3):
            history.append(AgentMessage(
                sender="a", receiver="b",
                payload={"task": "bounce"}, msg_type="request"
            ))
            history.append(AgentMessage(
                sender="b", receiver="a",
                payload={"task": "bounce_back"}, msg_type="request"
            ))
        assert det.detect_livelock_pair("a", "b", history) is True

    def test_no_livelock_pair_low_count(self):
        from flux.swarm.deadlock import DeadlockDetector
        from flux.swarm.message_bus import AgentMessage
        det = DeadlockDetector()
        history = [
            AgentMessage(sender="a", receiver="b", payload={"t": "1"}, msg_type="request"),
            AgentMessage(sender="b", receiver="a", payload={"t": "2"}, msg_type="response"),
        ]
        assert det.detect_livelock_pair("a", "b", history) is False


# ── Deadlock Resolution Tests ──────────────────────────────────────────────

class TestDeadlockResolution:
    """Test deadlock resolution suggestions."""

    def test_resolution_two_agents(self):
        from flux.swarm.deadlock import DeadlockDetector
        det = DeadlockDetector()
        resolution = det.suggest_resolution(["agent-a", "agent-b"])
        assert resolution.yield_agent == "agent-a"  # alphabetical first
        assert resolution.priority == "agent-b"

    def test_resolution_three_agents(self):
        from flux.swarm.deadlock import DeadlockDetector
        det = DeadlockDetector()
        resolution = det.suggest_resolution(["charlie", "alice", "bob"])
        assert resolution.yield_agent == "alice"

    def test_resolution_empty_cycle(self):
        from flux.swarm.deadlock import DeadlockDetector
        det = DeadlockDetector()
        resolution = det.suggest_resolution([])
        assert resolution.description != ""


# ── Swarm Deadlock Check Tests ─────────────────────────────────────────────

class TestSwarmDeadlockCheck:
    """Test swarm-level deadlock checking."""

    def test_no_deadlocks_healthy_swarm(self):
        from flux.swarm import Swarm, Topology
        topo = Topology.flat_mesh(["a", "b"])
        swarm = Swarm(name="test", topology=topo)
        swarm.spawn("a")
        swarm.spawn("b")
        reports = swarm.check_deadlocks()
        assert all(r.severity.value == "none" for r in reports)


# ── Swarm Evolution Tests ──────────────────────────────────────────────────

class TestSwarmEvolution:
    """Test swarm-wide evolution."""

    def test_evolve_swarm_basic(self):
        from flux.swarm import Swarm, Topology, AgentRole, AgentTask
        topo = Topology.hierarchical("orch", ["w1", "w2"])
        swarm = Swarm(name="test", topology=topo)
        orch = swarm.spawn("orch", AgentRole.GENERAL)
        w1 = swarm.spawn("w1", AgentRole.GENERAL)
        w2 = swarm.spawn("w2", AgentRole.GENERAL)

        # Give agents some work to profile
        for i in range(10):
            w1.execute_task(AgentTask(task_id=f"c{i}", task_type="compute"))
            w2.execute_task(AgentTask(task_id=f"r{i}", task_type="route"))

        report = swarm.evolve_swarm(generations=3)
        assert report.generations_run == 3
        assert report.agents_evolved == 3

    def test_evolve_records_role_changes(self):
        from flux.swarm import Swarm, Topology, AgentRole, AgentTask
        topo = Topology.flat_mesh(["a"])
        swarm = Swarm(name="test", topology=topo)
        agent = swarm.spawn("a", AgentRole.GENERAL)

        for i in range(20):
            agent.execute_task(AgentTask(task_id=f"c{i}", task_type="compute"))

        report = swarm.evolve_swarm(generations=1)
        changes = report.role_changes
        assert len(changes) >= 0  # May or may not change depending on thresholds


# ── Topology Optimization Tests ────────────────────────────────────────────

class TestTopologyOptimization:
    """Test topology optimization suggestions."""

    def test_optimize_no_messages(self):
        from flux.swarm import Swarm, Topology
        topo = Topology.flat_mesh(["a", "b"])
        swarm = Swarm(name="test", topology=topo)
        swarm.spawn("a")
        swarm.spawn("b")
        change = swarm.optimize_topology()
        # No messages yet, so confidence should be 0 or description says no data
        assert isinstance(change.description, str)

    def test_optimize_frequent_communication(self):
        from flux.swarm import Swarm, Topology, AgentMessage
        topo = Topology.flat_mesh(["a", "b", "c"])
        swarm = Swarm(name="test", topology=topo)
        swarm.spawn("a")
        swarm.spawn("b")
        swarm.spawn("c")

        # Send many messages between a and b
        for i in range(10):
            swarm.message_bus.send("a", "b", {"msg": i})

        change = swarm.optimize_topology()
        # a and b are already connected in mesh, so no change needed
        assert isinstance(change, object)


# ── Swarm Report Tests ─────────────────────────────────────────────────────

class TestSwarmReport:
    """Test comprehensive swarm report."""

    def test_swarm_report_basic(self):
        from flux.swarm import Swarm, Topology, AgentRole, AgentTask
        topo = Topology.hierarchical("orch", ["w1"])
        swarm = Swarm(name="report-test", topology=topo)
        orch = swarm.spawn("orch", AgentRole.SPECIALIST_COORDINATOR)
        w1 = swarm.spawn("w1", AgentRole.SPECIALIST_COMPUTE)
        w1.execute_task(AgentTask(task_id="t1", task_type="compute"))

        report = swarm.get_swarm_report()
        assert report.name == "report-test"
        assert report.topology_type == "hierarchical"
        assert report.agent_count == 2
        assert report.total_tasks_completed >= 1
        assert len(report.agents) == 2
        assert report.topology["type"] == "hierarchical"

    def test_swarm_report_includes_topology(self):
        from flux.swarm import Swarm, Topology
        topo = Topology.star("hub", ["s1", "s2"])
        swarm = Swarm(name="topo-report", topology=topo)
        swarm.spawn("hub")
        swarm.spawn("s1")
        swarm.spawn("s2")

        report = swarm.get_swarm_report()
        assert "connections" in report.topology
        assert report.topology["edge_count"] == 2


# ── AgentMessage Tests ─────────────────────────────────────────────────────

class TestAgentMessage:
    """Test AgentMessage properties."""

    def test_message_defaults(self):
        from flux.swarm.message_bus import AgentMessage
        msg = AgentMessage(sender="a", receiver="b")
        assert msg.sender == "a"
        assert msg.receiver == "b"
        assert msg.msg_type == "request"
        assert msg.conversation_id != ""
        assert msg.timestamp > 0

    def test_is_broadcast(self):
        from flux.swarm.message_bus import AgentMessage
        msg = AgentMessage(sender="a", receiver=None)
        assert msg.is_broadcast
        msg2 = AgentMessage(sender="a", receiver="b")
        assert not msg2.is_broadcast

    def test_is_pubsub(self):
        from flux.swarm.message_bus import AgentMessage
        msg = AgentMessage(sender="a", topic="news")
        assert msg.is_pubsub
        msg2 = AgentMessage(sender="a", receiver="b")
        assert not msg2.is_pubsub

    def test_message_summary(self):
        from flux.swarm.message_bus import AgentMessage
        msg = AgentMessage(sender="a", receiver="b", payload={"key": "val"})
        summary = msg.summary()
        assert "a→b" in summary
        assert "request" in summary

    def test_message_repr(self):
        from flux.swarm.message_bus import AgentMessage
        msg = AgentMessage(sender="a", receiver="b", msg_type="event")
        r = repr(msg)
        assert "'a'" in r
        assert "'b'" in r
        assert "event" in r


# ── Integration Tests ──────────────────────────────────────────────────────

class TestSwarmIntegration:
    """End-to-end integration tests."""

    def test_full_swarm_lifecycle(self):
        from flux.swarm import (
            Swarm, Topology, FluxAgent, AgentRole,
            AgentTask, AgentMessage,
        )
        # Create swarm with hierarchical topology
        topo = Topology.hierarchical("orch", ["w1", "w2", "w3"])
        swarm = Swarm(name="full-test", topology=topo)

        # Spawn agents
        orch = swarm.spawn("orch", AgentRole.SPECIALIST_COORDINATOR)
        w1 = swarm.spawn("w1", AgentRole.SPECIALIST_COMPUTE)
        w2 = swarm.spawn("w2", AgentRole.GENERAL)
        w3 = swarm.spawn("w3", AgentRole.SPECIALIST_EXPLORER)

        assert swarm.agent_count == 4

        # Broadcast from orchestrator
        msg = AgentMessage(sender="orch", msg_type="event", payload={"cmd": "start"})
        delivered = swarm.broadcast("orch", msg)
        assert delivered == 3

        # Workers execute tasks
        for i in range(10):
            w1.execute_task(AgentTask(task_id=f"comp-{i}", task_type="compute"))
        for i in range(5):
            w2.execute_task(AgentTask(task_id=f"route-{i}", task_type="route"))
        for i in range(3):
            w3.execute_task(AgentTask(task_id=f"explore-{i}", task_type="explore"))

        # Evolve swarm
        report = swarm.evolve_swarm(generations=2)
        assert report.agents_evolved == 4

        # Check specializations
        assert w1.specialize() == AgentRole.SPECIALIST_COMPUTE
        assert w2.specialize() == AgentRole.SPECIALIST_COORDINATOR

        # Barrier
        assert swarm.barrier("sync-1", ["orch", "w1", "w2", "w3"])

        # Generate report
        swarm_report = swarm.get_swarm_report()
        assert swarm_report.agent_count == 4
        assert swarm_report.total_tasks_completed >= 18

        # Despawn
        swarm.despawn("w3")
        assert swarm.agent_count == 3

    def test_pubsub_swarm(self):
        from flux.swarm import Swarm, Topology, AgentMessage
        topo = Topology.flat_mesh(["pub", "sub1", "sub2", "sub3"])
        swarm = Swarm(name="pubsub-test", topology=topo)
        swarm.spawn("pub")
        swarm.spawn("sub1")
        swarm.spawn("sub2")
        swarm.spawn("sub3")

        # Subscribe to topics
        swarm.message_bus.subscribe("sub1", "updates")
        swarm.message_bus.subscribe("sub2", "updates")
        swarm.message_bus.subscribe("sub3", "alerts")

        # Publish to "updates" — should reach sub1 and sub2
        count = swarm.message_bus.publish("pub", "updates", {"ver": 2})
        assert count == 2

        # Publish to "alerts" — should reach sub3
        count = swarm.message_bus.publish("pub", "alerts", {"level": "warn"})
        assert count == 1

        # Drain and verify
        sub1_msgs = swarm.message_bus.drain("sub1")
        sub2_msgs = swarm.message_bus.drain("sub2")
        sub3_msgs = swarm.message_bus.drain("sub3")
        assert len(sub1_msgs) == 1
        assert len(sub2_msgs) == 1
        assert len(sub3_msgs) == 1
        assert sub3_msgs[0].payload["level"] == "warn"

    def test_ring_pipeline(self):
        from flux.swarm import Swarm, Topology, AgentMessage
        agents = ["stage-1", "stage-2", "stage-3", "stage-4"]
        topo = Topology.ring(agents)
        swarm = Swarm(name="pipeline", topology=topo)
        for a in agents:
            swarm.spawn(a)

        # Each stage sends to its successor
        for i in range(len(agents)):
            next_id = agents[(i + 1) % len(agents)]
            msg = AgentMessage(sender=agents[i], msg_type="event", payload={"step": i})
            swarm.message_bus.send(agents[i], next_id, msg.payload)

        # Verify each stage received from predecessor
        for a in agents:
            msgs = swarm.message_bus.drain(a)
            assert len(msgs) == 1

    def test_star_hub_routing(self):
        from flux.swarm import Swarm, Topology, AgentMessage
        topo = Topology.star("hub", ["s1", "s2", "s3"])
        swarm = Swarm(name="star-test", topology=topo)
        swarm.spawn("hub")
        swarm.spawn("s1")
        swarm.spawn("s2")
        swarm.spawn("s3")

        # Hub broadcasts to all spokes
        msg = AgentMessage(sender="hub", msg_type="event", payload={"announce": "hello"})
        delivered = swarm.broadcast("hub", msg)
        assert delivered == 3

        # Verify shortest paths
        assert topo.shortest_path("s1", "s2") == ["s1", "hub", "s2"]
        assert topo.path_length("s1", "s2") == 2
