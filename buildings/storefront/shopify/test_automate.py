"""Unit tests for Shopify respond + schedule playbooks."""
from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from buildings.storefront.shopify import automate


class FakeShopify:
    def __init__(self, ready=True, orders=None, products=None, low=None, errors=None):
        self.domain = "effataprints.myshopify.com"
        self.ready = ready
        self._orders = orders or {"data": {"orders": {"edges": []}}}
        self._products = products or {"data": {"products": {"edges": []}}}
        self._low = low if low is not None else []
        self._errors = errors

    def get_orders(self, limit=10):
        return self._errors or self._orders

    def get_products(self, limit=20):
        return self._errors or self._products

    def get_low_stock(self, threshold=5):
        return self._errors or self._low


class FakeDepartment:
    def process_abandoned_carts(self):
        return {"checked": 2, "recovered": 1}

    def _c_analytics(self, kind=None):
        return {"note": "ShopifyQL analytics", "query": "FROM sales SHOW sum(net_sales)"}


def _ok_page(url, **extra):
    page = {"ok": True, "url": url, "status": 200, "password": False, "title": "Effata"}
    page.update(extra)
    return page


class DetectIntentTests(unittest.TestCase):
    def test_default_status(self):
        self.assertEqual(automate.detect_intents("status"), ["health", "inventory"])

    def test_orders_and_stock(self):
        self.assertEqual(automate.detect_intents("any new orders or low stock?"), ["orders", "inventory"])

    def test_health(self):
        self.assertIn("health", automate.detect_intents("did the shipping policy 404 again?"))


class HealthTests(unittest.TestCase):
    def test_flags_404_and_password(self):
        def fake_get(url):
            if url.endswith("/policies/shipping-policy"):
                return {"ok": False, "url": url, "status": 404, "password": False}
            if url.rstrip("/").endswith("effataprints.myshopify.com"):
                return _ok_page(url, password=True, ok=False)
            return _ok_page(url)

        report = automate.check_storefront_health(
            base_url="https://effataprints.myshopify.com",
            paths=("/", "/policies/shipping-policy", "/cart"),
            opener=fake_get,
        )
        self.assertFalse(report["ok"])
        self.assertTrue(report["password_wall"])
        self.assertEqual(len(report["broken"]), 2)

    def test_clean_storefront(self):
        report = automate.check_storefront_health(
            base_url="https://example.test",
            paths=("/", "/cart"),
            opener=lambda url: _ok_page(url),
        )
        self.assertTrue(report["ok"])
        self.assertEqual(report["checked"], 2)


class PlaybookTests(unittest.TestCase):
    def test_respond_read_only_without_admin(self):
        shop = FakeShopify(ready=False)
        with patch.object(automate, "check_storefront_health", return_value={
            "ok": True, "checked": 2, "broken": [], "password_wall": False,
        }):
            report = automate.run_respond("status", shopify=shop, notify=False)
        self.assertTrue(report["ok"])
        self.assertIn("health", report["intents"])
        self.assertIn("inventory", report["intents"])
        self.assertTrue(report["sections"]["inventory"].get("skipped"))
        self.assertIn("Shopify respond", report["markdown"])

    def test_respond_orders(self):
        shop = FakeShopify(orders={"data": {"orders": {"edges": [
            {"node": {
                "name": "#1001",
                "email": "a@b.com",
                "totalPriceSet": {"shopMoney": {"amount": "32.00", "currencyCode": "USD"}},
                "displayFulfillmentStatus": "UNFULFILLED",
                "displayFinancialStatus": "PAID",
                "createdAt": "2026-09-18T00:00:00Z",
            }}
        ]}}})
        with patch.object(automate, "check_storefront_health", return_value={"ok": True, "checked": 1, "broken": []}):
            report = automate.run_respond("show recent orders", shopify=shop, notify=False)
        self.assertTrue(report["ok"])
        self.assertEqual(report["sections"]["orders"]["count"], 1)
        self.assertIn("#1001", report["markdown"])

    def test_schedule_weekly_notifies_slack(self):
        shop = FakeShopify(low=[{"product": "Hold My Beer", "inventory": 2}])
        dept = FakeDepartment()
        with patch.object(automate, "check_storefront_health", return_value={
            "ok": True, "checked": 3, "broken": [], "password_wall": False,
        }):
            with patch.object(automate, "notify_slack", return_value={"ok": True, "status": 200}) as notify:
                report = automate.run_schedule(weekly=True, shopify=shop, department=dept, notify=True)
        self.assertTrue(report["ok"])
        self.assertTrue(report["weekly"])
        self.assertEqual(report["sections"]["inventory"]["count"], 1)
        self.assertEqual(report["sections"]["carts"]["recovered"], 1)
        self.assertIn("analytics", report["sections"])
        notify.assert_called_once()

    def test_cli_respond_json(self):
        shop = FakeShopify(ready=False)
        with patch.object(automate, "_client", return_value=shop):
            with patch.object(automate, "check_storefront_health", return_value={
                "ok": True, "checked": 1, "broken": [], "password_wall": False,
            }):
                with patch("sys.stdout", new_callable=io.StringIO) as buf:
                    code = automate.main(["respond", "--query", "status", "--json"])
                    payload = json.loads(buf.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(payload["mode"], "respond")


class FormatAndSlackTests(unittest.TestCase):
    def test_format_mentions_needs_attention(self):
        text = automate.format_report({
            "mode": "schedule",
            "ran_at": "2026-09-18T00:00:00+00:00",
            "ok": False,
            "sections": {
                "connection": {"domain": "effataprints.myshopify.com", "admin_ready": False},
                "health": {
                    "ok": False,
                    "checked": 1,
                    "password_wall": False,
                    "broken": [{"status": 404, "url": "https://x/policies/shipping-policy"}],
                },
            },
        })
        self.assertIn("needs attention", text)
        self.assertIn("404", text)

    def test_notify_slack_skips_without_url(self):
        with patch.dict("os.environ", {}, clear=False):
            with patch.object(automate, "_env", return_value=""):
                result = automate.notify_slack("hello")
        self.assertTrue(result.get("skipped"))


if __name__ == "__main__":
    unittest.main()
