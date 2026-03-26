# Intelligent Fund Flow Tracking & Suspicious Pattern Detection Platform

A production-grade AI/ML system for detecting money laundering patterns in banking transactions using graph analysis and machine learning.

## Project Structure

```
├── docker-compose.yml          # Neo4j + Postgres + Redis (local dev)
├── data-generator/             # Synthetic transaction generator
│   ├── data_generator/
│   │   ├── accounts.py         # Account profile generator
│   │   ├── transactions.py     # Normal transaction generator
│   │   ├── generator.py        # Main orchestrator
│   │   ├── output.py           # JSON/summary writer
│   │   └── patterns/
│   │       ├── layering.py             # Multi-hop fund layering
│   │       ├── round_tripping.py       # Circular fund flows
│   │       ├── structuring.py          # Deposit splitting (smurfing)
│   │       ├── dormant_activation.py   # Dormant account reactivation
│   │       └── profile_mismatch.py     # Profile-transaction anomalies
│   └── tests/
│       └── test_generator.py   # Generator test suite
│
├── graph-engine/               # Neo4j graph construction & queries
│   ├── graph_engine/
│   │   ├── schema.py           # Constraints & indexes
│   │   ├── loader.py           # Batch graph loader
│   │   └── queries.py          # Cypher query library
│   └── tests/
│       └── test_graph_engine.py
│
└── docs/                       # Architecture documentation
```

## Quick Start

### 1. Start Infrastructure

```bash
docker compose up -d
```

This starts:
- **Neo4j** at http://localhost:7474 (bolt: `localhost:7687`, credentials: `neo4j/fundflow_pass`)
- **PostgreSQL** at `localhost:5432` (db: `fundflow`, credentials: `fundflow/fundflow_pass`)
- **Redis** at `localhost:6379`

### 2. Install Python Dependencies

```bash
# Data generator
cd data-generator
pip install -e ".[dev]"

# Graph engine
cd ../graph-engine
pip install -e ".[dev]"
```

### 3. Generate Synthetic Data

```bash
cd data-generator

# Small dataset (quick test)
python -m data_generator.generator --accounts 1000 --days 30 --output ./output

# Full dataset
python -m data_generator.generator --accounts 10000 --days 90 --output ./output
```

Output files:
- `output/accounts.json` — Account profiles
- `output/transactions.json` — All transactions (normal + suspicious)
- `output/ground_truth.json` — Labelled suspicious patterns with metadata
- `output/summary.txt` — Human-readable dataset summary

### 4. Load Into Neo4j

```bash
cd graph-engine
python -m graph_engine.loader --accounts ../data-generator/output/accounts.json \
                                --transactions ../data-generator/output/transactions.json \
                                --clear
```

### 5. Explore the Graph

Open http://localhost:7474 and try:

```cypher
// See a layering chain
MATCH path = (a:Account)-[t:TRANSFERRED_TO*3..5]->(b:Account)
WHERE ALL(r IN relationships(path) WHERE r.is_suspicious = true
      AND r.suspicious_pattern = 'LAYERING')
RETURN path LIMIT 5

// Find high-value fund flows
MATCH (a:Account)-[t:TRANSFERRED_TO]->(b:Account)
WHERE t.amount > 500000
RETURN a.account_id, b.account_id, t.amount, t.timestamp
ORDER BY t.amount DESC LIMIT 20

// Graph statistics
MATCH (n) RETURN labels(n) AS type, count(n) AS count
```

### 6. Run Tests

```bash
# Data generator tests
cd data-generator
pytest tests/ -v

# Graph engine tests (no Neo4j required)
cd ../graph-engine
pytest tests/ -v
```

## Suspicious Patterns Generated

| Pattern | Description | Default Count |
|---------|-------------|---------------|
| **Layering** | Rapid A→B→C→D→E chains, 97-99% amount preserved per hop | 100 |
| **Round-tripping** | Circular flows A→B→C→A within 3-30 days | 80 |
| **Structuring** | Cash deposits split below ₹10L threshold | 120 |
| **Dormant activation** | 6-24 month dormant accounts suddenly transacting | 80 |
| **Profile mismatch** | Transactions inconsistent with declared occupation/income | 120 |

## Architecture

See `docs/` for the full system design document covering:
- Data ingestion layer
- Graph construction engine
- ML detection models
- Risk scoring engine
- Investigator dashboard
- Feedback & model improvement loop
