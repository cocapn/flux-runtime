"""Tests for PaperBridge — working implementations of paper concepts."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from flux.open_interp.paper_bridge import PaperBridge


class TestConfidenceCascade:
    def setup_method(self):
        self.bridge = PaperBridge()
    
    def test_first_value_uncertain(self):
        r = self.bridge.confidence_cascade(50.0)
        assert r.zone == 2  # Medium confidence on first value
        assert r.should_recompute is True
    
    def test_deadband_skips_recompute(self):
        self.bridge.confidence_cascade(50.0)
        r = self.bridge.confidence_cascade(50.05, deadband=0.1)
        assert r.should_recompute is False
    
    def test_large_change_high_confidence(self):
        self.bridge.confidence_cascade(50.0)
        r = self.bridge.confidence_cascade(100.0, deadband=0.1)
        assert r.should_recompute is True
        assert r.confidence > 0.8
        assert r.zone == 1


class TestOCDS:
    def test_basic_tracking(self):
        bridge = PaperBridge()
        r = bridge.ocds_track("sensor-1", 42.5, "celsius_to_fahrenheit", "F = C*9/5+32")
        assert r.origin == "sensor-1"
        assert r.data == 42.5
        assert len(r.lineage_hash) == 16
    
    def test_deterministic_hash(self):
        bridge = PaperBridge()
        r1 = bridge.ocds_track("s", 1, "t", "f")
        r2 = bridge.ocds_track("s", 1, "t", "f")
        assert r1.lineage_hash == r2.lineage_hash


class TestTileCompose:
    def test_composition(self):
        bridge = PaperBridge()
        r = bridge.tile_compose(7, 14.0, f_confidence=0.9, g_confidence=0.8)
        assert r.output == 14.0
        assert r.confidence == 0.72  # 0.9 * 0.8
    
    def test_full_confidence(self):
        bridge = PaperBridge()
        r = bridge.tile_compose(10, 20, f_confidence=1.0, g_confidence=1.0)
        assert r.confidence == 1.0


class TestRateOfChange:
    def test_steady_state(self):
        bridge = PaperBridge()
        history = [(1, 10), (2, 11), (3, 12), (4, 13)]
        r = bridge.rate_of_change(history)
        assert r.current_rate == 1.0
        assert r.predicted_next == 14.0
        assert r.anomaly is False
    
    def test_single_point(self):
        bridge = PaperBridge()
        r = bridge.rate_of_change([(1, 10)])
        assert r.current_rate == 0.0
    
    def test_spike_detection(self):
        bridge = PaperBridge()
        # Need enough baseline for stdev + spike
        history = [(i, 10 + i) for i in range(1, 20)] + [(20, 500)]
        r = bridge.rate_of_change(history)
        assert r.current_rate > 10  # Huge rate
        assert r.is_accelerating is True
        assert r.anomaly is True


class TestEmergence:
    def test_no_emergence(self):
        bridge = PaperBridge()
        r = bridge.emergence_detect([5.0, 5.0, 5.0])
        assert r.emerged is False
    
    def test_emergence_with_diverse_agents(self):
        bridge = PaperBridge()
        r = bridge.emergence_detect([1.0, 3.0, 9.0, 27.0])
        # Diverse results may trigger emergence
        assert r.individual_avg > 0
    
    def test_empty(self):
        bridge = PaperBridge()
        r = bridge.emergence_detect([])
        assert r.emerged is False


class TestStructuralMemory:
    def test_normal_load(self):
        bridge = PaperBridge()
        r = bridge.structural_memory_encode(100.0, 50.0, age=0)
        assert r.safety_factor == 0.5
        assert r.remaining_life > 0.8
    
    def test_overloaded(self):
        bridge = PaperBridge()
        r = bridge.structural_memory_encode(100.0, 99.0, age=10)
        assert r.safety_factor < 0.05
    
    def test_aged_system(self):
        bridge = PaperBridge()
        r = bridge.structural_memory_encode(100.0, 50.0, age=80)
        assert r.remaining_life < 0.5
