export const dynamic = "force-dynamic";

import { supabase } from "@/lib/db/supabase";

export default async function TasksPage() {
  let rows: any[] = [];
  let err = "";
  try {
    const { data, error } = await supabase
      .from("scheduled_tasks")
      .select("*")
      .order("next_run", { ascending: true });
    if (error) err = error.message;
    else rows = data || [];
  } catch (e: any) {
    err = e.message;
  }

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Scheduled Tasks</h1>
      {err && <div style={{ color: "#ff5470" }}>{err}</div>}
      <div className="card" style={{ padding: 0 }}>
        {rows.length === 0 && (
          <div style={{ padding: "0.6rem", color: "#7c8aa3" }}>
            No scheduled tasks. Inngest owns the cron workflows (daily inventory, weekly report).
          </div>
        )}
        {rows.map((t) => (
          <div
            key={t.id}
            style={{
              display: "flex",
              justifyContent: "space-between",
              padding: "0.5rem 0.7rem",
              borderBottom: "1px solid #1a2030",
              fontSize: 12,
            }}
          >
            <div>
              <b>{t.name}</b>
              <div style={{ color: "#7c8aa3" }}>{t.cron_expression}</div>
            </div>
            <div style={{ color: "#7c8aa3" }}>{t.enabled ? "enabled" : "disabled"}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
