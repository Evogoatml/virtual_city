import { inngest } from "./inngest";
import { getResend } from "../email";
import { getLowStockProducts, runShopifyQL } from "../shopify/queries";
import { summarize } from "../agent/llm";

async function sendEmail(subject: string, body: string) {
  await getResend().emails.send({
    from: "Effata Picks <noreply@effataprints.com>",
    to: ["owner@effataprints.com"],
    subject,
    html: body.replace(/\n/g, "<br>"),
  });
}

export const abandonedCartFlow = inngest.createFunction(
  { id: "abandoned-cart-recovery", triggers: [{ event: "shopify/checkouts.create" }] },
  async ({ event, step }) => {
    await step.sleep("wait-1-hour", "1h");
    const checkout = await step.run("check-if-completed", async () => {
      const orders = await runShopifyQL(
        `query { orders(first: 5, query: "name:${event.data.body?.name ?? ""}") { edges { node { name financialStatus } } } }`
      );
      return orders;
    });
    const completed = checkout?.orders?.edges?.length > 0;
    if (!completed) {
      await step.run("send-recovery-email", async () => {
        return sendEmail(
          "🛒 Still thinking it over? Your new apparel is waiting",
          "Hi! You left some great apparel in your cart. Complete your order before it sells out."
        );
      });
    }
    return { sent: !completed };
  }
);

export const dailyInventoryCheck = inngest.createFunction(
  { id: "daily-inventory-check", triggers: [{ cron: "0 8 * * *" }] },
  async ({ step }) => {
    const lowStock = await step.run("get-low-stock", async () => {
      return getLowStockProducts(5);
    });
    if (lowStock.length > 0) {
      await step.run("notify-owner", async () => {
        const lines = lowStock.map((p) => `${p.title} (${p.sku}): ${p.quantity} left`).join("\n");
        return sendEmail(`⚠️ ${lowStock.length} products low on stock`, lines);
      });
    }
    return { lowStock: lowStock.length };
  }
);

export const weeklySalesReport = inngest.createFunction(
  { id: "weekly-sales-report", triggers: [{ cron: "0 9 * * MON" }] },
  async ({ step }) => {
    const analytics = await step.run("query-analytics", async () => {
      return runShopifyQL(
        `FROM sales SHOW sum(net_sales) AS total_sales, count(orders) AS order_count SINCE -7d UNTIL today ORDER BY total_sales DESC`
      );
    });
    const summary = await step.run("generate-summary", async () => {
      return summarize(JSON.stringify(analytics));
    });
    await step.run("send-report", async () => {
      return sendEmail("📊 Weekly Sales Report — Effata Picks", summary);
    });
    return { sent: true };
  }
);
