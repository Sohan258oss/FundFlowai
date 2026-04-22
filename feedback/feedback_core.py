"""
Feedback & Model Improvement Loop — Phase 6.

Handles:
- Investigator disposition recording (TP / FP / Indeterminate)
- Reason-coded FP handling (dampening, not blind retraining)
- Retraining trigger logic (fires at 50+ new confirmed TPs)
- Secondary FP prediction model (post-filter logistic regression)
- Population Stability Index (PSI) monitoring
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

# ─── Constants ───────────────────────────────────────────────────────────────

DISPOSITION_TP           = "TRUE_POSITIVE"
DISPOSITION_FP           = "FALSE_POSITIVE"
DISPOSITION_INDETERMINATE = "INDETERMINATE"
DISPOSITION_ESCALATED    = "ESCALATED"

FP_REASON_CODES = {
    "NORMAL_BUSINESS":    "Normal business activity — entity type explains flow",
    "SALARY_ADVANCE":     "Large credit explained by salary advance or bonus",
    "FAMILY_TRANSFER":    "Intra-family transfers — documented relationship",
    "CORPORATE_TREASURY": "Corporate treasury management — normal for entity",
    "LOAN_DISBURSEMENT":  "Loan disbursement — verified product transaction",
    "INSUFFICIENT_EVIDENCE": "Cannot confirm — insufficient evidence",
}

RETRAIN_TP_THRESHOLD = 50
PSI_ALERT_THRESHOLD  = 0.25

# Resolve storage path relative to this module, not CWD, to avoid path mismatches
_default_store = Path(__file__).resolve().parent.parent / "feedback_store.json"
STORAGE_PATH = Path(os.environ.get("FEEDBACK_STORAGE", str(_default_store)))


# ─── Persistence helpers ──────────────────────────────────────────────────────

def _load_store() -> dict:
    if STORAGE_PATH.exists():
        with open(STORAGE_PATH, "r") as f:
            return json.load(f)
    return {"records": [], "tp_since_last_retrain": 0, "baseline_features": None}


def _save_store(store: dict) -> None:
    STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STORAGE_PATH, "w") as f:
        json.dump(store, f, indent=2, default=str)


# ─── Disposition Recorder ────────────────────────────────────────────────────

class DispositionRecorder:
    """
    Records investigator dispositions and manages the feedback corpus.
    Persists to a JSON file — swap for PostgreSQL in production.
    """

    def record(
        self,
        cluster_id: str,
        investigator_id: str,
        disposition: str,
        reason_code: Optional[str] = None,
        feature_vector: Optional[dict] = None,
        notes: Optional[str] = None,
    ) -> dict:
        """
        Record a disposition.

        Args:
            cluster_id:      The scored cluster being dispositioned.
            investigator_id: Analyst ID.
            disposition:     TRUE_POSITIVE | FALSE_POSITIVE | INDETERMINATE | ESCALATED
            reason_code:     Required for FALSE_POSITIVE (see FP_REASON_CODES).
            feature_vector:  Model scores at time of alert (for retraining).
            notes:           Free-text notes.

        Returns:
            The recorded disposition dict.
        """
        if disposition not in [DISPOSITION_TP, DISPOSITION_FP,
                                DISPOSITION_INDETERMINATE, DISPOSITION_ESCALATED]:
            raise ValueError(f"Invalid disposition: {disposition}")

        if disposition == DISPOSITION_FP and not reason_code:
            raise ValueError(
                f"reason_code required for FALSE_POSITIVE. "
                f"Valid codes: {list(FP_REASON_CODES.keys())}"
            )

        if reason_code and reason_code not in FP_REASON_CODES:
            raise ValueError(
                f"Invalid reason_code '{reason_code}'. "
                f"Valid: {list(FP_REASON_CODES.keys())}"
            )

        store = _load_store()

        # Assign training label
        if disposition == DISPOSITION_TP:
            label = "TP"
            store["tp_since_last_retrain"] = store.get("tp_since_last_retrain", 0) + 1
        elif disposition == DISPOSITION_FP:
            label = "INDETERMINATE" if reason_code == "INSUFFICIENT_EVIDENCE" else "FP_SOFT"
        elif disposition == DISPOSITION_ESCALATED:
            label = "PENDING"
        else:
            label = "INDETERMINATE"

        record = {
            "cluster_id":       cluster_id,
            "investigator_id":  investigator_id,
            "disposition":      disposition,
            "reason_code":      reason_code,
            "feature_vector":   feature_vector or {},
            "notes":            notes,
            "label":            label,
            "timestamp":        datetime.now(timezone.utc).isoformat(),
            "used_in_training": False,
        }

        store["records"].append(record)
        _save_store(store)
        return record

    def should_retrain(self) -> bool:
        store = _load_store()
        return store.get("tp_since_last_retrain", 0) >= RETRAIN_TP_THRESHOLD

    def reset_retrain_counter(self) -> None:
        store = _load_store()
        store["tp_since_last_retrain"] = 0
        _save_store(store)

    def get_training_corpus(self) -> tuple[list[dict], list[dict]]:
        """Returns (true_positives, soft_false_positives) for retraining."""
        store = _load_store()
        tps  = [r for r in store["records"] if r["label"] == "TP"]
        fps  = [r for r in store["records"] if r["label"] == "FP_SOFT"]
        return tps, fps

    def get_all_records(self) -> list[dict]:
        return _load_store()["records"]

    def get_stats(self) -> dict:
        store = _load_store()
        records = store["records"]
        return {
            "total_dispositions": len(records),
            "true_positives":     sum(1 for r in records if r["label"] == "TP"),
            "false_positives":    sum(1 for r in records if r["label"] == "FP_SOFT"),
            "indeterminate":      sum(1 for r in records if r["label"] == "INDETERMINATE"),
            "pending":            sum(1 for r in records if r["label"] == "PENDING"),
            "tp_since_retrain":   store.get("tp_since_last_retrain", 0),
            "retrain_threshold":  RETRAIN_TP_THRESHOLD,
            "retrain_needed":     store.get("tp_since_last_retrain", 0) >= RETRAIN_TP_THRESHOLD,
        }


# ─── FP Dampening Model ───────────────────────────────────────────────────────

class FPDampeningModel:
    """
    Secondary logistic regression model that predicts P(false_positive).

    Trained on confirmed TPs and soft FPs from investigator feedback.
    Alerts where P(FP) > 0.85 are auto-deprioritised — but still logged.

    This is NOT the main detection model. It's a post-filter that reduces
    alert volume without retraining the core models on FP data.
    """

    def __init__(self):
        self.model   = LogisticRegression(class_weight="balanced", max_iter=500)
        self.scaler  = StandardScaler()
        self.trained = False
        self.feature_names = [
            "layering_gnn",
            "round_tripping_xgb",
            "structuring_iforest",
            "dormant_activation_svm",
            "profile_mismatch_lgbm",
            "risk_score",
        ]

    def _extract_features(self, records: list[dict]) -> np.ndarray:
        rows = []
        for r in records:
            fv = r.get("feature_vector", {})
            row = [
                fv.get("layering_gnn", 0.0),
                fv.get("round_tripping_xgb", 0.0),
                fv.get("structuring_iforest", 0.0),
                fv.get("dormant_activation_svm", 0.0),
                fv.get("profile_mismatch_lgbm", 0.0),
                fv.get("risk_score", 0.0) / 100.0,
            ]
            rows.append(row)
        return np.array(rows, dtype=float)

    def train(self, tps: list[dict], fps: list[dict]) -> bool:
        """
        Train the FP dampening model.

        Returns True if training succeeded, False if insufficient data.
        """
        if len(tps) < 5 or len(fps) < 5:
            print(f"[FPDampening] Insufficient data: {len(tps)} TPs, {len(fps)} FPs. Need 5+ each.")
            return False

        X_tp = self._extract_features(tps)
        X_fp = self._extract_features(fps)
        X    = np.vstack([X_tp, X_fp])
        y    = np.array([0] * len(tps) + [1] * len(fps))  # 0=TP, 1=FP

        X_scaled     = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)
        self.trained = True
        print(f"[FPDampening] Trained on {len(tps)} TPs and {len(fps)} FPs.")
        return True

    def predict_fp_probability(self, feature_vector: dict) -> float:
        """
        Returns P(false_positive) for a given alert.
        Returns 0.0 if model not trained yet.
        """
        if not self.trained:
            return 0.0

        row = np.array([[
            feature_vector.get("layering_gnn", 0.0),
            feature_vector.get("round_tripping_xgb", 0.0),
            feature_vector.get("structuring_iforest", 0.0),
            feature_vector.get("dormant_activation_svm", 0.0),
            feature_vector.get("profile_mismatch_lgbm", 0.0),
            feature_vector.get("risk_score", 0.0) / 100.0,
        ]])
        X_scaled = self.scaler.transform(row)
        prob = self.model.predict_proba(X_scaled)[0][1]
        return float(prob)

    def should_deprioritize(self, feature_vector: dict, threshold: float = 0.85) -> bool:
        """Returns True if alert should be auto-deprioritised."""
        return self.predict_fp_probability(feature_vector) > threshold


# ─── PSI Monitor ─────────────────────────────────────────────────────────────

class PSIMonitor:
    """
    Population Stability Index monitor.

    Tracks distribution of model scores over time.
    PSI > 0.25 on any feature triggers a model review alert.

    PSI interpretation:
        < 0.10 — no significant change
        0.10–0.25 — moderate change, monitor
        > 0.25 — significant drift, investigate
    """

    @staticmethod
    def calculate_psi(
        baseline: np.ndarray,
        current: np.ndarray,
        bins: int = 10,
    ) -> float:
        """Calculate PSI between baseline and current distributions."""
        # Create bins from baseline
        breakpoints = np.linspace(0, 1, bins + 1)

        baseline_pct = np.histogram(baseline, bins=breakpoints)[0] / len(baseline)
        current_pct  = np.histogram(current,  bins=breakpoints)[0] / len(current)

        # Avoid division by zero / log(0)
        baseline_pct = np.where(baseline_pct == 0, 0.0001, baseline_pct)
        current_pct  = np.where(current_pct  == 0, 0.0001, current_pct)

        psi = np.sum((current_pct - baseline_pct) * np.log(current_pct / baseline_pct))
        return float(psi)

    def run_check(
        self,
        baseline_scores: dict[str, list[float]],
        current_scores:  dict[str, list[float]],
    ) -> dict:
        """
        Run PSI check across all model features.

        Args:
            baseline_scores: Dict of {model_name: [scores]} from training period.
            current_scores:  Dict of {model_name: [scores]} from recent period.

        Returns:
            Dict with PSI per feature and overall drift status.
        """
        results = {}
        drift_detected = False

        for feature in baseline_scores:
            if feature not in current_scores:
                continue
            base = np.array(baseline_scores[feature])
            curr = np.array(current_scores[feature])

            if len(base) < 10 or len(curr) < 10:
                results[feature] = {"psi": None, "status": "INSUFFICIENT_DATA"}
                continue

            psi = self.calculate_psi(base, curr)
            if psi > PSI_ALERT_THRESHOLD:
                status = "DRIFT_DETECTED"
                drift_detected = True
            elif psi > 0.10:
                status = "MODERATE_CHANGE"
            else:
                status = "STABLE"

            results[feature] = {"psi": round(psi, 4), "status": status}

        return {
            "feature_psi":     results,
            "drift_detected":  drift_detected,
            "alert_threshold": PSI_ALERT_THRESHOLD,
            "checked_at":      datetime.now(timezone.utc).isoformat(),
            "recommendation":  "Force model review" if drift_detected else "No action required",
        }
