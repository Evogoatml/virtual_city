import { NextResponse } from "next/server";
import { supabase } from "@/lib/db/supabase";
export const dynamic = "force-dynamic";

export async function GET() {
  const { data, error } = await supabase
    .from("agent_actions")
    .select("*")
    .eq("status", "pending")
    .order("created_at", { ascending: false })
    .limit(100);
  if (error) return NextResponse.json({ error: error.message }, { status: 500 });
  return NextResponse.json(data);
}
