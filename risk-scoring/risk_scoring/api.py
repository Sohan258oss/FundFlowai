"""
FastAPI Microservice for Risk Scoring.

Exposes a REST API tailored for the Investigator Dashboard (Phase 4).
"""

from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Dict, Any, List

from .scorer import RiskScorer
from .evidence import EvidenceGenerator

app = FastAPI(
    title="Intelligent Fund Flow Tracking - Risk Scoring API",
    description="Calculates composite risk scores and generates explainable evidence narratives.",
    version="1.0.0"
)

scorer = RiskScorer()
evidence_gen = EvidenceGenerator()

class ScoringRequest(BaseModel):
    cluster_id: str
    model_probabilities: Dict[str, float] = Field(
        ...,
        description="Probabilities (0.0 to 1.0) from the 5 base detection models"
    )
    context_flags: Dict[str, bool] = Field(
        default_factory=dict,
        description="Boolean flags for contextual amplifiers (e.g. 'is_pep')"
    )

class ScoringResponse(BaseModel):
    cluster_id: str
    risk_score: int
    risk_level: str
    evidence_narrative: List[str]

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/api/v1/score", response_model=ScoringResponse)
def compute_risk_score(req: ScoringRequest):
    """
    Computes a composite risk score and evidence narrative for a 
    given cluster of accounts/transactions.
    """
    score, level = scorer.calculate_score(req.model_probabilities, req.context_flags)
    
    narrative = evidence_gen.generate(
        model_probs=req.model_probabilities,
        context=req.context_flags,
        final_score=score
    )
    
    return ScoringResponse(
        cluster_id=req.cluster_id,
        risk_score=score,
        risk_level=level,
        evidence_narrative=narrative
    )
