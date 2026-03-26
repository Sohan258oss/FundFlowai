"""
Layering pattern injector.

Generates multi-hop fund flows (A→B→C→D→E) where money moves rapidly
through intermediary accounts with minimal amount loss, designed to
obscure the original source of funds.
"""

import random
from datetime import datetime, timedelta
from typing import List, Tuple

from data_generator.accounts import Account
from data_generator.transactions import Transaction


def _random_hex(length: int) -> str:
    return ''.join(random.choices('0123456789ABCDEF', k=length))


def inject_layering_patterns(
    accounts: List[Account],
    count: int = 100,
    end_date: datetime | None = None,
    seed: int = 1001,
) -> Tuple[List[Transaction], List[dict]]:
    """
    Inject layering chains into the transaction set.

    Each layering pattern creates a chain of 3-6 hops where:
    - Total elapsed time is 2-72 hours
    - Amount is preserved within 90-99% across hops
    - Intermediary accounts often have mismatched profiles

    Args:
        accounts: Full list of accounts to pick from.
        count: Number of layering patterns to inject.
        end_date: Latest timestamp for the pattern.
        seed: Random seed.

    Returns:
        Tuple of (transactions, ground_truth_records).
    """
    random.seed(seed)

    if end_date is None:
        end_date = datetime.now()

    active = [a for a in accounts if a.status == "ACTIVE"]
    if len(active) < 6:
        return [], []

    transactions: List[Transaction] = []
    ground_truth: List[dict] = []

    for pattern_idx in range(count):
        # Number of hops: 3-6
        n_hops = random.randint(3, 6)
        chain_accounts = random.sample(active, n_hops + 1)

        # Starting amount: large enough to be material (₹2L - ₹50L)
        initial_amount = round(float(random.uniform(500_000, 10_000_000)), 2)  # type: ignore

        # Start time: random point within last 90 days
        days_back = random.randint(1, 90)
        chain_start = end_date - timedelta(days=days_back)
        chain_start = chain_start.replace(
            hour=random.randint(6, 22),
            minute=random.randint(0, 59),
        )

        pattern_id = f"LAYER-{_random_hex(8)}"
        current_amount = initial_amount
        current_time = chain_start
        chain_txn_ids = []

        for hop in range(n_hops):
            sender = chain_accounts[hop]
            receiver = chain_accounts[hop + 1]

            # Amount leakage: 1-3% per hop (fees, small diversions)
            leakage = random.uniform(0.01, 0.03)
            preservation = 1 - leakage # Added this line to define 'preservation'
            current_amount = round(float(current_amount * preservation), 2)  # type: ignore

            # Time between hops: 10 minutes to 18 hours
            # Earlier hops tend to be faster (urgency)
            max_delay_hours = min(4 + hop * 3, 18)
            delay_minutes = random.randint(10, int(max_delay_hours * 60))
            current_time = current_time + timedelta(minutes=delay_minutes)

            # Layerers often use digital channels
            channel = random.choice(["MOBILE", "INTERNET", "API"])

            # Source system: mix of instant rails
            source = random.choice(["UPI", "IMPS", "NEFT", "RTGS"])
            if current_amount >= 200_000:
                source = random.choice(["RTGS", "NEFT", "IMPS"])

            txn_id = f"TXN-{_random_hex(16)}"
            chain_txn_ids.append(txn_id)

            txn = Transaction(
                txn_id=txn_id,
                source_system=source,
                original_ref=f"{source}-{_random_hex(10)}",
                timestamp_initiated=current_time.strftime("%Y-%m-%dT%H:%M:%S"),
                timestamp_settled=(
                    (current_time + timedelta(minutes=random.randint(1, 30)))
                    .strftime("%Y-%m-%dT%H:%M:%S")
                ),
                amount_value=current_amount,
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
                suspicious_pattern="LAYERING",
                pattern_group_id=pattern_id,
            )
            transactions.append(txn)

        # Record ground truth
        ground_truth.append({
            "pattern_id": pattern_id,
            "pattern_type": "LAYERING",
            "num_hops": n_hops,
            "initial_amount": initial_amount,
            "final_amount": current_amount,
            "amount_preservation_ratio": round(float(current_amount / initial_amount), 4),  # type: ignore
            "elapsed_hours": round((current_time - chain_start).total_seconds() / 3600, 2),  # type: ignore
            "account_chain": [a.account_id for a in chain_accounts],
            "transaction_ids": chain_txn_ids,
            "start_time": chain_start.strftime("%Y-%m-%dT%H:%M:%S"),
            "end_time": current_time.strftime("%Y-%m-%dT%H:%M:%S"),
        })

    return transactions, ground_truth
