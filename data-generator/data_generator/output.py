"""
Output writer — serializes generated data to JSON files in the canonical schema.
"""

import json
import os
from datetime import datetime
from typing import List
from dataclasses import asdict

from data_generator.accounts import Account
from data_generator.transactions import Transaction


def write_accounts(accounts: List[Account], output_dir: str) -> str:
    """Write accounts to a JSON file."""
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "accounts.json")
    data = [asdict(a) for a in accounts]
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    return filepath


def write_transactions(transactions: List[Transaction], output_dir: str) -> str:
    """Write transactions to a JSON file (canonical schema)."""
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "transactions.json")
    data = [asdict(t) for t in transactions]
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    return filepath


def write_ground_truth(ground_truth: List[dict], output_dir: str) -> str:
    """Write ground truth labels to a JSON file."""
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "ground_truth.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(ground_truth, f, indent=2, default=str)
    return filepath


def write_summary(
    accounts: List[Account],
    transactions: List[Transaction],
    ground_truth: List[dict],
    output_dir: str,
) -> str:
    """Write a human-readable summary of the generated dataset."""
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "summary.txt")

    suspicious_txns = [t for t in transactions if t.is_suspicious]
    pattern_counts = {}
    for gt in ground_truth:
        pt = gt["pattern_type"]
        pattern_counts[pt] = pattern_counts.get(pt, 0) + 1

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("FUND FLOW SYNTHETIC DATA — GENERATION SUMMARY\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write("=" * 60 + "\n\n")

        f.write(f"Total accounts:       {len(accounts):>10,}\n")
        f.write(f"Total transactions:   {len(transactions):>10,}\n")
        f.write(f"Normal transactions:  {len(transactions) - len(suspicious_txns):>10,}\n")
        f.write(f"Suspicious txns:      {len(suspicious_txns):>10,}\n")
        f.write(f"Suspicious ratio:     {len(suspicious_txns)/max(len(transactions),1)*100:>9.3f}%\n\n")

        f.write("PATTERN BREAKDOWN:\n")
        f.write("-" * 40 + "\n")
        for pattern_type, count in sorted(pattern_counts.items()):
            f.write(f"  {pattern_type:<25} {count:>5} patterns\n")

        f.write("\nACCOUNT STATUS DISTRIBUTION:\n")
        f.write("-" * 40 + "\n")
        status_counts = {}
        for a in accounts:
            status_counts[a.status] = status_counts.get(a.status, 0) + 1
        for status, count in sorted(status_counts.items()):
            f.write(f"  {status:<25} {count:>5}\n")

        f.write("\nACCOUNT TYPE DISTRIBUTION:\n")
        f.write("-" * 40 + "\n")
        type_counts = {}
        for a in accounts:
            type_counts[a.account_type] = type_counts.get(a.account_type, 0) + 1
        for acct_type, count in sorted(type_counts.items()):
            f.write(f"  {acct_type:<25} {count:>5}\n")

    return filepath
