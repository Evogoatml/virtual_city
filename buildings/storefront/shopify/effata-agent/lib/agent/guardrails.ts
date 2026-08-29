import { Ratelimit } from "@upstash/ratelimit";
import { Redis } from "@upstash/redis";
import { tools, getTool } from "./tools";
import { logAction, updateAction, getAction } from "./memory";

let _rl: Ratelimit | null = null;
function getRatelimit(): Ratelimit {
  if (!_rl) {
    const redis = Redis.fromEnv();
    _rl = new Ratelimit({ redis, limiter: Ratelimit.slidingWindow(50, "1h") });
  }
  return _rl;
}

async function notifyOwner(message: string) {
  const url = process.env.SLACK_WEBHOOK_URL;
  if (!url) return;
  await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: message }),
  });
}

export async function callTool(toolName: string, args: unknown, reasoning?: string): Promise<{ status: string; actionId?: string; result?: unknown }> {
  const tool = getTool(toolName);
  if (!tool) throw new Error("unknown tool: " + toolName);

  const { success } = await getRatelimit().limit("agent:" + toolName);
  if (!success) throw new Error("Rate limit exceeded for tool: " + toolName);

  if (tool.requiresApproval) {
    const id = await logAction({ tool_name: toolName, args, reasoning, status: "pending" });
    await notifyOwner(`⚠️ Approval needed: \`${toolName}\`\n${JSON.stringify(args).slice(0, 500)}`);
    return { status: "pending", actionId: id };
  }

  const result = await tool.execute(args);
  await logAction({ tool_name: toolName, args, reasoning, status: "executed", result });
  return { status: "executed", result };
}

export async function approveAction(id: string): Promise<unknown> {
  const action = await getAction(id);
  const tool = getTool(action.tool_name);
  if (!tool) throw new Error("unknown tool: " + action.tool_name);
  const result = await tool.execute(action.args);
  await updateAction(id, { status: "approved" });
  await updateAction(id, { status: "executed", result });
  return result;
}

export async function rejectAction(id: string) {
  await updateAction(id, { status: "rejected" });
}

export async function rollbackAction(id: string) {
  const action = await getAction(id);
  if (!action.rollback_data) throw new Error("No rollback data available");
  const tool = getTool(action.tool_name);
  if (!tool) throw new Error("unknown tool: " + action.tool_name);
  switch (action.tool_name) {
    case "update_product":
      await tool.execute(action.rollback_data);
      break;
    case "adjust_inventory":
      await tool.execute({ ...action.rollback_data, delta: -action.args.delta });
      break;
    default:
      throw new Error("Rollback not implemented for " + action.tool_name);
  }
  await updateAction(id, { status: "rolled_back" });
}
