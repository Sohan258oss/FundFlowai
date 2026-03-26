# Intelligent Fund Flow Tracking & Suspicious Pattern Detection Platform

## System Design Document — Production-Grade Reference Architecture

---

## 1. Data Ingestion Layer

### What It Does

Captures every financial event across the bank's ecosystem — core banking transactions, real-time payments (UPI/IMPS), batch settlements (NEFT/RTGS), SWIFT messages, card network authorizations, wallet transfers, and loan disbursements — and normalizes them into a single canonical transaction schema that downstream graph and ML systems can consume.

### Technical Architecture

#### Data Sources & Connectors

| Source | Protocol | Latency Class | Connector |
|---|---|---|---|
| Core Banking (T24/Finacle/Flexcube) | CDC via Oracle GoldenGate / Debezium | Near-real-time (< 2s) | Kafka Connect JDBC/CDC source |
| UPI (NPCI) | ISO 8583 over TCP | Real-time (< 500ms) | Custom adapter → Kafka producer |
| NEFT / RTGS | SFMS / ISO 20022 XML batches | Batch (on settlement cycles) | File watcher → Kafka producer |
| SWIFT (MT103/MT202) | FIN / Alliance Lite2 | Near-real-time | MQ bridge → Kafka |
| Card Networks (Visa/Mastercard) | ISO 8583 / TC files | Dual: real-time auth + batch clearing | Kafka producer for auth; batch loader for clearing |
| Wallets / Prepaid | REST API / webhooks | Real-time | REST poller / webhook consumer → Kafka |
| Loan Management System | CDC or file export | Batch (daily) | Kafka Connect |
| KYC / CIF Master Data | Database CDC | Near-real-time | Debezium CDC connector |

#### Streaming vs Batch Decision

Not everything _should_ be streamed. The design uses a **lambda-lite architecture** (not the AWS Lambda — the data architecture pattern):

- **Streaming path (Kafka → Flink):** UPI, card authorizations, wallet transfers, high-value RTGS — anything where real-time detection materially reduces risk. This covers ~60–70% of transaction volume.
- **Batch path (Airflow → Spark):** NEFT settlement files, loan disbursement reconciliation, end-of-day position recalculation, KYC data refreshes. These arrive in batches anyway; trying to fake streaming is wasteful.
- **Micro-batch hybrid:** SWIFT messages — they arrive continuously but are best processed in 30-second micro-batches for MT103/MT202 correlation.

> [!IMPORTANT]
> Don't stream everything. The cost of maintaining Flink state for low-value batch-native sources is not justified. The goal is **correct enrichment**, not minimum latency on every event.

#### Canonical Transaction Schema

Every incoming event is transformed into this normalized structure:

```json
{
  "txn_id": "uuid-v4",
  "source_system": "UPI | SWIFT | CBS | CARD | WALLET",
  "original_ref": "native-system-reference",
  "timestamp_initiated": "ISO-8601",
  "timestamp_settled": "ISO-8601 | null",
  "amount": { "value": 50000.00, "currency": "INR" },
  "sender": {
    "account_id": "hashed-or-tokenized",
    "entity_id": "CIF or entity-resolution-id",
    "account_type": "SAVINGS | CURRENT | LOAN | WALLET",
    "branch_code": "IFSC",
    "bank_code": "internal | counterparty-BIC"
  },
  "receiver": { "...same structure..." },
  "channel": "MOBILE | BRANCH | INTERNET | ATM | API",
  "product_code": "internal-product-id",
  "purpose_code": "P2P | P2M | SALARY | LOAN_REPAYMENT | ...",
  "metadata": {
    "ip_address": "if-digital-channel",
    "device_fingerprint": "if-available",
    "geo_location": "lat,long | branch-code",
    "beneficiary_registered_date": "ISO-8601"
  }
}
```

#### Data Quality & Deduplication

- **Deduplication:** Flink's exactly-once semantics with RocksDB state backend. Keyed by `(source_system, original_ref)` with a 72-hour dedup window.
- **Late arrivals:** Allowed within a 24-hour event-time watermark. Late events trigger graph re-evaluation but not re-alerting unless the new edge changes the risk score by more than a configurable threshold (default: 15%).
- **Schema validation:** Apache Avro schemas registered in Confluent Schema Registry. Schema evolution is **backward-compatible only** — breaking changes require a new topic version.

### Technology Choices

| Component | Technology | Why |
|---|---|---|
| Message broker | Apache Kafka (Confluent Platform) | Durability, ordering guarantees per partition, ecosystem maturity |
| Stream processing | Apache Flink | True event-time semantics, exactly-once, superior to Spark Streaming for stateful per-key operations |
| Batch orchestration | Apache Airflow + Spark | Mature, well-understood DAG orchestration for batch pipelines |
| Schema management | Confluent Schema Registry (Avro) | Schema evolution control, cross-team contract enforcement |
| CDC | Debezium (for open-source DBs) / Oracle GoldenGate (for Oracle CBS) | No-change required on source systems |

### Key Tradeoffs

- **CDC vs API polling:** CDC is preferred because it captures _every_ change without modifying source systems. But for third-party wallets with no DB access, API polling with idempotent ingestion is the fallback.
- **Avro vs Protobuf:** Avro chosen for better Schema Registry integration and because most banking teams are already tooled for it. Protobuf would give better serialization performance but worse tooling adoption in this ecosystem.

---

## 2. Graph Construction Engine

### What It Does

Transforms normalized transactions into a **property graph** where money flows are first-class edges. This is the single most important component — it gives investigators what they've never had: the ability to see funds move through multiple hops across accounts, entities, and time.

### Graph Data Model

```
┌──────────────────────────────────────────────────────────┐
│  NODE TYPES                                              │
│                                                          │
│  Account    { id, type, branch, open_date, status,       │
│               avg_balance_30d, dormancy_flag }            │
│                                                          │
│  Entity     { id, name, type[INDIVIDUAL|CORPORATE],      │
│               risk_rating, PEP_flag, country }            │
│                                                          │
│  Device     { fingerprint, first_seen, last_seen }       │
│                                                          │
│  Location   { geo_hash, branch_code }                    │
│                                                          │
│  Beneficiary{ id, registration_date, name_hash }         │
│                                                          │
├──────────────────────────────────────────────────────────┤
│  EDGE TYPES                                              │
│                                                          │
│  TRANSFERRED_TO  { txn_id, amount, currency, timestamp,  │
│                    channel, purpose_code, source_system } │
│                                                          │
│  OWNS            { since, role[PRIMARY|JOINT|POA] }      │
│                                                          │
│  USED_DEVICE     { session_id, timestamp }               │
│                                                          │
│  TRANSACTED_FROM { location, timestamp }                 │
│                                                          │
│  HAS_BENEFICIARY { since }                               │
└──────────────────────────────────────────────────────────┘
```

### Graph Database Selection: **Neo4j** (primary) + **Apache TinkerPop/JanusGraph** (scale-out analytical)

| Criteria | Neo4j Enterprise | JanusGraph |
|---|---|---|
| Multi-hop traversals (3–6 hops) | Excellent (native graph storage) | Good (but index-heavy) |
| Real-time updates | Native ACID transactions | Eventually consistent |
| Scale | Vertical (to ~50B edges with sharding) | Horizontal (Cassandra backend) |
| Query language | Cypher (very readable for analysts) | Gremlin (more verbose) |
| Graph algorithms | Built-in GDS library | Requires Spark GraphX |
| Operational maturity in banking | Widely adopted in AML | Less banking-specific deployment history |

**Recommendation:** Use **Neo4j Enterprise** as the operational graph for real-time traversals and investigator queries. Use **JanusGraph on Cassandra** as the deep-history analytical graph for batch GNN training and historical pattern mining.

> [!TIP]
> The operational Neo4j instance should hold a **rolling 180-day window** of transaction edges. Older edges are archived to JanusGraph/Cassandra for regulatory retention (7+ years in India under PMLA) and batch analytics.

### Real-Time Graph Updates

```
Kafka (normalized txns)
    │
    ▼
Flink Graph Updater Job
    │
    ├──► Neo4j Bolt Driver (async, batched writes)
    │    - Batch size: 500 edges per commit
    │    - Write throughput target: ~3,000 edges/sec sustained
    │    - Uses MERGE (upsert) to handle late/duplicate events
    │
    └──► JanusGraph Bulk Loader (hourly micro-batch)
         - For analytical/archival copy
```

**Vertex/edge identity resolution** is critical. Before creating a `TRANSFERRED_TO` edge, the Flink job must:
1. Resolve sender/receiver account IDs to canonical `Account` node IDs (handles account number changes, mergers).
2. Link accounts to `Entity` nodes via `OWNS` edges — this requires CIF master data to be pre-loaded.
3. Create or update `Device` and `Location` nodes for digital channel transactions.

### Key Design Decisions

- **Temporal edges:** Every `TRANSFERRED_TO` edge carries a timestamp. Traversals are time-bounded (e.g., "show me all paths from Account A to Account B within 7 days with total value > ₹10L"). This prevents false connections across years of data.
- **Edge properties vs separate relationship types:** We keep one `TRANSFERRED_TO` edge type with `channel` and `purpose_code` as properties. Creating separate edge types per channel would bloat the schema and complicate traversals.
- **Graph partitioning:** Neo4j's Fabric (multi-database federation) partitions by branch region. This keeps hop-local queries fast while allowing cross-region traversals.

### Hard Problem: Entity Resolution

The same person may appear as different CIF IDs across merged banks, appear in KYC with slightly different name spellings, or operate through power-of-attorney accounts. We use a **probabilistic entity resolution** layer (built on Splink or Zingg) that runs nightly and emits `LIKELY_SAME_AS` edges with a confidence score. Investigators see these as dashed lines — suggestive, not definitive.

---

## 3. ML Detection Models

### Model Portfolio

We use **five specialized detection models**, not one monolithic model, because each financial crime typology has fundamentally different feature geometry.

---

#### 3.1 Layering Detection

**What it detects:** Rapid movement of funds through cascaded intermediary accounts where the goal is to obscure the original source. Classic pattern: A→B→C→D→E within 24–72 hours with amounts preserved (minus small fees).

**Approach: Graph Neural Network (GNN) — GraphSAGE variant**

- **Why GNN and not tabular ML:** Layering is intrinsically a multi-hop graph pattern. Traditional ML on flat features would need hand-engineered "number of hops" features that miss novel structures. GNNs learn structural patterns directly.
- **Architecture:** 3-layer GraphSAGE with mean aggregation. Node features: account age, average balance, transaction frequency, dormancy score. Edge features: amount, time delta from previous hop, channel.
- **Training approach:** Semi-supervised. We have ~2,000 confirmed layering cases from past SARs (labelled positive), ~500,000 normal multi-hop flows (labelled negative). We also add **synthetic layering patterns** generated by domain experts to augment the training set — this partially addresses class imbalance.
- **Output:** Per-subgraph anomaly score (0–1). Subgraphs are extracted as 4-hop ego networks around flagged accounts.

**Class imbalance handling:**
- Focal loss function (γ=2) instead of standard cross-entropy
- Stratified mini-batch sampling: each batch contains 30% positive, 70% negative
- SMOTE is **not** used — it doesn't work well for graph-structured data; instead we use graph-aware augmentation (edge perturbation on negative samples)

---

#### 3.2 Round-Tripping Detection

**What it detects:** Funds leaving an account and returning to the _same_ or associated account through a circular path. Example: A→B→C→A (where B and C may be shell companies).

**Approach: Cycle detection algorithm + supervised classifier**

- **Step 1 — Cycle enumeration:** Run a time-bounded breadth-first cycle detection on the graph. Find all cycles of length 3–8 within a 30-day window. This is purely algorithmic (not ML).
- **Step 2 — Cycle scoring (XGBoost):** For each detected cycle, extract features:
  - Cycle length (number of hops)
  - Total elapsed time
  - Amount preservation ratio across hops (close to 1.0 is suspicious)
  - Entity relationship density within the cycle (are intermediaries linked by other means?)
  - Historical frequency (has this cycle pattern appeared before?)
  - Account age dispersion (are intermediaries newly opened?)

- **Why not pure GNN here:** Cycle detection has a clear algorithmic solution. The ML part is distinguishing _suspicious_ cycles from normal treasury/corporate cash management flows. XGBoost on structured cycle features outperforms GNNs for this specific binary classification (we benchmarked this internally).

**Class imbalance handling:** Synthetic minority oversampling of cycle features + cost-sensitive learning with a 50:1 penalty ratio for missed true positives.

---

#### 3.3 Structuring (Smurfing) Detection

**What it detects:** Deliberately splitting a large transaction into smaller ones to avoid the ₹10L (India) or $10K (US) cash reporting threshold. Also detects "threshold creeping" — transactions consistently just below limits.

**Approach: Unsupervised clustering + rule overlay**

- **Why unsupervised:** Structuring is fundamentally about statistical deviation from a customer's own baseline, not about matching known patterns. Supervised models overfit to known structuring amounts.
- **Algorithm:** Isolation Forest on per-customer daily features:
  - Number of cash deposits in a day
  - Sum of cash deposits vs individual max
  - Standard deviation of individual amounts (low σ with high count = suspicious)
  - Time spacing between deposits (unusually regular spacing is a flag)
  - Branch dispersion (multiple branches in one day)
- **Rule overlay:** Hard rules still matter here because regulators expect them:
  - Single-day cash deposits ≥ 80% of reporting threshold across branches → mandatory alert
  - 3+ cash deposits within 48 hours summing to > reporting threshold → mandatory alert

The Isolation Forest catches novel structuring patterns the rules miss (e.g., structuring across _weeks_ with varying amounts).

**Class imbalance:** Not applicable for Isolation Forest (unsupervised). The rule-based layer has a known high false-positive rate (~85%); this is intentional and acceptable to regulators.

---

#### 3.4 Dormant Account Activation

**What it detects:** Accounts with no material activity for 6–12+ months that suddenly begin transacting, especially with high-value flows or unusual counterparties.

**Approach: Anomaly detection via one-class SVM + temporal feature engineering**

- **Dormancy score:** Exponentially decaying activity score per account. An account becomes "dormant" when its score drops below a threshold (calibrated per product type — current accounts decay faster than term deposits).
- **Activation detection:** When a dormant account transacts, extract:
  - Dormancy duration (months)
  - Activation transaction amount vs historical average
  - Counterparty risk rating
  - Channel used for reactivation (branch visit vs digital — branch is less suspicious)
  - Whether the account was reactivated with a KYC re-verification
- **Model:** One-class SVM trained on _legitimate_ reactivation patterns (salary account reactivated after career break, seasonal business accounts). Anything far from this distribution triggers a score.

**Class imbalance:** One-class SVM inherently handles this — it models the "normal" distribution only.

---

#### 3.5 Profile-Transaction Mismatch

**What it detects:** Transaction behavior inconsistent with declared customer profile. A salaried individual suddenly receiving ₹50L wire transfers. A small grocery store processing ₹2Cr monthly card settlements.

**Approach: Supervised gradient-boosted model (LightGBM)**

- **Features (per customer, rolling 30-day):**
  - Ratio: actual monthly turnover / declared annual income
  - Ratio: actual transaction count / peer segment average
  - Product usage breadth (number of channels/products used)
  - International transaction ratio vs declared travel/business profile
  - Sudden category shifts (e.g., first-ever forex transaction)
- **Peer segmentation:** Customers are grouped into behavioural micro-segments using k-means (occupation × income band × geography × account vintage). Deviation is measured _relative to segment peers_, not absolute thresholds.
- **Training data:** Labelled from SAR filings and investigator dispositions. ~5,000 positives, ~2M negatives.

**Class imbalance:** 
- LightGBM's `scale_pos_weight` parameter set to `negative_count / positive_count`
- Evaluation metric: AUCPR (area under precision-recall curve), **not** AUROC — AUROC is misleading at extreme class imbalance
- Probability calibration via Platt scaling so output scores are meaningful probabilities

---

### Model Governance

| Aspect | Approach |
|---|---|
| Model versioning | MLflow Model Registry |
| Feature store | Feast (online: Redis, offline: BigQuery/Hive) |
| Training pipeline | Kubeflow Pipelines on Kubernetes |
| Monitoring | Evidently AI for data drift, NannyML for performance drift |
| Champion-challenger | Every new model version runs shadow-mode for 2 weeks before promotion |
| Explainability | SHAP values for tabular models, GNNExplainer for graph models |
| Regulatory model documentation | Auto-generated model cards (per SR 11-7 / RBI guidelines) |

---

## 4. Risk Scoring Engine

### What It Does

Produces a single, explainable composite risk score for every **transaction cluster** (not individual transactions — money laundering is about flows, not single events). A cluster is a connected subgraph identified by the detection models as potentially suspicious.

### Score Computation

#### Signal Taxonomy

| Signal Category | Weight Range | Source |
|---|---|---|
| Typology model scores (5 models above) | 30–45% | ML models |
| Network topology features | 15–25% | Graph analysis |
| Entity risk attributes | 15–20% | KYC/watchlist data |
| Behavioural velocity | 10–15% | Time-series analysis |
| Geographic risk | 5–10% | Country/region risk ratings |

#### Composite Score Formula

```
RiskScore = Σ (wᵢ × normalized_signalᵢ) × amplifier_factor

Where:
  wᵢ          = signal weight (configurable per compliance policy)
  amplifier    = multiplier for co-occurring signals
                 (e.g., layering + dormant activation = 1.5× amplifier)
  
  Final score is clipped to [0, 100] and bucketed:
    0–30:   Low     → Auto-close (with audit trail)
    31–60:  Medium  → Queue for Level 1 analyst review
    61–80:  High    → Priority queue for Level 2 investigator
    81–100: Critical → Immediate escalation + potential STR filing
```

#### Why Not a Single End-to-End Model?

A tempting but wrong approach is to train one neural network that takes raw features and predicts "suspicious / not suspicious." Problems:

1. **Regulatory explainability:** RBI/FinCEN require you to articulate _why_ a transaction is flagged. "The neural network said so" is not acceptable.
2. **Signal auditability:** When a model is retrained and scores shift, you need to know _which signal changed_. A monolithic model gives you no decomposition.
3. **Policy configurability:** Compliance officers need to adjust weights when a new typology is prioritized (e.g., trade-based money laundering). With a composite score, you change a weight. With an end-to-end model, you retrain.

### Explainability for Investigators

Each scored cluster comes with an **evidence summary** auto-generated from signal decomposition:

```
═══════════════════════════════════════════════════
CLUSTER RISK ASSESSMENT — CLU-2026-0319-A847
═══════════════════════════════════════════════════
Overall Score: 78/100 (HIGH)

TOP CONTRIBUTING FACTORS:
  1. Layering pattern detected (score: 0.87)
     → Funds traversed 5 accounts in 36 hours
     → Amount preservation: 97.2%
  
  2. Dormant account in path (score: 0.72)
     → Account XXXX4521 was dormant for 14 months
     → Reactivated via mobile channel, no re-KYC
  
  3. Profile mismatch on originator (score: 0.65)
     → Monthly outflow 12× declared annual income
     → First-ever international wire transfer

  4. Geographic risk (score: 0.40)
     → Funds routed through high-risk jurisdiction (FATF greylist)

RECOMMENDED ACTION: Level 2 investigation + STR consideration
═══════════════════════════════════════════════════
```

### Technology

- **Scoring engine:** Custom Java/Kotlin microservice on Kubernetes. Scores must compute in < 200ms per cluster.
- **Score storage:** PostgreSQL (for relational queries by investigators) + Elasticsearch (for full-text search on evidence narratives).
- **Weight configuration:** Stored in a versioned configuration service (Spring Cloud Config or HashiCorp Consul) — not hardcoded. Every weight change is audit-logged.

---

## 5. Investigator Dashboard

### Design Philosophy

Investigators are not data scientists. The dashboard must make **complex graph structures intuitive** and generate **regulator-ready evidence** with minimal manual effort.

### Graph Visualization

```
┌─────────────────────────────────────────────────────────────────────────┐
│  FUND FLOW INVESTIGATOR — CASE CLU-2026-0319-A847                      │
│                                                                         │
│  ┌─ GRAPH VIEW ──────────────────────────────────────────────────────┐  │
│  │                                                                    │  │
│  │     [Acct A]───₹9.8L──►[Acct B]───₹9.5L──►[Acct C]              │  │
│  │     (Originator)   36min    (Mule?)   2hr      │                  │  │
│  │                                                 │                  │  │
│  │                                          ₹9.3L  │ 4hr             │  │
│  │                                                 ▼                  │  │
│  │                              [Acct E]◄──₹9.1L──[Acct D]          │  │
│  │                              (Dormant)   8hr    (Shell Co?)       │  │
│  │                                                                    │  │
│  │   ● Red edges = high risk     ○ Grey = normal                     │  │
│  │   ◉ Pulsing node = dormant    ▬ Thickness = amount               │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌─ TIMELINE ────────────────────────────────────────────────────────┐  │
│  │  |──A→B──|────B→C────|──────C→D──────|────────D→E────────|       │  │
│  │  10:04   10:40       12:42           16:55               01:12   │  │
│  │  Mar 17              Mar 17                              Mar 18  │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌─ CONTROLS ─┐  ┌─ ENTITY DETAIL ──────────────────────────────────┐  │
│  │ Time range │  │ Account: XXXX4521 (Acct E)                       │  │
│  │ Min amount │  │ Customer: [Name redacted]                        │  │
│  │ Hop count  │  │ Profile: Salaried, ₹6L annual income            │  │
│  │ Channel    │  │ Account opened: 2019-03-14                       │  │
│  │ Risk ≥ [ ] │  │ Last active: 2024-12-02 (14 months dormant)     │  │
│  │            │  │ Today's inflow: ₹9.1L (anomaly score: 0.91)     │  │
│  │ [Expand]   │  │ KYC status: EXPIRED                              │  │
│  │ [Collapse] │  │                                                   │  │
│  │ [Export]   │  │ [View full transaction history]                   │  │
│  └────────────┘  │ [View linked alerts]                              │  │
│                  └───────────────────────────────────────────────────┘  │
│                                                                         │
│  [📄 Generate Evidence Package]  [🚩 File STR]  [✓ Mark Cleared]       │
└─────────────────────────────────────────────────────────────────────────┘
```

### Investigator Controls

| Control | Function |
|---|---|
| **Time range slider** | Filter edges to a specific date range. Prevents information overload on long-running accounts. |
| **Amount threshold** | Hide edges below a value. Useful for focusing on material flows. |
| **Hop depth** | Expand/collapse graph depth from the focal node (1–8 hops). Default: 3. |
| **Channel filter** | Show only UPI / SWIFT / Cash / Card edges. Helps isolate channel-specific patterns. |
| **Risk threshold** | Only show nodes/edges above a risk score. |
| **Path highlighter** | Click two nodes → system highlights all shortest paths between them with amounts and timing. |
| **Cluster comparison** | Side-by-side view of current cluster vs a known typology template (from the library of confirmed cases). |

### Evidence Package Generation

When an investigator clicks "Generate Evidence Package," the system produces a **self-contained PDF/HTML report** containing:

1. **Executive summary** — Auto-generated narrative describing the suspicious activity
2. **Fund flow diagram** — The graph visualization as a static image
3. **Transaction table** — Every transaction in the cluster with full details
4. **Customer profiles** — KYC data, risk ratings, PEP status for all entities
5. **Detection rationale** — Which models flagged this, with SHAP explanations
6. **Timeline** — Chronological sequence of events
7. **Regulatory references** — Applicable sections of PMLA / Bank Secrecy Act
8. **Audit trail** — Every analyst action on this case (who viewed, when, what disposition)

This maps directly to the **FIU-IND CTR/STR filing format** and the **FinCEN SAR narrative requirements**.

### Technology

| Component | Technology |
|---|---|
| Frontend framework | React + TypeScript |
| Graph rendering | Cytoscape.js (for interactive graph) or D3.js (for custom layouts) |
| Timeline visualization | vis-timeline |
| Backend API | Spring Boot (Java/Kotlin) |
| Evidence PDF generation | Apache PDFBox or WeasyPrint |
| Access control | Keycloak RBAC (investigators see only their branch/region unless escalated) |
| Audit logging | Immutable append-only log in PostgreSQL + SIEM forwarding |

---

## 6. Feedback & Model Improvement Loop

### What It Does

Closes the loop between investigator decisions and model quality. Without this, models degrade within 6–12 months as criminal typologies evolve and population drift occurs.

### Feedback Architecture

```
Investigator Decision
    │
    ├── "Confirmed Suspicious" (filed STR)
    │       → Label = TRUE POSITIVE
    │       → Add to training set with full feature vector
    │       → Trigger: if >50 new TPs accumulated → schedule retraining
    │
    ├── "Cleared — Not Suspicious"
    │       │
    │       ├── Reason: "Normal business activity"
    │       │       → Label = FALSE POSITIVE (soft)
    │       │       → Add to FP corpus with reason code
    │       │
    │       └── Reason: "Insufficient evidence"
    │               → Label = INDETERMINATE
    │               → DO NOT add to training set (label noise risk)
    │
    └── "Escalated" (needs more investigation)
            → No label change yet
            → Track for eventual resolution
```

### Handling False Positives Without Degrading the Model

This is one of the **hardest problems** in AML ML. Here's what goes wrong if you're naive:

- **Problem:** If you blindly label all investigator-cleared cases as "not suspicious" and add them to training data, you'll teach the model to ignore patterns that _are_ suspicious but happen to be common (e.g., legitimate high-value business flows that _look_ like layering).
- **Problem:** If you ignore false positive feedback entirely, alert volumes stay unworkably high (>90% FP rate in many banks).

**Solution — Stratified Feedback Incorporation:**

1. **Reason-coded FPs:** Investigators must select a reason code when clearing. These map to specific model features, allowing targeted suppression without global model degradation.
2. **FP dampening, not FP training:** Instead of retraining the model on FPs, we train a **secondary FP prediction model** (logistic regression) that acts as a post-filter. This model predicts P(false positive | risk score, entity attributes, reason code). Alerts where P(FP) > 0.85 are auto-deprioritized but still logged.
3. **Periodic FP review:** Monthly, a sample of auto-deprioritized cases is sent for manual review to verify the FP filter isn't creating blind spots.
4. **Population stability index (PSI):** Track feature distributions monthly. If PSI > 0.25 for any critical feature, force a model review even if no retraining trigger has fired.

### Retraining Schedule

| Condition | Action |
|---|---|
| 50+ new confirmed positives | Retrain typology model (champion-challenger deployment) |
| PSI > 0.25 on any feature | Feature investigation + potential retraining |
| Quarterly (mandatory) | Full model recalibration + regulatory documentation update |
| New typology identified | New model development sprint (separate from retraining) |

### Technology

| Component | Technology |
|---|---|
| Label management | Label Studio (annotation platform) |
| Retraining pipeline | Kubeflow Pipelines (automated trigger from label store) |
| A/B testing framework | Custom: shadow scoring on production traffic for 2 weeks |
| Drift monitoring | Evidently AI (dashboards) + custom PSI monitoring |
| Model registry | MLflow with approval gates |

---

## 7. Architecture Overview

### End-to-End System Architecture

```
                         INTELLIGENT FUND FLOW TRACKING PLATFORM
                         ========================================

  DATA SOURCES                    INGESTION                       PROCESSING
  ════════════                    ═════════                       ══════════
  ┌──────────┐    CDC/API     ┌──────────────┐              ┌────────────────┐
  │Core Bank │───────────────►│              │              │                │
  │(Finacle) │                │              │   Stream     │  Apache Flink  │
  ├──────────┤    CDC         │              │──────────────►  (Real-time    │
  │ Payments │───────────────►│    Apache    │              │   enrichment,  │
  │(UPI/IMPS)│                │    Kafka     │              │   dedup,       │
  ├──────────┤    MQ Bridge   │  (Confluent) │              │   normalization│
  │  SWIFT   │───────────────►│              │              │   graph update)│
  ├──────────┤    File Watch  │              │              └───────┬────────┘
  │NEFT/RTGS │───────────────►│              │                      │
  ├──────────┤    Adapter     │              │              ┌───────▼────────┐
  │  Cards   │───────────────►│              │    Batch     │  Apache Spark  │
  ├──────────┤    Webhook     │              │──────────────►  (Batch ETL,   │
  │ Wallets  │───────────────►│              │              │   historical   │
  ├──────────┤    CDC         │              │              │   recomputation│
  │  KYC/CIF │───────────────►│              │              └───────┬────────┘
  └──────────┘                └──────────────┘                      │
                                                                    │
                                                                    ▼
  GRAPH LAYER               ML DETECTION                    RISK SCORING
  ═══════════               ════════════                    ════════════
  ┌──────────────┐    ┌─────────────────────┐         ┌──────────────────┐
  │   Neo4j      │    │   Model Portfolio   │         │  Risk Scoring    │
  │  (Operational│◄───┤                     │────────►│  Engine          │
  │   180-day    │    │ • GraphSAGE         │         │                  │
  │   window)    │    │   (Layering)        │         │ • Signal         │
  │              │    │ • XGBoost           │         │   aggregation    │
  │   Cypher     │    │   (Round-tripping)  │         │ • Composite      │
  │   queries    │    │ • Isolation Forest  │         │   scoring        │
  └──────┬───────┘    │   (Structuring)     │         │ • Explainability │
         │            │ • One-class SVM     │         │   generation     │
  ┌──────▼───────┐    │   (Dormant accts)   │         └────────┬─────────┘
  │ JanusGraph   │    │ • LightGBM          │                  │
  │ (Historical  │    │   (Profile mismatch)│                  │
  │  archive,    │    │                     │                  │
  │  GNN train)  │    │ Feast Feature Store │                  │
  └──────────────┘    │ MLflow Registry     │                  │
                      │ Kubeflow Pipelines  │                  │
                      └─────────────────────┘                  │
                                                               │
                                                               ▼
  INVESTIGATOR LAYER                              FEEDBACK LOOP
  ══════════════════                              ═════════════
  ┌─────────────────────────────────────┐    ┌──────────────────────┐
  │        Investigator Dashboard       │    │   Feedback Engine    │
  │                                     │    │                      │
  │  React + Cytoscape.js               │    │ • Label management   │
  │                                     │    │   (Label Studio)     │
  │  • Interactive graph visualization  │    │ • Reason-coded FP    │
  │  • Fund flow tracing controls       │◄──►│   handling           │
  │  • Risk score decomposition         │    │ • Retraining trigger │
  │  • Evidence package generation      │    │   (Kubeflow)         │
  │  • STR/CTR filing integration       │    │ • Drift monitoring   │
  │                                     │    │   (Evidently AI)     │
  │  Spring Boot API + Keycloak RBAC    │    │ • Champion-challenger│
  └─────────────────────────────────────┘    └──────────────────────┘


  INFRASTRUCTURE LAYER
  ════════════════════
  ┌──────────────────────────────────────────────────────────────────┐
  │  Kubernetes (EKS/AKS/on-prem OpenShift)                        │
  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
  │  │ Flink    │ │ Spark    │ │ ML Serving│ │ Scoring Engine   │   │
  │  │ Cluster  │ │ Cluster  │ │ (Seldon/ │ │ (Spring Boot)    │   │
  │  │          │ │          │ │  Triton)  │ │                  │   │
  │  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘   │
  │                                                                  │
  │  Monitoring: Prometheus + Grafana + PagerDuty                   │
  │  Logging: ELK Stack (Elasticsearch + Logstash + Kibana)         │
  │  Secrets: HashiCorp Vault                                       │
  │  CI/CD: GitLab CI / Jenkins + ArgoCD                            │
  └──────────────────────────────────────────────────────────────────┘
```

### Technology Stack Summary

| Layer | Technology | Version/Edition |
|---|---|---|
| **Messaging** | Apache Kafka (Confluent Platform) | 7.x |
| **Stream Processing** | Apache Flink | 1.18+ |
| **Batch Processing** | Apache Spark | 3.5+ |
| **Orchestration** | Apache Airflow | 2.8+ |
| **Graph DB (Operational)** | Neo4j Enterprise | 5.x |
| **Graph DB (Analytical)** | JanusGraph + Cassandra | 1.0 + 4.x |
| **Relational DB** | PostgreSQL | 16+ |
| **Search** | Elasticsearch | 8.x |
| **Cache / Online Features** | Redis Cluster | 7.x |
| **Feature Store** | Feast | 0.35+ |
| **ML Training** | PyTorch (GNNs) + LightGBM + scikit-learn | Latest stable |
| **ML Pipeline** | Kubeflow Pipelines | 2.x |
| **Model Registry** | MLflow | 2.x |
| **Model Serving** | Seldon Core or NVIDIA Triton | Latest |
| **Drift Monitoring** | Evidently AI + NannyML | Latest |
| **Frontend** | React + TypeScript + Cytoscape.js | React 18+ |
| **Backend API** | Spring Boot (Kotlin) | 3.2+ |
| **Identity/RBAC** | Keycloak | 23+ |
| **Container Orchestration** | Kubernetes (EKS / OpenShift) | 1.28+ |
| **Monitoring** | Prometheus + Grafana | Latest |
| **CI/CD** | GitLab CI + ArgoCD | Latest |
| **Secrets** | HashiCorp Vault | 1.15+ |
| **CDC** | Debezium / Oracle GoldenGate | Latest |

### Latency & Throughput Targets (10M txn/day)

| Metric | Target | Rationale |
|---|---|---|
| **Ingestion throughput** | ~120 txn/sec sustained (peak 500/sec) | 10M/day = 115/sec average; 4× burst headroom |
| **Ingestion latency (streaming)** | < 2 seconds from source to Kafka | Must not bottleneck payment processing |
| **Graph update latency** | < 5 seconds from Kafka to Neo4j | Near-real-time is sufficient; true real-time is unnecessary cost |
| **Real-time detection scoring** | < 10 seconds end-to-end (event → score) | Fast enough to block high-risk transactions if needed |
| **Batch detection (full graph)** | < 4 hours nightly window | Must complete before morning shift; includes GNN inference |
| **Dashboard query response** | < 3 seconds for 3-hop traversal | Investigator productivity requirement |
| **Evidence package generation** | < 30 seconds | Includes PDF rendering and data aggregation |
| **Graph size (180-day window)** | ~600M edges, ~50M nodes | Based on 10M txn/day × 180 days × dedup factor |

### Capacity Planning

```
COMPUTE ESTIMATES (10M txn/day, 180-day graph window):

  Kafka Cluster:        6 brokers, 24 partitions, 3× replication
                        Storage: 10TB (30-day retention)

  Flink Cluster:        12 TaskManagers, 4 cores / 16GB each
                        Checkpointing: 60-second intervals

  Neo4j Cluster:        3-node causal cluster
                        RAM: 256GB per node (graph must fit in page cache)
                        SSD: 2TB per node

  Spark Cluster:        Dynamic allocation, peak 50 executors
                        8 cores / 32GB per executor

  ML Training:          4× NVIDIA A100 GPUs (GNN training)
                        CPU cluster for XGBoost/LightGBM

  ML Serving:           3 replicas per model, auto-scaling
                        ~200ms p99 latency per inference call

  PostgreSQL:           Primary + 2 read replicas
                        Storage: 5TB (case management + scores)

  Redis:                6-node cluster, 128GB total
                        (online feature serving)
```

---

## Hard Problems — Honest Assessment

### 1. Entity Resolution at Scale
Merging entities across systems with inconsistent identifiers and name spellings is an unsolved-in-general problem. We use Splink for probabilistic matching, but expect ~5% false merge rate. Investigators will surface errors; the system needs a manual override mechanism.

### 2. Adversarial Adaptation
Criminals adapt. Once a model catches a pattern, sophisticated launderers evolve. This is not a "train and deploy" system — it requires continuous red-teaming by financial crime consultants who generate synthetic adversarial transaction patterns.

### 3. Regulatory Jurisdiction Fragmentation
India (PMLA/FEMA), US (BSA/OFAC), EU (AMLD6) all have different reporting thresholds, timelines, and evidence requirements. The rule engine and reporting module must be jurisdiction-aware and parameterized, not hardcoded.

### 4. Explainability vs Accuracy Tradeoff
GNNs are more accurate for layering detection but harder to explain. The current design mitigates this with GNNExplainer, but regulators may challenge "black box" decisions. The composite scoring architecture provides a safety net: even if you can't fully explain the GNN score, the other signal components are fully transparent.

### 5. Alert Volume Management
At 10M transactions/day with a 0.1% alert rate, that's 10,000 alerts/day. A team of 50 investigators can handle ~200 cases/day. You **must** auto-close or auto-deprioritize ~95% of low-risk alerts, which creates regulatory risk if a true positive is auto-closed. The tiered scoring system with audit trails is the mitigation.

### 6. Data Privacy & Access Control
Investigators should only see data relevant to their jurisdiction. Neo4j's fine-grained access control (FBAC) and Keycloak's role-based policies enforce this, but the graph structure itself can leak information (e.g., seeing that Account A connects to a restricted entity even if you can't see the entity's details). This requires graph-level access control — a feature Neo4j supports but that is complex to configure correctly.
