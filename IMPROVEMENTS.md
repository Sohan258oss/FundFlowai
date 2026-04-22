# FundFlow AI — Future Improvements Roadmap

> Detailed improvement suggestions with implementation prompts for each item.

---

## Table of Contents

1. [Security Hardening](#1-security-hardening)
2. [Architecture & Scalability](#2-architecture--scalability)
3. [ML Model Improvements](#3-ml-model-improvements)
4. [Dashboard & UX](#4-dashboard--ux)
5. [DevOps & CI/CD](#5-devops--cicd)
6. [Compliance & Reporting](#6-compliance--reporting)
7. [Data Pipeline](#7-data-pipeline)
8. [Monitoring & Observability](#8-monitoring--observability)

---

## 1. Security Hardening

### 1.1 JWT-Based Authentication with RBAC

**Current State**: Simple API key header check. No role differentiation.

**Why**: Production AML systems need role-based access — analysts can view alerts, senior investigators can file STRs, admins can trigger retraining.

**Prompt**:
> Implement JWT-based authentication for both the Risk Scoring API (FastAPI on port 8000) and Feedback API (FastAPI on port 8001). Use `python-jose` for JWT encoding/decoding and `passlib` for password hashing. Create three roles: `ANALYST` (read-only alerts), `INVESTIGATOR` (read alerts + submit dispositions), and `ADMIN` (full access including retraining triggers and drift monitoring). Store users in the PostgreSQL database already defined in `docker-compose.yml`. Add a `/api/v1/auth/login` endpoint that returns access and refresh tokens. Create a `dependencies.py` file with a `get_current_user` dependency that extracts and validates the JWT from the `Authorization: Bearer` header. Apply role checks to each endpoint using FastAPI's `Depends()`. Update the dashboard's `api.ts` to store the JWT in localStorage and attach it to every axios request via an interceptor. Add a login page component to the React dashboard.

### 1.2 Rate Limiting

**Current State**: No rate limiting on any endpoint.

**Why**: Prevents brute-force attacks and DoS on scoring/feedback endpoints.

**Prompt**:
> Add rate limiting to both FastAPI services using the `slowapi` library. Configure the following limits: `/api/v1/alerts` — 30 requests/minute per IP, `/api/v1/score` — 60 requests/minute per IP, `/api/v1/feedback/disposition` — 20 requests/minute per IP, `/api/v1/feedback/retrain` — 2 requests/hour per IP. Add a custom rate limit exceeded handler that returns HTTP 429 with a `Retry-After` header. Store rate limit state in the Redis instance already running in `docker-compose.yml` on port 6379. Add the `slowapi` dependency to both `pyproject.toml` files.

### 1.3 TLS/HTTPS Configuration

**Current State**: All API communication is plaintext HTTP.

**Prompt**:
> Configure TLS for the uvicorn servers serving risk-scoring (port 8000) and feedback (port 8001) APIs. Add `--ssl-keyfile` and `--ssl-certfile` parameters to the uvicorn startup commands in `run_demo.py`. Create a `scripts/generate_dev_certs.sh` script that uses `openssl` to generate self-signed certificates for local development. Update the dashboard's `api.ts` base URLs to use `https://`. Add environment variables `SSL_KEYFILE` and `SSL_CERTFILE` to `.env.example`. Document the production certificate setup (Let's Encrypt / corporate CA) in README.md.

### 1.4 Input Sanitization & Request Validation

**Current State**: Basic Pydantic validation on some endpoints only.

**Prompt**:
> Add comprehensive input validation to all API endpoints. For the `/api/v1/feedback/disposition` endpoint, validate that `cluster_id` matches the pattern `^[A-Z]{2,5}-[A-Z0-9-]+$`, `investigator_id` matches `^INV-[0-9]{3,6}$`, and `notes` is limited to 2000 characters with HTML tags stripped. For the `/api/v1/graph/{account_id}` endpoint, validate that `account_id` matches `^ACC-[A-F0-9]{12}$`. Add a global exception handler in both APIs that catches `ValidationError` and returns structured error responses with field-level details. Use Pydantic's `Field(regex=...)` and custom validators.

---

## 2. Architecture & Scalability

### 2.1 Migrate Feedback Storage to PostgreSQL

**Current State**: Feedback persisted to a JSON file (`feedback_store.json`) — not concurrent-safe.

**Prompt**:
> Migrate the feedback persistence layer from JSON file storage to PostgreSQL. The PostgreSQL instance is already defined in `docker-compose.yml` (host: `localhost:5432`, db: `fundflow`, user: `fundflow`, pass: `fundflow_pass`). Create a `feedback/models.py` file using SQLAlchemy ORM with these tables: `dispositions` (id, cluster_id, investigator_id, disposition, reason_code, feature_vector JSONB, notes, label, timestamp, used_in_training), `retrain_events` (id, triggered_at, tp_count, model_version), and `baseline_features` (id, feature_name, bin_edges JSONB, bin_counts JSONB, created_at). Create a `feedback/database.py` with async SQLAlchemy engine setup using `asyncpg`. Refactor `DispositionRecorder` in `feedback_core.py` to use SQLAlchemy sessions instead of `_load_store()`/`_save_store()`. Add Alembic for schema migrations with an initial migration script. Keep the JSON fallback as a read-only legacy import path.

### 2.2 Event-Driven Architecture with Redis Pub/Sub

**Current State**: Services communicate via synchronous REST calls only.

**Prompt**:
> Implement event-driven communication between services using the Redis instance already in `docker-compose.yml`. Create a `shared/events.py` module with an `EventBus` class that publishes and subscribes to Redis channels. Define these events: `ALERT_SCORED` (published by risk-scoring after scoring a pattern), `DISPOSITION_RECORDED` (published by feedback after a disposition), `RETRAIN_TRIGGERED` (published by feedback when TP threshold is reached), `DRIFT_DETECTED` (published by feedback PSI monitor). The risk-scoring API should publish `ALERT_SCORED` events after each scoring call. The feedback API should subscribe to `ALERT_SCORED` to auto-populate its baseline features. The dashboard should receive real-time updates via Server-Sent Events (SSE) — add a `/api/v1/events/stream` endpoint to risk-scoring that streams Redis pub/sub messages as SSE to the React frontend using `EventSource`.

### 2.3 Async API Endpoints

**Current State**: All FastAPI endpoints are synchronous (`def` not `async def`).

**Prompt**:
> Convert all FastAPI endpoints in `risk-scoring/risk_scoring/api.py` and `feedback/api.py` from synchronous `def` to `async def`. Replace synchronous file I/O (`open()`, `json.load()`) with `aiofiles` for reading `ground_truth.json` and `transactions.json`. For the feedback persistence (once migrated to PostgreSQL), use `async with AsyncSession()`. For the graph endpoint `/api/v1/graph/{account_id}`, use `asyncio.to_thread()` to wrap the CPU-bound BFS computation. Add `aiofiles` to both `pyproject.toml` dependencies. Benchmark before/after using `locust` with 50 concurrent users hitting `/api/v1/alerts`.

### 2.4 API Gateway with Request Routing

**Current State**: Dashboard talks directly to two separate API ports (8000, 8001).

**Prompt**:
> Add an nginx reverse proxy as an API gateway in `docker-compose.yml` that routes all API traffic through a single port (80). Route `/api/v1/alerts`, `/api/v1/score`, and `/api/v1/graph/*` to the risk-scoring service (port 8000). Route `/api/v1/feedback/*` to the feedback service (port 8001). Serve the dashboard's static build files from `/`. Add request logging, gzip compression, and a 30-second timeout. Create `nginx/nginx.conf` with the routing rules. Update the dashboard's `api.ts` to use a single `baseURL` (no port-specific URLs). Add health check upstream configuration so nginx can detect and report service failures.

---

## 3. ML Model Improvements

### 3.1 Model Versioning & Registry

**Current State**: Models are trained in-memory and not persisted or versioned.

**Prompt**:
> Implement a model registry system for the 5 detection models. Create a `detection-models/registry/` directory with a `ModelRegistry` class that saves trained model artifacts (pickle/joblib for sklearn/xgb, torch state_dict for GNN) to a `models/` directory with versioned filenames like `layering_gnn_v1.2_20260422.pt`. Store metadata in a `model_manifest.json` with fields: model_name, version, trained_at, training_data_hash, metrics (precision, recall, PR-AUC), feature_columns, hyperparameters. Add a `registry.get_latest(model_name)` method that loads the most recent version. Update `run_demo.py` to save models after training. Update the risk-scoring API to load models from the registry on startup. Add a `/api/v1/models` endpoint that returns the current model versions and their metrics.

### 3.2 Hyperparameter Tuning Pipeline

**Current State**: All model hyperparameters are hardcoded.

**Prompt**:
> Add an automated hyperparameter tuning pipeline using `optuna`. Create `detection-models/tuning/tune_all.py` that runs Bayesian optimization for each model. For `RoundTripDetector` (XGBoost): tune `n_estimators` (50-500), `max_depth` (3-8), `learning_rate` (0.01-0.3), `scale_pos_weight` (5-50). For `StructuringDetector` (IsolationForest): tune `n_estimators` (50-300), `contamination` (0.001-0.05). For `DormantActivationDetector` (OneClassSVM): tune `kernel` (rbf/poly), `nu` (0.01-0.1), `gamma` (scale/auto/float). For `ProfileMismatchDetector` (LightGBM): tune `n_estimators`, `learning_rate`, `num_leaves`, `min_child_samples`. Use PR-AUC as the optimization objective with 3-fold cross-validation. Save the best parameters to `tuning_results.json` and auto-update model constructors.

### 3.3 Ensemble Scoring with Calibration

**Current State**: Risk scorer uses raw model probabilities with fixed weights.

**Prompt**:
> Improve the `RiskScorer` in `risk-scoring/risk_scoring/scorer.py`. First, add probability calibration using `sklearn.calibration.CalibratedClassifierCV` (isotonic method) for each model before combining scores — currently raw model outputs may not be well-calibrated probabilities. Second, replace the fixed weight system (`0.35, 0.30, 0.15, 0.10, 0.10`) with an adaptive weighting scheme that adjusts weights based on each model's recent precision (from feedback data). Create a `WeightOptimizer` class that recalculates weights monthly from `feedback_store` TP/FP data per model. Third, add a stacking meta-learner option — train a logistic regression on the 5 model outputs + 3 context flags as features, using feedback labels as ground truth. Add A/B comparison logging so both scoring methods run in parallel and their accuracy can be compared.

### 3.4 Real-Time Feature Store

**Current State**: Features computed on-demand from raw data during training.

**Prompt**:
> Implement a feature store using Redis for real-time feature serving. Create `detection-models/feature_store/` with a `FeatureStore` class that precomputes and caches account-level features (velocity, dormancy, graph metrics) in Redis hashes keyed by `account_id`. Add a `FeatureStore.refresh(account_id)` method that recomputes features when new transactions arrive. The risk-scoring API should fetch precomputed features from Redis instead of computing them on each request. Add a background worker (using `celery` or `asyncio`) that refreshes features every 15 minutes for accounts with recent activity. Store feature metadata (feature name, computation timestamp, staleness threshold) alongside values.

---

## 4. Dashboard & UX

### 4.1 Real-Time Alert Updates via WebSocket

**Current State**: Dashboard fetches alerts once on load; no live updates.

**Prompt**:
> Add WebSocket support for real-time alert streaming. In the risk-scoring API, add a `/ws/alerts` WebSocket endpoint using FastAPI's `WebSocket` class that pushes new alerts as they're scored. On the React side, create a `useAlertStream` custom hook in `dashboard/src/hooks/useAlertStream.ts` that connects to the WebSocket, receives new alert JSON messages, and merges them into the existing `alerts` state with a visual "new alert" animation (slide-in from top with a subtle glow). Add a reconnection strategy with exponential backoff (1s, 2s, 4s, max 30s). Show a connection status indicator in the top bar (green dot = connected, yellow = reconnecting, red = disconnected). Add a notification sound option (toggle in settings) for CRITICAL alerts.

### 4.2 Advanced Graph Visualization

**Current State**: Basic Cytoscape.js graph with static layout.

**Prompt**:
> Enhance the `GraphView` component in `dashboard/src/components/GraphView.tsx`. Add these features: (1) Edge thickness proportional to transaction amount (log scale). (2) Node color coding: green for normal accounts, orange for accounts with 1 suspicious flag, red for accounts in multiple suspicious patterns. (3) Time-slider control that filters edges by timestamp range, allowing investigators to "replay" the flow chronologically. (4) Cluster highlighting — when an alert is selected, highlight its specific account chain with pulsing edges and dim unrelated nodes to 30% opacity. (5) Right-click context menu on nodes with options: "View Account Details", "Trace Upstream (2 hops)", "Trace Downstream (2 hops)", "Add to Investigation". (6) Minimap in the bottom-right corner for large graphs. (7) Export graph as PNG/SVG button. Use Cytoscape.js extensions `cytoscape-context-menus` and `cytoscape-navigator`.

### 4.3 Investigation Workspace

**Current State**: Single-alert view only; no multi-alert investigation support.

**Prompt**:
> Add an Investigation Workspace feature to the dashboard. Create a new `InvestigationPanel` component that allows investigators to: (1) Group related alerts into a "Case" by dragging them from the alert queue into a case panel. (2) Add free-text notes per case with timestamps and investigator ID. (3) Link external evidence (document uploads stored as base64 in localStorage or a backend endpoint). (4) Track case status: OPEN → IN_PROGRESS → PENDING_REVIEW → CLOSED. (5) View a unified graph that merges the subgraphs of all alerts in the case, highlighting shared accounts/entities across alerts. Add a `cases` state in App.tsx managed by `useReducer`. Add a `/api/v1/cases` CRUD endpoint to the feedback API with persistence in the feedback store. Add a case summary export as PDF using `jspdf`.

### 4.4 Dark Mode & Accessibility

**Current State**: Light theme only, no accessibility features.

**Prompt**:
> Add dark mode and WCAG 2.1 AA accessibility to the dashboard. Create a `ThemeProvider` context in `dashboard/src/contexts/ThemeContext.tsx` with light/dark theme objects defining colors, backgrounds, borders, and shadows. Add a toggle button in the top bar. Persist preference in localStorage. For dark mode: background `#0f172a`, card background `#1e293b`, text `#e2e8f0`, borders `#334155`. For accessibility: add `aria-label` to all interactive elements, ensure minimum 4.5:1 contrast ratio, add keyboard navigation (Tab/Enter/Escape) for the alert list and graph nodes, add screen reader announcements for alert selections and disposition submissions using `aria-live` regions. Add focus-visible outlines. Test with the axe-core browser extension.

---

## 5. DevOps & CI/CD

### 5.1 GitHub Actions CI Pipeline

**Prompt**:
> Create `.github/workflows/ci.yml` with these jobs: (1) `lint` — run `ruff check` on all Python modules and `eslint` on dashboard TypeScript. (2) `test-backend` — run pytest for data-generator (23 tests), graph-engine (7 tests), detection-models (7 tests), risk-scoring (3 tests), and feedback (14 tests) in parallel using a matrix strategy. (3) `test-frontend` — run `tsc --noEmit` and `npx vite build` for the dashboard. (4) `security-scan` — run `pip-audit` on all Python dependencies and `npm audit` on dashboard dependencies. (5) `docker-build` — build Docker images for each service and verify they start. Use Python 3.13 and Node 20. Cache pip and npm dependencies. Run on push to `main` and on all pull requests. Add branch protection rules requiring all checks to pass.

### 5.2 Dockerize All Services

**Current State**: Only infrastructure (Neo4j, PostgreSQL, Redis) is dockerized.

**Prompt**:
> Create Dockerfiles for each service and update `docker-compose.yml` to run the full stack. Create `risk-scoring/Dockerfile` (Python 3.13-slim, install from pyproject.toml, run uvicorn on port 8000). Create `feedback/Dockerfile` (same pattern, port 8001). Create `dashboard/dashboard/Dockerfile` (Node 20 build stage → nginx serve stage, port 3000). Create `data-generator/Dockerfile` for one-shot data generation. Add all services to `docker-compose.yml` with proper `depends_on` (risk-scoring depends on neo4j; feedback depends on postgres and redis; dashboard depends on risk-scoring and feedback). Add health checks for each service. Add a `docker-compose.override.yml` for development with volume mounts for hot-reload. Create a `Makefile` with targets: `make up`, `make down`, `make test`, `make generate-data`.

### 5.3 Database Migrations with Alembic

**Prompt**:
> Set up Alembic database migrations for the feedback service's PostgreSQL schema. Run `alembic init feedback/migrations`. Configure `alembic.ini` to read the database URL from the `POSTGRES_*` environment variables. Create the initial migration with tables: `dispositions`, `retrain_events`, `baseline_features`, and `investigators`. Add a `feedback/migrations/seed.py` script that imports existing data from `feedback_store.json` into PostgreSQL. Add migration commands to the Makefile (`make migrate`, `make migrate-rollback`). Document the migration workflow in README.md.

---

## 6. Compliance & Reporting

### 6.1 STR Report Generator (FIU-IND Format)

**Current State**: STR filing is just a UI button with a notification — no actual report generated.

**Prompt**:
> Implement a full STR (Suspicious Transaction Report) generator compliant with FIU-IND format. Create `risk-scoring/risk_scoring/str_generator.py` with a `STRReportGenerator` class that produces reports containing: Part A (reporting entity details — configurable via env vars), Part B (suspect details — pulled from account data), Part C (suspicious transaction details — from alert data), Part D (reason for suspicion — from evidence narrative). Generate output in both PDF (using `reportlab`) and XML (FIU-IND schema) formats. Add a `/api/v1/str/generate/{cluster_id}` POST endpoint that creates the report and returns a download URL. Store generated STRs in a `str_reports/` directory with filenames like `STR-2026-04-22-CLU001.pdf`. Add a STR history table in the feedback database. Update the dashboard's "File STR" button to call this endpoint and open the PDF in a new tab.

### 6.2 Audit Trail & Compliance Logging

**Prompt**:
> Implement a comprehensive audit trail system. Create `shared/audit_logger.py` with an `AuditLogger` class that logs every significant action to a dedicated `audit_log` PostgreSQL table with fields: timestamp, actor_id, action_type (ALERT_VIEWED, DISPOSITION_SUBMITTED, STR_FILED, RETRAIN_TRIGGERED, MODEL_UPDATED), resource_id, resource_type, details (JSONB), ip_address, user_agent. Add middleware to both APIs that automatically logs all write operations. Add a `/api/v1/audit/log` GET endpoint (ADMIN only) with filtering by date range, actor, and action type. Add an "Audit Trail" tab to the dashboard that shows a chronological feed of all actions. Ensure audit logs are append-only (no UPDATE/DELETE permissions on the table).

### 6.3 Scheduled Compliance Reports

**Prompt**:
> Add automated compliance report generation. Create `risk-scoring/risk_scoring/reports.py` with functions to generate: (1) Daily Alert Summary — total alerts by risk level, disposition breakdown, average response time. (2) Weekly Model Performance — precision/recall per model, FP rate trend, drift status. (3) Monthly Compliance Report — total STRs filed, alert-to-STR conversion rate, top typologies, investigator workload distribution. Use `matplotlib` for charts embedded in the reports. Generate PDF output using `reportlab`. Add a `celery` beat schedule to auto-generate reports. Add a `/api/v1/reports` endpoint to list and download past reports. Email reports to configured recipients using `smtplib`.

---

## 7. Data Pipeline

### 7.1 Real-Time Transaction Ingestion with Kafka

**Current State**: Batch processing from static JSON files only.

**Prompt**:
> Add Apache Kafka for real-time transaction ingestion. Add `kafka` (KRaft mode, no Zookeeper) to `docker-compose.yml`. Create `data-generator/streaming/kafka_producer.py` that generates transactions in real-time (configurable rate, e.g., 100 txns/second) and publishes to a `transactions` topic. Create `risk-scoring/consumers/transaction_consumer.py` that consumes from Kafka, runs the scoring pipeline on each transaction batch (micro-batch every 5 seconds), and pushes scored alerts to a `scored_alerts` topic. Create `graph-engine/consumers/graph_consumer.py` that consumes transactions and updates Neo4j in real-time. Use `confluent-kafka` Python client. Add consumer group management so multiple instances can scale horizontally. Add a Kafka health check to the API health endpoints.

### 7.2 Data Quality Validation

**Prompt**:
> Add data quality validation to the data ingestion pipeline. Create `data-generator/validation/schema_validator.py` using `pydantic` models that validate every generated transaction and account against the canonical schema before writing to output. Check: amount_value > 0, valid ISO-8601 timestamps, sender != receiver (except cash ops), valid currency codes, referential integrity (all account_ids in transactions exist in accounts). Create a `DataQualityReport` that summarizes: total records, valid records, invalid records with failure reasons, data completeness percentage per field. Add a `--validate` flag to the data generator CLI. Add a `/api/v1/data/quality` endpoint that returns the latest validation report.

### 7.3 Historical Data Archival

**Prompt**:
> Implement data archival for old transactions and resolved alerts. Create `shared/archival.py` with an `ArchivalManager` class that: (1) Moves transactions older than 90 days from the active `transactions.json` to compressed archives (`archive/transactions_2026_Q1.json.gz`). (2) Moves disposed alerts older than 30 days from active storage to an `archived_alerts` PostgreSQL table. (3) Maintains a summary index of archived data for compliance queries. Add a `celery` periodic task that runs archival nightly. Add a `/api/v1/archive/search` endpoint that queries both active and archived data. Ensure archived data is immutable (write-once, read-many).

---

## 8. Monitoring & Observability

### 8.1 Structured Logging with Correlation IDs

**Current State**: Basic `print()` statements for logging.

**Prompt**:
> Replace all `print()` statements across the codebase with structured JSON logging. Create `shared/logging_config.py` that configures Python's `logging` module with a JSON formatter outputting: timestamp, level, service_name, correlation_id, message, and extra fields. Add correlation ID middleware to both APIs — generate a UUID for each request, attach it to all log entries, and return it in the `X-Correlation-ID` response header. The dashboard should capture and display correlation IDs when API errors occur. Configure log levels via environment variable (`LOG_LEVEL=INFO`). Add log rotation (10MB per file, 5 backups). In production, these logs can be shipped to ELK stack or CloudWatch.

### 8.2 Prometheus Metrics & Grafana Dashboard

**Prompt**:
> Add Prometheus metrics collection to both APIs. Install `prometheus-fastapi-instrumentator` and add it to both FastAPI apps. Expose `/metrics` endpoint on each service. Add custom metrics: `alerts_scored_total` (counter), `alert_score_histogram` (histogram of risk scores), `disposition_total` (counter by type), `model_inference_duration_seconds` (histogram), `feedback_store_size` (gauge), `drift_psi_value` (gauge per feature). Add Prometheus and Grafana services to `docker-compose.yml`. Create a `monitoring/grafana/dashboards/fundflow.json` pre-provisioned dashboard with panels: Alert volume over time, Risk score distribution, Disposition breakdown pie chart, Model inference latency p50/p95/p99, Drift PSI trend, API error rate.

### 8.3 Alerting & On-Call Integration

**Prompt**:
> Add operational alerting for system health issues. Create `monitoring/alerting/rules.yml` with Prometheus alerting rules: (1) `HighErrorRate` — API 5xx rate > 5% for 5 minutes. (2) `SlowInference` — Model inference p95 > 2 seconds. (3) `DriftDetected` — PSI value > 0.25 on any feature. (4) `FeedbackStoreGrowing` — Store size > 10,000 unprocessed records. (5) `ServiceDown` — Any health check failing for 2 minutes. Add Alertmanager to `docker-compose.yml` configured to send alerts via webhook (Slack/Teams integration). Create a `monitoring/alertmanager/config.yml` with routing rules — critical alerts go to `#fundflow-critical` channel, warnings go to `#fundflow-ops`. Add a `/api/v1/system/status` endpoint that returns aggregate health of all services.

---

## Priority Matrix

| Priority | Item | Impact | Effort |
|----------|------|--------|--------|
| 🔴 P0 | 2.1 PostgreSQL Migration | Critical for production | 3-4 hrs |
| 🔴 P0 | 1.1 JWT Authentication | Security requirement | 4-5 hrs |
| 🔴 P0 | 5.2 Dockerize All Services | Deployment blocker | 3-4 hrs |
| 🟠 P1 | 5.1 CI/CD Pipeline | Dev velocity | 2-3 hrs |
| 🟠 P1 | 1.2 Rate Limiting | Security hardening | 1-2 hrs |
| 🟠 P1 | 4.2 Advanced Graph Viz | Investigator productivity | 4-6 hrs |
| 🟠 P1 | 8.1 Structured Logging | Debuggability | 2-3 hrs |
| 🟡 P2 | 6.1 STR Report Generator | Compliance requirement | 4-5 hrs |
| 🟡 P2 | 3.1 Model Versioning | ML ops maturity | 3-4 hrs |
| 🟡 P2 | 4.1 WebSocket Alerts | UX improvement | 3-4 hrs |
| 🟡 P2 | 2.2 Event-Driven Architecture | Scalability | 5-6 hrs |
| 🟢 P3 | 3.2 Hyperparameter Tuning | Model accuracy | 3-4 hrs |
| 🟢 P3 | 4.3 Investigation Workspace | Advanced UX | 6-8 hrs |
| 🟢 P3 | 7.1 Kafka Ingestion | Real-time processing | 6-8 hrs |
| 🟢 P3 | 8.2 Prometheus + Grafana | Observability | 3-4 hrs |
