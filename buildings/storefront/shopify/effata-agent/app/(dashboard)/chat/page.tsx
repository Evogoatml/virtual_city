"use client";

import { useState } from "react";

type Msg = { role: string; content: string };

export default function ChatPage() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  async function send() {
    if (!input.trim() || busy) return;
    const next = [...messages, { role: "user", content: input }];
    setMessages(next);
    setInput("");
    setBusy(true);
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: next }),
      });
      const data = await res.json();
      setMessages([...next, { role: "assistant", content: data.reply || "(no reply)" }]);
    } catch (e: any) {
      setMessages([...next, { role: "assistant", content: "error: " + e.message }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Command Chat</h1>
      <div style={{ maxWidth: 720 }}>
        {messages.map((m, i) => (
          <div
            key={i}
            style={{
              margin: "0.5rem 0",
              padding: "0.5rem 0.7rem",
              borderRadius: 6,
              background: m.role === "user" ? "#161b29" : "#11141f",
              border: "1px solid #222a3d",
            }}
          >
            <div style={{ color: "#7c8aa3", fontSize: 10, textTransform: "uppercase" }}>{m.role}</div>
            <div style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>
          </div>
        ))}
        <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.6rem" }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder="e.g. Generate a description for my new mountain canvas"
            style={{
              flex: 1,
              background: "#161b29",
              border: "1px solid #222a3d",
              color: "#c7d2e0",
              padding: "0.5rem",
              borderRadius: 6,
              fontFamily: "inherit",
            }}
          />
          <button className="btn go" onClick={send} disabled={busy}>
            {busy ? "…" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}
