# Effata Picks — Autonomous Shopify Store Agent

AI agent that runs the Effata Picks canvas-wall-art (print-on-demand) Shopify store with
minimal human intervention: order → Printful fulfillment, product content generation,
low-stock alerts, abandoned-cart recovery, weekly reports, and a chat command interface.

## Stack
- **Next.js 14 (App Router) + TypeScript + Tailwind** — dashboard + API routes
- **Anthropic Claude** — reasoning / tool-use agent (chat + content gen)
- **Shopify Admin GraphQL** — orders, products, inventory, discounts, metafields
- **Printful API** — print-on-demand fulfillment
- **Supabase (Postgres + pgvector)** — audit log, memory, embeddings
- **Upstash Redis** — rate limiting
- **Inngest** — durable webhooks, cron workflows, retries
- **Resend** — email (campaigns, alerts, reports)

## Setup
```bash
cp .env.example .env.local   # fill in real keys
npm install
npm run dev                  # http://localhost:3000
```

## Webhooks
Register in Shopify Admin → Settings → Notifications → Webhooks (or via Admin API).
Endpoint pattern: `https://<your-app>/api/webhooks/<topic>`.
Topics handled: `orders/create`, `orders/fulfilled`, `orders/cancelled`,
`inventory_levels/update`, `products/create`, `products/update`, `customers/create`,
`checkouts/create`, `app/uninstalled`. All are HMAC-verified with `SHOPIFY_WEBHOOK_SECRET`.

Priority workflows:
1. `orders/create` → auto-submit to Printful
2. `products/create` → generate SEO description (via chat tool)
3. daily inventory check (Inngest cron) → low-stock alert
4. abandoned cart (Inngest, 1h delay) → recovery email
5. weekly sales report (Inngest cron) → summarized email
6. chat command interface at `/chat`

## Database
Run `supabase/schema.sql` in Supabase.

## Deploy
Vercel (dashboard + API) with the same env vars. Inngest serves at `/api/inngest`.
The dashboard lives under the root route group `(dashboard)` at `/`, `/chat`, `/actions`,
`/approvals`, `/analytics`, `/tasks`, `/settings`.

## Notes
- Destructive tools (`create_discount`, `send_email_campaign`, `adjust_inventory`) are gated
  behind owner approval (see `/approvals`). Every action is logged in `agent_actions` with
  rollback data where supported.
- Auth in this scaffold is a simple `OWNER_API_KEY` gate; swap for Clerk/NextAuth in production.
