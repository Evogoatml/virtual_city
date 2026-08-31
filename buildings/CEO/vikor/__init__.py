"""Vikor Building — AI agent that bridges Slack, Shopify, and the Virtual City.

Vikor acts as the operator-facing assistant: it can receive commands via Slack,
query the live Shopify store, trigger city building actions, and report back.
Runs as a standalone building on the city grid.

Env:
    VIKOR_API_KEY    — Vikor platform key (zt_live_sk_...)
    VIKOR_BASE_URL   — Vikor API endpoint (default: https://api.vikor.ai)
    SLACK_BOT_TOKEN  — xoxb- token for posting to Slack channels
    SLACK_CHANNEL    — default channel for reports (e.g. #general)
"""
import json
import os
import re
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone

from city.agent import Agent
from city.db import now_iso, log_event


def _env(name, default=""):
    return os.environ.get(name, default).strip()


class VikorAgent(Agent):
    name = "vikor"
    subject = "Vikor — Operator AI"
    district = "Command Center"
    color = "#7c3aed"  # purple

    def setup_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS vikor_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL DEFAULT 'system',
                direction TEXT NOT NULL DEFAULT 'inbound',
                channel TEXT,
                text TEXT NOT NULL,
                response TEXT,
                created_at TEXT NOT NULL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS vikor_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_type TEXT NOT NULL,
                message TEXT NOT NULL,
                data_json TEXT,
                sent_to_slack INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        self.conn.commit()
        self.vikor_key = _env("VIKOR_API_KEY")
        self.vikor_base = _env("VIKOR_BASE_URL", "https://api.vikor.ai")
        self.slack_token = _env("SLACK_BOT_TOKEN")
        self.slack_channel = _env("SLACK_CHANNEL", "#general")

    def register_rules(self):
        self.rule(r"^status$")(self._c_status)
        self.rule(r"^orders$")(self._c_orders)
        self.rule(r"^products$")(self._c_products)
        self.rule(r"^revenue$")(self._c_revenue)
        self.rule(r"^low stock$")(self._c_low_stock)
        self.rule(r"^say (?P<text>.+)$")(self._c_say)
        self.rule(r"^alert (?P<text>.+)$")(self._c_alert)
        self.rule(r"^slack (?P<text>.+)$")(self._c_slack)
        self.rule(r"^ask vikor (?P<text>.+)$")(self._c_ask_vikor)
        self.rule(r"^daily report$")(self._c_daily_report)

    # ------------------------------------------------------------------
    # Slack integration
    # ------------------------------------------------------------------
    def _slack_post(self, text, channel=None):
        """Post a message to Slack via Bot API."""
        if not self.slack_token:
            return {"error": "SLACK_BOT_TOKEN not set"}
        url = "https://slack.com/api/chat.postMessage"
        payload = json.dumps({
            "channel": channel or self.slack_channel,
            "text": text,
        }).encode()
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.slack_token}")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            return {"error": str(e)}

    def _send_alert(self, alert_type, message, data=None):
        """Record and optionally post an alert to Slack."""
        self.conn.execute(
            "INSERT INTO vikor_alerts (alert_type, message, data_json, created_at) VALUES (?,?,?,?)",
            (alert_type, message, json.dumps(data or {}), now_iso()),
        )
        self.conn.commit()
        if self.slack_token:
            result = self._slack_post(f"[{alert_type}] {message}")
            if result.get("ok"):
                self.conn.execute(
                    "UPDATE vikor_alerts SET sent_to_slack = 1 WHERE id = last_insert_rowid()"
                )
                self.conn.commit()

    # ------------------------------------------------------------------
    # Shopify bridge (pulls from the shopify building's client)
    # ------------------------------------------------------------------
    def _get_shopify_client(self):
        from city.registry import get_registry
        registry = get_registry(self.conn)
        shopify = registry.get("shopify")
        if shopify:
            return shopify.shopify
        return None

    # ------------------------------------------------------------------
    # Vikor AI bridge
    # ------------------------------------------------------------------
    def _vikor_call(self, endpoint, payload=None):
        """Call the Vikor AI API."""
        if not self.vikor_key:
            return {"error": "VIKOR_API_KEY not set"}
        url = f"{self.vikor_base.rstrip('/')}/{endpoint.lstrip('/')}"
        data = json.dumps(payload or {}).encode() if payload else None
        req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.vikor_key}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}: {e.read().decode()[:300]}"}
        except Exception as e:
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------
    def _c_status(self):
        shopify_client = self._get_shopify_client()
        shopify_ready = shopify_client.ready if shopify_client else False
        return {
            "agent": self.name,
            "vikor_connected": bool(self.vikor_key),
            "slack_connected": bool(self.slack_token),
            "shopify_bridge": shopify_ready,
            "slack_channel": self.slack_channel,
        }

    def _c_orders(self):
        client = self._get_shopify_client()
        if not client or not client.ready:
            return {"error": "Shopify not connected"}
        result = client.get_orders(10)
        if "errors" in result:
            return {"error": str(result["errors"])[:200]}
        orders = result.get("data", {}).get("orders", {}).get("edges", [])
        out = []
        for e in orders:
            n = e["node"]
            items = [li["node"]["title"] for li in n.get("lineItems", {}).get("edges", [])]
            out.append({
                "name": n["name"],
                "date": n["createdAt"][:10],
                "status": n.get("displayFinancialStatus", "?"),
                "fulfillment": n.get("displayFulfillmentStatus", "?"),
                "total": n["totalPriceSet"]["shopMoney"]["amount"],
                "items": items,
            })
        return {"orders": out, "count": len(out)}

    def _c_products(self):
        client = self._get_shopify_client()
        if not client or not client.ready:
            return {"error": "Shopify not connected"}
        result = client.get_products(50)
        if "errors" in result:
            return {"error": str(result["errors"])[:200]}
        prods = result.get("data", {}).get("products", {}).get("edges", [])
        out = []
        for e in prods:
            n = e["node"]
            variants = n.get("variants", {}).get("edges", [])
            price = variants[0]["node"].get("price", "?") if variants else "?"
            inv = sum(v["node"].get("inventoryQuantity", 0) or 0 for v in variants)
            out.append({
                "title": n["title"],
                "status": n["status"],
                "price": price,
                "inventory": inv,
                "vendor": n.get("vendor", "?"),
            })
        return {"products": out, "count": len(out)}

    def _c_revenue(self):
        rows = self.conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM ledger_entries WHERE status = 'confirmed'"
        ).fetchone()
        total = rows[0] if rows else 0
        # Also check shopify_orders
        try:
            row2 = self.conn.execute(
                "SELECT COALESCE(SUM(revenue), 0) AS rev, COUNT(*) AS n FROM shopify_orders"
            ).fetchone()
            shopify_rev = row2[0] if row2 else 0
            shopify_count = row2[1] if row2 else 0
        except Exception:
            shopify_rev = 0
            shopify_count = 0
        return {
            "ledger_total_usd": round(total, 2),
            "shopify_revenue_usd": round(shopify_rev, 2),
            "shopify_orders_count": shopify_count,
        }

    def _c_low_stock(self):
        client = self._get_shopify_client()
        if not client or not client.ready:
            return {"error": "Shopify not connected"}
        low = client.get_low_stock(5)
        return {"low_stock": low, "count": len(low)}

    def _c_say(self, text):
        """Post a message to Slack."""
        result = self._slack_post(text)
        self.conn.execute(
            "INSERT INTO vikor_messages (source, direction, channel, text, created_at) VALUES (?,?,?,?,?)",
            ("operator", "outbound", self.slack_channel, text, now_iso()),
        )
        self.conn.commit()
        return result

    def _c_alert(self, text):
        """Create and post an alert."""
        self._send_alert("manual", text)
        return {"ok": True, "alert": text}

    def _c_slack(self, text):
        """Send a message to Slack."""
        return self._c_say(text)

    def _c_ask_vikor(self, text):
        """Send a query to the Vikor AI agent."""
        result = self._vikor_call("/v1/agent/chat", {"message": text})
        self.conn.execute(
            "INSERT INTO vikor_messages (source, direction, text, response, created_at) VALUES (?,?,?,?,?)",
            ("vikor", "outbound", text, json.dumps(result), now_iso()),
        )
        self.conn.commit()
        return result

    def _c_daily_report(self):
        """Generate a daily ops report and post to Slack."""
        orders = self._c_orders()
        revenue = self._c_revenue()
        low_stock = self._c_low_stock()
        products = self._c_products()

        report_lines = [
            f"*Virtual City Daily Report* — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            f"Revenue (ledger): ${revenue.get('ledger_total_usd', 0):.2f}",
            f"Shopify orders: {revenue.get('shopify_orders_count', 0)} (${revenue.get('shopify_revenue_usd', 0):.2f})",
            f"Products live: {products.get('count', 0)}",
            f"Low stock alerts: {low_stock.get('count', 0)}",
        ]
        if orders.get("orders"):
            report_lines.append(f"Recent orders: {len(orders['orders'])}")
            for o in orders["orders"][:5]:
                report_lines.append(f"  {o['name']} — ${o['total']} ({o['status']})")
        if low_stock.get("low_stock"):
            report_lines.append("Low stock items:")
            for item in low_stock["low_stock"][:5]:
                report_lines.append(f"  {item['product']} — {item['inventory']} left")

        text = "\n".join(report_lines)
        result = self._slack_post(text)
        return {"report": text, "slack_sent": result.get("ok", False)}

    # ------------------------------------------------------------------
    # Background work — check for new orders, post alerts
    # ------------------------------------------------------------------
    def work(self):
        """Periodic tick: check Shopify for new orders, alert on low stock."""
        client = self._get_shopify_client()
        if not client or not client.ready:
            return

        # Check for new orders (poll)
        try:
            result = client.get_orders(5)
            if "errors" not in result:
                orders = result.get("data", {}).get("orders", {}).get("edges", [])
                if orders:
                    latest = orders[0]["node"]
                    latest_id = latest["id"]
                    # Check if we've seen this order
                    row = self.conn.execute(
                        "SELECT COUNT(*) AS c FROM vikor_messages WHERE text LIKE ?",
                        (f"%{latest_id}%",),
                    ).fetchone()
                    if row and row[0] == 0:
                        amt = latest["totalPriceSet"]["shopMoney"]["amount"]
                        self._send_alert("new_order", f"New order {latest['name']}: ${amt}")
        except Exception:
            pass

        # Low stock check
        try:
            low = client.get_low_stock(3)
            if low:
                existing = self.conn.execute(
                    "SELECT COUNT(*) AS c FROM vikor_alerts WHERE alert_type = 'low_stock' AND created_at > datetime('now', '-1 hour')"
                ).fetchone()
                if not existing or existing[0] == 0:
                    names = ", ".join(item["product"] for item in low[:5])
                    self._send_alert("low_stock", f"Low stock: {names}")
        except Exception:
            pass

    def report(self):
        row = self.conn.execute(
            "SELECT COUNT(*) AS c FROM vikor_messages"
        ).fetchone()
        alerts = self.conn.execute(
            "SELECT COUNT(*) AS c FROM vikor_alerts"
        ).fetchone()
        return {
            "agent": self.name,
            "subject": self.subject,
            "vikor_connected": bool(self.vikor_key),
            "slack_connected": bool(self.slack_token),
            "messages_logged": row[0] if row else 0,
            "alerts_sent": alerts[0] if alerts else 0,
        }
