"""
Synthetic account generator.

Creates realistic bank account profiles with demographics, product types,
branch assignments, and behavioral baselines.
"""

import random
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import List

from faker import Faker

fake = Faker("en_IN")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACCOUNT_TYPES = ["SAVINGS", "CURRENT", "SALARY", "LOAN", "WALLET", "FD"]
ACCOUNT_TYPE_WEIGHTS = [0.40, 0.20, 0.20, 0.10, 0.07, 0.03]

CHANNELS = ["MOBILE", "INTERNET", "BRANCH", "ATM", "API"]

OCCUPATION_CATEGORIES = [
    "SALARIED_PRIVATE",
    "SALARIED_GOVT",
    "SELF_EMPLOYED_PROFESSIONAL",
    "SELF_EMPLOYED_BUSINESS",
    "RETIRED",
    "STUDENT",
    "HOMEMAKER",
    "AGRICULTURE",
]

# Annual income bands by occupation (INR)
INCOME_BANDS = {
    "SALARIED_PRIVATE": (300_000, 5_000_000),
    "SALARIED_GOVT": (400_000, 3_000_000),
    "SELF_EMPLOYED_PROFESSIONAL": (500_000, 10_000_000),
    "SELF_EMPLOYED_BUSINESS": (200_000, 50_000_000),
    "RETIRED": (200_000, 2_000_000),
    "STUDENT": (0, 200_000),
    "HOMEMAKER": (0, 500_000),
    "AGRICULTURE": (100_000, 3_000_000),
}

# Typical monthly transaction count ranges by occupation
TXN_COUNT_BANDS = {
    "SALARIED_PRIVATE": (10, 60),
    "SALARIED_GOVT": (5, 30),
    "SELF_EMPLOYED_PROFESSIONAL": (20, 100),
    "SELF_EMPLOYED_BUSINESS": (30, 200),
    "RETIRED": (3, 15),
    "STUDENT": (5, 40),
    "HOMEMAKER": (3, 20),
    "AGRICULTURE": (2, 15),
}

# Sample IFSC-like branch codes
BRANCHES = [f"FUND0{str(i).zfill(4)}" for i in range(1, 201)]


@dataclass
class Account:
    """A synthetic bank account with realistic profile attributes."""

    account_id: str
    entity_id: str
    entity_name: str
    entity_type: str  # INDIVIDUAL or CORPORATE
    account_type: str
    branch_code: str
    open_date: str  # ISO-8601
    status: str  # ACTIVE, DORMANT, CLOSED
    occupation: str
    annual_income: float
    avg_monthly_txn_count: int
    avg_balance_30d: float
    preferred_channels: List[str] = field(default_factory=list)
    pep_flag: bool = False
    kyc_status: str = "VERIFIED"
    phone_hash: str = ""
    city: str = ""


def _random_hex(length: int = 12) -> str:
    """Generate a random hex string using Python's seeded random (reproducible)."""
    return ''.join(random.choices('0123456789ABCDEF', k=length))


def generate_accounts(
    count: int = 100_000,
    start_date: datetime | None = None,
    seed: int = 42,
) -> List[Account]:
    """
    Generate synthetic bank accounts.

    Args:
        count: Number of accounts to generate.
        start_date: Earliest possible account opening date.
                    Defaults to 5 years before today.
        seed: Random seed for reproducibility.

    Returns:
        List of Account dataclass instances.
    """
    random.seed(seed)
    Faker.seed(seed)

    if start_date is None:
        start_date = datetime.now() - timedelta(days=5 * 365)

    end_date = datetime.now() - timedelta(days=30)
    date_range_days = (end_date - start_date).days

    accounts: List[Account] = []

    # Pre-generate entity IDs — some entities own multiple accounts
    # ~80% of entities have 1 account, ~15% have 2, ~5% have 3+
    entity_pool: List[dict] = []
    entities_needed = int(count * 0.85)  # rough estimate
    for _ in range(entities_needed):
        is_corporate = random.random() < 0.15
        entity_pool.append({
            "entity_id": f"ENT-{_random_hex(12)}",
            "entity_name": fake.company() if is_corporate else fake.name(),
            "entity_type": "CORPORATE" if is_corporate else "INDIVIDUAL",
            "occupation": (
                "SELF_EMPLOYED_BUSINESS"
                if is_corporate
                else random.choice(OCCUPATION_CATEGORIES)
            ),
            "city": fake.city(),
            "phone_hash": _random_hex(16),
        })

    # Assign entities to accounts — some entities get multiple accounts
    entity_assignments = []
    idx = 0
    while len(entity_assignments) < count:
        entity = entity_pool[idx % len(entity_pool)]
        # Decide how many accounts this entity gets
        if idx < len(entity_pool):
            n_accounts = random.choices([1, 2, 3], weights=[0.80, 0.15, 0.05])[0]
        else:
            n_accounts = 1
        for _ in range(min(n_accounts, count - len(entity_assignments))):
            entity_assignments.append(entity)
        idx += 1

    random.shuffle(entity_assignments)

    for i in range(count):
        entity = entity_assignments[i]
        occupation = entity["occupation"]
        income_low, income_high = INCOME_BANDS[occupation]
        annual_income = round(random.uniform(income_low, income_high), -3)  # type: ignore

        txn_low, txn_high = TXN_COUNT_BANDS[occupation]
        avg_txn_count = random.randint(txn_low, txn_high)

        acct_type = random.choices(ACCOUNT_TYPES, weights=ACCOUNT_TYPE_WEIGHTS)[0]
        open_offset = random.randint(0, date_range_days)
        open_date = start_date + timedelta(days=open_offset)

        # Dormancy: ~5% of accounts are dormant (no txns for 6+ months)
        status = "ACTIVE"
        if random.random() < 0.05:
            status = "DORMANT"
        elif random.random() < 0.01:
            status = "CLOSED"

        avg_balance = round(float(annual_income * random.uniform(0.05, 0.4)), 2)  # type: ignore

        # Preferred channels: salaried prefer mobile/internet,
        # retired prefer branch
        if occupation in ("RETIRED", "AGRICULTURE"):
            channels = random.sample(["BRANCH", "ATM", "MOBILE"], k=2)
        elif occupation == "STUDENT":
            channels = random.sample(["MOBILE", "INTERNET", "ATM"], k=2)
        else:
            channels = random.sample(CHANNELS, k=random.randint(2, 4))

        # PEP flag: ~0.5% of individuals
        pep = (
            entity["entity_type"] == "INDIVIDUAL" and random.random() < 0.005
        )

        # KYC: most verified, ~3% expired for dormant accounts
        kyc = "EXPIRED" if (status == "DORMANT" and random.random() < 0.6) else "VERIFIED"

        account = Account(
            account_id=f"ACC-{_random_hex(12)}",
            entity_id=entity["entity_id"],
            entity_name=entity["entity_name"],
            entity_type=entity["entity_type"],
            account_type=acct_type,
            branch_code=random.choice(BRANCHES),
            open_date=open_date.strftime("%Y-%m-%dT%H:%M:%S"),
            status=status,
            occupation=occupation,
            annual_income=annual_income,
            avg_monthly_txn_count=avg_txn_count,
            avg_balance_30d=avg_balance,
            preferred_channels=channels,
            pep_flag=pep,
            kyc_status=kyc,
            phone_hash=entity["phone_hash"],
            city=entity["city"],
        )
        accounts.append(account)

    return accounts


def accounts_to_dicts(accounts: List[Account]) -> List[dict]:
    """Convert account list to list of dicts for JSON serialization."""
    return [asdict(a) for a in accounts]  # type: ignore
