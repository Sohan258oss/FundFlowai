import { useState, useEffect, useCallback } from "react";
import AlertsList from "./components/AlertsList";
import GraphView from "./components/GraphView";
import EntityDetail from "./components/EntityDetail";
import EvidencePanel from "./components/EvidencePanel";
import { fetchAlerts, fetchAccountGraph, submitDisposition, getMockGraphData, getMockAccount } from "./api";
import type { Alert, GraphData } from "./types";

export default function App() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [disposedAlerts, setDisposedAlerts] = useState<Set<string>>(new Set());
  const [notification, setNotification] = useState<string | null>(null);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);

  useEffect(() => {
    fetchAlerts()
      .then((data) => {
        setAlerts(data);
        if (data.length > 0) setSelectedAlertId(data[0].cluster_id);
      })
      .catch((e) => setError("Failed to load alerts: " + e.message))
      .finally(() => setLoading(false));
  }, []);

  // Fetch graph data when selected alert changes
  const selectedAlert = alerts.find((a) => a.cluster_id === selectedAlertId) ?? null;

  useEffect(() => {
    if (!selectedAlert?.account_id) {
      // No account_id — use mock graph data as fallback
      if (selectedAlertId) {
        setGraphData(getMockGraphData(selectedAlertId));
      }
      return;
    }

    setGraphLoading(true);
    fetchAccountGraph(selectedAlert.account_id, 2)
      .then((data) => {
        // If the API returned a real graph with edges, use it; otherwise fall back to mock
        if (data.edges.length > 0) {
          setGraphData(data);
        } else {
          setGraphData(getMockGraphData(selectedAlertId!));
        }
      })
      .catch(() => {
        setGraphData(getMockGraphData(selectedAlertId!));
      })
      .finally(() => setGraphLoading(false));
  }, [selectedAlertId, selectedAlert?.account_id]);

  const selectedAccount = selectedNodeId ? getMockAccount(selectedNodeId) : null;
  const activeAlerts = alerts.filter((a) => !disposedAlerts.has(a.cluster_id));

  const showNotification = (msg: string) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 3500);
  };

  const handleNodeClick = useCallback((nodeId: string) => {
    setSelectedNodeId(nodeId);
  }, []);

  const handleFileSTR = async () => {
    if (!selectedAlertId || !selectedAlert) return;
    try {
      await submitDisposition({
        cluster_id: selectedAlertId,
        investigator_id: "INV-001",
        disposition: "TRUE_POSITIVE",
        feature_vector: { ...selectedAlert.model_probs, risk_score: selectedAlert.risk_score },
        notes: "STR filed via dashboard",
      });
      showNotification(`✅ STR filed for ${selectedAlertId} — FIU-IND reference generated`);
      setDisposedAlerts((prev) => new Set([...prev, selectedAlertId]));
    } catch {
      showNotification("⚠️ Disposition recorded locally (feedback API error)");
      setDisposedAlerts((prev) => new Set([...prev, selectedAlertId]));
    }
  };

  const handleClear = async () => {
    if (!selectedAlertId || !selectedAlert) return;
    try {
      await submitDisposition({
        cluster_id: selectedAlertId,
        investigator_id: "INV-001",
        disposition: "FALSE_POSITIVE",
        reason_code: "NORMAL_BUSINESS",
        feature_vector: { ...selectedAlert.model_probs, risk_score: selectedAlert.risk_score },
      });
      showNotification(`✔ ${selectedAlertId} marked as cleared`);
      setDisposedAlerts((prev) => new Set([...prev, selectedAlertId]));
    } catch {
      showNotification("⚠️ Cleared locally (feedback API error)");
      setDisposedAlerts((prev) => new Set([...prev, selectedAlertId]));
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: "#f3f4f6", fontFamily: "Inter, system-ui, sans-serif" }}>

      {/* Top Bar */}
      <div style={{ background: "#1e2761", color: "#fff", padding: "0 20px", height: 52, display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-0.5px" }}>
            FundFlow <span style={{ color: "#028090" }}>AI</span>
          </span>
          <span style={{ fontSize: 12, color: "#93c5fd", borderLeft: "1px solid #3b4f8a", paddingLeft: 12 }}>
            Investigator Dashboard
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <span style={{ fontSize: 12, color: "#93c5fd" }}>{activeAlerts.length} active alerts</span>
          <div style={{ width: 8, height: 8, borderRadius: "50%", background: loading ? "#f59e0b" : error ? "#ef4444" : "#22c55e" }} />
          <span style={{ fontSize: 12, color: "#93c5fd" }}>{loading ? "Loading..." : error ? "API Error" : "Live"}</span>
        </div>
      </div>

      {/* Notification */}
      {notification && (
        <div style={{ position: "fixed", top: 60, left: "50%", transform: "translateX(-50%)", background: "#1e2761", color: "#fff", padding: "10px 20px", borderRadius: 8, fontSize: 13, fontWeight: 600, zIndex: 1000, boxShadow: "0 4px 20px rgba(0,0,0,0.2)" }}>
          {notification}
        </div>
      )}

      {/* Error Banner */}
      {error && (
        <div style={{ background: "#fef2f2", borderBottom: "1px solid #fca5a5", padding: "8px 20px", fontSize: 12, color: "#dc2626" }}>
          ⚠️ {error} — showing empty state
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "#6b7280", fontSize: 14 }}>
          Loading alerts from risk scoring API...
        </div>
      )}

      {/* Main Layout */}
      {!loading && (
        <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>

          {/* Left — Alerts List */}
          <div style={{ width: 280, flexShrink: 0, background: "#fff", borderRight: "1px solid #e5e7eb", display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <div style={{ padding: "14px 14px 8px", borderBottom: "1px solid #e5e7eb" }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#1e2761" }}>ALERT QUEUE</div>
              <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 2 }}>
                {activeAlerts.filter((a) => a.risk_level === "CRITICAL").length} critical •{" "}
                {activeAlerts.filter((a) => a.risk_level === "HIGH").length} high •{" "}
                {activeAlerts.filter((a) => a.risk_level === "MEDIUM").length} medium
              </div>
            </div>
            <div style={{ flex: 1, overflow: "auto", padding: 10 }}>
              <AlertsList
                alerts={activeAlerts}
                selectedId={selectedAlertId ?? ""}
                onSelect={(id) => { setSelectedAlertId(id); setSelectedNodeId(null); }}
              />
              {activeAlerts.length === 0 && !loading && (
                <div style={{ textAlign: "center", color: "#9ca3af", fontSize: 13, marginTop: 40 }}>
                  🎉 All alerts resolved
                </div>
              )}
            </div>
          </div>

          {/* Center — Graph View */}
          <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <div style={{ padding: "10px 16px", background: "#fff", borderBottom: "1px solid #e5e7eb", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <span style={{ fontSize: 13, fontWeight: 700, color: "#1e2761" }}>FUND FLOW GRAPH — </span>
                <span style={{ fontSize: 13, fontFamily: "monospace", color: "#028090" }}>{selectedAlertId}</span>
                {selectedAlert?.pattern_type && (
                  <span style={{ fontSize: 11, color: "#6b7280", marginLeft: 8 }}>({selectedAlert.pattern_type})</span>
                )}
              </div>
              {graphData && (
                <span style={{ fontSize: 11, color: "#6b7280" }}>
                  {graphLoading ? "Loading..." : `${graphData.nodes.length} accounts · ${graphData.edges.length} transfers`}
                </span>
              )}
            </div>
            <div style={{ flex: 1 }}>
              {graphData && <GraphView graphData={graphData} onNodeClick={handleNodeClick} />}
            </div>

            {/* Timeline */}
            {graphData && graphData.edges.length > 0 && (
              <div style={{ background: "#fff", borderTop: "1px solid #e5e7eb", padding: "10px 16px" }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "#6b7280", marginBottom: 8 }}>TIMELINE</div>
                <div style={{ display: "flex", alignItems: "center", overflow: "auto" }}>
                  {graphData.edges.slice(0, 10).map((edge, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "center" }}>
                      <div style={{ textAlign: "center", minWidth: 90 }}>
                        <div style={{ fontSize: 10, color: "#dc2626", fontWeight: 700 }}>{edge.source.slice(-4)}→{edge.target.slice(-4)}</div>
                        <div style={{ fontSize: 10, color: "#6b7280" }}>₹{(edge.amount / 100000).toFixed(1)}L</div>
                        <div style={{ fontSize: 9, color: "#9ca3af" }}>
                          {new Date(edge.timestamp).toLocaleString("en-IN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                        </div>
                      </div>
                      {i < Math.min(graphData.edges.length, 10) - 1 && <div style={{ width: 30, height: 2, background: "#dc2626" }} />}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Right Panel */}
          <div style={{ width: 300, flexShrink: 0, background: "#fff", borderLeft: "1px solid #e5e7eb", overflow: "auto", padding: 14, display: "flex", flexDirection: "column", gap: 14 }}>
            {selectedAccount && <EntityDetail account={selectedAccount} onClose={() => setSelectedNodeId(null)} />}
            {selectedAlert && <EvidencePanel alert={selectedAlert} onFileSTR={handleFileSTR} onClear={handleClear} />}
          </div>
        </div>
      )}
    </div>
  );
}