import { supabase } from "../db/supabase";

export type ActionStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "executed"
  | "rolled_back";

export async function logAction(params: {
  tool_name: string;
  args: unknown;
  reasoning?: string;
  status?: ActionStatus;
  rollback_data?: unknown;
  result?: unknown;
}) {
  const { data, error } = await supabase
    .from("agent_actions")
    .insert({
      tool_name: params.tool_name,
      args: params.args,
      reasoning: params.reasoning ?? null,
      status: params.status ?? "executed",
      rollback_data: params.rollback_data ?? null,
      result: params.result ?? null,
    })
    .select("id")
    .single();
  if (error) throw new Error("logAction: " + error.message);
  return data.id as string;
}

export async function updateAction(
  id: string,
  patch: { status?: ActionStatus; result?: unknown; rollback_data?: unknown; approved_by?: string }
) {
  const { error } = await supabase.from("agent_actions").update(patch).eq("id", id);
  if (error) throw new Error("updateAction: " + error.message);
}

export async function getAction(id: string) {
  const { data, error } = await supabase
    .from("agent_actions")
    .select("*")
    .eq("id", id)
    .single();
  if (error) throw new Error("getAction: " + error.message);
  return data;
}

export async function insertEmbedding(params: {
  shopify_product_id: string;
  title: string;
  description: string;
  embedding: number[];
}) {
  const { error } = await supabase.from("product_embeddings").upsert(params);
  if (error) throw new Error("insertEmbedding: " + error.message);
}

export async function matchProducts(
  queryEmbedding: number[],
  matchThreshold = 0.7,
  matchCount = 5
) {
  const { data, error } = await supabase.rpc("match_products", {
    query_embedding: queryEmbedding,
    match_threshold: matchThreshold,
    match_count: matchCount,
  });
  if (error) throw new Error("matchProducts: " + error.message);
  return data;
}

export async function appendMemory(params: {
  session_id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  tool_name?: string;
}) {
  const { error } = await supabase.from("agent_memory").insert(params);
  if (error) throw new Error("appendMemory: " + error.message);
}
