"""
Structuring (smurfing) pattern injector.

Generates split cash deposits designed to stay just below the ₹10L
(₹10,00,000) cash transaction reporting threshold.
"""

import random
from datetime import datetime, timedelta
from typing import List, Tuple

from data_generator.accounts import Account, BRANCHES
from data_generator.transactions import Transaction

# Indian CTR reporting threshold for cash transactions
REPORTING_THRESHOLD = 1_000_000  # ₹10 Lakh


def _random_hex(length: int) -> str:
    return ''.join(random.choices('0123456789ABCDEF', k=length))


def _split_below_threshold(total: float, n_splits: int) -> List[float]:
    """
    Split a total amount into n_splits pieces, each below REPORTING_THRESHOLD.

    If n_splits is too few to keep every piece below the threshold,
    extra splits are added automatically.
    """
    max_per_split = REPORTING_THRESHOLD * 0.95  # leave a small margin
    min_per_split = REPORTING_THRESHOLD * 0.50

    splits = []
    remaining = total

    for i in range(n_splits - 1):
        if remaining <= 0:
            break
        upper = min(max_per_split, remaining - min_per_split * 0.5)
        lower = min(min_per_split, upper * 0.8)
        if lower > upper:
            lower = upper * 0.5
        amount = round(float(random.uniform(lower, upper)), 2)  # type: ignore
        splits.append(amount)
        remaining -= amount

    # Handle the remainder: keep splitting if it exceeds threshold
    while remaining >= REPORTING_THRESHOLD:
        amount = round(float(random.uniform(min_per_split, max_per_split)), 2)  # type: ignore
        amount = min(amount, remaining - 1000)  # ensure remainder stays positive
        splits.append(amount)
        remaining -= amount

    if remaining > 0:
        splits.append(round(float(remaining), 2))  # type: ignore

    return splits


def inject_structuring_patterns(
    accounts: List[Account],
    count: int = 120,
    end_date: datetime | None = None,
    seed: int = 3001,
) -> Tuple[List[Transaction], List[dict]]:
    """
    Inject structuring (smurfing) patterns.

    Each pattern represents a deliberate splitting of a large cash
    deposit into smaller ones to avoid the ₹10L reporting threshold.

    Variants:
    1. Same-day, same-branch: 3-6 deposits at one branch within hours
    2. Same-day, multi-branch: deposits spread across branches
    3. Multi-day drip: deposits spread over 2-5 days

    Args:
        accounts: Full account list.
        count: Number of structuring patterns.
        end_date: Latest timestamp.
        seed: Random seed.

    Returns:
        Tuple of (transactions, ground_truth_records).
    """
    random.seed(seed)

    if end_date is None:
        end_date = datetime.now()

    active = [a for a in accounts if a.status == "ACTIVE"]
    if not active:
        return [], []

    transactions: List[Transaction] = []
    ground_truth: List[dict] = []

    # Variant distribution
    variants = ["SAME_DAY_SAME_BRANCH", "SAME_DAY_MULTI_BRANCH", "MULTI_DAY_DRIP"]
    variant_weights = [0.3, 0.4, 0.3]

    for pattern_idx in range(count):
        account = random.choice(active)
        variant = random.choices(variants, weights=variant_weights)[0]
        pattern_id = f"STRUCT-{_random_hex(8)}"

        # Total intended amount: ₹10L - ₹50L
        total_intended = round(float(random.uniform(1_000_000, 5_000_000)), 2)  # type: ignore

        # Number of splits
        if variant == "SAME_DAY_SAME_BRANCH":
            n_splits = random.randint(3, 6)
        elif variant == "SAME_DAY_MULTI_BRANCH":
            n_splits = random.randint(3, 5)
        else:  # MULTI_DAY_DRIP
            n_splits = random.randint(4, 8)

        # Generate split amounts — all guaranteed below threshold
        split_amounts = _split_below_threshold(total_intended, n_splits)

        # Base time
        days_back = random.randint(1, 90)
        base_time = end_date - timedelta(days=days_back)
        base_time = base_time.replace(
            hour=random.randint(9, 16),
            minute=random.randint(0, 59),
        )

        chain_txn_ids = []
        branches_used = set()

        for split_idx, amount in enumerate(split_amounts):
            if variant == "SAME_DAY_SAME_BRANCH":
                # All within same day, same branch, 15-90 min apart
                offset = timedelta(minutes=random.randint(15, 90) * split_idx)
                txn_time = base_time + offset
                branch = account.branch_code

            elif variant == "SAME_DAY_MULTI_BRANCH":
                # Same day, different branches, 30-120 min apart
                offset = timedelta(minutes=random.randint(30, 120) * split_idx)
                txn_time = base_time + offset
                branch = random.choice(BRANCHES)

            else:  # MULTI_DAY_DRIP
                # Spread over 2-5 days
                day_offset = random.randint(0, 4)
                txn_time = base_time + timedelta(
                    days=day_offset,
                    hours=random.randint(9, 17),
                    minutes=random.randint(0, 59),
                )
                branch = random.choice(
                    [account.branch_code, random.choice(BRANCHES)]
                )

            branches_used.add(branch)

            txn_id = f"TXN-{_random_hex(16)}"
            chain_txn_ids.append(txn_id)

            txn = Transaction(
                txn_id=txn_id,
                source_system="CASH",
                original_ref=f"CASH-{_random_hex(10)}",
                timestamp_initiated=txn_time.strftime("%Y-%m-%dT%H:%M:%S"),
                timestamp_settled=txn_time.strftime("%Y-%m-%dT%H:%M:%S"),
                amount_value=amount,
                amount_currency="INR",
                sender_account_id=account.account_id,
                sender_entity_id=account.entity_id,
                sender_account_type=account.account_type,
                sender_branch_code=branch,
                sender_bank_code="INTERNAL",
                receiver_account_id=account.account_id,
                receiver_entity_id=account.entity_id,
                receiver_account_type=account.account_type,
                receiver_branch_code=branch,
                receiver_bank_code="INTERNAL",
                channel="BRANCH",
                product_code="RETAIL_TXN",
                purpose_code="CASH_DEPOSIT",
                is_suspicious=True,
                suspicious_pattern="STRUCTURING",
                pattern_group_id=pattern_id,
            )
            transactions.append(txn)

        ground_truth.append({
            "pattern_id": pattern_id,
            "pattern_type": "STRUCTURING",
            "variant": variant,
            "account_id": account.account_id,
            "total_amount": round(float(sum(split_amounts)), 2),  # type: ignore
            "num_splits": len(split_amounts),
            "individual_amounts": split_amounts,
            "max_single_deposit": max(split_amounts),
            "all_below_threshold": all(a < REPORTING_THRESHOLD for a in split_amounts),
            "branches_used": list(branches_used),
            "multi_branch": len(branches_used) > 1,
            "transaction_ids": chain_txn_ids,
        })

    return transactions, ground_truth
