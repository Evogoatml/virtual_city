import { NextRequest, NextResponse } from "next/server";
import { readVerifiedWebhook } from "@/lib/shopify/webhooks";
import { fulfillFromShopifyOrder } from "@/lib/agent/fulfillment";
import { inngest } from "@/lib/inngest/inngest";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const { ok, body } = await readVerifiedWebhook(req);
  if (!ok) return new NextResponse("invalid signature", { status: 401 });

  try {
    await fulfillFromShopifyOrder(body);
  } catch (e) {
    console.error("fulfillment failed", e);
  }

  await inngest.send({ name: "shopify/order.created", data: { order: body } });
  return NextResponse.json({ ok: true });
}
