---
title: Affiliate Funnel SOP
tags: [sop, affiliates, funnel]
buildings: [social_affiliates, media_building]
personas: [ecom_operator, full_multistream]
priority: 2
---

# SOP — Affiliate Funnel

1. **Pick an offer.** Choose a high-converting offer for the active persona.
2. **Publish content.** Content building publishes a post carrying the offer link and
   emits `content.published {offer, url}`.
3. **Affiliates react.** Social Affiliates opens/updates a campaign for that offer.
4. **Drive clicks.** Promote the post; log `click <offer>` as interest accrues.
5. **Convert.** On a sale, log `convert <offer> revenue <amount>`; emit
   `affiliate.conversion {offer, revenue}`.
6. **Treasury.** Finance consumes `affiliate.conversion` and writes a ledger income entry.
7. **Optimize.** Review conversion_rate; double down on the top platform/offer pair.
