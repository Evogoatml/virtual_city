import { NextRequest, NextResponse } from "next/server";
import { llmMessages, ChatMessage } from "@/lib/agent/llm";
import { toolDefs } from "@/lib/agent/tools";
import { callTool } from "@/lib/agent/guardrails";
export const dynamic = "force-dynamic";

const SYSTEM = `You are an AI store manager for Effata Picks, a Shopify store selling framed canvas wall art via print-on-demand.
You have tools to manage products, orders, inventory, discounts, analytics, and email campaigns.
Always explain what you're about to do before doing it. For destructive or spend actions, ask for confirmation.
Store domain: effataprints.myshopify.com`;

export async function POST(req: NextRequest) {
  const { messages } = await req.json();
  const conv: ChatMessage[] = messages || [];

  let finalText = "";
  for (let i = 0; i < 5; i++) {
    const res = await llmMessages(conv, SYSTEM, toolDefs);
    if (res.stop_reason !== "tool_use") {
      finalText = res.content
        .filter((b: any) => b.type === "text")
        .map((b: any) => b.text)
        .join("");
      break;
    }
    const toolUse = res.content.find((b: any) => b.type === "tool_use");
    conv.push({ role: "assistant", content: res.content });
    const outcome = await callTool(toolUse.name, toolUse.input, "chat command");
    conv.push({
      role: "user",
      content: [
        { type: "tool_result", tool_use_id: toolUse.id, content: JSON.stringify(outcome) },
      ],
    });
  }

  return NextResponse.json({ reply: finalText, conversation: conv });
}
