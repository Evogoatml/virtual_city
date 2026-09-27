export default function OverviewPage() {
  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Store Overview</h1>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))", gap: "0.8rem" }}>
        <div className="card">
          <div className="h">Agent</div>
          <div style={{ fontSize: 18, fontWeight: 700, color: "#39ff14" }}>Online</div>
          <div style={{ color: "#7c8aa3", fontSize: 11 }}>ReAct loop active</div>
        </div>
        <div className="card">
          <div className="h">Store</div>
          <div style={{ fontSize: 18, fontWeight: 700 }}>effataprints</div>
          <div style={{ color: "#7c8aa3", fontSize: 11 }}>Apparel · POD</div>
        </div>
        <div className="card">
          <div className="h">Fulfillment</div>
          <div style={{ fontSize: 18, fontWeight: 700 }}>NinjaPod</div>
          <div style={{ color: "#7c8aa3", fontSize: 11 }}>External fulfillment</div>
        </div>
        <div className="card">
          <div className="h">Guardrails</div>
          <div style={{ fontSize: 18, fontWeight: 700 }}>On</div>
          <div style={{ color: "#7c8aa3", fontSize: 11 }}>Approval + rate limit</div>
        </div>
      </div>

      <div className="h">Quick actions</div>
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <a className="btn go" href="/chat">Open chat command</a>
        <a className="btn" href="/approvals">Review pending approvals</a>
        <a className="btn" href="/actions">View audit log</a>
        <a className="btn" href="/analytics">Sales analytics</a>
      </div>

      <div className="h">How it works</div>
      <div className="card" style={{ color: "#7c8aa3", fontSize: 12, lineHeight: 1.6 }}>
        Shopify webhooks (orders, products, inventory, checkouts) land at <code>/api/webhooks/*</code>,
        are HMAC-verified, then drive Inngest workflows and the agent tool registry. New orders emit an
        event; fulfillment is handled externally. High-stakes tools (discounts, email, inventory) require owner approval in the Approvals queue.
      </div>
    </div>
  );
}
