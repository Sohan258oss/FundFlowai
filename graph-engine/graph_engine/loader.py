"""
Graph loader — reads canonical JSON and batch-loads into Neo4j.

Creates:
  - Entity nodes (from account.entity_id)
  - Account nodes (linked to entities via OWNS)
  - TRANSFERRED_TO edges (from transactions)
"""

import json
import time
import argparse
from typing import List

from neo4j import GraphDatabase
from tqdm import tqdm

from graph_engine.schema import setup_schema, clear_database


# ---------------------------------------------------------------------------
# Cypher templates for batch loading
# ---------------------------------------------------------------------------

MERGE_ENTITY = """
UNWIND $batch AS row
MERGE (e:Entity {entity_id: row.entity_id})
ON CREATE SET
    e.entity_name = row.entity_name,
    e.entity_type = row.entity_type,
    e.occupation = row.occupation,
    e.annual_income = row.annual_income,
    e.pep_flag = row.pep_flag,
    e.city = row.city
"""

MERGE_ACCOUNT = """
UNWIND $batch AS row
MERGE (a:Account {account_id: row.account_id})
ON CREATE SET
    a.account_type = row.account_type,
    a.branch_code = row.branch_code,
    a.open_date = row.open_date,
    a.status = row.status,
    a.avg_monthly_txn_count = row.avg_monthly_txn_count,
    a.avg_balance_30d = row.avg_balance_30d,
    a.kyc_status = row.kyc_status
WITH a, row
MATCH (e:Entity {entity_id: row.entity_id})
MERGE (e)-[:OWNS]->(a)
"""

MERGE_TRANSACTION = """
UNWIND $batch AS row
MATCH (sender:Account {account_id: row.sender_account_id})
MATCH (receiver:Account {account_id: row.receiver_account_id})
CREATE (sender)-[t:TRANSFERRED_TO {
    txn_id: row.txn_id,
    amount: row.amount_value,
    currency: row.amount_currency,
    timestamp: row.timestamp_initiated,
    settled: row.timestamp_settled,
    source_system: row.source_system,
    channel: row.channel,
    purpose_code: row.purpose_code,
    is_suspicious: row.is_suspicious,
    suspicious_pattern: row.suspicious_pattern,
    pattern_group_id: row.pattern_group_id
}]->(receiver)
"""


def _batch_iter(items: list, batch_size: int):
    """Yield successive batches from a list."""
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


def load_accounts(
    driver: GraphDatabase.driver,
    accounts: List[dict],
    batch_size: int = 500,
) -> None:
    """Load accounts and entities into Neo4j."""
    # Deduplicate entities
    seen_entities = set()
    entity_batch = []
    for acct in accounts:
        if acct["entity_id"] not in seen_entities:
            seen_entities.add(acct["entity_id"])
            entity_batch.append({
                "entity_id": acct["entity_id"],
                "entity_name": acct["entity_name"],
                "entity_type": acct["entity_type"],
                "occupation": acct["occupation"],
                "annual_income": acct["annual_income"],
                "pep_flag": acct.get("pep_flag", False),
                "city": acct.get("city", ""),
            })

    print(f"Loading {len(entity_batch):,} entities...")
    with driver.session() as session:
        for batch in tqdm(
            list(_batch_iter(entity_batch, batch_size)),
            desc="  Entities",
        ):
            session.run(MERGE_ENTITY, batch=batch)

    print(f"Loading {len(accounts):,} accounts...")
    with driver.session() as session:
        for batch in tqdm(
            list(_batch_iter(accounts, batch_size)),
            desc="  Accounts",
        ):
            session.run(MERGE_ACCOUNT, batch=batch)


def load_transactions(
    driver: GraphDatabase.driver,
    transactions: List[dict],
    batch_size: int = 500,
) -> None:
    """Load transactions as TRANSFERRED_TO edges into Neo4j."""
    print(f"Loading {len(transactions):,} transactions...")
    with driver.session() as session:
        for batch in tqdm(
            list(_batch_iter(transactions, batch_size)),
            desc="  Transactions",
        ):
            session.run(MERGE_TRANSACTION, batch=batch)


def load_from_files(
    uri: str = "bolt://localhost:7687",
    user: str = "neo4j",
    password: str = "fundflow_pass",
    accounts_file: str = "./output/accounts.json",
    transactions_file: str = "./output/transactions.json",
    batch_size: int = 500,
    clear: bool = False,
) -> dict:
    """
    Load a full dataset from JSON files into Neo4j.

    Returns:
        Dict with load statistics.
    """
    driver = GraphDatabase.driver(uri, auth=(user, password))

    try:
        # Verify connectivity
        driver.verify_connectivity()
        print(f"Connected to Neo4j at {uri}")

        if clear:
            clear_database(driver)

        setup_schema(driver)

        # Load accounts
        print(f"\nReading {accounts_file}...")
        with open(accounts_file, "r", encoding="utf-8") as f:
            accounts = json.load(f)
        print(f"  Read {len(accounts):,} accounts")

        t0 = time.time()
        load_accounts(driver, accounts, batch_size=batch_size)
        acct_time = time.time() - t0

        # Load transactions
        print(f"\nReading {transactions_file}...")
        with open(transactions_file, "r", encoding="utf-8") as f:
            transactions = json.load(f)
        print(f"  Read {len(transactions):,} transactions")

        t0 = time.time()
        load_transactions(driver, transactions, batch_size=batch_size)
        txn_time = time.time() - t0

        # Print stats
        with driver.session() as session:
            node_count = session.run(
                "MATCH (n) RETURN count(n) AS c"
            ).single()["c"]
            edge_count = session.run(
                "MATCH ()-[r]->() RETURN count(r) AS c"
            ).single()["c"]

        print(f"\n{'='*50}")
        print(f"LOAD COMPLETE")
        print(f"  Nodes:         {node_count:>10,}")
        print(f"  Edges:         {edge_count:>10,}")
        print(f"  Account load:  {acct_time:>10.1f}s")
        print(f"  Txn load:      {txn_time:>10.1f}s")
        print(f"{'='*50}")

        return {
            "nodes": node_count,
            "edges": edge_count,
            "account_load_seconds": acct_time,
            "txn_load_seconds": txn_time,
        }

    finally:
        driver.close()


def main():
    parser = argparse.ArgumentParser(description="Load synthetic data into Neo4j")
    parser.add_argument("--uri", default="bolt://localhost:7687")
    parser.add_argument("--user", default="neo4j")
    parser.add_argument("--password", default="fundflow_pass")
    parser.add_argument("--accounts", default="./output/accounts.json")
    parser.add_argument("--transactions", default="./output/transactions.json")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--clear", action="store_true", help="Clear DB before loading")
    args = parser.parse_args()

    load_from_files(
        uri=args.uri,
        user=args.user,
        password=args.password,
        accounts_file=args.accounts,
        transactions_file=args.transactions,
        batch_size=args.batch_size,
        clear=args.clear,
    )


if __name__ == "__main__":
    main()
