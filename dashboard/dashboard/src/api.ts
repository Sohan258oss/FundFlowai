import axios from "axios";
import type { ScoringRequest, ScoringResponse, GraphData } from "./types";

const riskApi = axios.create({ baseURL: "http://localhost:8000" });
const feedbackApi = axios.create({ baseURL: "http://localhost:8001" });

// ─── Risk Scoring API ──────────────────────────────────────────────────────

export async function fetchAlerts(limit = 50) {
  const { data } = await riskApi.get(`/api/v1/alerts?limit=${limit}`);
  return data.alerts as any[];
}

export async function scoreCluster(req: ScoringRequest): Promise<ScoringResponse> {
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

// ─── Graph API (real endpoint) ─────────────────────────────────────────────

export async function fetchAccountGraph(accountId: string, depth = 2): Promise<GraphData> {
  try {
    const { data } = await riskApi.get(`/api/v1/graph/${accountId}?depth=${depth}`);
    return data as GraphData;
  } catch {
    // Fallback to empty graph on error
    return { center: accountId, depth, nodes: [accountId], edges: [] };
  }
}

// ─── Feedback API ──────────────────────────────────────────────────────────

export async function submitDisposition(payload: {
  cluster_id: string;
  investigator_id: string;
  disposition: "TRUE_POSITIVE" | "FALSE_POSITIVE" | "INDETERMINATE" | "ESCALATED";
  reason_code?: string;
  feature_vector?: Record<string, number>;
  notes?: string;
}) {
  const { data } = await feedbackApi.post("/api/v1/feedback/disposition", payload);
  return data;
}

export async function fetchFeedbackStats() {
  const { data } = await feedbackApi.get("/api/v1/feedback/stats");
  return data;
}

export async function fetchReasonCodes(): Promise<string[]> {
  const { data } = await feedbackApi.get("/api/v1/feedback/reason-codes");
  return data.reason_codes;
}

// ─── Mock helpers (used as fallback when graph API has no data) ──────────

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
  };
  return accounts[accountId] || null;
}