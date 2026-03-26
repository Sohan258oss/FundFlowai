import axios from "axios";
import type { ScoringRequest, ScoringResponse, GraphData } from "./types";

const riskApi = axios.create({ baseURL: "http://localhost:8000" });
const neo4jApi = axios.create({ baseURL: "http://localhost:8001" }); // graph proxy

// ─── Risk Scoring API ────────────────────────────────────────────────────────

export async function scoreCluster(
  req: ScoringRequest
): Promise<ScoringResponse> {
  const { data } = await riskApi.post("/api/v1/score", req);
  return data;
}

export async function healthCheck(): Promise<boolean> {
  try {
    await riskApi.get("/health");
    return true;
  } catch {
    return false;
  }
}

// ─── Mock data (used when APIs are not running) ──────────────────────────────

export function getMockAlerts() {
  return [
    {
      cluster_id: "CLU-2026-0321-A001",
      risk_score: 87,
      risk_level: "CRITICAL" as const,
      created_at: "2026-03-21T10:04:00",
      model_probs: {
        layering_gnn: 0.91,
        round_tripping_xgb: 0.22,
        structuring_iforest: 0.15,
        dormant_activation_svm: 0.78,
        profile_mismatch_lgbm: 0.65,
      },
      context_flags: { is_pep: false, high_risk_jurisdiction: true, rapid_pass_through: true },
      evidence_narrative: [
        "CRITICAL: Cluster flagged as HIGH risk (Score: 87/100).",
        "- Strong topological evidence of Layering (A→B→C chain detected via GraphSAGE).",
        "- Dormant Account Activation flagged (sudden massive outflow breaking historical norm).",
        "- Extreme Profile Mismatch: Transaction volumes drastically exceed expected baseline.",
        "- Counterparties are located in a High-Risk Jurisdiction (FATF grey list).",
        "- Rapid pass-through behavior detected (funds wired out within 24h of receipt).",
      ],
    },
    {
      cluster_id: "CLU-2026-0321-A002",
      risk_score: 72,
      risk_level: "HIGH" as const,
      created_at: "2026-03-21T11:22:00",
      model_probs: {
        layering_gnn: 0.74,
        round_tripping_xgb: 0.81,
        structuring_iforest: 0.12,
        dormant_activation_svm: 0.20,
        profile_mismatch_lgbm: 0.33,
      },
      context_flags: { is_pep: true, high_risk_jurisdiction: false, rapid_pass_through: false },
      evidence_narrative: [
        "- Strong topological evidence of Layering detected via GraphSAGE.",
        "- High probability of Round Tripping (circular flows returning to originator).",
        "- ALERT: Entity involves a Politically Exposed Person (PEP amplifier triggered).",
      ],
    },
    {
      cluster_id: "CLU-2026-0321-A003",
      risk_score: 54,
      risk_level: "MEDIUM" as const,
      created_at: "2026-03-21T13:45:00",
      model_probs: {
        layering_gnn: 0.21,
        round_tripping_xgb: 0.18,
        structuring_iforest: 0.82,
        dormant_activation_svm: 0.15,
        profile_mismatch_lgbm: 0.44,
      },
      context_flags: { is_pep: false, high_risk_jurisdiction: false, rapid_pass_through: false },
      evidence_narrative: [
        "- Anomalous structuring behavior detected (multiple sub-threshold deposits).",
        "- Extreme Profile Mismatch: Transaction volumes exceed expected baseline.",
      ],
    },
    {
      cluster_id: "CLU-2026-0321-A004",
      risk_score: 21,
      risk_level: "LOW" as const,
      created_at: "2026-03-21T14:10:00",
      model_probs: {
        layering_gnn: 0.08,
        round_tripping_xgb: 0.12,
        structuring_iforest: 0.19,
        dormant_activation_svm: 0.11,
        profile_mismatch_lgbm: 0.09,
      },
      context_flags: {},
      evidence_narrative: [
        "No distinctly suspicious topological or behavioral traits identified.",
      ],
    },
    {
      cluster_id: "CLU-2026-0321-A005",
      risk_score: 63,
      risk_level: "HIGH" as const,
      created_at: "2026-03-21T15:30:00",
      model_probs: {
        layering_gnn: 0.55,
        round_tripping_xgb: 0.29,
        structuring_iforest: 0.18,
        dormant_activation_svm: 0.71,
        profile_mismatch_lgbm: 0.58,
      },
      context_flags: { rapid_pass_through: true },
      evidence_narrative: [
        "- Strong topological evidence of Layering detected via GraphSAGE.",
        "- Dormant Account Activation flagged (sudden massive outflow).",
        "- Rapid pass-through behavior detected.",
      ],
    },
  ];
}

export function getMockGraphData(clusterId: string): GraphData {
  const nodes = ["ACC-A1B2C3", "ACC-D4E5F6", "ACC-G7H8I9", "ACC-J1K2L3", "ACC-M4N5O6"];
  return {
    center: nodes[0],
    depth: 4,
    nodes,
    edges: [
      { source: nodes[0], target: nodes[1], amount: 980000, timestamp: "2026-03-17T10:04:00", channel: "NEFT", purpose_code: "TRANSFER", is_suspicious: true, suspicious_pattern: "LAYERING" },
      { source: nodes[1], target: nodes[2], amount: 950000, timestamp: "2026-03-17T10:40:00", channel: "IMPS", purpose_code: "TRANSFER", is_suspicious: true, suspicious_pattern: "LAYERING" },
      { source: nodes[2], target: nodes[3], amount: 930000, timestamp: "2026-03-17T12:42:00", channel: "NEFT", purpose_code: "TRANSFER", is_suspicious: true, suspicious_pattern: "LAYERING" },
      { source: nodes[3], target: nodes[4], amount: 910000, timestamp: "2026-03-18T01:12:00", channel: "RTGS", purpose_code: "TRANSFER", is_suspicious: true, suspicious_pattern: "LAYERING" },
    ],
  };
}

export function getMockAccount(accountId: string) {
  const accounts: Record<string, any> = {
    "ACC-A1B2C3": { account_id: "ACC-A1B2C3", entity_name: "Rajesh Kumar", account_type: "CURRENT", status: "ACTIVE", occupation: "SELF_EMPLOYED_BUSINESS", annual_income: 1200000, avg_balance_30d: 450000, kyc_status: "VERIFIED", branch_code: "FUND00042", open_date: "2021-03-14", pep_flag: false },
    "ACC-D4E5F6": { account_id: "ACC-D4E5F6", entity_name: "Priya Enterprises Ltd", account_type: "CURRENT", status: "ACTIVE", occupation: "SELF_EMPLOYED_BUSINESS", annual_income: 5000000, avg_balance_30d: 800000, kyc_status: "VERIFIED", branch_code: "FUND00078", open_date: "2020-07-22", pep_flag: false },
    "ACC-G7H8I9": { account_id: "ACC-G7H8I9", entity_name: "Suresh Patel", account_type: "SAVINGS", status: "ACTIVE", occupation: "SALARIED_PRIVATE", annual_income: 600000, avg_balance_30d: 120000, kyc_status: "VERIFIED", branch_code: "FUND00015", open_date: "2019-11-05", pep_flag: false },
    "ACC-J1K2L3": { account_id: "ACC-J1K2L3", entity_name: "Meena Shah", account_type: "SAVINGS", status: "ACTIVE", occupation: "HOMEMAKER", annual_income: 0, avg_balance_30d: 50000, kyc_status: "VERIFIED", branch_code: "FUND00033", open_date: "2022-01-18", pep_flag: false },
    "ACC-M4N5O6": { account_id: "ACC-M4N5O6", entity_name: "Vikram Nair", account_type: "SAVINGS", status: "DORMANT", occupation: "RETIRED", annual_income: 300000, avg_balance_30d: 80000, kyc_status: "EXPIRED", branch_code: "FUND00091", open_date: "2018-06-30", pep_flag: false },
  };
  return accounts[accountId] || accounts["ACC-A1B2C3"];
}
