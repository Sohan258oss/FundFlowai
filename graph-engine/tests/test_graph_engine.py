"""
Tests for the graph engine.

Note: Tests that require a running Neo4j instance are marked with
@pytest.mark.neo4j and skipped by default. Run them with:
    pytest -m neo4j --neo4j-uri bolt://localhost:7687
"""

import pytest
import os

from graph_engine.schema import CONSTRAINTS, INDEXES
from graph_engine.loader import (
    load_accounts,
    load_transactions,
    load_from_files,
    _batch_iter,
)
from graph_engine.queries import (
    find_multi_hop_paths,
    find_shortest_path,
    detect_cycles,
    find_rapid_pass_through,
    find_high_fan_out,
    get_account_neighborhood,
    get_graph_stats,
    get_driver,
)

# Mark tests that need a live Neo4j connection
pytestmark_neo4j = pytest.mark.skipif(
    not os.environ.get("NEO4J_TEST"),
    reason="Set NEO4J_TEST=1 to run Neo4j integration tests",
)


class TestSchemaModule:
    """Test schema module loads without errors."""

    def test_import(self):
        assert len(CONSTRAINTS) > 0
        assert len(INDEXES) > 0

    def test_constraints_are_valid_cypher(self):
        for stmt in CONSTRAINTS:
            assert "CREATE CONSTRAINT" in stmt
            assert "IF NOT EXISTS" in stmt

    def test_indexes_are_valid_cypher(self):
        for stmt in INDEXES:
            assert "CREATE INDEX" in stmt
            assert "IF NOT EXISTS" in stmt


class TestLoaderModule:
    """Test loader utilities (no Neo4j required)."""

    def test_import(self):
        assert callable(load_accounts)
        assert callable(load_transactions)
        assert callable(load_from_files)

    def test_batch_iter(self):
        items = list(range(10))
        batches = list(_batch_iter(items, 3))
        assert len(batches) == 4
        assert batches[0] == [0, 1, 2]
        assert batches[-1] == [9]


class TestQueriesModule:
    """Test query module imports and query structure."""

    def test_import(self):
        assert callable(find_multi_hop_paths)
        assert callable(find_shortest_path)
        assert callable(detect_cycles)
        assert callable(find_rapid_pass_through)
        assert callable(find_high_fan_out)
        assert callable(get_account_neighborhood)
        assert callable(get_graph_stats)

    def test_get_driver(self):
        # Should create a driver without connection (lazy connect)
        driver = get_driver(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="test",
        )
        assert driver is not None
        driver.close()
