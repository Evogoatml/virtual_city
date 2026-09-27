---
title: Ecommerce Domain Knowledge
tags: [domain, ecommerce]
buildings: [shopify, product_flipping, social_affiliates, sourcing_research]
personas: [ecom_operator, full_multistream]
priority: 2
---

# Ecommerce Domain

## Shopify (Effata Picks — print-on-demand apparel)
- Store: effataprints.myshopify.com. Catalog focus: t-shirts, performance tees, and crop tops. Fulfillment is handled by NinjaPod outside this application; no NinjaPod API integration is included.
- Levers: traffic, conversion rate, AOV, margins. Watch fulfillment + shipping times.

## Product Flipping
- Source undervalued items, resell at margin. Track sourced_at, list price, sell price.
- Keep flip velocity high; cap capital tied in unsold inventory.

## Social Affiliates
- Campaigns map an offer to a platform. A click is interest; a conversion is revenue.
- Feed affiliates from published content (content.published -> affiliate picks up the link).
- On conversion, publish `affiliate.conversion`; Finance records it in the ledger.

## Sourcing & Research
- Leads scored by opportunity. Push strong leads to flipping + Shopify.
