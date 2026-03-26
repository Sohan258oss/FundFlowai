"""
Tests for the synthetic data generator.

These tests validate that:
1. Account generation produces correct counts and distributions
2. Normal transaction generation creates realistic activity
3. Each pattern injector produces correctly labelled suspicious transactions
4. The main orchestrator ties everything together
"""

import pytest
from datetime import datetime, timedelta

from data_generator.accounts import generate_accounts, Account
from data_generator.transactions import generate_normal_transactions, Transaction
from data_generator.patterns.layering import inject_layering_patterns
from data_generator.patterns.round_tripping import inject_round_tripping_patterns
from data_generator.patterns.structuring import inject_structuring_patterns
from data_generator.patterns.dormant_activation import inject_dormant_activation_patterns
from data_generator.patterns.profile_mismatch import inject_profile_mismatch_patterns


# ─────────────────────────────────────────────────────────────────────────────
# Account Generation
# ─────────────────────────────────────────────────────────────────────────────

class TestAccountGeneration:
    def test_generates_correct_count(self):
        accounts = generate_accounts(count=100, seed=42)
        assert len(accounts) == 100

    def test_all_accounts_have_required_fields(self):
        accounts = generate_accounts(count=50, seed=42)
        for acct in accounts:
            assert acct.account_id.startswith("ACC-")
            assert acct.entity_id.startswith("ENT-")
            assert acct.account_type in [
                "SAVINGS", "CURRENT", "SALARY", "LOAN", "WALLET", "FD"
            ]
            assert acct.status in ["ACTIVE", "DORMANT", "CLOSED"]
            assert acct.annual_income >= 0
            assert acct.branch_code.startswith("FUND0")

    def test_dormant_accounts_exist(self):
        accounts = generate_accounts(count=1000, seed=42)
        dormant = [a for a in accounts if a.status == "DORMANT"]
        # At 5% rate, expect roughly 50 ± 30
        assert len(dormant) > 10

    def test_entity_deduplication(self):
        """Some entities should own multiple accounts."""
        accounts = generate_accounts(count=500, seed=42)
        entity_ids = [a.entity_id for a in accounts]
        unique_entities = set(entity_ids)
        # Should have fewer unique entities than accounts
        assert len(unique_entities) < len(accounts)

    def test_reproducibility(self):
        a1 = generate_accounts(count=50, seed=99)
        a2 = generate_accounts(count=50, seed=99)
        assert [a.account_id for a in a1] == [a.account_id for a in a2]

    def test_pep_flag_rare(self):
        accounts = generate_accounts(count=2000, seed=42)
        peps = [a for a in accounts if a.pep_flag]
        # PEP rate ~0.5% of individuals
        assert len(peps) < 30  # generous upper bound


# ─────────────────────────────────────────────────────────────────────────────
# Normal Transaction Generation
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalTransactions:
    @pytest.fixture
    def accounts(self):
        return generate_accounts(count=200, seed=42)

    def test_generates_transactions(self, accounts):
        txns = generate_normal_transactions(accounts, days=30, seed=42)
        assert len(txns) > 0

    def test_transactions_are_sorted(self, accounts):
        txns = generate_normal_transactions(accounts, days=30, seed=42)
        timestamps = [t.timestamp_initiated for t in txns]
        assert timestamps == sorted(timestamps)

    def test_all_transactions_have_required_fields(self, accounts):
        txns = generate_normal_transactions(accounts, days=10, seed=42)
        for txn in txns[:100]:  # check first 100
            assert txn.txn_id.startswith("TXN-")
            assert txn.source_system in [
                "UPI", "NEFT", "RTGS", "IMPS", "SWIFT", "CARD", "CASH", "WALLET"
            ]
            assert txn.amount_value > 0
            assert txn.amount_currency == "INR"
            assert txn.sender_account_id.startswith("ACC-")
            assert txn.receiver_account_id.startswith("ACC-")
            assert not txn.is_suspicious

    def test_no_suspicious_flags(self, accounts):
        txns = generate_normal_transactions(accounts, days=10, seed=42)
        suspicious = [t for t in txns if t.is_suspicious]
        assert len(suspicious) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Layering Pattern
# ─────────────────────────────────────────────────────────────────────────────

class TestLayeringPattern:
    @pytest.fixture
    def accounts(self):
        return generate_accounts(count=500, seed=42)

    def test_injects_patterns(self, accounts):
        txns, gt = inject_layering_patterns(accounts, count=10)
        assert len(gt) == 10
        assert all(t.is_suspicious for t in txns)
        assert all(t.suspicious_pattern == "LAYERING" for t in txns)

    def test_chain_structure(self, accounts):
        txns, gt = inject_layering_patterns(accounts, count=5)
        for pattern in gt:
            assert pattern["pattern_type"] == "LAYERING"
            assert pattern["num_hops"] >= 3
            assert pattern["amount_preservation_ratio"] > 0.80
            assert pattern["amount_preservation_ratio"] < 1.0
            assert len(pattern["transaction_ids"]) == pattern["num_hops"]

    def test_pattern_ids_unique(self, accounts):
        _, gt = inject_layering_patterns(accounts, count=20)
        ids = [p["pattern_id"] for p in gt]
        assert len(ids) == len(set(ids))


# ─────────────────────────────────────────────────────────────────────────────
# Round-Tripping Pattern
# ─────────────────────────────────────────────────────────────────────────────

class TestRoundTrippingPattern:
    @pytest.fixture
    def accounts(self):
        return generate_accounts(count=500, seed=42)

    def test_injects_patterns(self, accounts):
        txns, gt = inject_round_tripping_patterns(accounts, count=10)
        assert len(gt) > 0  # may be slightly less than 10 if sampling fails
        assert all(t.is_suspicious for t in txns)
        assert all(t.suspicious_pattern == "ROUND_TRIPPING" for t in txns)

    def test_cycle_structure(self, accounts):
        _, gt = inject_round_tripping_patterns(accounts, count=5)
        for pattern in gt:
            assert pattern["pattern_type"] == "ROUND_TRIPPING"
            assert pattern["cycle_length"] >= 4  # at least 4 accounts in cycle
            assert pattern["amount_preservation_ratio"] > 0.80


# ─────────────────────────────────────────────────────────────────────────────
# Structuring Pattern
# ─────────────────────────────────────────────────────────────────────────────

class TestStructuringPattern:
    @pytest.fixture
    def accounts(self):
        return generate_accounts(count=200, seed=42)

    def test_injects_patterns(self, accounts):
        txns, gt = inject_structuring_patterns(accounts, count=10)
        assert len(gt) == 10
        assert all(t.is_suspicious for t in txns)
        assert all(t.suspicious_pattern == "STRUCTURING" for t in txns)

    def test_below_threshold(self, accounts):
        _, gt = inject_structuring_patterns(accounts, count=10)
        for pattern in gt:
            assert pattern["pattern_type"] == "STRUCTURING"
            # Total should exceed threshold
            assert pattern["total_amount"] >= 1_000_000
            # Each individual deposit should be below threshold
            assert pattern["all_below_threshold"]

    def test_variants_present(self, accounts):
        _, gt = inject_structuring_patterns(accounts, count=50, seed=42)
        variants = set(p["variant"] for p in gt)
        # With 50 patterns, we should see at least 2 variants
        assert len(variants) >= 2


# ─────────────────────────────────────────────────────────────────────────────
# Dormant Activation Pattern
# ─────────────────────────────────────────────────────────────────────────────

class TestDormantActivationPattern:
    @pytest.fixture
    def accounts(self):
        return generate_accounts(count=500, seed=42)

    def test_injects_patterns(self, accounts):
        txns, gt = inject_dormant_activation_patterns(accounts, count=10)
        assert len(gt) == 10
        assert all(t.is_suspicious for t in txns)
        assert all(t.suspicious_pattern == "DORMANT_ACTIVATION" for t in txns)

    def test_high_amount_ratio(self, accounts):
        _, gt = inject_dormant_activation_patterns(accounts, count=10)
        for pattern in gt:
            assert pattern["pattern_type"] == "DORMANT_ACTIVATION"
            # Amount should be disproportionate to income
            assert pattern["amount_to_income_ratio"] > 0.5


# ─────────────────────────────────────────────────────────────────────────────
# Profile Mismatch Pattern
# ─────────────────────────────────────────────────────────────────────────────

class TestProfileMismatchPattern:
    @pytest.fixture
    def accounts(self):
        return generate_accounts(count=500, seed=42)

    def test_injects_patterns(self, accounts):
        txns, gt = inject_profile_mismatch_patterns(accounts, count=10)
        assert len(gt) == 10
        assert all(t.is_suspicious for t in txns)
        assert all(t.suspicious_pattern == "PROFILE_MISMATCH" for t in txns)

    def test_high_amount_to_income(self, accounts):
        _, gt = inject_profile_mismatch_patterns(accounts, count=10)
        for pattern in gt:
            # Amount should be many multiples of income
            assert pattern["amount_to_annual_income_ratio"] > 1.0

    def test_occupation_coverage(self, accounts):
        _, gt = inject_profile_mismatch_patterns(accounts, count=50, seed=42)
        occupations = set(p["occupation"] for p in gt)
        # Should hit at least 3 different occupation types
        assert len(occupations) >= 3
