# Cursor automation — Shopify Schedule

Create this as a **Schedule** automation at https://cursor.com/automations

- Trigger: cron, **every day at 08:00 America/Los_Angeles**.
- Repository: `Evogoatml/virtual_city`
- Model: the default cloud agent model is fine.

Optional second schedule: **Monday 09:00 America/Los_Angeles** with `--weekly` (sales snapshot). One daily job that adds `--weekly` on Mondays is enough.

## Prompt (paste as the automation instructions)

You run the Effata Picks Shopify store from this repo. This automation is **Schedule** — no human is waiting, so only speak when something needs attention.

1. Read `buildings/storefront/shopify/automate.py` and `.cursor/automations/shopify-schedule.md`.
2. Run the schedule playbook:

```bash
# daily
python -m buildings.storefront.shopify.automate schedule --no-notify --json

# also on Monday (America/Los_Angeles)
python -m buildings.storefront.shopify.automate schedule --weekly --no-notify --json
```

3. Use `--no-notify` so this agent owns the Slack message (avoids a double post if `SLACK_WEBHOOK_URL` is also set on the city process).
4. Post to Slack **only if**:
   - a public page is 404 / password-walled, or
   - low-stock count is greater than 0, or
   - admin was expected (`SHOPIFY_ADMIN_API_ACCESS_TOKEN` is present) and the Admin API failed, or
   - it is the Monday weekly run (always post the weekly summary).
5. Stay read-only. Do not create discounts, change prices, restock, or push Printful. Abandoned-cart rows may be marked recovered in the city DB; that is the only mutation allowed.
6. If the storefront health check is clean, admin is disconnected, and it is not Monday: exit quietly with a one-line city log, no Slack ping.

Public pages checked: `/`, `/collections/all`, `/pages/about-us`, `/policies/shipping-policy`, `/policies/refund-policy`, `/policies/privacy-policy`, `/cart`.
