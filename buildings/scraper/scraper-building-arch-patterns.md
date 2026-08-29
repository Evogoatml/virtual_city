# Scraper Building — Architectural Patterns from 7 Reference Repos

## Per-Repo: One Idea Worth Stealing

1. **Scrapling** — **Adaptive element relocation**: the parser remembers selector contexts and auto-relocates them when sites change, plus three-tier fetcher abstraction (basic → stealthy with TLS fingerprinting → full browser) behind the same API.

2. **Firecrawl** — **LLM-ready output as the default contract**: every scrape delivers clean markdown / structured JSON by default, with an Agent endpoint that takes a natural-language description of what data you want.

3. **Crawlee** — **Unified HTTP + browser crawling interface**: one request handler works identically with Cheerio (lightweight HTTP) or Playwright (full browser), plus a persistent URL queue, pluggable result storage, and automatic human-like fingerprint generation.

4. **Maxun** — **Recorder mode → reusable robot**: a no-code UI where users record clicks/scrolls, which generates a deterministic "robot" script that can be scheduled, replayed, and exported as an API — dual-mode extraction (recorded + LLM-described).

5. **Bypass-forbidden** — **Request mutation fallback chain**: when a primary request gets a 403, try URL path tricks (/*/, /%2f/, /./), header spoofing (X-Forwarded-For, X-Original-URL), and HTTP method overloading before giving up.

6. **Swarms** — **Agent as a composable unit (LLM + Tools + Memory)**: agents are the building blocks; sequential/concurrent/hierarchical workflow patterns let you chain scraper agents that hand off tasks. `max_loops="auto"` lets agents decide when a task is complete rather than using fixed iteration counts.

7. **InverseUI-Recorder** — **Intent-based script generation + self-healing**: recordings are not just raw selector replays but annotated with semantic intent, and the runner retries failing steps with AI-generated fixes automatically.

## Three-Line Synthesis for a Virtual City Scraper Building

1. **Architecture**: The building has a configurable **Fetcher Pipeline** (basic HTTP → stealthy with TLS spoofing → headless browser) feeding into an **Adaptive Parser** that caches selector contexts and auto-relocates on page changes, with a **Robots layer** (recorded scripts from a recorder mode) and an **Agent layer** (LLM-powered agents for ad-hoc scraping) both writing to a shared **URL Queue** and **Result Store**.

2. **Resilience**: Every scrape passes through a **403 Bypass Chain** (path mutation → header spoofing → method overloading) before failing, and the **Self-Healing Runner** retries broken automations with intent-based repair rather than raw selector retries.

3. **Orchestration**: The building exposes a **Swarms-style agent routing** where scraper agents (composible LLM + Tools units) can run sequentially, concurrently, or hierarchically — a "scrape all product pages" agent delegates to page-level extraction agents, which report back structured data that is immediately LLM-ready markdown/JSON.