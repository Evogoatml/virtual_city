import Anthropic from "@anthropic-ai/sdk";

const KEY = process.env.ANTHROPIC_API_KEY || "";
const MODEL = process.env.LLM_MODEL || "claude-sonnet-4-5";

let _client: Anthropic | null = null;
function getClient(): Anthropic {
  if (!_client) _client = new Anthropic({ apiKey: KEY });
  return _client;
}

export type ChatMessage = {
  role: "user" | "assistant";
  content: any;
};

export async function llmMessages(
  messages: ChatMessage[],
  system: string,
  tools?: any[]
): Promise<any> {
  return getClient().messages.create({
    model: MODEL,
    max_tokens: 4096,
    system,
    messages: messages as any,
    tools: tools as any,
  });
}

export async function generateProductDescription(
  title: string,
  imageUrl?: string,
  tone: string = "gallery"
): Promise<string> {
  const prompt = `Write an SEO-optimized product description for a print-on-demand apparel product (t-shirt, performance tee, or crop top).
Title: ${title}
Tone: ${tone}
${imageUrl ? `Reference image: ${imageUrl}` : ""}
Return only the HTML description, no preamble.`;
  const res = await getClient().messages.create({
    model: MODEL,
    max_tokens: 1024,
    messages: [{ role: "user", content: prompt }],
  });
  return res.content
    .filter((b: any) => b.type === "text")
    .map((b: any) => b.text)
    .join("");
}

export async function summarize(text: string): Promise<string> {
  const res = await getClient().messages.create({
    model: MODEL,
    max_tokens: 1024,
    messages: [
      {
        role: "user",
        content: `Summarize the following store analytics into a short owner-facing report with 3-4 bullet points of actionable insight:\n\n${text}`,
      },
    ],
  });
  return res.content
    .filter((b: any) => b.type === "text")
    .map((b: any) => b.text)
    .join("");
}
