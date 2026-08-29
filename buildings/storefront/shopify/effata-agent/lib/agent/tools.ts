import { getRecentOrders, getLowStockProducts, updateProduct, runShopifyQL } from "../shopify/queries";
import { submitOrderToPrintful, PrintfulLineItem, PrintfulRecipient } from "../printful/client";
import { generateProductDescription, summarize } from "./llm";
import { getResend } from "../email";

export type AgentTool = {
  name: string;
  description: string;
  parameters: any;
  execute: (args: any) => Promise<unknown>;
  requiresApproval?: boolean;
  rateLimit?: number;
};



export const tools: AgentTool[] = [
  {
    name: "get_orders",
    description: "Fetch recent Shopify orders with line items and fulfillment status",
    parameters: { type: "object", properties: { limit: { type: "number" } } },
    execute: async ({ limit }) => getRecentOrders(limit ?? 10),
  },
  {
    name: "update_product",
    description: "Update a product title, description, tags, or price",
    parameters: {
      type: "object",
      properties: {
        productId: { type: "string" },
        title: { type: "string" },
        descriptionHtml: { type: "string" },
        tags: { type: "array", items: { type: "string" } },
        price: { type: "string" },
      },
      required: ["productId"],
    },
    execute: async (args) => updateProduct(args),
    requiresApproval: false,
  },
  {
    name: "create_discount",
    description: "Create a percentage or fixed discount code",
    parameters: {
      type: "object",
      properties: {
        code: { type: "string" },
        percentage: { type: "number" },
        expiresAt: { type: "string" },
      },
      required: ["code", "percentage"],
    },
    execute: async (args) => runShopifyQL(`mutation { discountCodeBasicCreate(basicCodeDiscount: { title: "${args.code}", percentage: ${args.percentage}, endsAt: ${args.expiresAt ? `"${args.expiresAt}"` : "null"} }) { codeDiscountNode { id } userErrors { field message } } }`),
    requiresApproval: true,
  },
  {
    name: "send_email_campaign",
    description: "Send a marketing email to a customer segment",
    parameters: {
      type: "object",
      properties: { segmentId: { type: "string" }, subject: { type: "string" }, bodyHtml: { type: "string" } },
      required: ["segmentId", "subject", "bodyHtml"],
    },
    execute: async ({ subject, bodyHtml }) =>
      getResend().emails.send({ from: "Effata Picks <noreply@effatapicks.com>", to: ["owner@effatapicks.com"], subject, html: bodyHtml }),
    requiresApproval: true,
  },
  {
    name: "query_analytics",
    description: "Run a ShopifyQL query for sales, sessions, or product performance",
    parameters: { type: "object", properties: { query: { type: "string" } }, required: ["query"] },
    execute: async ({ query }) => runShopifyQL(query),
  },
  {
    name: "adjust_inventory",
    description: "Adjust inventory quantity for a product variant",
    parameters: {
      type: "object",
      properties: { inventoryItemId: { type: "string" }, locationId: { type: "string" }, delta: { type: "number" } },
      required: ["inventoryItemId", "locationId", "delta"],
    },
    execute: async (args) =>
      runShopifyQL(`mutation { inventoryAdjustQuantity(input: { inventoryItemId: "${args.inventoryItemId}", locationId: "${args.locationId}", availableDelta: ${args.delta} }) { inventoryLevel { available } userErrors { field message } } }`),
    requiresApproval: true,
  },
  {
    name: "submit_printful_order",
    description: "Submit a Shopify order to Printful for fulfillment",
    parameters: { type: "object", properties: { shopifyOrderId: { type: "string" } }, required: ["shopifyOrderId"] },
    execute: async ({ shopifyOrderId }) => {
      const orders = await getRecentOrders(50);
      const order = orders.find((o) => o.id === shopifyOrderId);
      if (!order) throw new Error("order not found");
      const recipient: PrintfulRecipient = {
        name: order.name,
        address1: "auto",
        city: "auto",
        state_code: "CA",
        country_code: "US",
        zip: "00000",
      };
      const items: PrintfulLineItem[] = order.lineItems.edges.map((e) => ({
        sync_variant_id: e.node.variant.sku,
        quantity: e.node.quantity,
      }));
      return submitOrderToPrintful({
        recipient,
        items,
        retail_costs: { currency: "USD", subtotal: order.totalPriceSet.shopMoney.amount },
      });
    },
    requiresApproval: false,
  },
  {
    name: "generate_product_description",
    description: "Use AI to generate an SEO-optimized product description from a title and image",
    parameters: {
      type: "object",
      properties: { productTitle: { type: "string" }, imageUrl: { type: "string" }, tone: { type: "string", enum: ["gallery", "minimal", "bold"] } },
      required: ["productTitle"],
    },
    execute: async (args) => generateProductDescription(args.productTitle, args.imageUrl, args.tone),
  },
  {
    name: "get_low_stock_products",
    description: "Return all products with inventory below a threshold",
    parameters: { type: "object", properties: { threshold: { type: "number" } } },
    execute: async ({ threshold }) => getLowStockProducts(threshold ?? 5),
  },
  {
    name: "write_metafield",
    description: "Write a custom metafield to a Shopify resource",
    parameters: {
      type: "object",
      properties: { ownerId: { type: "string" }, namespace: { type: "string" }, key: { type: "string" }, value: { type: "string" }, type: { type: "string" } },
      required: ["ownerId", "namespace", "key", "value", "type"],
    },
    execute: async (args) =>
      runShopifyQL(`mutation { metafieldsSet(metafields: [{ ownerId: "${args.ownerId}", namespace: "${args.namespace}", key: "${args.key}", value: "${args.value}", type: "${args.type}" }]) { metafields { id } userErrors { field message } } }`),
  },
  {
    name: "summarize_analytics",
    description: "Summarize analytics text into an owner-facing report",
    parameters: { type: "object", properties: { text: { type: "string" } }, required: ["text"] },
    execute: async ({ text }) => summarize(text),
  },
];

export function getTool(name: string): AgentTool | undefined {
  return tools.find((t) => t.name === name);
}

export const toolDefs = tools.map((t) => ({
  name: t.name,
  description: t.description,
  input_schema: t.parameters,
}));
