# Effata Picks — Autonomous Shopify Store Agent (Build Spec)

> Store: Effata Picks | Platform: Shopify Basic | Niche: Canvas Wall Art (Print-on-Demand)
> Goal: a fully autonomous AI agent that monitors, manages, and grows the store with minimal human intervention.
> Source spec handed over 2026-08-26.

## 1. Project Goals
- Automate day-to-day Shopify operations (orders, inventory, products, customers)
- Connect print-on-demand fulfillment (Printful) with zero manual syncing
- Generate and optimize product content (titles, descriptions, SEO, images)
- Run marketing automations (email, social, abandoned cart)
- Surface weekly analytics and actionable insights
- Expose a chat interface for the owner to issue plain-language commands
- Log every agent action with full audit trail and rollback support

## 2. Tech Stack (as specified)
- LLM: Claude 3.5 Sonnet (Anthropic), fallback GPT-4o
- Agent: LangGraph or custom ReAct loop
- Backend: Node.js (TypeScript) or Python 3.12
- API: Next.js App Router OR FastAPI
- Frontend: Next.js 14+ + Tailwind
- DB: Supabase (PostgreSQL + pgvector)
- Cache: Upstash Redis
- Event bus: Inngest
- Hosting: Vercel + Railway
- Auth: Clerk / NextAuth
- Monitoring: Axiom / Datadog
- Secrets: Doppler / Vercel env

## 3. Shopify Integration
- Store: `effataprints.myshopify.com`
- Env: `SHOPIFY_STORE_DOMAIN`, `SHOPIFY_ADMIN_API_ACCESS_TOKEN` (shpat_), `SHOPIFY_STOREFRONT_API_TOKEN`, `SHOPIFY_WEBHOOK_SECRET`, `SHOPIFY_API_VERSION=2026-01`
- Admin GraphQL: `https://{store}/admin/api/{version}/graphql.json` (X-Shopify-Access-Token)
- Storefront API: `https://{store}/api/{version}/graphql.json` (Storefront token)
- REST Admin: legacy, use sparingly
- Key queries: recent orders, products+inventory, update product description, create discount, adjust inventory, write metafield
- ShopifyQL: weekly sales summary, top products by revenue, sessions/conversion

## 4. Webhooks to register
| Topic | Purpose |
|-------|---------|
| orders/create | new order -> fulfillment check |
| orders/fulfilled | notify customer, log |
| orders/cancelled | restock, log |
| inventory_levels/update | low stock alert |
| products/create | auto-generate description/SEO |
| products/update | sync to POD |
| customers/create | welcome email |
| checkouts/create | abandoned cart tracking |
| app/uninstalled | cleanup |

## 5. Printful Integration
- Base `https://api.printful.com`, `Authorization: Bearer {PRINTFUL_API_KEY}`
- Endpoints: `/store/products`, `/orders`, `/products` (catalog), `/shipping/rates`
- Auto-submit order: recipient + items(sync_variant_id, qty) + retail_costs

## 6. Agent Architecture
- ReAct loop: thought -> action -> observation -> memory -> complete
- Tool registry (TS interface AgentTool with name/description/parameters/execute/requiresApproval/rateLimit)
- Tools: get_orders, update_product, create_discount, send_email_campaign, query_analytics,
  adjust_inventory, submit_printful_order, generate_product_description, get_low_stock_products, write_metafield

## 7. Memory & Embeddings
- Supabase tables: agent_actions (audit + rollback), product_embeddings (pgvector 1536), agent_memory, scheduled_tasks
- Vector search via `match_products` RPC

## 8. Event Bus (Inngest)
- abandonedCartFlow (checkouts/create + 1h delay -> recovery email)
- dailyInventoryCheck (cron 0 8 * -> low stock notify)
- weeklySalesReport (cron 0 9 MON -> ShopifyQL + summarize + email)

## 9. Safety & Guardrails
- Approval gate for requiresApproval tools (pending/approved/executed/rolled_back)
- Rate limiting (50 tool calls/hr sliding window)
- Rollback per tool (update_product, create_discount, adjust_inventory)

## 10. Dashboard (Next.js)
- `/` overview + agent status, `/chat` NL commands, `/actions` audit log, `/approvals` queue,
  `/analytics` sales/traffic/products, `/tasks` scheduled, `/settings` keys
- Chat API: Claude 3.5 Sonnet with tool use, explain-before-do, confirm destructive

## 11. Env Vars (complete)
Shopify (above) + Printful (PRINTFUL_API_KEY, PRINTFUL_STORE_ID) + AI (ANTHROPIC_API_KEY, OPENAI_API_KEY)
+ SUPABASE_URL/ANON/SERVICE_ROLE + UPSTASH_REDIS + INNGEST + RESEND_API_KEY + CLERK + SLACK_WEBHOOK_URL + NEXT_PUBLIC_APP_URL

## 12. Folder structure (TS/Next.js) — see original spec
app/api/{chat,webhooks/*,approvals}, lib/{shopify,printful,agent,inngest,db}, inngest.ts, middleware.ts

## 13. Starter workflows (priority order)
1. New order -> submit to Printful
2. New product -> generate description
3. Low stock alert (daily cron)
4. Abandoned cart recovery
5. Weekly sales report
6. Chat command interface

## 14. Architecture diagram — Trigger(Inngest) -> Orchestrator(ReAct) -> Shopify/Printful/OpenAI -> Data(Supabase/Redis) -> Guardrails -> Dashboard

---
NOTE: Our running system (Virtual City, Python/Flask) already provides: a Shopify building with
verified webhooks (orders/paid -> finance ledger), a finance/agent event bus, agent runtime with
tool-style skills, audit traces, and an operator dashboard. The work below is to extend THAT with the
store-automation features in this spec, or to stand up the separate TS stack — see decision in chat.
