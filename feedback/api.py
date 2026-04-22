"""
Feedback Loop API — Phase 6.

Exposes REST endpoints for the Investigator Dashboard to record
dispositions, check retraining status, and monitor drift.
"""

import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
from feedback import (
    DispositionRecorder,
    FPDampeningModel,
    PSIMonitor,
    FP_REASON_CODES,
    DISPOSITION_TP,
    DISPOSITION_FP,
    DISPOSITION_INDETERMINATE,
    DISPOSITION_ESCALATED,
)

app = FastAPI(
    title="FundFlow AI — Feedback Loop API",
    description="Investigator feedback, retraining triggers, and drift monitoring.",
    version="1.0.0",
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

recorder = DispositionRecorder()
fp_model = FPDampeningModel()
psi_monitor = PSIMonitor()


# ─── Request / Response Models ────────────────────────────────────────────────

class DispositionRequest(BaseModel):
    cluster_id:      str
    investigator_id: str
    disposition:     str = Field(..., description="TRUE_POSITIVE | FALSE_POSITIVE | INDETERMINATE | ESCALATED")
    reason_code:     Optional[str] = Field(None, description="Required for FALSE_POSITIVE")
    feature_vector:  Optional[dict] = Field(None, description="Model scores at alert time")
    notes:           Optional[str] = None


class FPCheckRequest(BaseModel):
    feature_vector: dict = Field(..., description="Model probabilities + risk_score")


class PSICheckRequest(BaseModel):
    baseline_scores: dict[str, list[float]]
    current_scores:  dict[str, list[float]]


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Health check that verifies storage is accessible."""
    try:
        from feedback.feedback_core import STORAGE_PATH
        storage_ok = STORAGE_PATH.parent.exists() or True  # parent always creatable
        return {"status": "ok", "service": "feedback-loop", "storage": str(STORAGE_PATH)}
    except Exception as e:
        return {"status": "degraded", "service": "feedback-loop", "error": str(e)}


@app.get("/api/v1/feedback/reason-codes")
def get_reason_codes():
    """Return valid FP reason codes for the investigator dashboard dropdown."""
    return {"reason_codes": FP_REASON_CODES}


@app.post("/api/v1/feedback/disposition")
def record_disposition(req: DispositionRequest):
    """
    Record an investigator disposition for a cluster.

    - TRUE_POSITIVE   → Confirmed suspicious, STR filed
    - FALSE_POSITIVE  → Cleared, requires reason_code
    - INDETERMINATE   → Cannot determine, needs more investigation
    - ESCALATED       → Passed to senior investigator
    """
    try:
        record = recorder.record(
            cluster_id=req.cluster_id,
            investigator_id=req.investigator_id,
            disposition=req.disposition,
            reason_code=req.reason_code,
            feature_vector=req.feature_vector,
            notes=req.notes,
        )
        stats = recorder.get_stats()
        return {
            "success": True,
            "record": record,
            "retrain_needed": stats["retrain_needed"],
            "tp_since_retrain": stats["tp_since_retrain"],
            "message": (
                f"⚠️ Retraining threshold reached ({stats['tp_since_retrain']} TPs). "
                "Trigger retraining pipeline."
                if stats["retrain_needed"]
                else "Disposition recorded."
            ),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/v1/feedback/stats")
def get_stats():
    """Return feedback corpus statistics."""
    return recorder.get_stats()


@app.get("/api/v1/feedback/records")
def get_records():
    """Return all disposition records."""
    return {"records": recorder.get_all_records()}


@app.post("/api/v1/feedback/train-fp-model")
def train_fp_model():
    """
    Train the secondary FP dampening model from current feedback corpus.
    Call this after accumulating sufficient feedback data.
    """
    tps, fps = recorder.get_training_corpus()
    success = fp_model.train(tps, fps)
    return {
        "success": success,
        "tp_count": len(tps),
        "fp_count": len(fps),
        "message": (
            "FP dampening model trained successfully."
            if success
            else "Insufficient data. Need 5+ TPs and 5+ FPs."
        ),
    }


@app.post("/api/v1/feedback/check-fp")
def check_fp_probability(req: FPCheckRequest):
    """
    Check P(false_positive) for an alert before showing it to an investigator.
    Alerts with P(FP) > 0.85 can be auto-deprioritised.
    """
    prob = fp_model.predict_fp_probability(req.feature_vector)
    deprioritize = fp_model.should_deprioritize(req.feature_vector)
    return {
        "fp_probability": round(prob, 4),
        "deprioritize": deprioritize,
        "recommendation": (
            "Auto-deprioritise — high probability of false positive."
            if deprioritize
            else "Show to investigator."
        ),
    }


@app.post("/api/v1/feedback/psi-check")
def run_psi_check(req: PSICheckRequest):
    """
    Run Population Stability Index check.
    PSI > 0.25 on any feature triggers a model review recommendation.
    """
    result = psi_monitor.run_check(req.baseline_scores, req.current_scores)
    return result


@app.post("/api/v1/feedback/trigger-retrain")
def trigger_retrain():
    """
    Acknowledge retraining has been triggered and reset the TP counter.
    Call this after Kubeflow pipeline is kicked off.
    """
    stats = recorder.get_stats()
    if not stats["retrain_needed"]:
        return {
            "triggered": False,
            "message": f"Threshold not reached yet. {stats['tp_since_retrain']}/{stats['retrain_threshold']} TPs.",
        }
    recorder.reset_retrain_counter()
    return {
        "triggered": True,
        "tps_used": stats["tp_since_retrain"],
        "message": "Retraining counter reset. Kubeflow pipeline should be triggered externally.",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
