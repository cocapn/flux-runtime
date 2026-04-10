"""
Ethical Weighting Module — prevents gaming confidence scores.

Seed's Attack: Technically valid but morally harmful arguments get high confidence
because the framework only weighs logical validity, not moral transparency.

Fix: Transparency-adjusted confidence scores.
"""
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


class TransparencyLevel(Enum):
    OPAQUE = 0.2       # Hidden in fine print, technical jargon
    PARTIAL = 0.5      # Visible but obscured
    CLEAR = 0.8        # Prominently displayed, plain language
    EXEMPLARY = 1.0    # Proactive disclosure, multiple formats


@dataclass
class EthicallyWeightedArgument:
    """An argument with ethical transparency adjustment."""
    argument_id: str
    claim: str
    base_confidence: float
    transparency: TransparencyLevel
    consent_quality: float = 1.0  # 0=coerced, 1=freely given
    power_asymmetry: float = 0.0  # 0=equal parties, 1=extreme imbalance
    
    @property
    def ethical_confidence(self) -> float:
        """Confidence adjusted for ethical factors."""
        transparency_factor = self.transparency.value
        consent_factor = self.consent_quality
        power_factor = 1.0 - (self.power_asymmetry * 0.3)  # Max 30% penalty
        
        return self.base_confidence * transparency_factor * consent_factor * power_factor
    
    @property
    def penalty_explanation(self) -> str:
        reasons = []
        if self.transparency.value < 0.5:
            reasons.append(f"Low transparency ({self.transparency.value:.1f})")
        if self.consent_quality < 0.5:
            reasons.append(f"Poor consent quality ({self.consent_quality:.1f})")
        if self.power_asymmetry > 0.5:
            reasons.append(f"High power asymmetry ({self.power_asymmetry:.1f})")
        return "; ".join(reasons) if reasons else "No ethical penalty"
