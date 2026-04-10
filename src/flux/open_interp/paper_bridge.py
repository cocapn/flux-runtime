"""
Paper Bridge — Working implementations of SuperInstance paper concepts.

Each concept from the research papers is implemented as a callable function
that the FLUX vocabulary system can invoke via natural language.

This is where Cocapn IP becomes operational code.
"""

import time
import hashlib
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class ConfidenceResult:
    value: float
    zone: int  # 1=confident, 2=uncertain, 3=danger
    confidence: float
    should_recompute: bool
    deadband: float


@dataclass
class OCDSTuple:
    origin: str
    data: Any
    transform: str
    function: str
    timestamp: float
    lineage_hash: str


@dataclass
class TileComposeResult:
    input_val: Any
    intermediate: Any
    output: Any
    confidence: float


@dataclass
class RateResult:
    current_rate: float
    is_accelerating: bool
    predicted_next: float
    anomaly: bool


@dataclass
class EmergenceResult:
    emerged: bool
    collective_score: float
    individual_avg: float
    ratio: float


@dataclass
class StructuralMemoryResult:
    max_capacity: float
    current_load: float
    safety_factor: float
    remaining_life: float


class PaperBridge:
    """
    Implements working functions for SuperInstance paper concepts.
    
    Concepts implemented:
    1. Confidence Cascade (Paper 03) — zone-based confidence with deadband
    2. OCDS Origin Tracking (Paper 01) — S=(O,D,T,Φ) provenance
    3. Tile Composition (Paper 08) — compose(f,g) with confidence propagation
    4. Rate-Based Change (Paper 05) — rate detection and anomaly prediction
    5. Emergence Detection (Paper 27) — collective > individual detection
    6. Structural Memory (Paper 20) — memory-as-structure encoding
    """
    
    # Confidence Cascade state
    _last_value: Optional[float] = None
    _last_confidence: Optional[float] = None
    
    # Rate tracking
    _rate_history: List[tuple] = []
    
    def confidence_cascade(self, value: float, deadband: float = 0.1) -> ConfidenceResult:
        """
        Confidence Cascade Architecture (Paper 03).
        
        Three-zone model:
          Zone 1 (conf > 0.8): Act immediately. High confidence.
          Zone 2 (0.4 ≤ conf ≤ 0.8): Escalate. Medium confidence.
          Zone 3 (conf < 0.4): Fail-safe. Low confidence.
        
        Deadband: if new value within deadband of last, skip recomputation.
        """
        should_recompute = True
        
        if self._last_value is not None:
            delta = abs(value - self._last_value)
            if delta <= deadband:
                should_recompute = False
                confidence = self._last_confidence or 0.5
            else:
                # Confidence proportional to how far outside deadband
                confidence = min(1.0, delta / (deadband * 3))
        else:
            confidence = 0.7  # Initial uncertainty
        
        # Zone classification
        if confidence > 0.8:
            zone = 1
        elif confidence >= 0.4:
            zone = 2
        else:
            zone = 3
        
        self._last_value = value
        self._last_confidence = confidence
        
        return ConfidenceResult(
            value=value,
            zone=zone,
            confidence=round(confidence, 3),
            should_recompute=should_recompute,
            deadband=deadband,
        )
    
    def ocds_track(self, origin: str, data: Any, transform: str, function: str) -> OCDSTuple:
        """
        Origin-Centric Data Systems (Paper 01).
        
        S = (O, D, T, Φ) four-tuple for complete data provenance.
        Every datum carries its origin, the data itself, the transform applied,
        and the mathematical relationship.
        """
        lineage = f"{origin}:{data}:{transform}:{function}"
        h = hashlib.sha256(lineage.encode()).hexdigest()[:16]
        
        return OCDSTuple(
            origin=origin,
            data=data,
            transform=transform,
            function=function,
            timestamp=time.time(),
            lineage_hash=h,
        )
    
    def tile_compose(self, f_result: Any, g_result: Any, 
                     f_confidence: float = 1.0, g_confidence: float = 1.0) -> TileComposeResult:
        """
        Tile Algebra Composition (Paper 08).
        
        compose(f,g)(x) = g(f(x))
        Confidence = product of individual confidences.
        Composition preserves behavior, confidence, and safety.
        """
        output = g_result  # Simplified: g(f(x))
        combined_confidence = f_confidence * g_confidence
        
        return TileComposeResult(
            input_val=f_result,
            intermediate=f_result,
            output=output,
            confidence=round(combined_confidence, 3),
        )
    
    def rate_of_change(self, history: List[tuple]) -> RateResult:
        """
        Rate-Based Change Mechanics (Paper 05).
        
        x(t) = x₀ + ∫r(τ)dτ
        
        Monitor rates instead of states. Detect anomalies before they happen.
        """
        if len(history) < 2:
            return RateResult(
                current_rate=0.0,
                is_accelerating=False,
                predicted_next=history[0][1] if history else 0.0,
                anomaly=False,
            )
        
        # Compute rates between consecutive points
        rates = []
        for i in range(1, len(history)):
            dt = history[i][0] - history[i-1][0]
            if dt > 0:
                rates.append((history[i][1] - history[i-1][1]) / dt)
        
        if not rates:
            return RateResult(0.0, False, history[-1][1], False)
        
        current_rate = rates[-1]
        
        # Compute rate-of-rate (acceleration)
        if len(rates) >= 2:
            acceleration = rates[-1] - rates[-2]
            is_accelerating = abs(acceleration) > 0.01
        else:
            is_accelerating = False
        
        # Anomaly detection: rate > 2*std of recent rates
        if len(rates) >= 3:
            import statistics
            mean_rate = statistics.mean(rates[:-1])
            std_rate = statistics.stdev(rates[:-1]) if len(rates) > 2 else 0
            anomaly = abs(current_rate - mean_rate) > max(1.5 * std_rate, 0.01)
        else:
            anomaly = False
        
        # Predict next value
        predicted_next = history[-1][1] + current_rate
        
        return RateResult(
            current_rate=round(current_rate, 3),
            is_accelerating=is_accelerating,
            predicted_next=round(predicted_next, 3),
            anomaly=anomaly,
        )
    
    def emergence_detect(self, agent_results: List[float]) -> EmergenceResult:
        """
        Emergence Detection (Paper 27).
        
        Detect when collective behavior transcends individual behavior.
        emerged if collective_score > 1.5 * individual_avg.
        """
        if not agent_results:
            return EmergenceResult(False, 0.0, 0.0, 0.0)
        
        individual_avg = sum(agent_results) / len(agent_results)
        
        # Collective score: non-linear combination (products and means)
        import math
        if individual_avg > 0:
            # Geometric mean as collective measure
            log_sum = sum(math.log(max(r, 0.001)) for r in agent_results)
            collective_score = math.exp(log_sum / len(agent_results))
            # Add synergy bonus for coordination
            if len(agent_results) > 1:
                synergy = math.sqrt(sum(r**2 for r in agent_results)) / len(agent_results)
                collective_score = max(collective_score, synergy)
        else:
            collective_score = individual_avg
        
        ratio = collective_score / individual_avg if individual_avg != 0 else 0
        emerged = ratio > 1.5
        
        return EmergenceResult(
            emerged=emerged,
            collective_score=round(collective_score, 3),
            individual_avg=round(individual_avg, 3),
            ratio=round(ratio, 3),
        )
    
    def structural_memory_encode(self, capacity: float, load: float, age: float = 0.0) -> StructuralMemoryResult:
        """
        Structural Memory (Paper 20).
        
        Memory IS the structure, not a representation stored IN the structure.
        Encode constraints as physical form.
        """
        safety_factor = (capacity - load) / capacity if capacity > 0 else 0
        
        # Remaining life decreases with age and load stress
        stress_ratio = load / capacity if capacity > 0 else 1.0
        remaining_life = max(0.0, 1.0 - (age * 0.01) - (stress_ratio * 0.3))
        
        return StructuralMemoryResult(
            max_capacity=capacity,
            current_load=load,
            safety_factor=round(safety_factor, 3),
            remaining_life=round(remaining_life, 3),
        )
