"""
Composite Risk Scoring Engine.

Aggregates individual ML model probabilities and applies contextual amplifiers
to produce a final risk score (0-100) and a risk classification.
"""

from typing import Dict, Any, Tuple
from .config import config
from .signals import SignalProcessor

class RiskScorer:
    def __init__(self):
        self.processor = SignalProcessor()

    def calculate_score(self, model_probs: Dict[str, float], context: Dict[str, Any] = None) -> Tuple[int, str]:
        """
        Calculate final risk score from a set of base ML probabilities.
        
        Args:
            model_probs: dict like {'layering_gnn': 0.85, 'round_tripping_xgb': 0.10}
            context: dict for amplifiers like {'is_pep': True}
            
        Returns:
            (final_score: int 0-100, risk_level: str)
        """
        if context is None:
            context = {}
            
        base_score = 0.0
        
        # 1. Calculate weighted sum of ML signals
        for model_name, prob in model_probs.items():
            weight = config.get_model_weight(model_name)
            normalized_signal = self.processor.normalize_probability(prob)
            base_score += normalized_signal * weight
            
        # 2. Apply contextual amplifiers
        multiplier = self.processor.calculate_amplifiers(context)
        final_score = base_score * multiplier
        
        # 3. Cap at 100 and round
        final_score_int = int(min(100, max(0, round(final_score))))
        
        # 4. Classify
        if final_score_int >= config.get_threshold("high_risk"):
            level = "HIGH"
        elif final_score_int >= config.get_threshold("medium_risk"):
            level = "MEDIUM"
        else:
            level = "LOW"
            
        return final_score_int, level
