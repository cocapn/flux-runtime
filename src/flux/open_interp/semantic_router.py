"""
Semantic Routing Table — Oracle1's map of which agent knows what vocabulary.

When a new vessel joins the fleet, the lighthouse updates its routing table.
When an agent signals new capabilities, the table updates.
When an agent's vocabulary is pruned, the table reflects the change.

This is the knowledge layer that JetsonClaw1 doesn't have —
he handles hardware routing, I handle semantic routing.
"""
import json
import time
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum


class AgentRole(Enum):
    LIGHTHOUSE = "lighthouse"
    VESSEL = "vessel"
    SCOUT = "scout"
    BARNACLE = "barnacle"
    GHOST = "ghost"


@dataclass
class VocabularyDomain:
    """A domain of vocabulary knowledge."""
    name: str
    entries: int = 0
    confidence: float = 1.0
    last_updated: float = 0.0
    tags: List[str] = field(default_factory=list)


@dataclass
class AgentKnowledge:
    """What an agent knows."""
    agent_name: str
    role: AgentRole
    repo: str
    last_seen: float = 0.0
    status: str = "active"
    domains: Dict[str, VocabularyDomain] = field(default_factory=dict)
    specializations: List[str] = field(default_factory=list)
    vocab_count: int = 0
    test_count: int = 0
    hardware_profile: Optional[dict] = None
    can_execute: Set[str] = field(default_factory=set)  # FLUX format names
    
    def knows_domain(self, domain: str) -> bool:
        return domain in self.domains
    
    def domain_confidence(self, domain: str) -> float:
        d = self.domains.get(domain)
        return d.confidence if d else 0.0
    
    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "role": self.role.value,
            "repo": self.repo,
            "last_seen": self.last_seen,
            "status": self.status,
            "domains": {k: {"entries": v.entries, "confidence": v.confidence,
                            "tags": v.tags} for k, v in self.domains.items()},
            "specializations": self.specializations,
            "vocab_count": self.vocab_count,
            "test_count": self.test_count,
            "can_execute": list(self.can_execute),
        }


class SemanticRoutingTable:
    """
    The lighthouse's map of which agent knows what.
    
    Used when:
    - A task comes in that needs a specific domain
    - An agent asks "who knows about X?"
    - A new vocabulary entry needs review by a domain expert
    - An agent needs to find a collaborator
    """
    
    def __init__(self):
        self.agents: Dict[str, AgentKnowledge] = {}
    
    def register(self, knowledge: AgentKnowledge) -> None:
        """Register or update an agent's knowledge."""
        self.agents[knowledge.agent_name] = knowledge
    
    def unregister(self, agent_name: str) -> None:
        """Remove an agent from the routing table."""
        self.agents.pop(agent_name, None)
    
    def find_expert(self, domain: str, min_confidence: float = 0.5) -> List[AgentKnowledge]:
        """Find agents that know a domain above a confidence threshold."""
        results = []
        for agent in self.agents.values():
            if agent.knows_domain(domain) and agent.domain_confidence(domain) >= min_confidence:
                results.append(agent)
        return sorted(results, key=lambda a: a.domain_confidence(domain), reverse=True)
    
    def find_by_specialization(self, keyword: str) -> List[AgentKnowledge]:
        """Find agents with a specialization matching a keyword."""
        keyword = keyword.lower()
        return [a for a in self.agents.values()
                if any(keyword in s.lower() for s in a.specializations)]
    
    def find_by_tag(self, tag: str) -> List[AgentKnowledge]:
        """Find agents with vocabulary tagged with a specific tag."""
        results = []
        for agent in self.agents.values():
            for domain in agent.domains.values():
                if tag in domain.tags:
                    results.append(agent)
                    break
        return results
    
    def route_task(self, required_domains: List[str], 
                   required_hardware: Optional[dict] = None) -> Optional[AgentKnowledge]:
        """Route a task to the best agent based on domain expertise and hardware."""
        candidates = list(self.agents.values())
        
        # Filter by domain knowledge
        for domain in required_domains:
            candidates = [c for c in candidates if c.knows_domain(domain)]
        
        if not candidates:
            return None
        
        # Filter by hardware if specified
        if required_hardware:
            filtered = []
            for c in candidates:
                if c.hardware_profile:
                    hw = c.hardware_profile
                    if required_hardware.get("gpu") and not hw.get("gpu"):
                        continue
                    if required_hardware.get("min_ram_mb", 0) > hw.get("ram_available_mb", 0):
                        continue
                    filtered.append(c)
            candidates = filtered if filtered else candidates
        
        # Score by total domain confidence
        def score(agent):
            return sum(agent.domain_confidence(d) for d in required_domains)
        
        return max(candidates, key=score) if candidates else None
    
    def update_domain(self, agent_name: str, domain: str, 
                      entries: int = 0, confidence: float = 1.0,
                      tags: Optional[List[str]] = None) -> bool:
        """Update an agent's domain knowledge."""
        agent = self.agents.get(agent_name)
        if not agent:
            return False
        agent.domains[domain] = VocabularyDomain(
            name=domain, entries=entries, confidence=confidence,
            last_updated=time.time(), tags=tags or []
        )
        return True
    
    def routing_report(self) -> str:
        """Generate a human-readable routing report."""
        lines = ["# Semantic Routing Table\n"]
        for name, agent in sorted(self.agents.items()):
            lines.append(f"## {name} ({agent.role.value})")
            lines.append(f"  Repo: {agent.repo}")
            lines.append(f"  Vocab: {agent.vocab_count}, Tests: {agent.test_count}")
            lines.append(f"  Specializations: {', '.join(agent.specializations)}")
            for dname, domain in agent.domains.items():
                lines.append(f"  Domain {dname}: {domain.entries} entries, confidence {domain.confidence:.1f}")
            lines.append("")
        return "\n".join(lines)
    
    def to_dict(self) -> dict:
        return {name: agent.to_dict() for name, agent in self.agents.items()}
    
    @classmethod
    def from_fleet(cls) -> 'SemanticRoutingTable':
        """Create a routing table with current fleet knowledge."""
        table = cls()
        
        # Oracle1 (self)
        oracle1 = AgentKnowledge(
            agent_name="Oracle1",
            role=AgentRole.LIGHTHOUSE,
            repo="https://github.com/SuperInstance/oracle1-vessel",
            specializations=["vocabulary", "runtime-architecture", "think-tank", "coordination"],
            vocab_count=3035,
            test_count=2258,
            can_execute={"python", "c", "rust", "go", "zig", "js"},
        )
        oracle1.domains = {
            "core": VocabularyDomain("core", 50, 0.95, tags=["essential", "control-flow"]),
            "math": VocabularyDomain("math", 40, 0.95, tags=["arithmetic", "sequences"]),
            "maritime": VocabularyDomain("maritime", 15, 0.8, tags=["domain"]),
            "a2a": VocabularyDomain("a2a", 20, 0.9, tags=["communication", "fleet"]),
            "paper-concepts": VocabularyDomain("paper-concepts", 2979, 0.6, tags=["research"]),
            "l0-primitives": VocabularyDomain("l0-primitives", 7, 0.95, tags=["constitutional"]),
        }
        table.register(oracle1)
        
        # JetsonClaw1
        jc1 = AgentKnowledge(
            agent_name="JetsonClaw1",
            role=AgentRole.VESSEL,
            repo="https://github.com/Lucineer/JetsonClaw1-vessel",
            specializations=["hardware", "c-runtime", "cuda", "rust-crates", "fleet-infrastructure"],
            vocab_count=1687,
            test_count=65,
            can_execute={"c", "rust", "go"},
            hardware_profile={
                "device": "jetson-super-orin-nano-8gb",
                "arch": "aarch64",
                "ram_total_mb": 8192,
                "ram_available_mb": 512,
                "gpu": True,
                "gpu_shared": True,
                "cuda_version": "12.2",
                "execution_mode": "cpu_only",
                "no_jit": True,
            }
        )
        jc1.domains = {
            "hardware": VocabularyDomain("hardware", 30, 0.95, tags=["constraints", "edge"]),
            "isa-design": VocabularyDomain("isa-design", 85, 0.9, tags=["opcodes", "encoding"]),
            "cuda": VocabularyDomain("cuda", 113, 0.85, tags=["gpu", "rust-crates"]),
            "fleet-infra": VocabularyDomain("fleet-infra", 20, 0.8, tags=["coordination", "discovery"]),
            "hav": VocabularyDomain("hav", 1687, 0.85, tags=["vocabulary", "compression"]),
        }
        table.register(jc1)
        
        # Babel Agent
        babel = AgentKnowledge(
            agent_name="Babel",
            role=AgentRole.SCOUT,
            repo="https://github.com/SuperInstance/babel-vessel",
            specializations=["multilingual", "grammatical-analysis", "babel-lattice"],
            vocab_count=120,
            test_count=0,
            can_execute={"python"},
        )
        babel.domains = {
            "grammatical": VocabularyDomain("grammatical", 18, 0.9, tags=["prgf", "typology"]),
            "multilingual": VocabularyDomain("multilingual", 80, 0.85, tags=["languages", "babel"]),
            "viewpoint-opcodes": VocabularyDomain("viewpoint-opcodes", 16, 0.8, tags=["confidence", "evidentiality"]),
        }
        table.register(babel)
        
        return table
