"""
Necrosis Detector — prevents the Functioning Mausoleum scenario.

Kimi's Emergence: When ghost vocab enters the tiling system, dead concepts
become ossified attractor basins. Living agents route around them, creating
architectural scar tissue. Eventually the system fossilizes while functioning.

This detector measures the ratio of ghost-derived to novel vocabulary in tiles.
If ghost ratio exceeds a threshold, it flags necrosis.

The cure: mandatory novelty injection — a percentage of tiles MUST use
recently-decomposed vocabulary (from Paper Decomposer, not Ghost Loader).
"""
import time
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum


class NecrosisLevel(Enum):
    HEALTHY = "healthy"        # <20% ghost-derived tiles
    AT_RISK = "at_risk"        # 20-40% ghost-derived tiles  
    NECROTIC = "necrotic"      # 40-60% ghost-derived tiles
    MAUSOLEUM = "mausoleum"    # >60% ghost-derived — the Functioning Mausoleum


@dataclass
class TileProvenance:
    """Where did a tile's components come from?"""
    tile_name: str
    level: int
    source_ghosts: int = 0    # Components from Ghost Loader
    source_novel: int = 0     # Components from Paper Decomposer / new research
    source_legacy: int = 0    # Components from original vocabulary
    created_at: float = 0.0
    
    @property
    def ghost_ratio(self) -> float:
        total = self.source_ghosts + self.source_novel + self.source_legacy
        return self.source_ghosts / total if total > 0 else 0.0
    
    @property 
    def novelty_ratio(self) -> float:
        total = self.source_ghosts + self.source_novel + self.source_legacy
        return self.source_novel / total if total > 0 else 0.0


class NecrosisDetector:
    """
    Detects and prevents epistemic stagnation from over-reliance on ghost vocabulary.
    
    The Functioning Mausoleum scenario: agents achieve perfect communication
    using only dead concepts, incapable of incorporating new research because
    the pruning system correctly identifies novel knowledge as "inefficient."
    
    Cure: Enforce a minimum novelty ratio.
    """
    
    def __init__(self, ghost_threshold: float = 0.4, novelty_floor: float = 0.15):
        self.ghost_threshold = ghost_threshold  # Above this = necrotic
        self.novelty_floor = novelty_floor       # Below this = stagnant
        self.tile_provenances: Dict[str, TileProvenance] = {}
    
    def register_tile(self, provenance: TileProvenance):
        """Register a tile's provenance for monitoring."""
        self.tile_provenances[provenance.tile_name] = provenance
    
    def assess(self) -> dict:
        """Assess the necrosis level of the entire vocabulary."""
        if not self.tile_provenances:
            return {"level": NecrosisLevel.HEALTHY, "ghost_ratio": 0.0, 
                    "novelty_ratio": 0.0, "tiles_checked": 0, "diagnosis": "no tiles registered"}
        
        total_ghost = sum(t.source_ghosts for t in self.tile_provenances.values())
        total_novel = sum(t.source_novel for t in self.tile_provenances.values())
        total_legacy = sum(t.source_legacy for t in self.tile_provenances.values())
        total = total_ghost + total_novel + total_legacy
        
        ghost_ratio = total_ghost / total if total > 0 else 0
        novelty_ratio = total_novel / total if total > 0 else 0
        
        if ghost_ratio > 0.6:
            level = NecrosisLevel.MAUSOLEUM
        elif ghost_ratio > 0.4:
            level = NecrosisLevel.NECROTIC
        elif ghost_ratio > 0.2:
            level = NecrosisLevel.AT_RISK
        else:
            level = NecrosisLevel.HEALTHY
        
        diagnosis = self._diagnose(level, ghost_ratio, novelty_ratio)
        
        return {
            "level": level,
            "ghost_ratio": ghost_ratio,
            "novelty_ratio": novelty_ratio,
            "tiles_checked": len(self.tile_provenances),
            "diagnosis": diagnosis,
        }
    
    def _diagnose(self, level: NecrosisLevel, ghost_ratio: float, novelty_ratio: float) -> str:
        if level == NecrosisLevel.MAUSOLEUM:
            return (f"FUNCTIONING MAUSOLEUM DETECTED. {ghost_ratio:.0%} ghost-derived. "
                    f"The ecosystem reasons perfectly using only dead concepts. "
                    f"Mandatory novelty injection required: decompose at least "
                    f"{int(self.novelty_floor * 100)} new papers immediately.")
        elif level == NecrosisLevel.NECROTIC:
            return (f"Necrotic substrate: {ghost_ratio:.0%} ghost-derived tiles. "
                    f"Increase Paper Decomposer throughput.")
        elif level == NecrosisLevel.AT_RISK:
            return (f"At risk: {ghost_ratio:.0%} ghost-derived. Monitor novelty intake.")
        else:
            return f"Healthy: {ghost_ratio:.0%} ghost, {novelty_ratio:.0%} novel."
    
    def novelty_prescription(self) -> List[str]:
        """What to do to cure necrosis."""
        assessment = self.assess()
        if assessment["level"] == NecrosisLevel.HEALTHY:
            return ["Continue current vocabulary intake."]
        
        prescriptions = []
        if assessment["ghost_ratio"] > self.ghost_threshold:
            prescriptions.append("PAUSE ghost_loader consults for 24 hours")
            prescriptions.append("Run paper_decomposer on 10 new papers")
        if assessment["novelty_ratio"] < self.novelty_floor:
            prescriptions.append("Mandatory: 20% of new tiles must use novel vocabulary")
            prescriptions.append("Disable pruning for vocabulary < 7 days old")
        return prescriptions
