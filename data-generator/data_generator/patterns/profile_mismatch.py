"""
Profile-transaction mismatch pattern injector.

Generates transactions that are grossly inconsistent with the customer's
declared profile — e.g., a salaried individual receiving multi-crore
wire transfers, or a student account processing business payments.
"""

import random
from datetime import datetime, timedelta
from typing import List, Tuple

from data_generator.accounts import Account
from data_generator.transactions import Transaction


def _random_hex(length: int) -> str:
    return ''.join(random.choices('0123456789ABCDEF', k=length))


# Mismatch scenarios keyed by occupation
MISMATCH_SCENARIOS = {
    "SALARIED_PRIVATE": {
        "description": "Salaried employee receiving large business payments",
        "amount_multiplier": (10, 50),  # × monthly income
        "purpose_codes": ["TRADE_PAYMENT", "INVESTMENT", "TRANSFER"],
        "source_systems": ["SWIFT", "RTGS", "NEFT"],
    },
    "SALARIED_GOVT": {
        "description": "Govt employee with unexplained large inflows",
        "amount_multiplier": (15, 100),
        "purpose_codes": ["TRANSFER", "TRADE_PAYMENT"],
        "source_systems": ["NEFT", "RTGS"],
    },
    "STUDENT": {
        "description": "Student account with business-scale transactions",
        "amount_multiplier": (50, 200),
        "purpose_codes": ["TRADE_PAYMENT", "TRANSFER", "INVESTMENT"],
        "source_systems": ["NEFT", "RTGS", "SWIFT"],
    },
    "HOMEMAKER": {
        "description": "Homemaker account with commercial activity",
        "amount_multiplier": (20, 100),
        "purpose_codes": ["TRADE_PAYMENT", "TRANSFER"],
        "source_systems": ["NEFT", "RTGS"],
    },
    "RETIRED": {
        "description": "Retired person with sudden high-value activity",
        "amount_multiplier": (10, 40),
        "purpose_codes": ["TRANSFER", "INVESTMENT", "TRADE_PAYMENT"],
        "source_systems": ["NEFT", "RTGS", "SWIFT"],
    },
    "AGRICULTURE": {
        "description": "Agriculture worker receiving forex/trade payments",
        "amount_multiplier": (15, 60),
        "purpose_codes": ["TRADE_PAYMENT", "TRANSFER"],
        "source_systems": ["SWIFT", "NEFT"],
    },
}

# Occupations with clear mismatch potential
MISMATCH_OCCUPATIONS = list(MISMATCH_SCENARIOS.keys())


def inject_profile_mismatch_patterns(
    accounts: List[Account],
    count: int = 120,
    end_date: datetime | None = None,
    seed: int = 5001,
) -> Tuple[List[Transaction], List[dict]]:
    """
    Inject profile-transaction mismatch patterns.

    Selects accounts where the customer profile makes certain transaction
    types highly anomalous and generates those transactions.

    Args:
        accounts: Full account list.
        count: Number of patterns.
        end_date: Latest timestamp.
        seed: Random seed.

    Returns:
        Tuple of (transactions, ground_truth_records).
    """
    random.seed(seed)

    if end_date is None:
        end_date = datetime.now()

    # Filter to accounts with mismatch-capable occupations
    eligible = [
        a for a in accounts
        if a.status == "ACTIVE" and a.occupation in MISMATCH_OCCUPATIONS
    ]
    active = [a for a in accounts if a.status == "ACTIVE"]

    if not eligible or not active:
        return [], []

    transactions: List[Transaction] = []
    ground_truth: List[dict] = []

    for pattern_idx in range(count):
        account = random.choice(eligible)
        scenario = MISMATCH_SCENARIOS[account.occupation]
        pattern_id = f"MISMATCH-{_random_hex(8)}"

        # Generate 2-5 mismatched transactions over 1-14 days
        n_txns = random.randint(2, 5)
        chain_txn_ids = []
        total_amount = 0.0

        days_back = random.randint(1, 60)
        base_time = end_date - timedelta(days=days_back)

        monthly_income = account.annual_income / 12
        low_mult, high_mult = scenario["amount_multiplier"]

        for txn_idx in range(n_txns):
            offset_days = random.uniform(0, 14)
            txn_time = base_time + timedelta(
                days=offset_days,
                hours=random.randint(8, 20),
                minutes=random.randint(0, 59),
            )

            # Amount: dramatically higher than profile would suggest
            multiplier = random.uniform(float(low_mult), float(high_mult))
            amount = round(float(monthly_income * multiplier), 2)  # type: ignore
            amount = max(amount, 100_000)  # floor

            purpose = random.choice(scenario["purpose_codes"])  # type: ignore
            source = random.choice(scenario["source_systems"])  # type: ignore

            # Mostly inflows (receiving money they shouldn't)
            is_inflow = random.random() < 0.7
            counterparty = random.choice(active)
            while counterparty.account_id == account.account_id:
                counterparty = random.choice(active)

            if is_inflow:
                sender, receiver = counterparty, account
            else:
                sender, receiver = account, counterparty

            # SWIFT transactions suggest international — extra suspicious
            # for domestic profiles
            channel = random.choice(["INTERNET", "MOBILE", "API"])

            txn_id = f"TXN-{_random_hex(16)}"
            chain_txn_ids.append(txn_id)

            txn = Transaction(
                txn_id=txn_id,
                source_system=source,
                original_ref=f"{source}-{_random_hex(10)}",
                timestamp_initiated=txn_time.strftime("%Y-%m-%dT%H:%M:%S"),
                timestamp_settled=(
                    (txn_time + timedelta(hours=random.randint(1, 48)))
                    .strftime("%Y-%m-%dT%H:%M:%S")
                ),
                amount_value=amount,
                amount_currency="INR",
                sender_account_id=sender.account_id,
                sender_entity_id=sender.entity_id,
                sender_account_type=sender.account_type,
                sender_branch_code=sender.branch_code,
                sender_bank_code=(
                    "EXTERNAL_BIC" if source == "SWIFT" else "INTERNAL"
                ),
                receiver_account_id=receiver.account_id,
                receiver_entity_id=receiver.entity_id,
                receiver_account_type=receiver.account_type,
                receiver_branch_code=receiver.branch_code,
                receiver_bank_code="INTERNAL",
                channel=channel,
                product_code=(
                    "FX_TXN" if source == "SWIFT" else "RETAIL_TXN"
                ),
                purpose_code=purpose,
                is_suspicious=True,
                suspicious_pattern="PROFILE_MISMATCH",
                pattern_group_id=pattern_id,
            )
            transactions.append(txn)
            total_amount += amount

        ground_truth.append({
            "pattern_id": pattern_id,
            "pattern_type": "PROFILE_MISMATCH",
            "account_id": account.account_id,
            "occupation": account.occupation,
            "annual_income": account.annual_income,
            "mismatch_description": scenario["description"],
            "total_suspicious_amount": round(float(total_amount), 2),  # type: ignore
            "amount_to_annual_income_ratio": round(float(total_amount / max(account.annual_income, 1)), 2),  # type: ignore
            "num_transactions": n_txns,
            "involved_swift": any(
                t.source_system == "SWIFT" for t in transactions[-n_txns:]
            ),
            "transaction_ids": chain_txn_ids,
        })

    return transactions, ground_truth
