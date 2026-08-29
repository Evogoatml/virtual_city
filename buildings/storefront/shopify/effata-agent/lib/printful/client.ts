const API_KEY = process.env.PRINTFUL_API_KEY || "";
const BASE = "https://api.printful.com";

async function pf<T = any>(path: string, method = "GET", body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${API_KEY}`,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const json = await res.json();
  if (json.error) {
    throw new Error("Printful error: " + JSON.stringify(json.error));
  }
  return json as T;
}

export type PrintfulLineItem = {
  sync_variant_id: string;
  quantity: number;
};

export type PrintfulRecipient = {
  name: string;
  address1: string;
  city: string;
  state_code: string;
  country_code: string;
  zip: string;
};

export async function listStoreProducts() {
  return pf("/store/products");
}

export async function listCatalog() {
  return pf("/products");
}

export async function getShippingRates(recipient: PrintfulRecipient, items: PrintfulLineItem[]) {
  return pf("/shipping/rates", "POST", { recipient, items });
}

export async function submitOrderToPrintful(payload: {
  recipient: PrintfulRecipient;
  items: PrintfulLineItem[];
  retail_costs: { currency: string; subtotal: string };
}) {
  return pf("/orders", "POST", payload);
}
