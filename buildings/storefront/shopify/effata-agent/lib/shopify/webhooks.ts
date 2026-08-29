import crypto from "crypto";

export function verifyShopifyWebhook(
  rawBody: string | Buffer,
  hmacHeader: string | null,
  secret: string
): boolean {
  if (!hmacHeader || !secret) return false;
  const body = Buffer.isBuffer(rawBody) ? rawBody : Buffer.from(rawBody, "utf8");
  const hash = crypto
    .createHmac("sha256", secret)
    .update(body)
    .digest("base64");
  const a = Buffer.from(hash);
  const b = Buffer.from(hmacHeader);
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(a, b);
}

export function shopifyTopic(req: Request): string {
  return req.headers.get("x-shopify-topic") || "";
}

export async function readVerifiedWebhook(req: Request): Promise<{
  ok: boolean;
  topic: string;
  body: any;
}> {
  const raw = await req.text();
  const hmac = req.headers.get("x-shopify-hmac-sha256");
  const secret = process.env.SHOPIFY_WEBHOOK_SECRET || "";
  if (!verifyShopifyWebhook(raw, hmac, secret)) {
    return { ok: false, topic: "", body: null };
  }
  const topic = req.headers.get("x-shopify-topic") || "";
  let body: any = null;
  try {
    body = JSON.parse(raw);
  } catch {
    body = null;
  }
  return { ok: true, topic, body };
}
