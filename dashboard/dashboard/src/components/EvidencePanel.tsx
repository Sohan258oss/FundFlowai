import type { Alert } from "../types";

interface Props {
  alert: Alert;
  onFileSTR: () => void;
  onClear: () => void;
}

const modelLabels: Record<string, string> = {
  layering_gnn: "Layering (GraphSAGE GNN)",
  round_tripping_xgb: "Round-Tripping (XGBoost)",
  structuring_iforest: "Structuring (Isolation Forest)",
  dormant_activation_svm: "Dormant Activation (One-Class SVM)",
  profile_mismatch_lgbm: "Profile Mismatch (LightGBM)",
};

const levelColors: Record<string, string> = {
  CRITICAL: "#dc2626",
  HIGH: "#ea580c",
  MEDIUM: "#d97706",
  LOW: "#16a34a",
};

export default function EvidencePanel({ alert, onFileSTR, onClear }: Props) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>

      {/* Risk Score Header */}
      <div
        style={{
          background: levelColors[alert.risk_level],
          borderRadius: 10,
          padding: "14px 18px",
          color: "#fff",
        }}
      >
        <div style={{ fontSize: 12, opacity: 0.85, marginBottom: 4 }}>COMPOSITE RISK SCORE</div>
        <div style={{ fontSize: 42, fontWeight: 800, lineHeight: 1 }}>{alert.risk_score}</div>
        <div style={{ fontSize: 13, opacity: 0.9, marginTop: 4 }}>
          {alert.risk_level} — {alert.cluster_id}
        </div>
      </div>

      {/* Model Probabilities */}
      <div style={{ background: "#f9fafb", borderRadius: 8, padding: 14 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: "#1e2761", marginBottom: 10 }}>
          MODEL SIGNALS
        </div>
        {Object.entries(alert.model_probs).map(([model, prob]) => (
          <div key={model} style={{ marginBottom: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
              <span style={{ fontSize: 11, color: "#374151" }}>{modelLabels[model]}</span>
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  color: prob > 0.7 ? "#dc2626" : prob > 0.4 ? "#d97706" : "#16a34a",
                }}
              >
                {(prob * 100).toFixed(0)}%
              </span>
            </div>
            <div style={{ height: 5, background: "#e5e7eb", borderRadius: 3, overflow: "hidden" }}>
              <div
                style={{
                  width: `${prob * 100}%`,
                  height: "100%",
                  background: prob > 0.7 ? "#dc2626" : prob > 0.4 ? "#d97706" : "#16a34a",
                  borderRadius: 3,
                  transition: "width 0.4s ease",
                }}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Context Flags */}
      {Object.keys(alert.context_flags).length > 0 && (
        <div style={{ background: "#fef3c7", borderRadius: 8, padding: 12, border: "1px solid #fcd34d" }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: "#92400e", marginBottom: 6 }}>
            ⚠️ CONTEXT AMPLIFIERS
          </div>
          {alert.context_flags.is_pep && (
            <div style={{ fontSize: 12, color: "#92400e" }}>• Politically Exposed Person (2× multiplier)</div>
          )}
          {alert.context_flags.high_risk_jurisdiction && (
            <div style={{ fontSize: 12, color: "#92400e" }}>• High-Risk Jurisdiction (1.5× multiplier)</div>
          )}
          {alert.context_flags.rapid_pass_through && (
            <div style={{ fontSize: 12, color: "#92400e" }}>• Rapid Pass-Through Detected (1.3× multiplier)</div>
          )}
        </div>
      )}

      {/* Evidence Narrative */}
      <div style={{ background: "#f0f9ff", borderRadius: 8, padding: 14, border: "1px solid #bae6fd" }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: "#0369a1", marginBottom: 8 }}>
          EVIDENCE NARRATIVE
        </div>
        {alert.evidence_narrative.map((line, i) => (
          <div key={i} style={{ fontSize: 12, color: "#1e40af", marginBottom: 4, lineHeight: 1.5 }}>
            {line}
          </div>
        ))}
      </div>

      {/* Action Buttons */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <button
          onClick={() => {
            const text = [
              `CLUSTER RISK ASSESSMENT — ${alert.cluster_id}`,
              `Overall Score: ${alert.risk_score}/100 (${alert.risk_level})`,
              "",
              "MODEL PROBABILITIES:",
              ...Object.entries(alert.model_probs).map(
                ([m, p]) => `  ${modelLabels[m]}: ${(p * 100).toFixed(0)}%`
              ),
              "",
              "EVIDENCE:",
              ...alert.evidence_narrative,
              "",
              `Generated: ${new Date().toISOString()}`,
              "Regulatory reference: PMLA 2002 | FIU-IND STR Format",
            ].join("\n");

            const blob = new Blob([text], { type: "text/plain" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `evidence_${alert.cluster_id}.txt`;
            a.click();
          }}
          style={{
            padding: "10px",
            background: "#1e2761",
            color: "#fff",
            border: "none",
            borderRadius: 7,
            cursor: "pointer",
            fontWeight: 600,
            fontSize: 13,
          }}
        >
          📄 Generate Evidence Package
        </button>
        <button
          onClick={onFileSTR}
          style={{
            padding: "10px",
            background: "#dc2626",
            color: "#fff",
            border: "none",
            borderRadius: 7,
            cursor: "pointer",
            fontWeight: 600,
            fontSize: 13,
          }}
        >
          🚩 File STR
        </button>
        <button
          onClick={onClear}
          style={{
            padding: "10px",
            background: "#fff",
            color: "#16a34a",
            border: "2px solid #16a34a",
            borderRadius: 7,
            cursor: "pointer",
            fontWeight: 600,
            fontSize: 13,
          }}
        >
          ✓ Mark Cleared
        </button>
      </div>
    </div>
  );
}
