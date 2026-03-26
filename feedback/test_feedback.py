"""
Tests for the feedback loop module.
"""
import pytest
import os
import json
import tempfile
from pathlib import Path

from feedback_core import (
    DispositionRecorder,
    FPDampeningModel,
    PSIMonitor,
    DISPOSITION_TP,
    DISPOSITION_FP,
    DISPOSITION_INDETERMINATE,
    DISPOSITION_ESCALATED,
    FP_REASON_CODES,
    STORAGE_PATH,
)


def _fresh_store(tmp_path):
    """Point STORAGE_PATH to a fresh temp file and wipe it."""
    import feedback_core
    feedback_core.STORAGE_PATH = Path(tmp_path)
    if Path(tmp_path).exists():
        Path(tmp_path).unlink()


class TestDispositionRecorder:
    def setup_method(self):
        self.tmp = tempfile.mktemp(suffix=".json")
        _fresh_store(self.tmp)
        self.recorder = DispositionRecorder()

    def test_record_true_positive(self):
        rec = self.recorder.record(
            cluster_id="CLU-001",
            investigator_id="INV-001",
            disposition=DISPOSITION_TP,
            feature_vector={"risk_score": 85},
        )
        assert rec["label"] == "TP"
        assert rec["disposition"] == DISPOSITION_TP

    def test_record_false_positive_requires_reason(self):
        with pytest.raises(ValueError, match="reason_code required"):
            self.recorder.record(
                cluster_id="CLU-002",
                investigator_id="INV-001",
                disposition=DISPOSITION_FP,
            )

    def test_record_false_positive_with_reason(self):
        rec = self.recorder.record(
            cluster_id="CLU-003",
            investigator_id="INV-001",
            disposition=DISPOSITION_FP,
            reason_code="NORMAL_BUSINESS",
        )
        assert rec["label"] == "FP_SOFT"

    def test_insufficient_evidence_is_indeterminate(self):
        rec = self.recorder.record(
            cluster_id="CLU-004",
            investigator_id="INV-001",
            disposition=DISPOSITION_FP,
            reason_code="INSUFFICIENT_EVIDENCE",
        )
        assert rec["label"] == "INDETERMINATE"

    def test_retrain_trigger(self):
        assert not self.recorder.should_retrain()
        for i in range(50):
            self.recorder.record(
                cluster_id=f"CLU-{i:03d}",
                investigator_id="INV-001",
                disposition=DISPOSITION_TP,
            )
        assert self.recorder.should_retrain()

    def test_reset_retrain_counter(self):
        for i in range(50):
            self.recorder.record(
                cluster_id=f"CLU-R{i:03d}",
                investigator_id="INV-001",
                disposition=DISPOSITION_TP,
            )
        assert self.recorder.should_retrain()
        self.recorder.reset_retrain_counter()
        assert not self.recorder.should_retrain()

    def test_stats(self):
        self.recorder.record("CLU-S1", "INV-001", DISPOSITION_TP)
        self.recorder.record("CLU-S2", "INV-001", DISPOSITION_FP, reason_code="NORMAL_BUSINESS")
        stats = self.recorder.get_stats()
        assert stats["true_positives"] == 1
        assert stats["false_positives"] == 1
        assert stats["total_dispositions"] == 2


class TestFPDampeningModel:
    def setup_method(self):
        self.model = FPDampeningModel()

    def _make_records(self, n: int, label: str) -> list[dict]:
        import random
        records = []
        for _ in range(n):
            records.append({
                "label": label,
                "feature_vector": {
                    "layering_gnn":           random.uniform(0.5, 1.0) if label == "TP" else random.uniform(0.0, 0.4),
                    "round_tripping_xgb":     random.uniform(0.0, 1.0),
                    "structuring_iforest":    random.uniform(0.0, 1.0),
                    "dormant_activation_svm": random.uniform(0.0, 1.0),
                    "profile_mismatch_lgbm":  random.uniform(0.0, 1.0),
                    "risk_score":             random.uniform(60, 100) if label == "TP" else random.uniform(20, 50),
                },
            })
        return records

    def test_train_requires_minimum_data(self):
        result = self.model.train([], [])
        assert result is False

    def test_train_succeeds_with_sufficient_data(self):
        tps = self._make_records(10, "TP")
        fps = self._make_records(10, "FP_SOFT")
        result = self.model.train(tps, fps)
        assert result is True
        assert self.model.trained is True

    def test_predict_returns_zero_when_untrained(self):
        prob = self.model.predict_fp_probability({"risk_score": 80})
        assert prob == 0.0

    def test_predict_returns_probability_after_training(self):
        tps = self._make_records(10, "TP")
        fps = self._make_records(10, "FP_SOFT")
        self.model.train(tps, fps)
        prob = self.model.predict_fp_probability({"risk_score": 85, "layering_gnn": 0.9})
        assert 0.0 <= prob <= 1.0


class TestPSIMonitor:
    def setup_method(self):
        self.monitor = PSIMonitor()

    def test_stable_distribution(self):
        import random
        baseline = {"layering_gnn": [random.uniform(0, 1) for _ in range(100)]}
        current  = {"layering_gnn": [random.uniform(0, 1) for _ in range(100)]}
        result = self.monitor.run_check(baseline, current)
        assert "feature_psi" in result
        assert "drift_detected" in result

    def test_drifted_distribution_detected(self):
        baseline = {"layering_gnn": [0.1] * 100}
        current  = {"layering_gnn": [0.9] * 100}
        result = self.monitor.run_check(baseline, current)
        assert result["drift_detected"] is True
        assert result["feature_psi"]["layering_gnn"]["psi"] > 0.25

    def test_insufficient_data_handled(self):
        baseline = {"layering_gnn": [0.5] * 3}
        current  = {"layering_gnn": [0.5] * 3}
        result = self.monitor.run_check(baseline, current)
        assert result["feature_psi"]["layering_gnn"]["status"] == "INSUFFICIENT_DATA"