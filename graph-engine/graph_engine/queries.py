"""
Cypher query library — reusable graph queries for fund flow analysis.

Each function returns results directly from Neo4j. Designed to be used
both programmatically and as a reference for investigators.
"""

from neo4j import GraphDatabase
from typing import List, Optional


def get_driver(
    uri: str = "bolt://localhost:7687",
    user: str = "neo4j",
    password: str = "fundflow_pass",
) -> GraphDatabase.driver:
    """Create a Neo4j driver instance."""
    return GraphDatabase.driver(uri, auth=(user, password))


# ─────────────────────────────────────────────────────────────────────────────
# Fund Flow Tracing
# ─────────────────────────────────────────────────────────────────────────────

def find_multi_hop_paths(
    driver,
    source_account_id: str,
    min_hops: int = 2,
    max_hops: int = 5,
    min_amount: float = 0,
    time_window_days: int = 7,
    limit: int = 25,
) -> list:
    """
    Find all multi-hop fund flow paths originating from a given account.

    Args:
        source_account_id: Starting account ID.
        min_hops: Minimum path length.
        max_hops: Maximum path length.
        min_amount: Minimum amount per hop (INR).
        time_window_days: Max time span for the entire path.
        limit: Max results.

    Returns:
        List of path dictionaries.
    """
    query = """
    MATCH path = (source:Account {account_id: $source_id})
                  -[:TRANSFERRED_TO*""" + str(min_hops) + """..""" + str(max_hops) + """]->(dest:Account)
    WHERE ALL(r IN relationships(path) WHERE r.amount >= $min_amount)
    WITH path,
         [r IN relationships(path) | r.timestamp] AS timestamps,
         [r IN relationships(path) | r.amount] AS amounts,
         [n IN nodes(path) | n.account_id] AS account_chain
    WHERE duration.between(date(timestamps[0]), date(timestamps[-1])).days <= $time_window
    RETURN account_chain,
           amounts,
           timestamps,
           length(path) AS hops,
           reduce(s = 0.0, a IN amounts | s + a) AS total_flow
    ORDER BY total_flow DESC
    LIMIT $limit
    """
    with driver.session() as session:
        result = session.run(
            query,
            source_id=source_account_id,
            min_amount=min_amount,
            time_window=time_window_days,
            limit=limit,
        )
        return [dict(record) for record in result]


def find_shortest_path(
    driver,
    source_account_id: str,
    target_account_id: str,
    max_hops: int = 8,
) -> list:
    """
    Find the shortest path(s) between two accounts.

    Returns:
        List of path dictionaries.
    """
    query = """
    MATCH path = shortestPath(
        (source:Account {account_id: $source_id})
        -[:TRANSFERRED_TO*1..""" + str(max_hops) + """]-
        (target:Account {account_id: $target_id})
    )
    RETURN [n IN nodes(path) | n.account_id] AS account_chain,
           [r IN relationships(path) | r.amount] AS amounts,
           [r IN relationships(path) | r.timestamp] AS timestamps,
           length(path) AS hops
    """
    with driver.session() as session:
        result = session.run(
            query,
            source_id=source_account_id,
            target_id=target_account_id,
        )
        return [dict(record) for record in result]


# ─────────────────────────────────────────────────────────────────────────────
# Pattern Detection Queries
# ─────────────────────────────────────────────────────────────────────────────

def detect_cycles(
    driver,
    min_length: int = 3,
    max_length: int = 6,
    min_amount: float = 50_000,
    limit: int = 50,
) -> list:
    """
    Find circular fund flows (potential round-tripping).

    Returns cycles where the same account appears at start and end.
    """
    query = """
    MATCH path = (start:Account)-[:TRANSFERRED_TO*""" + str(min_length) + """..""" + str(max_length) + """]->(start)
    WHERE ALL(r IN relationships(path) WHERE r.amount >= $min_amount)
    WITH path,
         [r IN relationships(path) | r.amount] AS amounts,
         [r IN relationships(path) | r.timestamp] AS timestamps,
         [n IN nodes(path) | n.account_id] AS cycle_accounts,
         start.account_id AS origin
    RETURN DISTINCT origin,
           cycle_accounts,
           amounts,
           timestamps,
           length(path) AS cycle_length,
           reduce(s = 0.0, a IN amounts | s + a) AS total_cycle_flow
    ORDER BY total_cycle_flow DESC
    LIMIT $limit
    """
    with driver.session() as session:
        result = session.run(query, min_amount=min_amount, limit=limit)
        return [dict(record) for record in result]


def find_rapid_pass_through(
    driver,
    max_hold_minutes: int = 120,
    min_amount: float = 100_000,
    limit: int = 50,
) -> list:
    """
    Find accounts that receive and forward funds within a short time window.

    These are potential mule/pass-through accounts.
    """
    query = """
    MATCH (a:Account)<-[inflow:TRANSFERRED_TO]-(sender:Account)
    MATCH (a)-[outflow:TRANSFERRED_TO]->(receiver:Account)
    WHERE inflow.amount >= $min_amount
      AND outflow.amount >= $min_amount
      AND outflow.amount <= inflow.amount
      AND outflow.amount >= inflow.amount * 0.85
      AND duration.between(
            datetime(inflow.timestamp),
            datetime(outflow.timestamp)
          ).minutes <= $max_hold
    RETURN a.account_id AS pass_through_account,
           sender.account_id AS from_account,
           receiver.account_id AS to_account,
           inflow.amount AS amount_in,
           outflow.amount AS amount_out,
           inflow.timestamp AS time_in,
           outflow.timestamp AS time_out,
           outflow.amount / inflow.amount AS preservation_ratio
    ORDER BY preservation_ratio DESC
    LIMIT $limit
    """
    with driver.session() as session:
        result = session.run(
            query,
            min_amount=min_amount,
            max_hold=max_hold_minutes,
            limit=limit,
        )
        return [dict(record) for record in result]


def find_high_fan_out(
    driver,
    min_recipients: int = 10,
    time_window_hours: int = 24,
    limit: int = 50,
) -> list:
    """
    Find accounts that sent to many distinct recipients within a short window.

    Potential indicator of fund distribution phase of layering.
    """
    query = """
    MATCH (sender:Account)-[t:TRANSFERRED_TO]->(receiver:Account)
    WITH sender,
         collect(DISTINCT receiver.account_id) AS recipients,
         collect(t.amount) AS amounts,
         min(t.timestamp) AS first_txn,
         max(t.timestamp) AS last_txn
    WHERE size(recipients) >= $min_recipients
    RETURN sender.account_id AS account_id,
           size(recipients) AS num_recipients,
           recipients,
           reduce(s = 0.0, a IN amounts | s + a) AS total_sent,
           first_txn,
           last_txn
    ORDER BY num_recipients DESC
    LIMIT $limit
    """
    with driver.session() as session:
        result = session.run(
            query,
            min_recipients=min_recipients,
            limit=limit,
        )
        return [dict(record) for record in result]


# ─────────────────────────────────────────────────────────────────────────────
# Account Intelligence
# ─────────────────────────────────────────────────────────────────────────────

def get_account_neighborhood(
    driver,
    account_id: str,
    depth: int = 2,
) -> dict:
    """
    Get the full neighborhood of an account up to N hops.

    Returns nodes and edges for visualization.
    """
    query = """
    MATCH path = (center:Account {account_id: $account_id})
                  -[:TRANSFERRED_TO*1..""" + str(depth) + """]-(neighbor)
    WITH collect(path) AS paths
    UNWIND paths AS p
    UNWIND relationships(p) AS rel
    WITH DISTINCT rel,
         startNode(rel) AS src,
         endNode(rel) AS dst
    RETURN src.account_id AS source,
           dst.account_id AS target,
           rel.amount AS amount,
           rel.timestamp AS timestamp,
           rel.channel AS channel,
           rel.purpose_code AS purpose,
           rel.is_suspicious AS is_suspicious
    """
    with driver.session() as session:
        result = session.run(query, account_id=account_id)
        edges = [dict(record) for record in result]

    # Extract unique nodes
    nodes = set()
    for e in edges:
        nodes.add(e["source"])
        nodes.add(e["target"])

    return {
        "center": account_id,
        "depth": depth,
        "nodes": list(nodes),
        "edges": edges,
    }


def get_graph_stats(driver) -> dict:
    """Get basic graph statistics."""
    with driver.session() as session:
        stats = {}
        stats["total_nodes"] = session.run(
            "MATCH (n) RETURN count(n) AS c"
        ).single()["c"]
        stats["total_accounts"] = session.run(
            "MATCH (n:Account) RETURN count(n) AS c"
        ).single()["c"]
        stats["total_entities"] = session.run(
            "MATCH (n:Entity) RETURN count(n) AS c"
        ).single()["c"]
        stats["total_edges"] = session.run(
            "MATCH ()-[r]->() RETURN count(r) AS c"
        ).single()["c"]
        stats["total_transfers"] = session.run(
            "MATCH ()-[r:TRANSFERRED_TO]->() RETURN count(r) AS c"
        ).single()["c"]
        stats["suspicious_transfers"] = session.run(
            "MATCH ()-[r:TRANSFERRED_TO]->() WHERE r.is_suspicious = true RETURN count(r) AS c"
        ).single()["c"]
    return stats
