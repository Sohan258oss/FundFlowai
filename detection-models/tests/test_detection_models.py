"""
Smoke tests for detection models — Phase 2.

Tests basic instantiation, data preparation shape validation,
and training pipeline without requiring Neo4j or large datasets.
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch


# ─── Test Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def sample_accounts_df():
    """Minimal accounts DataFrame for testing."""
    np.random.seed(42)
    n = 50
    return pd.DataFrame({
        "account_id": [f"ACC-{i:04d}" for i in range(n)],
        "entity_id": [f"ENT-{i:04d}" for i in range(n)],
        "entity_name": [f"Entity {i}" for i in range(n)],
        "account_type": np.random.choice(["SAVINGS", "CURRENT"], n),
        "annual_income": np.random.uniform(200_000, 5_000_000, n),
        "avg_balance_30d": np.random.uniform(10_000, 500_000, n),
        "status": np.random.choice(["ACTIVE", "DORMANT"], n, p=[0.9, 0.1]),
        "occupation": np.random.choice(
            ["SALARIED_PRIVATE", "SELF_EMPLOYED_BUSINESS", "STUDENT", "RETIRED"], n
        ),
        "branch_code": [f"FUND{i:05d}" for i in range(n)],
    })


@pytest.fixture
def sample_transactions_df(sample_accounts_df):
    """Minimal transactions DataFrame for testing."""
    np.random.seed(42)
    accounts = sample_accounts_df["account_id"].tolist()
    n_txns = 200
    senders = np.random.choice(accounts, n_txns)
    receivers = np.random.choice(accounts, n_txns)
    # Avoid self-transfers
    for i in range(n_txns):
        while receivers[i] == senders[i]:
            receivers[i] = np.random.choice(accounts)

    base_time = pd.Timestamp("2026-01-01")
    timestamps = [base_time + pd.Timedelta(hours=np.random.randint(0, 2160)) for _ in range(n_txns)]

    return pd.DataFrame({
        "txn_id": [f"TXN-{i:06d}" for i in range(n_txns)],
        "sender_account_id": senders,
        "receiver_account_id": receivers,
        "amount_value": np.random.uniform(100, 1_000_000, n_txns),
        "amount_currency": "INR",
        "timestamp_initiated": timestamps,
        "timestamp_settled": timestamps,
        "source_system": np.random.choice(["UPI", "NEFT", "RTGS", "IMPS", "SWIFT"], n_txns),
        "channel": np.random.choice(["MOBILE", "INTERNET", "BRANCH"], n_txns),
        "purpose_code": np.random.choice(["P2P", "TRANSFER", "TRADE_PAYMENT", "SALARY"], n_txns),
        "is_suspicious": [False] * n_txns,
        "suspicious_pattern": [None] * n_txns,
    })


@pytest.fixture
def sample_ground_truth(sample_accounts_df):
    """Minimal ground truth with at least one of each pattern type."""
    accounts = sample_accounts_df["account_id"].tolist()
    return [
        # Layering patterns
        *[{
            "pattern_id": f"LAY-{i:03d}",
            "pattern_type": "LAYERING",
            "account_chain": [accounts[i], accounts[i + 1], accounts[i + 2]],
            "depth": 3,
            "transaction_ids": [f"TXN-LAY-{i}"],
        } for i in range(0, 10)],
        # Round-tripping patterns
        *[{
            "pattern_id": f"RT-{i:03d}",
            "pattern_type": "ROUND_TRIPPING",
            "account_cycle": [accounts[i + 10], accounts[i + 11], accounts[i + 12], accounts[i + 10]],
            "originator_account": accounts[i + 10],
            "transaction_ids": [f"TXN-RT-{i}"],
        } for i in range(0, 8)],
        # Structuring patterns
        *[{
            "pattern_id": f"STR-{i:03d}",
            "pattern_type": "STRUCTURING",
            "account_id": accounts[i + 20],
            "transaction_ids": [f"TXN-STR-{i}"],
        } for i in range(0, 10)],
        # Dormant activation patterns
        *[{
            "pattern_id": f"DORM-{i:03d}",
            "pattern_type": "DORMANT_ACTIVATION",
            "account_id": accounts[i + 30],
            "transaction_ids": [f"TXN-DORM-{i}"],
        } for i in range(0, 8)],
        # Profile mismatch patterns
        *[{
            "pattern_id": f"PM-{i:03d}",
            "pattern_type": "PROFILE_MISMATCH",
            "account_id": accounts[i + 38],
            "transaction_ids": [f"TXN-PM-{i}"],
        } for i in range(0, 10)],
    ]


# ─── Account Feature Extractor Tests ─────────────────────────────────────────

class TestAccountFeatureExtractor:
    def test_extracts_all_features(self, sample_accounts_df, sample_transactions_df):
        from detection_models.features.account_features import AccountFeatureExtractor

        extractor = AccountFeatureExtractor(sample_accounts_df, sample_transactions_df)
        features = extractor.get_all_features()

        assert not features.empty
        assert "annual_income" in features.columns
        assert "max_daily_outflow" in features.columns
        assert "max_dormancy_days" in features.columns

    def test_velocity_features_non_negative(self, sample_accounts_df, sample_transactions_df):
        from detection_models.features.account_features import AccountFeatureExtractor

        extractor = AccountFeatureExtractor(sample_accounts_df, sample_transactions_df)
        vel = extractor.extract_velocity_features()

        assert (vel["max_daily_outflow"] >= 0).all()
        assert (vel["avg_daily_outflow"] >= 0).all()

    def test_dormancy_features_non_negative(self, sample_accounts_df, sample_transactions_df):
        from detection_models.features.account_features import AccountFeatureExtractor

        extractor = AccountFeatureExtractor(sample_accounts_df, sample_transactions_df)
        dorm = extractor.extract_dormancy_features()

        assert (dorm["max_dormancy_days"] >= 0).all()


# ─── Round Trip Detector Tests ────────────────────────────────────────────────

class TestRoundTripDetector:
    def test_prepare_data_shapes(self, sample_accounts_df, sample_transactions_df, sample_ground_truth):
        from detection_models.models.round_trip_xgb import RoundTripDetector
        from detection_models.features.account_features import AccountFeatureExtractor

        acc_ext = AccountFeatureExtractor(sample_accounts_df, sample_transactions_df)
        account_features = acc_ext.get_all_features()
        # Empty graph features (no Neo4j)
        graph_features = pd.DataFrame(index=account_features.index)

        detector = RoundTripDetector()
        X, y = detector.prepare_data(graph_features, account_features, sample_ground_truth)

        assert len(X) == len(y)
        assert y.sum() > 0, "Should have at least some positive labels"


# ─── Structuring Detector Tests ───────────────────────────────────────────────

class TestStructuringDetector:
    def test_prepare_data_shapes(self, sample_transactions_df, sample_ground_truth):
        from detection_models.models.structuring_iforest import StructuringDetector

        detector = StructuringDetector()
        daily, X, y = detector.prepare_data(sample_transactions_df, sample_ground_truth)

        assert len(X) == len(y)
        assert "daily_txns" in X.columns
        assert "daily_inflow" in X.columns


# ─── Dormant Activation Detector Tests ────────────────────────────────────────

class TestDormantActivationDetector:
    def test_prepare_data_shapes(self, sample_accounts_df, sample_transactions_df, sample_ground_truth):
        from detection_models.models.dormant_svm import DormantActivationDetector
        from detection_models.features.account_features import AccountFeatureExtractor

        acc_ext = AccountFeatureExtractor(sample_accounts_df, sample_transactions_df)
        account_features = acc_ext.get_all_features()

        detector = DormantActivationDetector()
        df, X, y = detector.prepare_data(account_features, sample_ground_truth)

        assert len(X) == len(y)
        assert "max_dormancy_days" in X.columns


# ─── Profile Mismatch Detector Tests ─────────────────────────────────────────

class TestProfileMismatchDetector:
    def test_prepare_data_shapes(self, sample_accounts_df, sample_transactions_df, sample_ground_truth):
        from detection_models.models.profile_mismatch_lgbm import ProfileMismatchDetector

        detector = ProfileMismatchDetector()
        df, X, y = detector.prepare_data(sample_accounts_df, sample_transactions_df, sample_ground_truth)

        assert len(X) == len(y)
        assert "tx_to_income_ratio" in X.columns
        assert "is_swift" in X.columns
