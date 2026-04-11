"""Tests for Semantic Routing Table."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from flux.open_interp.semantic_router import (
    SemanticRoutingTable, AgentKnowledge, AgentRole, VocabularyDomain
)


class TestAgentKnowledge:
    def test_knows_domain(self):
        ak = AgentKnowledge("test", AgentRole.VESSEL, "http://example.com")
        ak.domains["math"] = VocabularyDomain("math", 10, 0.9)
        assert ak.knows_domain("math")
        assert not ak.knows_domain("cuda")
    
    def test_domain_confidence(self):
        ak = AgentKnowledge("test", AgentRole.VESSEL, "http://example.com")
        ak.domains["math"] = VocabularyDomain("math", 10, 0.8)
        assert ak.domain_confidence("math") == 0.8
        assert ak.domain_confidence("unknown") == 0.0


class TestSemanticRoutingTable:
    def test_register_find(self):
        table = SemanticRoutingTable()
        ak = AgentKnowledge("test", AgentRole.SCOUT, "http://example.com")
        ak.domains["math"] = VocabularyDomain("math", 10, 0.9)
        table.register(ak)
        experts = table.find_expert("math")
        assert len(experts) == 1
        assert experts[0].agent_name == "test"
    
    def test_find_by_specialization(self):
        table = SemanticRoutingTable()
        ak = AgentKnowledge("test", AgentRole.SCOUT, "http://example.com",
                           specializations=["multilingual", "grammars"])
        table.register(ak)
        found = table.find_by_specialization("grammar")
        assert len(found) == 1
    
    def test_route_task(self):
        table = SemanticRoutingTable()
        ak1 = AgentKnowledge("agent1", AgentRole.LIGHTHOUSE, "http://a.com")
        ak1.domains["math"] = VocabularyDomain("math", 10, 0.9)
        ak1.domains["core"] = VocabularyDomain("core", 20, 0.95)
        ak2 = AgentKnowledge("agent2", AgentRole.VESSEL, "http://b.com")
        ak2.domains["math"] = VocabularyDomain("math", 5, 0.7)
        table.register(ak1)
        table.register(ak2)
        best = table.route_task(["math", "core"])
        assert best.agent_name == "agent1"
    
    def test_route_no_match(self):
        table = SemanticRoutingTable()
        ak = AgentKnowledge("test", AgentRole.SCOUT, "http://example.com")
        ak.domains["math"] = VocabularyDomain("math", 10, 0.9)
        table.register(ak)
        best = table.route_task(["cuda"])
        assert best is None
    
    def test_update_domain(self):
        table = SemanticRoutingTable()
        ak = AgentKnowledge("test", AgentRole.SCOUT, "http://example.com")
        table.register(ak)
        table.update_domain("test", "new_domain", entries=5, confidence=0.8, tags=["fresh"])
        assert ak.knows_domain("new_domain")
    
    def test_routing_report(self):
        table = SemanticRoutingTable()
        ak = AgentKnowledge("test", AgentRole.LIGHTHOUSE, "http://example.com",
                           specializations=["math"], vocab_count=100, test_count=50)
        ak.domains["math"] = VocabularyDomain("math", 50, 0.9)
        table.register(ak)
        report = table.routing_report()
        assert "test" in report
        assert "lighthouse" in report
    
    def test_unregister(self):
        table = SemanticRoutingTable()
        ak = AgentKnowledge("test", AgentRole.SCOUT, "http://example.com")
        table.register(ak)
        table.unregister("test")
        assert len(table.agents) == 0


class TestFleetRoutingTable:
    def test_fleet_table(self):
        table = SemanticRoutingTable.from_fleet()
        assert len(table.agents) == 3
        assert "Oracle1" in table.agents
        assert "JetsonClaw1" in table.agents
        assert "Babel" in table.agents
    
    def test_fleet_find_hardware_expert(self):
        table = SemanticRoutingTable.from_fleet()
        experts = table.find_expert("hardware")
        assert any(e.agent_name == "JetsonClaw1" for e in experts)
    
    def test_fleet_find_vocab_expert(self):
        table = SemanticRoutingTable.from_fleet()
        experts = table.find_expert("core")
        assert any(e.agent_name == "Oracle1" for e in experts)
    
    def test_fleet_find_multilingual_expert(self):
        table = SemanticRoutingTable.from_fleet()
        found = table.find_by_specialization("multilingual")
        assert any(f.agent_name == "Babel" for f in found)
    
    def test_fleet_route_isa_task(self):
        table = SemanticRoutingTable.from_fleet()
        # ISA design needs isa-design AND hardware knowledge
        best = table.route_task(["isa-design", "hardware"])
        assert best is not None
        assert best.agent_name == "JetsonClaw1"
    
    def test_fleet_route_vocab_task(self):
        table = SemanticRoutingTable.from_fleet()
        best = table.route_task(["core", "math"])
        assert best is not None
        assert best.agent_name == "Oracle1"
