export const dynamic = "force-dynamic";

import { runShopifyQL } from "@/lib/shopify/queries";
import { summarize } from "@/lib/agent/llm";

export default async function AnalyticsPage() {
  let report = "";
  let raw = "";
  try {
    const data = await runShopifyQL(
      `FROM sales SHOW sum(net_sales) AS total_sales, count(orders) AS order_count SINCE -7d UNTIL today ORDER BY total_sales DESC`
    );
    raw = JSON.stringify(data, null, 2);
    report = await summarize(raw);
  } catch (e: any) {
    report = "Could not load analytics: " + e.message;
  }

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Analytics</h1>
      <div className="card">
        <div className="h">Weekly summary (owner-facing)</div>
        <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>{report}</div>
      </div>
      <details style={{ marginTop: "0.6rem" }}>
        <summary style={{ color: "#7c8aa3", cursor: "pointer" }}>Raw ShopifyQL response</summary>
        <pre>{raw}</pre>
      </details>
    </div>
  );
}
