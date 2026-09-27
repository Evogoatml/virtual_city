# Archived Printful/canvas-wall-art material

This directory keeps the superseded Effata Picks Printful/canvas-wall-art implementation
for historical reference. It is not imported, registered, served, or included in the
active Flask or nested Next.js application.

## Files moved here

- `specs/effata_picks_agent_spec.md` — obsolete canvas-wall-art and Printful build spec.
- `buildings/storefront/shopify/effata-agent/lib/printful/client.ts` — Printful REST client.
- `buildings/storefront/shopify/effata-agent/lib/agent/fulfillment.ts` — Printful order-submission helper.

## Code removed from mixed files

- `buildings/storefront/shopify/clients.py`: removed `PrintfulClient`; the generic Shopify
  Admin/Storefront client, webhook verification, product/order, inventory, discount, and
  metafield operations remain.
- `buildings/storefront/shopify/shopify_store.py`: removed Printful initialization,
  commands, tool dispatch, order auto-submit webhook behavior, Printful sync, and
  Printful status reporting. Generic Shopify reads, writes, audit/approval flow,
  analytics, webhooks, and Venice copywriting remain.
- `buildings/storefront/shopify/effata-agent/lib/agent/tools.ts`: removed the
  `submit_printful_order` tool while retaining generic Shopify and AI tools.
- `buildings/storefront/shopify/effata-agent/app/api/webhooks/orders/create/route.ts`: removed
  the fulfillment import and call; the webhook now only emits the order event.
- Nested dashboard/settings/config files: removed Printful status, credentials, and copy.
- Product prompts, dashboard copy, specs, and environment templates now describe
  Effata Picks as print-on-demand apparel (t-shirts, performance tees, and crop tops).
  Fulfillment is handled externally by NinjaPod; no NinjaPod API integration was added.

## Deliberately not moved

HTML/3D and Slack canvas references are unrelated uses of “canvas” and remain in place.
Generic Shopify routes and the nested Shopify/Slack applications remain active.
