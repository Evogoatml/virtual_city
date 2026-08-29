"use client";

import { useEffect, useState } from "react";

type Action = {
  id: string;
  tool_name: string;
  status: string;
  args: any;
  reasoning?: string;
  created_at: string;
};

export default function ActionsPage() {
  const [rows, setRows] = useState<Action[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => {
    fetch("/api/actions")
      .then((r) => r.json())
      .then(setRows)
      .catch((e) => setErr(e.message));
  }, []);

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Audit Log</h1>
      {err && <div style={{ color: "#ff5470" }}>{err}</div>}
      <div className="card" style={{ padding: 0 }}>
        {rows.length === 0 && <div style={{ padding: "0.6rem", color: "#7c8aa3" }}>No actions yet.</div>}
        {rows.map((r) => (
          <div
            key={r.id}
            style={{
              display: "flex",
              justifyContent: "space-between",
              gap: "0.5rem",
              padding: "0.5rem 0.7rem",
              borderBottom: "1px solid #1a2030",
              fontSize: 12,
            }}
          >
            <div>
              <b>{r.tool_name}</b>
              <div style={{ color: "#7c8aa3" }}>{JSON.stringify(r.args).slice(0, 120)}</div>
            </div>
            <div style={{ textAlign: "right", whiteSpace: "nowrap" }}>
              <span style={{ color: statusColor(r.status) }}>{r.status}</span>
              <div style={{ color: "#7c8aa3", fontSize: 10 }}>{r.created_at?.slice(0, 19)}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function statusColor(s: string) {
  if (s === "executed") return "#39ff14";
  if (s === "pending") return "#ffb020";
  if (s === "rejected" || s === "rolled_back") return "#ff5470";
  return "#7c8aa3";
}
