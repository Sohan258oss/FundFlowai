from fastapi.testclient import TestClient
from risk_scoring.api import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_score_high_risk_cluster():
    payload = {
        "cluster_id": "CLS-9001",
        "model_probabilities": {
            "layering_gnn": 0.85,
            "round_tripping_xgb": 0.10,
            "structuring_iforest": 0.05,
            "dormant_activation_svm": 0.01,
            "profile_mismatch_lgbm": 0.20
        },
        "context_flags": {
            "is_pep": True,
            "high_risk_jurisdiction": False,
            "rapid_pass_through": False
        }
    }
    
    response = client.post("/api/v1/score", json=payload)
    assert response.status_code == 200
    
    data = response.json()
    assert data["cluster_id"] == "CLS-9001"
    assert data["risk_score"] > 60 # Base ~0.3 (GN) * 2.0 (PEP) -> ~0.6 -> 60
    assert data["risk_level"] in ["MEDIUM", "HIGH"]
    
    # Evidence should mention layering and PEP
    narrative = " ".join(data["evidence_narrative"])
    assert "Layering" in narrative
    assert "PEP" in narrative

def test_score_low_risk_cluster():
    payload = {
        "cluster_id": "CLS-1002",
        "model_probabilities": {
            "layering_gnn": 0.05,
            "round_tripping_xgb": 0.02,
            "structuring_iforest": 0.01,
            "dormant_activation_svm": 0.01,
            "profile_mismatch_lgbm": 0.05
        },
        "context_flags": {}
    }
    
    response = client.post("/api/v1/score", json=payload)
    assert response.status_code == 200
    
    data = response.json()
    assert data["risk_level"] == "LOW"
    assert "No distinctly suspicious" in " ".join(data["evidence_narrative"])
