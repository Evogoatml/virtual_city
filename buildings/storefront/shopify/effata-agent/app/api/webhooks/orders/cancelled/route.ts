import { NextRequest, NextResponse } from "next/server";
import { readVerifiedWebhook } from "@/lib/shopify/webhooks";
import { inngest } from "@/lib/inngest/inngest";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const { ok, topic, body } = await readVerifiedWebhook(req);
  if (!ok) return new NextResponse("invalid signature", { status: 401 });
  await inngest.send({ name: "shopify/" + topic.replace(/\//g, "."), data: { body } });
  return NextResponse.json({ ok: true });
}
