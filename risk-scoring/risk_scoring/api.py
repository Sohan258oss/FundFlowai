"""
FastAPI Microservice for Risk Scoring.
Exposes a REST API tailored for the Investigator Dashboard.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, List, Optional

from .scorer import RiskScorer
from .evidence import EvidenceGenerator

app = FastAPI(
    title="Intelligent Fund Flow Tracking - Risk Scoring API",
    description="Calculates composite risk scores and generates explainable evidence narratives.",
    version="1.0.0"
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
allowed_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── API Key Authentication ───────────────────────────────────────────────────
API_KEY = os.environ.get("FUNDFLOW_API_KEY", "")

@app.middleware("http")
async def check_api_key(request: Request, call_next):
    """Skip auth if no key is configured (dev mode) or for health/docs."""
    if API_KEY and request.url.path not in ("/health", "/docs", "/openapi.json"):
        provided = request.headers.get("X-API-Key", "")
        if provided != API_KEY:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})
    return await call_next(request)

scorer = RiskScorer()
evidence_gen = EvidenceGenerator()

# Path to generated data — relative to project root
GROUND_TRUTH_PATH = Path(__file__).resolve().parents[3] / "data-generator" / "output" / "ground_truth.json"


class ScoringRequest(BaseModel):
    cluster_id: str
    model_probabilities: Dict[str, float] = Field(...)
    context_flags: Dict[str, bool] = Field(default_factory=dict)


class ScoringResponse(BaseModel):
    cluster_id: str
    risk_score: int
    risk_level: str
    evidence_narrative: List[str]


def _pattern_to_model_probs(pattern: dict) -> Dict[str, float]:
    """Map a ground truth pattern to model probability estimates."""
    pt = pattern.get("pattern_type", "")
    base = {
        "layering_gnn": 0.05,
        "round_tripping_xgb": 0.05,
        "structuring_iforest": 0.05,
        "dormant_activation_svm": 0.05,
        "profile_mismatch_lgbm": 0.05,
    }
    if pt == "LAYERING":
        depth = pattern.get("depth", 3)
        base["layering_gnn"] = min(0.95, 0.70 + depth * 0.04)
        base["round_tripping_xgb"] = 0.20
    elif pt == "ROUND_TRIP":
        base["round_tripping_xgb"] = 0.88
        base["layering_gnn"] = 0.45
    elif pt == "STRUCTURING":
        splits = pattern.get("num_splits", 3)
        base["structuring_iforest"] = min(0.95, 0.65 + splits * 0.04)
        base["profile_mismatch_lgbm"] = 0.30 if pattern.get("multi_branch") else 0.15
    elif pt == "DORMANT_ACTIVATION":
        ratio = pattern.get("amount_to_income_ratio", 1.0)
        base["dormant_activation_svm"] = min(0.97, 0.55 + ratio * 0.03)
        base["profile_mismatch_lgbm"] = 0.40 if pattern.get("kyc_status") == "EXPIRED" else 0.20
    elif pt == "PROFILE_MISMATCH":
        ratio = pattern.get("amount_to_annual_income_ratio", 1.0)
        base["profile_mismatch_lgbm"] = min(0.97, 0.55 + ratio * 0.015)
        base["layering_gnn"] = 0.25 if pattern.get("involved_swift") else 0.10
    return base


def _pattern_to_context_flags(pattern: dict) -> Dict[str, bool]:
    flags = {}
    if pattern.get("involved_swift"):
        flags["high_risk_jurisdiction"] = True
    if pattern.get("kyc_status") == "EXPIRED":
        flags["rapid_pass_through"] = True
    activation_burst = pattern.get("activation_burst_txns", 0)
    if activation_burst >= 5:
        flags["rapid_pass_through"] = True
    return flags


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/api/v1/alerts")
def get_alerts(limit: int = Query(default=50, ge=1, le=500)):
    """
    Read ground_truth.json, score each pattern, return sorted alert list.
    Falls back to empty list if file not found.
    """
    if not GROUND_TRUTH_PATH.exists():
        return {"alerts": [], "source": "file_not_found"}

    with open(GROUND_TRUTH_PATH, "r") as f:
        patterns = json.load(f)

    alerts = []
    for pattern in patterns:
        cluster_id = pattern.get("pattern_id", "UNKNOWN")
        model_probs = _pattern_to_model_probs(pattern)
        context_flags = _pattern_to_context_flags(pattern)

        score, level = scorer.calculate_score(model_probs, context_flags)
        narrative = evidence_gen.generate(
            model_probs=model_probs,
            context=context_flags,
            final_score=score
        )

        alerts.append({
            "cluster_id": cluster_id,
            "pattern_type": pattern.get("pattern_type"),
            "account_id": pattern.get("account_id"),
            "risk_score": score,
            "risk_level": level,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "model_probs": model_probs,
            "context_flags": context_flags,
            "evidence_narrative": narrative,
            "raw": {
                "total_amount": pattern.get("total_amount") or pattern.get("total_suspicious_amount") or pattern.get("total_burst_amount"),
                "transaction_ids": pattern.get("transaction_ids", []),
            }
        })

    alerts.sort(key=lambda a: a["risk_score"], reverse=True)
    return {"alerts": alerts[:limit], "total": len(alerts)}


# Path to transactions data
TRANSACTIONS_PATH = Path(__file__).resolve().parents[3] / "data-generator" / "output" / "transactions.json"
ACCOUNTS_PATH = Path(__file__).resolve().parents[3] / "data-generator" / "output" / "accounts.json"


@app.get("/api/v1/graph/{account_id}")
def get_account_graph(account_id: str, depth: int = Query(default=2, ge=1, le=4)):
    """
    Build a subgraph around an account from transactions.json.
    Returns nodes and edges for the dashboard graph visualization.
    Falls back to empty graph if data not found.
    """
    if not TRANSACTIONS_PATH.exists():
        return {"center": account_id, "depth": depth, "nodes": [account_id], "edges": []}

    with open(TRANSACTIONS_PATH, "r") as f:
        transactions = json.load(f)

    # BFS to find connected accounts up to `depth` hops
    visited = {account_id}
    frontier = {account_id}
    relevant_edges = []

    for _ in range(depth):
        next_frontier = set()
        for txn in transactions:
            sender = txn.get("sender_account_id", "")
            receiver = txn.get("receiver_account_id", "")
            if sender in frontier:
                next_frontier.add(receiver)
                relevant_edges.append(txn)
            elif receiver in frontier:
                next_frontier.add(sender)
                relevant_edges.append(txn)
        frontier = next_frontier - visited
        visited |= frontier
        if not frontier:
            break

    # Deduplicate edges by txn_id
    seen_txns = set()
    unique_edges = []
    for txn in relevant_edges:
        tid = txn.get("txn_id", "")
        if tid not in seen_txns:
            seen_txns.add(tid)
            unique_edges.append({
                "source": txn.get("sender_account_id"),
                "target": txn.get("receiver_account_id"),
                "amount": txn.get("amount_value", 0),
                "timestamp": txn.get("timestamp_initiated", ""),
                "channel": txn.get("channel", ""),
                "purpose_code": txn.get("purpose_code", ""),
                "is_suspicious": txn.get("is_suspicious", False),
                "suspicious_pattern": txn.get("suspicious_pattern"),
            })

    # Sort by timestamp and limit to keep the response manageable
    unique_edges.sort(key=lambda e: e["timestamp"])
    unique_edges = unique_edges[:100]

    return {
        "center": account_id,
        "depth": depth,
        "nodes": list(visited),
        "edges": unique_edges,
    }


@app.post("/api/v1/score", response_model=ScoringResponse)
def compute_risk_score(req: ScoringRequest):
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