import { submitOrderToPrintful, PrintfulLineItem, PrintfulRecipient } from "../printful/client";
import { logAction } from "./memory";

export async function fulfillFromShopifyOrder(order: any) {
  const addr = order.shipping_address || {};
  const recipient: PrintfulRecipient = {
    name:
      [addr.first_name, addr.last_name].filter(Boolean).join(" ") ||
      order.customer?.first_name ||
      "Customer",
    address1: addr.address1 || "",
    city: addr.city || "",
    state_code: addr.province_code || "",
    country_code: addr.country_code || "",
    zip: addr.zip || "",
  };
  const items: PrintfulLineItem[] = (order.line_items || []).map((li: any) => ({
    sync_variant_id: String(li.sku || li.variant_id),
    quantity: li.quantity,
  }));
  const result = await submitOrderToPrintful({
    recipient,
    items,
    retail_costs: { currency: "USD", subtotal: String(order.total_price || "0") },
  });
  await logAction({
    tool_name: "submit_printful_order",
    args: { order_id: order.id, name: order.name },
    status: "executed",
    result,
  });
  return result;
}
