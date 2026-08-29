export const dynamic = "force-dynamic";

const KEYS = [
  "SHOPIFY_ADMIN_API_ACCESS_TOKEN",
  "SHOPIFY_STOREFRONT_API_TOKEN",
  "SHOPIFY_WEBHOOK_SECRET",
  "PRINTFUL_API_KEY",
  "ANTHROPIC_API_KEY",
  "SUPABASE_URL",
  "SUPABASE_SERVICE_ROLE_KEY",
  "UPSTASH_REDIS_REST_URL",
  "INNGEST_EVENT_KEY",
  "RESEND_API_KEY",
  "SLACK_WEBHOOK_URL",
];

export default function SettingsPage() {
  const status = KEYS.map((k) => ({
    key: k,
    set: Boolean(process.env[k]),
  }));

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Settings</h1>
      <div className="h">Environment</div>
      <div className="card" style={{ padding: 0 }}>
        {status.map((s) => (
          <div
            key={s.key}
            style={{
              display: "flex",
              justifyContent: "space-between",
              padding: "0.45rem 0.7rem",
              borderBottom: "1px solid #1a2030",
              fontSize: 12,
            }}
          >
            <span>{s.key}</span>
            <span style={{ color: s.set ? "#39ff14" : "#ff5470" }}>{s.set ? "set" : "missing"}</span>
          </div>
        ))}
      </div>
      <div className="h">Notes</div>
      <div className="card" style={{ color: "#7c8aa3", fontSize: 12, lineHeight: 1.6 }}>
        Add these in your Vercel / Railway project settings (or a <code>.env.local</code> locally).
        Webhook URL pattern: <code>/api/webhooks/&lt;topic&gt;</code> (register in Shopify Admin →
        Notifications, or via the Admin API). Inngest events process in the background worker.
      </div>
    </div>
  );
}
