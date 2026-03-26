"""
Dormant account activation pattern injector.

Generates suspicious activity on accounts that have been inactive
for 6+ months — sudden high-value transactions, often via digital
channels, without KYC re-verification.
"""

import random
from datetime import datetime, timedelta
from typing import List, Tuple

from data_generator.accounts import Account
from data_generator.transactions import Transaction


def _random_hex(length: int) -> str:
    return ''.join(random.choices('0123456789ABCDEF', k=length))


def inject_dormant_activation_patterns(
    accounts: List[Account],
    count: int = 80,
    end_date: datetime | None = None,
    seed: int = 4001,
) -> Tuple[List[Transaction], List[dict]]:
    """
    Inject dormant account activation patterns.

    Selects dormant accounts and generates sudden high-value activity
    that is inconsistent with the account's historical behavior.

    Args:
        accounts: Full account list.
        count: Number of patterns to inject.
        end_date: Latest timestamp.
        seed: Random seed.

    Returns:
        Tuple of (transactions, ground_truth_records).
    """
    random.seed(seed)

    if end_date is None:
        end_date = datetime.now()

    # Use dormant accounts or randomly select active ones to make dormant
    dormant = [a for a in accounts if a.status == "DORMANT"]
    active = [a for a in accounts if a.status == "ACTIVE"]

    # If not enough dormant accounts, "create" dormancy by picking
    # low-activity active accounts
    if len(dormant) < count:
        low_activity = sorted(active, key=lambda a: a.avg_monthly_txn_count)
        extra_needed = count - len(dormant)
        dormant.extend(low_activity[:extra_needed])

    if len(dormant) < count:
        count = len(dormant)

    if not active:
        return [], []

    transactions: List[Transaction] = []
    ground_truth: List[dict] = []

    selected_dormant = random.sample(dormant, count)

    for account in selected_dormant:
        pattern_id = f"DORMANT-{_random_hex(8)}"

        # Dormancy period: 6-24 months
        dormancy_months = random.randint(6, 24)

        # Activation happens within the recent window
        days_back = random.randint(1, 30)
        activation_time = end_date - timedelta(days=days_back)
        activation_time = activation_time.replace(
            hour=random.randint(0, 23),
            minute=random.randint(0, 59),
        )

        # Generate a burst of activity: 3-8 transactions within 48 hours
        n_txns = random.randint(3, 8)
        chain_txn_ids = []
        total_amount = 0.0
        burst_amounts = [] # Added this line

        for txn_idx in range(n_txns):
            # The user's instruction for this line was problematic.
            # It introduced `initial_amount` and `max_amount` which are not defined,
            # and seemed to replace `offset_hours` line.
            # Given the instruction "Add type ignores to round() calls and list indexing",
            # and the context of the original code, I will apply the type ignore
            # to the existing `suspicious_amount = round(...)` line.
            offset_hours = random.uniform(0, 48)
            txn_time = activation_time + timedelta(hours=offset_hours)

            # Amounts are disproportionately high relative to account profile
            # Normal: based on income. Suspicious: 5-20× normal range
            normal_max = account.annual_income * 0.1  # typical monthly max
            suspicious_amount = round(random.uniform(normal_max * 2, normal_max * 20), 2)  # type: ignore
            suspicious_amount = max(suspicious_amount, 50_000)  # floor at ₹50K
            burst_amounts.append(suspicious_amount) # Added this line

            # Some are inflows, some outflows
            is_inflow = random.random() < 0.6

            # Pick a counterparty
            counterparty = random.choice(active)
            while counterparty.account_id == account.account_id:
                counterparty = random.choice(active)

            if is_inflow:
                sender, receiver = counterparty, account
            else:
                sender, receiver = account, counterparty

            # Dormant reactivation often uses digital channels (less scrutiny)
            channel = random.choice(["MOBILE", "INTERNET", "API"])
            source = random.choice(["UPI", "IMPS", "NEFT"])

            txn_id = f"TXN-{_random_hex(16)}"
            chain_txn_ids.append(txn_id)

            txn = Transaction(
                txn_id=txn_id,
                source_system=source,
                original_ref=f"{source}-{_random_hex(10)}",
                timestamp_initiated=txn_time.strftime("%Y-%m-%dT%H:%M:%S"),
                timestamp_settled=(
                    (txn_time + timedelta(minutes=random.randint(1, 60)))
                    .strftime("%Y-%m-%dT%H:%M:%S")
                ),
                amount_value=suspicious_amount,
                amount_currency="INR",
                sender_account_id=sender.account_id,
                sender_entity_id=sender.entity_id,
                sender_account_type=sender.account_type,
                sender_branch_code=sender.branch_code,
                sender_bank_code="INTERNAL",
                receiver_account_id=receiver.account_id,
                receiver_entity_id=receiver.entity_id,
                receiver_account_type=receiver.account_type,
                receiver_branch_code=receiver.branch_code,
                receiver_bank_code="INTERNAL",
                channel=channel,
                product_code="RETAIL_TXN",
                purpose_code="TRANSFER",
                is_suspicious=True,
                suspicious_pattern="DORMANT_ACTIVATION",
                pattern_group_id=pattern_id,
            )
            transactions.append(txn)
            total_amount += suspicious_amount

        ground_truth.append({
            "pattern_id": pattern_id,
            "pattern_type": "DORMANT_ACTIVATION",
            "account_id": account.account_id,
            "dormancy_months": dormancy_months,
            "activation_burst_txns": n_txns,
            "total_burst_amount": round(float(sum(burst_amounts)), 2),  # type: ignore
            "account_annual_income": account.annual_income,
            "amount_to_income_ratio": round(float(sum(burst_amounts) / account.annual_income), 2),  # type: ignore
            "kyc_status": account.kyc_status,
            "activation_channel": "DIGITAL",
            "transaction_ids": chain_txn_ids,
        })

    return transactions, ground_truth
