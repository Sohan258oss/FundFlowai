"""
Round-tripping pattern injector.

Generates circular fund flows (A→B→C→A) where money leaves an account
and returns to the same or associated account via intermediaries.
"""

import random
from datetime import datetime, timedelta
from typing import List, Tuple
from collections import defaultdict

from data_generator.accounts import Account
from data_generator.transactions import Transaction


def _random_hex(length: int) -> str:
    return ''.join(random.choices('0123456789ABCDEF', k=length))


def inject_round_tripping_patterns(
    accounts: List[Account],
    count: int = 80,
    end_date: datetime | None = None,
    seed: int = 2001,
) -> Tuple[List[Transaction], List[dict]]:
    """
    Inject circular fund flow patterns.

    Each pattern creates a cycle where funds return to the originator
    (or an associated account owned by the same entity) within 3-30 days.

    Args:
        accounts: Full account list.
        count: Number of round-trip patterns.
        end_date: Latest timestamp.
        seed: Random seed.

    Returns:
        Tuple of (transactions, ground_truth_records).
    """
    random.seed(seed)

    if end_date is None:
        end_date = datetime.now()

    active = [a for a in accounts if a.status == "ACTIVE"]
    if len(active) < 4:
        return [], []

    # Build entity-to-account mapping for "associated account" return
    entity_accounts: dict[str, List[Account]] = defaultdict(list)
    for a in active:
        entity_accounts[a.entity_id].append(a)

    transactions: List[Transaction] = []
    ground_truth: List[dict] = []

    for pattern_idx in range(count):
        # Cycle length: 3-6 intermediaries
        cycle_len = random.randint(3, 6)

        # Pick the originator
        originator = random.choice(active)

        # Pick intermediaries (different entities)
        intermediaries = []
        attempts = 0
        while len(intermediaries) < cycle_len - 1 and attempts < 100:
            candidate = random.choice(active)
            if (
                candidate.entity_id != originator.entity_id
                and candidate not in intermediaries
            ):
                intermediaries.append(candidate)
            attempts += 1

        if len(intermediaries) < cycle_len - 1:
            continue

        # Decide if money returns to same account or associated account
        if (
            len(entity_accounts.get(originator.entity_id, [])) > 1
            and random.random() < 0.3
        ):
            # Return to a different account owned by the same entity
            return_account = random.choice(
                [a for a in entity_accounts[originator.entity_id]
                 if a.account_id != originator.account_id]
            )
        else:
            return_account = originator

        # Build the cycle: originator → intermediaries → return_account
        cycle_accounts = [originator] + intermediaries + [return_account]

        initial_amount = round(float(random.uniform(100_000, 3_000_000)), 2)  # type: ignore
        pattern_id = f"ROUND-{_random_hex(8)}"

        days_back = random.randint(5, 90)
        cycle_start = end_date - timedelta(days=days_back)
        cycle_start = cycle_start.replace(
            hour=random.randint(8, 20),
            minute=random.randint(0, 59),
        )

        current_amount = initial_amount
        current_time = cycle_start
        chain_txn_ids = []

        for hop in range(len(cycle_accounts) - 1):
            sender = cycle_accounts[hop]
            receiver = cycle_accounts[hop + 1]

            # Small leakage per hop
            leakage = random.uniform(0.005, 0.025)
            current_amount = round(float(current_amount * (1 - leakage)), 2)  # type: ignore

            # Delay between hops: 2 hours to 5 days
            delay_hours = random.uniform(2, 120)
            current_time = current_time + timedelta(hours=delay_hours)

            channel = random.choice(["MOBILE", "INTERNET", "BRANCH", "API"])
            source = random.choice(["UPI", "IMPS", "NEFT"])

            txn_id = f"TXN-{_random_hex(16)}"
            chain_txn_ids.append(txn_id)

            txn = Transaction(
                txn_id=txn_id,
                source_system=source,
                original_ref=f"{source}-{_random_hex(10)}",
                timestamp_initiated=current_time.strftime("%Y-%m-%dT%H:%M:%S"),
                timestamp_settled=(
                    (current_time + timedelta(minutes=random.randint(5, 120)))
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
                suspicious_pattern="ROUND_TRIPPING",
                pattern_group_id=pattern_id,
            )
            transactions.append(txn)

        ground_truth.append({
            "pattern_id": pattern_id,
            "pattern_type": "ROUND_TRIPPING",
            "cycle_length": len(cycle_accounts),
            "initial_amount": initial_amount,
            "return_amount": current_amount,
            "amount_preservation_ratio": round(float(current_amount / initial_amount), 4),  # type: ignore
            "elapsed_days": round(float((current_time - cycle_start).total_seconds() / 86400), 2),  # type: ignore
            "originator_account": originator.account_id,
            "return_account": return_account.account_id,
            "same_account_return": originator.account_id == return_account.account_id,
            "account_cycle": [a.account_id for a in cycle_accounts],
            "transaction_ids": chain_txn_ids,
        })

    return transactions, ground_truth
