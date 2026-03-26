"""
Normal transaction generator.

Generates baseline (non-suspicious) transaction activity for each account
based on its profile — income, occupation, preferred channels, etc.
"""

import random
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from collections import defaultdict
from typing import List

from data_generator.accounts import Account


@dataclass
class Transaction:
    """A single canonical transaction in the normalized schema."""

    txn_id: str
    source_system: str
    original_ref: str
    timestamp_initiated: str  # ISO-8601
    timestamp_settled: str | None
    amount_value: float
    amount_currency: str
    sender_account_id: str
    sender_entity_id: str
    sender_account_type: str
    sender_branch_code: str
    sender_bank_code: str
    receiver_account_id: str
    receiver_entity_id: str
    receiver_account_type: str
    receiver_branch_code: str
    receiver_bank_code: str
    channel: str
    product_code: str
    purpose_code: str
    is_suspicious: bool = False
    suspicious_pattern: str | None = None
    pattern_group_id: str | None = None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SOURCE_SYSTEMS = ["UPI", "NEFT", "RTGS", "IMPS", "SWIFT", "CARD", "CASH", "WALLET"]
SOURCE_SYSTEM_WEIGHTS = [0.35, 0.15, 0.05, 0.15, 0.02, 0.15, 0.08, 0.05]

PURPOSE_CODES = [
    "P2P", "P2M", "SALARY", "BILL_PAYMENT", "LOAN_REPAYMENT",
    "INVESTMENT", "INSURANCE", "RENT", "GROCERY", "FUEL",
    "UTILITY", "SUBSCRIPTION", "TRANSFER", "CASH_DEPOSIT",
    "CASH_WITHDRAWAL", "TRADE_PAYMENT",
]
PURPOSE_WEIGHTS = [
    0.15, 0.15, 0.10, 0.08, 0.06,
    0.05, 0.03, 0.06, 0.06, 0.04,
    0.05, 0.03, 0.06, 0.03,
    0.03, 0.02,
]

PRODUCT_CODES = ["RETAIL_TXN", "CORP_TXN", "CARD_TXN", "LOAN_TXN", "FX_TXN"]

# Amount ranges by purpose (INR)
AMOUNT_RANGES = {
    "SALARY": (15_000, 500_000),
    "RENT": (5_000, 100_000),
    "GROCERY": (200, 8_000),
    "FUEL": (500, 5_000),
    "UTILITY": (200, 15_000),
    "BILL_PAYMENT": (100, 50_000),
    "SUBSCRIPTION": (99, 2_000),
    "P2P": (100, 200_000),
    "P2M": (50, 100_000),
    "LOAN_REPAYMENT": (5_000, 300_000),
    "INVESTMENT": (1_000, 1_000_000),
    "INSURANCE": (1_000, 100_000),
    "TRANSFER": (1_000, 500_000),
    "CASH_DEPOSIT": (1_000, 500_000),
    "CASH_WITHDRAWAL": (500, 100_000),
    "TRADE_PAYMENT": (10_000, 5_000_000),
}


def _pick_channel(account: Account) -> str:
    """Pick a channel weighted toward the account's preferences."""
    if random.random() < 0.7 and account.preferred_channels:
        return random.choice(account.preferred_channels)
    return random.choice(["MOBILE", "INTERNET", "BRANCH", "ATM"])


def _pick_amount(purpose: str, account: Account) -> float:
    """Generate a transaction amount appropriate for the purpose and account."""
    low, high = AMOUNT_RANGES.get(purpose, (100, 50_000))
    # Scale by income — higher income accounts transact larger amounts
    income_factor = min(account.annual_income / 1_000_000, 5.0)
    scaled_high = min(high * max(income_factor, 0.3), high * 3)
    amount = random.uniform(low, scaled_high)
    return round(amount, 2)  # type: ignore


def _settlement_delay(source: str, timestamp: datetime) -> datetime | None:
    """Add realistic settlement delay based on payment rail."""
    delays = {
        "UPI": timedelta(seconds=random.randint(1, 30)),
        "IMPS": timedelta(seconds=random.randint(5, 60)),
        "NEFT": timedelta(hours=random.choice([1, 2, 4])),
        "RTGS": timedelta(minutes=random.randint(5, 30)),
        "SWIFT": timedelta(hours=random.randint(4, 72)),
        "CARD": timedelta(days=random.choice([1, 2, 3])),
        "CASH": timedelta(seconds=0),
        "WALLET": timedelta(seconds=random.randint(1, 10)),
    }
    delay = delays.get(source, timedelta(hours=1))
    return timestamp + delay


def generate_normal_transactions(
    accounts: List[Account],
    days: int = 90,
    end_date: datetime | None = None,
    seed: int = 42,
) -> List[Transaction]:
    """
    Generate normal (non-suspicious) transactions between accounts.

    Each account generates transactions proportional to its avg_monthly_txn_count.
    Transactions are created between random pairs of active accounts.

    Args:
        accounts: List of Account objects.
        days: Number of days of transaction history to generate.
        end_date: Last day of the transaction window. Defaults to today.
        seed: Random seed.

    Returns:
        List of Transaction objects sorted by timestamp.
    """
    random.seed(seed)

    if end_date is None:
        end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    # Build lookup of active accounts for receiver selection
    active_accounts = [a for a in accounts if a.status == "ACTIVE"]
    if len(active_accounts) < 2:
        return []

    # Group accounts by entity_id
    entity_to_accounts: dict[str, List[Account]] = defaultdict(list)
    for a in active_accounts:
        entity_to_accounts[a.entity_id].append(a)

    def _random_hex(length: int) -> str:
        return ''.join(random.choices('0123456789ABCDEF', k=length))

    transactions: List[Transaction] = []

    for account in active_accounts:
        # Calculate total txns for this account over the period
        daily_rate = account.avg_monthly_txn_count / 30.0
        total_txns = int(daily_rate * days * random.uniform(0.7, 1.3))

        for _ in range(total_txns):
            # Random timestamp within the window
            offset_seconds = random.randint(0, days * 86400)
            txn_time = start_date + timedelta(seconds=offset_seconds)

            # Business hours bias: 70% of txns between 8am-8pm
            if random.random() < 0.7:
                hour = random.randint(8, 20)
                txn_time = txn_time.replace(
                    hour=hour,
                    minute=random.randint(0, 59),
                    second=random.randint(0, 59),
                )

            purpose = random.choices(PURPOSE_CODES, weights=PURPOSE_WEIGHTS)[0]
            source_system = random.choices(
                SOURCE_SYSTEMS, weights=SOURCE_SYSTEM_WEIGHTS
            )[0]

            # For cash deposits/withdrawals, sender == receiver
            if purpose in ("CASH_DEPOSIT", "CASH_WITHDRAWAL"):
                receiver = account
            else:
                # Pick a random receiver (not same entity)
                receiver = random.choice(active_accounts)
                attempts = 0
                while receiver.entity_id == account.entity_id and attempts < 5:
                    receiver = random.choice(active_accounts)
                    attempts += 1

            amount = _pick_amount(purpose, account)
            settled = _settlement_delay(source_system, txn_time)
            channel = _pick_channel(account)

            # RTGS only for amounts >= 2L
            if source_system == "RTGS" and amount < 200_000:
                amount = round(float(random.uniform(500, 50_000)), 2)  # type: ignore

            # SWIFT typically for larger international amounts
            if source_system == "SWIFT":
                amount = round(random.uniform(50_000, 10_000_000), 2)  # type: ignore

            txn = Transaction(
                txn_id=f"TXN-{_random_hex(16)}",
                source_system=source_system,
                original_ref=f"{source_system}-{_random_hex(10)}",
                timestamp_initiated=txn_time.strftime("%Y-%m-%dT%H:%M:%S"),
                timestamp_settled=(
                    settled.strftime("%Y-%m-%dT%H:%M:%S") if settled else None
                ),
                amount_value=amount,
                amount_currency="INR",
                sender_account_id=account.account_id,
                sender_entity_id=account.entity_id,
                sender_account_type=account.account_type,
                sender_branch_code=account.branch_code,
                sender_bank_code="INTERNAL",
                receiver_account_id=receiver.account_id,
                receiver_entity_id=receiver.entity_id,
                receiver_account_type=receiver.account_type,
                receiver_branch_code=receiver.branch_code,
                receiver_bank_code="INTERNAL",
                channel=channel,
                product_code=(
                    "CORP_TXN" if account.entity_type == "CORPORATE" else "RETAIL_TXN"
                ),
                purpose_code=purpose,
            )
            transactions.append(txn)

    # Sort by timestamp
    transactions.sort(key=lambda t: t.timestamp_initiated)
    return transactions


def transactions_to_dicts(transactions: List[Transaction]) -> List[dict]:
    """Convert transaction list to list of dicts for JSON serialization."""
    return [asdict(t) for t in transactions]  # type: ignore
