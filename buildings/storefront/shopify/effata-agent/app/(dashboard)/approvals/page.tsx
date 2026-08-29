"use client";

import { useEffect, useState } from "react";

type Action = {
  id: string;
  tool_name: string;
  args: any;
  reasoning?: string;
  created_at: string;
};

export default function ApprovalsPage() {
  const [rows, setRows] = useState<Action[]>([]);
  const [err, setErr] = useState("");

  async function load() {
    const r = await fetch("/api/approvals");
    const data = await r.json();
    setRows(data);
  }

  useEffect(() => {
    load().catch((e) => setErr(e.message));
  }, []);

  async function act(id: string, action: string) {
    await fetch("/api/approvals/" + id, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    });
    load();
  }

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Approvals</h1>
      {err && <div style={{ color: "#ff5470" }}>{err}</div>}
      {rows.length === 0 && <div style={{ color: "#7c8aa3" }}>No pending approvals. 🎉</div>}
      {rows.map((r) => (
        <div key={r.id} className="card" style={{ marginBottom: "0.6rem" }}>
          <div style={{ fontWeight: 700 }}>{r.tool_name}</div>
          <div style={{ color: "#7c8aa3", fontSize: 12, margin: "0.3rem 0" }}>
            {JSON.stringify(r.args).slice(0, 200)}
          </div>
          <div style={{ display: "flex", gap: "0.4rem" }}>
            <button className="btn go" onClick={() => act(r.id, "approve")}>Approve</button>
            <button className="btn" onClick={() => act(r.id, "reject")}>Reject</button>
          </div>
        </div>
      ))}
    </div>
  );
}
