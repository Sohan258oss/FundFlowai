"""
Neo4j schema setup — constraints, indexes, and graph data model initialization.
"""

from typing import List
from neo4j import GraphDatabase


# ---------------------------------------------------------------------------
# Cypher statements for schema setup
# ---------------------------------------------------------------------------

CONSTRAINTS: List[str] = [
    # Unique constraints
    "CREATE CONSTRAINT account_id IF NOT EXISTS FOR (a:Account) REQUIRE a.account_id IS UNIQUE",
    "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.entity_id IS UNIQUE",
    "CREATE CONSTRAINT txn_id IF NOT EXISTS FOR (t:Transaction) REQUIRE t.txn_id IS UNIQUE",
]

INDEXES: List[str] = [
    # Performance indexes for common query patterns
    "CREATE INDEX account_status IF NOT EXISTS FOR (a:Account) ON (a.status)",
    "CREATE INDEX account_type IF NOT EXISTS FOR (a:Account) ON (a.account_type)",
    "CREATE INDEX account_branch IF NOT EXISTS FOR (a:Account) ON (a.branch_code)",
    "CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.entity_type)",
    "CREATE INDEX entity_risk IF NOT EXISTS FOR (e:Entity) ON (e.pep_flag)",
    # Full-text search index for entity names
    # "CREATE FULLTEXT INDEX entity_name_ft IF NOT EXISTS FOR (e:Entity) ON EACH [e.entity_name]",
]


def setup_schema(driver: GraphDatabase.driver) -> None:
    """
    Create all constraints and indexes in Neo4j.

    Safe to run multiple times — all statements use IF NOT EXISTS.
    """
    with driver.session() as session:
        print("Setting up Neo4j schema...")

        for stmt in CONSTRAINTS:
            print(f"  Constraint: {stmt[:70]}...")
            session.run(stmt)

        for stmt in INDEXES:
            print(f"  Index: {stmt[:70]}...")
            session.run(stmt)

        print("  Schema setup complete.")


def clear_database(driver: GraphDatabase.driver) -> None:
    """
    Delete all nodes and relationships. USE WITH CAUTION.
    Only for development/testing — batched to avoid memory issues.
    """
    with driver.session() as session:
        print("Clearing database (batched)...")
        while True:
            result = session.run(
                "MATCH (n) WITH n LIMIT 10000 DETACH DELETE n RETURN count(*) AS deleted"
            )
            deleted = result.single()["deleted"]
            if deleted == 0:
                break
            print(f"  Deleted {deleted} nodes...")
        print("  Database cleared.")
