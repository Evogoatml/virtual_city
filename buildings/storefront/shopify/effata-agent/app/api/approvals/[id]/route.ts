import { NextRequest, NextResponse } from "next/server";
import { approveAction, rejectAction, rollbackAction } from "@/lib/agent/guardrails";
import { getAction } from "@/lib/agent/memory";
import { supabase } from "@/lib/db/supabase";
export const dynamic = "force-dynamic";

export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  const { data, error } = await supabase
    .from("agent_actions")
    .select("*")
    .eq("id", params.id)
    .single();
  if (error) return NextResponse.json({ error: error.message }, { status: 404 });
  return NextResponse.json(data);
}

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const { action } = await req.json();
  try {
    if (action === "approve") {
      const result = await approveAction(params.id);
      return NextResponse.json({ ok: true, result });
    }
    if (action === "reject") {
      await rejectAction(params.id);
      return NextResponse.json({ ok: true });
    }
    if (action === "rollback") {
      await rollbackAction(params.id);
      return NextResponse.json({ ok: true });
    }
    return NextResponse.json({ error: "unknown action" }, { status: 400 });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 400 });
  }
}
