// ─── Core domain types ───────────────────────────────────────────────────────

export interface Alert {
  cluster_id: string;
  pattern_type?: string;
  account_id?: string;
  risk_score: number;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  created_at: string;
  model_probs: ModelProbs;
  context_flags: ContextFlags;
  evidence_narrative: string[];
  raw?: {
    total_amount?: number;
    transaction_ids?: string[];
  };
}

export interface ModelProbs {
  layering_gnn: number;
  round_tripping_xgb: number;
  structuring_iforest: number;
  dormant_activation_svm: number;
  profile_mismatch_lgbm: number;
}

export interface ContextFlags {
  is_pep?: boolean;
  high_risk_jurisdiction?: boolean;
  rapid_pass_through?: boolean;
}

export interface AccountNode {
  account_id: string;
  entity_id: string;
  entity_name: string;
  account_type: string;
  status: string;
  occupation: string;
  annual_income: number;
  avg_balance_30d: number;
  kyc_status: string;
  branch_code: string;
  open_date: string;
  pep_flag: boolean;
}

export interface TransferEdge {
  source: string;
  target: string;
  amount: number;
  timestamp: string;
  channel: string;
  purpose_code: string;
  is_suspicious: boolean;
  suspicious_pattern: string | null;
}

export interface GraphData {
  center: string;
  depth: number;
  nodes: string[];
  edges: TransferEdge[];
}

export interface ScoringRequest {
  cluster_id: string;
  model_probabilities: ModelProbs;
  context_flags: ContextFlags;
}

export interface ScoringResponse {
  cluster_id: string;
  risk_score: number;
  risk_level: string;
  evidence_narrative: string[];
}
