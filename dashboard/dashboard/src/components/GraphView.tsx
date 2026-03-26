import { useEffect, useRef } from "react";
import cytoscape from "cytoscape";
import type { GraphData } from "../types";

interface Props {
  graphData: GraphData;
  onNodeClick: (nodeId: string) => void;
}

export default function GraphView({ graphData, onNodeClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Build elements
    const elements: cytoscape.ElementDefinition[] = [];

    // Add nodes
    graphData.nodes.forEach((nodeId) => {
      elements.push({
        data: { id: nodeId, label: nodeId.slice(-6) },
      });
    });

    // Add edges
    graphData.edges.forEach((edge, i) => {
      const amountLabel = `₹${(edge.amount / 100000).toFixed(1)}L`;
      elements.push({
        data: {
          id: `edge-${i}`,
          source: edge.source,
          target: edge.target,
          label: amountLabel,
          isSuspicious: edge.is_suspicious,
          amount: edge.amount,
          timestamp: edge.timestamp,
          channel: edge.channel,
        },
      });
    });

    // Destroy previous instance
    if (cyRef.current) cyRef.current.destroy();

    cyRef.current = cytoscape({
      container: containerRef.current,
      elements,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "#1e2761",
            "border-color": "#028090",
            "border-width": 2,
            label: "data(label)",
            color: "#fff",
            "font-size": 10,
            "text-valign": "center",
            "text-halign": "center",
            width: 50,
            height: 50,
            "font-weight": "bold",
          },
        },
        {
          selector: `node[id = "${graphData.nodes[graphData.nodes.length - 1]}"]`,
          style: {
            "background-color": "#7c3aed",
            "border-color": "#a78bfa",
            "border-width": 3,
          },
        },
        {
          selector: `node[id = "${graphData.center}"]`,
          style: {
            "background-color": "#dc2626",
            "border-color": "#fca5a5",
            "border-width": 3,
            width: 60,
            height: 60,
          },
        },
        {
          selector: "edge",
          style: {
            width: 3,
            "line-color": "#dc2626",
            "target-arrow-color": "#dc2626",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(label)",
            "font-size": 9,
            color: "#dc2626",
            "text-background-color": "#fff",
            "text-background-opacity": 0.8,
            "text-background-padding": "2px",
            "font-weight": "bold",
          },
        },
        {
          selector: "edge[isSuspicious = false]",
          style: {
            "line-color": "#9ca3af",
            "target-arrow-color": "#9ca3af",
            color: "#6b7280",
          },
        },
        {
          selector: "node:selected",
          style: {
            "border-color": "#fbbf24",
            "border-width": 4,
          },
        },
      ],
      layout: {
        name: "breadthfirst",
        directed: true,
        spacingFactor: 1.5,
        padding: 30,
      },
    });

    // Node click handler
    cyRef.current.on("tap", "node", (evt) => {
      onNodeClick(evt.target.id());
    });

    return () => {
      if (cyRef.current) cyRef.current.destroy();
    };
  }, [graphData, onNodeClick]);

  return (
    <div style={{ width: "100%", height: "100%", position: "relative" }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
      <div
        style={{
          position: "absolute",
          bottom: 10,
          left: 10,
          background: "rgba(255,255,255,0.9)",
          padding: "6px 10px",
          borderRadius: 6,
          fontSize: 11,
          color: "#374151",
          border: "1px solid #e5e7eb",
        }}
      >
        <span style={{ color: "#dc2626", fontWeight: 700 }}>● </span>Originator &nbsp;
        <span style={{ color: "#7c3aed", fontWeight: 700 }}>● </span>Final &nbsp;
        <span style={{ color: "#1e2761", fontWeight: 700 }}>● </span>Intermediary &nbsp;
        <span style={{ color: "#dc2626" }}>— </span>Suspicious Flow
      </div>
    </div>
  );
}
