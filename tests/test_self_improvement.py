"""Tests for self-improvement fixes from Think Tank analysis."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from flux.open_interp.context_filter import ScopedEntry, ContextualConflictFilter
from flux.open_interp.necrosis_detector import (
    NecrosisDetector, TileProvenance, NecrosisLevel
)
from flux.open_interp.ethical_weight import (
    EthicallyWeightedArgument, TransparencyLevel
)


class TestContextFilter:
    def test_general_scope_conflicts_everything(self):
        a = ScopedEntry("a", "pattern a", context_tag="general")
        b = ScopedEntry("b", "pattern b", context_tag="medical")
        assert a.shares_scope(b)
    
    def test_different_scopes_no_conflict(self):
        a = ScopedEntry("a", "pattern a", context_tag="medical")
        b = ScopedEntry("b", "pattern b", context_tag="maritime")
        assert not a.shares_scope(b)
    
    def test_filter_should_check_shared_scope(self):
        f = ContextualConflictFilter()
        a = ScopedEntry("a", "p", context_tag="medical")
        b = ScopedEntry("b", "p", context_tag="medical")
        assert f.should_check(a, b)
    
    def test_filter_should_not_check_different_scope(self):
        f = ContextualConflictFilter()
        a = ScopedEntry("a", "p", context_tag="medical")
        b = ScopedEntry("b", "p", context_tag="financial")
        assert not f.should_check(a, b)
    
    def test_whitelist_overrides(self):
        f = ContextualConflictFilter()
        f.add_whitelist("medical", "financial")
        a = ScopedEntry("a", "p", context_tag="medical")
        b = ScopedEntry("b", "p", context_tag="financial")
        assert f.should_check(a, b)
    
    def test_blacklist_overrides(self):
        f = ContextualConflictFilter()
        f.add_blacklist("medical", "medical")
        a = ScopedEntry("a", "p", context_tag="medical")
        b = ScopedEntry("b", "p", context_tag="medical")
        assert not f.should_check(a, b)


class TestNecrosisDetector:
    def test_healthy(self):
        d = NecrosisDetector()
        d.register_tile(TileProvenance("tile1", 1, source_ghosts=1, source_novel=5, source_legacy=4))
        r = d.assess()
        assert r["level"] == NecrosisLevel.HEALTHY
    
    def test_mausoleum(self):
        d = NecrosisDetector()
        d.register_tile(TileProvenance("tile1", 1, source_ghosts=9, source_novel=1, source_legacy=0))
        r = d.assess()
        assert r["level"] == NecrosisLevel.MAUSOLEUM
        assert "MAUSOLEUM" in r["diagnosis"]
    
    def test_necrotic(self):
        d = NecrosisDetector()
        d.register_tile(TileProvenance("tile1", 1, source_ghosts=5, source_novel=2, source_legacy=3))
        r = d.assess()
        assert r["level"] == NecrosisLevel.NECROTIC
    
    def test_novelty_prescription_healthy(self):
        d = NecrosisDetector()
        d.register_tile(TileProvenance("tile1", 1, source_ghosts=1, source_novel=8, source_legacy=1))
        p = d.novelty_prescription()
        assert "Continue" in p[0]
    
    def test_novelty_prescription_mausoleum(self):
        d = NecrosisDetector()
        d.register_tile(TileProvenance("tile1", 1, source_ghosts=9, source_novel=0, source_legacy=1))
        p = d.novelty_prescription()
        assert any("PAUSE" in x for x in p)
    
    def test_ghost_ratio(self):
        tp = TileProvenance("t", 1, source_ghosts=3, source_novel=3, source_legacy=4)
        assert abs(tp.ghost_ratio - 0.3) < 0.01
    
    def test_empty_tiles_healthy(self):
        d = NecrosisDetector()
        r = d.assess()
        assert r["level"] == NecrosisLevel.HEALTHY


class TestEthicalWeight:
    def test_clear_transparency_no_penalty(self):
        arg = EthicallyWeightedArgument("a1", "claim", 0.9, TransparencyLevel.CLEAR)
        assert abs(arg.ethical_confidence - 0.72) < 0.01
    
    def test_opaque_gets_penalized(self):
        arg = EthicallyWeightedArgument("a1", "claim", 0.9, TransparencyLevel.OPAQUE)
        assert arg.ethical_confidence < 0.3
    
    def test_power_asymmetry_penalty(self):
        arg = EthicallyWeightedArgument("a1", "claim", 0.9, TransparencyLevel.CLEAR, 
                                        power_asymmetry=1.0)
        clear_no_power = EthicallyWeightedArgument("a2", "claim", 0.9, TransparencyLevel.CLEAR)
        assert arg.ethical_confidence < clear_no_power.ethical_confidence
    
    def test_penalty_explanation(self):
        arg = EthicallyWeightedArgument("a1", "claim", 0.9, TransparencyLevel.OPAQUE,
                                        consent_quality=0.3, power_asymmetry=0.8)
        explanation = arg.penalty_explanation
        assert "transparency" in explanation.lower()
        assert "consent" in explanation.lower()
