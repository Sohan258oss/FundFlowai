"""
Signal Normalization and Amplification Logic.

Translates raw model probabilities and rules into standardized (0-100) signals.
"""

from typing import Dict, Any
from .config import config

class SignalProcessor:
    @staticmethod
    def normalize_probability(prob: float) -> float:
        """Ensure probability is between 0 and 100."""
        return max(0.0, min(100.0, prob * 100.0))

    @staticmethod
    def calculate_amplifiers(context: Dict[str, Any]) -> float:
        """
        Calculates the total risk multiplier based on contextual flags.
        For example, if the transaction involves a PEP, the risk doubles.
        """
        multiplier = 1.0
        
        if context.get("is_pep", False):
            multiplier *= config.get_amplifier("pep_involved")
            
        if context.get("high_risk_jurisdiction", False):
            multiplier *= config.get_amplifier("high_risk_jurisdiction")
            
        if context.get("rapid_pass_through", False):
            multiplier *= config.get_amplifier("rapid_pass_through")
            
        return multiplier
