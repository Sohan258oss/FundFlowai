"""
Auto-generates human-readable evidence narratives from raw model outputs.
"""

from typing import Dict, Any, List

class EvidenceGenerator:
    @staticmethod
    def generate(model_probs: Dict[str, float], context: Dict[str, Any], final_score: int) -> List[str]:
        """
        Produce a list of structured bullet points explaining WHY
        this cluster received its specific risk score.
        """
        evidence = []
        
        if final_score >= 80:
            evidence.append(f"CRITICAL: Cluster flagged as HIGH risk (Score: {final_score}/100).")
            
        # Check individual ML triggers
        if model_probs.get("layering_gnn", 0) > 0.7:
            evidence.append("- Strong topological evidence of Layering (A->B->C chain structure detected via GraphSAGE).")
            
        if model_probs.get("round_tripping_xgb", 0) > 0.7:
            evidence.append("- High probability of Round Tripping (circular flows returning to originator detected).")
            
        if model_probs.get("structuring_iforest", 0) > 0.7:
            evidence.append("- Anomalous structuring behavior detected (multiple sub-threshold deposits).")
            
        if model_probs.get("dormant_activation_svm", 0) > 0.7:
            evidence.append("- Dormant Account Activation flagged (sudden massive outflow volume breaking historical norm).")
            
        if model_probs.get("profile_mismatch_lgbm", 0) > 0.7:
            evidence.append("- Extreme Profile Mismatch: Transaction volumes drastically exceed expected baseline for account occupation.")
            
        # Contextual Amplifiers
        if context.get("is_pep"):
            evidence.append("- ALERT: Entity involves a Politically Exposed Person (PEP requirement amplifier triggered).")
        
        if context.get("high_risk_jurisdiction"):
            evidence.append("- Counterparties are located in a High-Risk Jurisdiction (e.g. FATF grey list).")
            
        if context.get("rapid_pass_through"):
            evidence.append("- Rapid pass-through behavior detected (funds wired out within 24h of receipt without business logic).")
            
        if not evidence:
            evidence.append("No distinctly suspicious topological or behavioral traits identified.")
            
        return evidence
