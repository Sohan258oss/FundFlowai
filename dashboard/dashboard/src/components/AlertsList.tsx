import type { Alert } from "../types";

interface Props {
  alerts: Alert[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

const levelColors: Record<string, string> = {
  CRITICAL: "#dc2626",
  HIGH: "#ea580c",
  MEDIUM: "#d97706",
  LOW: "#16a34a",
};

const levelBg: Record<string, string> = {
  CRITICAL: "#fef2f2",
  HIGH: "#fff7ed",
  MEDIUM: "#fffbeb",
  LOW: "#f0fdf4",
};

export default function AlertsList({ alerts, selectedId, onSelect }: Props) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {alerts.map((alert) => (
        <div
          key={alert.cluster_id}
          onClick={() => onSelect(alert.cluster_id)}
          style={{
            padding: "12px 14px",
            borderRadius: 8,
            border: `2px solid ${selectedId === alert.cluster_id ? levelColors[alert.risk_level] : "#e5e7eb"}`,
            background: selectedId === alert.cluster_id ? levelBg[alert.risk_level] : "#fff",
            cursor: "pointer",
            transition: "all 0.15s",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: "#1e2761", fontFamily: "monospace" }}>
              {alert.cluster_id}
            </span>
            <span
              style={{
                fontSize: 11,
                fontWeight: 700,
                color: levelColors[alert.risk_level],
                background: levelBg[alert.risk_level],
                border: `1px solid ${levelColors[alert.risk_level]}`,
                borderRadius: 4,
                padding: "2px 7px",
              }}
            >
              {alert.risk_level}
            </span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6, alignItems: "center" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <div
                style={{
                  width: 90,
                  height: 6,
                  borderRadius: 3,
                  background: "#e5e7eb",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${alert.risk_score}%`,
                    height: "100%",
                    background: levelColors[alert.risk_level],
                    borderRadius: 3,
                  }}
                />
              </div>
              <span style={{ fontSize: 13, fontWeight: 700, color: levelColors[alert.risk_level] }}>
                {alert.risk_score}/100
              </span>
            </div>
            <span style={{ fontSize: 11, color: "#9ca3af" }}>
              {new Date(alert.created_at).toLocaleTimeString()}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
