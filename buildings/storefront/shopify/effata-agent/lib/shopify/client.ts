const DOMAIN = process.env.SHOPIFY_STORE_DOMAIN || "effataprints.myshopify.com";
const ADMIN_TOKEN = process.env.SHOPIFY_ADMIN_API_ACCESS_TOKEN || "";
const STOREFRONT_TOKEN = process.env.SHOPIFY_STOREFRONT_API_TOKEN || "";
const VERSION = process.env.SHOPIFY_API_VERSION || "2026-01";

export async function shopifyAdmin<T = any>(
  query: string,
  variables?: Record<string, unknown>
): Promise<T> {
  const res = await fetch(
    `https://${DOMAIN}/admin/api/${VERSION}/graphql.json`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": ADMIN_TOKEN,
      },
      body: JSON.stringify({ query, variables }),
    }
  );
  const json = await res.json();
  if (json.errors) {
    throw new Error("Shopify GraphQL error: " + JSON.stringify(json.errors));
  }
  return json.data as T;
}

export async function shopifyStorefront<T = any>(
  query: string,
  variables?: Record<string, unknown>
): Promise<T> {
  const res = await fetch(
    `https://${DOMAIN}/api/${VERSION}/graphql.json`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Shopify-Storefront-Access-Token": STOREFRONT_TOKEN,
      },
      body: JSON.stringify({ query, variables }),
    }
  );
  const json = await res.json();
  if (json.errors) {
    throw new Error("Storefront GraphQL error: " + JSON.stringify(json.errors));
  }
  return json.data as T;
}

export type ShopifyOrderNode = {
  id: string;
  name: string;
  email: string;
  totalPriceSet: { shopMoney: { amount: string; currencyCode: string } };
  fulfillmentStatus: string;
  financialStatus: string;
  createdAt: string;
  lineItems: {
    edges: {
      node: {
        title: string;
        quantity: number;
        variant: { id: string; sku: string; inventoryQuantity: number };
      };
    }[];
  };
};
