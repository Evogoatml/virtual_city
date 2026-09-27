import { NextRequest, NextResponse } from "next/server";
import { readVerifiedWebhook } from "@/lib/shopify/webhooks";
import { inngest } from "@/lib/inngest/inngest";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const { ok, body } = await readVerifiedWebhook(req);
  if (!ok) return new NextResponse("invalid signature", { status: 401 });

  // Fulfillment is handled externally; this webhook only emits the order event.

  await inngest.send({ name: "shopify/order.created", data: { order: body } });
  return NextResponse.json({ ok: true });
}
