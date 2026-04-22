import React from "react";

interface Props {
  account: any;
  onClose: () => void;
}

export default function EntityDetail({ account, onClose }: Props) {
  const kycColor = account.kyc_status === "VERIFIED" ? "#16a34a" : "#dc2626";
  const statusColor = account.status === "ACTIVE" ? "#16a34a" : account.status === "DORMANT" ? "#d97706" : "#6b7280";

  return (
    <div
      style={{
        background: "#fff",
        border: "1px solid #e5e7eb",
        borderRadius: 10,
        padding: 16,
        fontSize: 13,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12 }}>
        <span style={{ fontWeight: 700, color: "#1e2761", fontSize: 14 }}>Entity Detail</span>
        <button
          onClick={onClose}
          style={{ background: "none", border: "none", cursor: "pointer", color: "#6b7280", fontSize: 16 }}
        >
          ✕
        </button>
      </div>

      <Row label="Account ID" value={account.account_id} mono />
      <Row label="Name" value={account.entity_name} />
      <Row label="Type" value={account.account_type} />
      <Row
        label="Status"
        value={account.status}
        valueStyle={{ color: statusColor, fontWeight: 700 }}
      />
      <Row label="Occupation" value={account.occupation?.replace(/_/g, " ")} />
      <Row label="Annual Income" value={`₹${Number(account.annual_income).toLocaleString("en-IN")}`} />
      <Row label="Avg Balance" value={`₹${Number(account.avg_balance_30d).toLocaleString("en-IN")}`} />
      <Row label="Branch" value={account.branch_code} mono />
      <Row label="Opened" value={account.open_date?.slice(0, 10)} />
      <Row
        label="KYC"
        value={account.kyc_status}
        valueStyle={{ color: kycColor, fontWeight: 700 }}
      />
      <Row
        label="PEP Flag"
        value={account.pep_flag ? "⚠️ YES" : "No"}
        valueStyle={{ color: account.pep_flag ? "#dc2626" : "#16a34a", fontWeight: 700 }}
      />

      <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
        <button
          style={{
            flex: 1,
            padding: "7px 0",
            background: "#1e2761",
            color: "#fff",
            border: "none",
            borderRadius: 6,
            cursor: "pointer",
            fontSize: 12,
            fontWeight: 600,
          }}
        >
          View History
        </button>
        <button
          style={{
            flex: 1,
            padding: "7px 0",
            background: "#dc2626",
            color: "#fff",
            border: "none",
            borderRadius: 6,
            cursor: "pointer",
            fontSize: 12,
            fontWeight: 600,
          }}
        >
          Linked Alerts
        </button>
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  mono = false,
  valueStyle = {},
}: {
  label: string;
  value: string;
  mono?: boolean;
  valueStyle?: React.CSSProperties;
}) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        padding: "4px 0",
        borderBottom: "1px solid #f3f4f6",
      }}
    >
      <span style={{ color: "#6b7280", fontSize: 12 }}>{label}</span>
      <span
        style={{
          fontWeight: 500,
          fontSize: 12,
          fontFamily: mono ? "monospace" : "inherit",
          maxWidth: 160,
          textAlign: "right",
          ...valueStyle,
        }}
      >
        {value}
      </span>
    </div>
  );
}
