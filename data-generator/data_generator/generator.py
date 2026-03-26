"""
Main orchestrator — ties together account generation, normal transactions,
and all suspicious pattern injectors into a single dataset.

Usage:
    python -m data_generator.generator --accounts 10000 --days 90 --output ./output
"""

import argparse
import random
import time
from datetime import datetime

from data_generator.accounts import generate_accounts
from data_generator.transactions import generate_normal_transactions
from data_generator.patterns.layering import inject_layering_patterns
from data_generator.patterns.round_tripping import inject_round_tripping_patterns
from data_generator.patterns.structuring import inject_structuring_patterns
from data_generator.patterns.dormant_activation import inject_dormant_activation_patterns
from data_generator.patterns.profile_mismatch import inject_profile_mismatch_patterns
from data_generator.output import (
    write_accounts,
    write_transactions,
    write_ground_truth,
    write_summary,
)


def generate(
    num_accounts: int = 10_000,
    days: int = 90,
    seed: int = 42,
    output_dir: str = "./output",
    layering_count: int = 100,
    round_trip_count: int = 80,
    structuring_count: int = 120,
    dormant_count: int = 80,
    mismatch_count: int = 120,
) -> dict:
    """
    Generate a complete synthetic dataset.

    Returns:
        Summary dict with counts and file paths.
    """
    end_date = datetime.now()

    print(f"[1/7] Generating {num_accounts:,} accounts...")
    t0 = time.time()
    accounts = generate_accounts(count=num_accounts, seed=seed)
    print(f"       Done in {time.time() - t0:.1f}s")

    print(f"[2/7] Generating normal transactions ({days} days)...")
    t0 = time.time()
    normal_txns = generate_normal_transactions(
        accounts, days=days, end_date=end_date, seed=seed
    )
    print(f"       Generated {len(normal_txns):,} normal transactions in {time.time() - t0:.1f}s")

    all_ground_truth = []

    print(f"[3/7] Injecting {layering_count} layering patterns...")
    t0 = time.time()
    layering_txns, layering_gt = inject_layering_patterns(
        accounts, count=layering_count, end_date=end_date, seed=seed + 1000
    )
    all_ground_truth.extend(layering_gt)
    print(f"       Injected {len(layering_txns)} transactions in {time.time() - t0:.1f}s")

    print(f"[4/7] Injecting {round_trip_count} round-tripping patterns...")
    t0 = time.time()
    round_trip_txns, round_trip_gt = inject_round_tripping_patterns(
        accounts, count=round_trip_count, end_date=end_date, seed=seed + 2000
    )
    all_ground_truth.extend(round_trip_gt)
    print(f"       Injected {len(round_trip_txns)} transactions in {time.time() - t0:.1f}s")

    print(f"[5/7] Injecting {structuring_count} structuring patterns...")
    t0 = time.time()
    structuring_txns, structuring_gt = inject_structuring_patterns(
        accounts, count=structuring_count, end_date=end_date, seed=seed + 3000
    )
    all_ground_truth.extend(structuring_gt)
    print(f"       Injected {len(structuring_txns)} transactions in {time.time() - t0:.1f}s")

    print(f"[6/7] Injecting {dormant_count} dormant activation patterns...")
    t0 = time.time()
    dormant_txns, dormant_gt = inject_dormant_activation_patterns(
        accounts, count=dormant_count, end_date=end_date, seed=seed + 4000
    )
    all_ground_truth.extend(dormant_gt)
    print(f"       Injected {len(dormant_txns)} transactions in {time.time() - t0:.1f}s")

    print(f"[7/7] Injecting {mismatch_count} profile mismatch patterns...")
    t0 = time.time()
    mismatch_txns, mismatch_gt = inject_profile_mismatch_patterns(
        accounts, count=mismatch_count, end_date=end_date, seed=seed + 5000
    )
    all_ground_truth.extend(mismatch_gt)
    print(f"       Injected {len(mismatch_txns)} transactions in {time.time() - t0:.1f}s")

    # Merge all transactions and sort by timestamp
    all_txns = normal_txns + layering_txns + round_trip_txns + structuring_txns + dormant_txns + mismatch_txns
    all_txns.sort(key=lambda t: t.timestamp_initiated)

    print(f"\nTotal transactions: {len(all_txns):,}")
    suspicious = sum(1 for t in all_txns if t.is_suspicious)
    print(f"Suspicious:         {suspicious:,} ({suspicious/len(all_txns)*100:.3f}%)")
    print(f"Ground truth:       {len(all_ground_truth)} patterns")

    # Write output files
    print(f"\nWriting output to {output_dir}/...")
    acct_path = write_accounts(accounts, output_dir)
    txn_path = write_transactions(all_txns, output_dir)
    gt_path = write_ground_truth(all_ground_truth, output_dir)
    summary_path = write_summary(accounts, all_txns, all_ground_truth, output_dir)

    print(f"  Accounts:     {acct_path}")
    print(f"  Transactions: {txn_path}")
    print(f"  Ground truth: {gt_path}")
    print(f"  Summary:      {summary_path}")
    print("\nDone!")

    return {
        "num_accounts": len(accounts),
        "num_transactions": len(all_txns),
        "num_suspicious": suspicious,
        "num_patterns": len(all_ground_truth),
        "files": {
            "accounts": acct_path,
            "transactions": txn_path,
            "ground_truth": gt_path,
            "summary": summary_path,
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic banking transactions with embedded suspicious patterns"
    )
    parser.add_argument(
        "--accounts", type=int, default=10_000,
        help="Number of accounts to generate (default: 10,000)"
    )
    parser.add_argument(
        "--days", type=int, default=90,
        help="Days of transaction history (default: 90)"
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducibility"
    )
    parser.add_argument(
        "--output", type=str, default="./output",
        help="Output directory path"
    )
    parser.add_argument(
        "--layering", type=int, default=100,
        help="Number of layering patterns to inject"
    )
    parser.add_argument(
        "--round-trips", type=int, default=80,
        help="Number of round-tripping patterns"
    )
    parser.add_argument(
        "--structuring", type=int, default=120,
        help="Number of structuring patterns"
    )
    parser.add_argument(
        "--dormant", type=int, default=80,
        help="Number of dormant activation patterns"
    )
    parser.add_argument(
        "--mismatch", type=int, default=120,
        help="Number of profile mismatch patterns"
    )

    args = parser.parse_args()

    generate(
        num_accounts=args.accounts,
        days=args.days,
        seed=args.seed,
        output_dir=args.output,
        layering_count=args.layering,
        round_trip_count=args.round_trips,
        structuring_count=args.structuring,
        dormant_count=args.dormant,
        mismatch_count=args.mismatch,
    )


if __name__ == "__main__":
    main()
