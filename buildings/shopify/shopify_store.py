"""
Shopify Store Department — Autonomous store agent for Effata Picks
(Canvas Wall Art, print-on-demand via Printful).

Adapted from the Agentic AI Full-Stack Build Spec into virtual_city's
rule-based Department model:
  - Real Shopify Admin/Storefront GraphQL + Printful REST (see clients.py)
  - Tool registry executed through an approval gate + audit log
  - Rollback data captured for destructive tools
  - ReAct-style `chat` command backed by city.venice
  - Webhook handler for Shopify topics (HMAC-verified in app.py)
"""
import json
import os
import time
from datetime import datetime, timezone

from city.department import Department
from city.db import now_iso
from city.api_budget import budget
from buildings.shopify.clients import ShopifyClient, PrintfulClient


_AUTO_APPROVE = os.environ.get("SHOPIFY_AUTO_APPROVE", "").strip() in ("1", "true", "on")


class ShopifyStoreDepartment(Department):
    name = "shopify"
    subject = "Shopify Store Dept"
    district = "Commerce Row"
    color = "#95bf47"

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def setup_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS shopify_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product TEXT NOT NULL,
                revenue REAL NOT NULL,
                cost REAL NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'pod',
                placed_at TEXT NOT NULL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                args_json TEXT,
                result_json TEXT,
                reasoning TEXT,
                approved_by TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                rollback_json TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS shopify_checkouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                checkout_id TEXT UNIQUE NOT NULL,
                email TEXT,
                raw_json TEXT,
                created_at TEXT NOT NULL,
                recovered INTEGER NOT NULL DEFAULT 0
            )
        """)
        self.conn.commit()
        self.shopify = ShopifyClient()
        self.printful = PrintfulClient()

    def register_rules(self):
        self.rule(r"^orders(?:\s+(?P<limit>\d+))?$")(self._c_orders)
        self.rule(r"^products$")(self._c_products)
        self.rule(r"^low stock(?:\s+(?P<threshold>\d+))?$")(self._c_low_stock)
        self.rule(r"^update product\s+(?P<product_id>\S+)\s+(?P<field>title|description|price|tags)\s+(?P<value>.+)$")(self._c_update_product)
        self.rule(r"^discount\s+(?P<code>\S+)\s+(?P<percentage>[\d.]+)(?:\s+(?P<expires>\S+))?$")(self._c_discount)
        self.rule(r"^inventory adjust\s+(?P<item_id>\S+)\s+(?P<loc_id>\S+)\s+(?P<delta>-?\d+)$")(self._c_inventory)
        self.rule(r"^metafield set\s+(?P<owner_id>\S+)\s+(?P<namespace>\S+)\s+(?P<key>\S+)\s+(?P<value>.+?)(?:\s+(?P<mtype>\w+))?$")(self._c_metafield)
        self.rule(r"^submit printful\s+(?P<order_id>\S+)$")(self._c_submit_printful)
        self.rule(r"^describe product\s+(?P<title>.+?)(?:\s+(?P<tone>gallery|minimal|bold))?$")(self._c_describe)
        self.rule(r"^analytics(?:\s+(?P<kind>weekly|top))?$")(self._c_analytics)
        self.rule(r"^sync printful$")(self._c_sync_printful)
        self.rule(r"^chat\s+(?P<text>.+)$")(self._c_chat)
        self.rule(r"^pending$")(self._c_pending)
        self.rule(r"^actions(?:\s+(?P<limit>\d+))?$")(self._c_actions)
        self.rule(r"^(?P<action>approve|reject)\s+(?P<action_id>\d+)$")(self._c_approve_reject)
        self.rule(r"^rollback\s+(?P<action_id>\d+)$")(self._c_rollback)
        self.rule(r"^webhook\s+(?P<topic>\S+)$")(self._c_webhook_sim)
        self.rule(r"^status$")(self._c_status)

    # ------------------------------------------------------------------
    # audit / guardrails
    # ------------------------------------------------------------------
    def _log_action(self, tool, args, reasoning, requires_approval, status="pending",
                    result=None, rollback=None, approved_by=None):
        cur = self.conn.execute(
            """INSERT INTO agent_actions
               (created_at, tool_name, args_json, result_json, reasoning, approved_by, status, rollback_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (now_iso(), tool, json.dumps(args), json.dumps(result) if result is not None else None,
             reasoning, approved_by, status,
             json.dumps(rollback) if rollback is not None else None),
        )
        self.conn.commit()
        return cur.lastrowid

    def execute_tool(self, tool, args, reasoning="", requires_approval=False):
        """Run a tool through the approval gate + audit log."""
        self.trace("think", "plan", "♢", f"tool={tool} requires_approval={requires_approval}",
                   {"args": args, "reasoning": reasoning})
        if requires_approval and not _AUTO_APPROVE:
            aid = self._log_action(tool, args, reasoning, True, status="pending")
            self.trace("observe", "plan", "↺", f"{tool} deferred for approval (action {aid})",
                       {"action_id": aid})
            return {"ok": False, "pending": aid,
                    "message": f"requires owner approval — run: approve {aid}"}

        rollback = self._capture_rollback(tool, args)
        try:
            if tool == "get_orders":
                data = self._api("shopify", f"orders:{args.get('limit')}", lambda: self.shopify.get_orders(args.get("limit", 10)))
            elif tool == "get_products":
                data = self._api("shopify", "products", self.shopify.get_products)
            elif tool == "get_low_stock":
                data = self._api("shopify", f"lowstock:{args.get('threshold')}", lambda: self.shopify.get_low_stock(args.get("threshold", 5)))
            elif tool == "update_product":
                data = self._api("shopify", f"update:{args.get('productId')}", lambda: self.shopify.update_product(args))
            elif tool == "create_discount":
                data = self._api("shopify", f"discount:{args.get('code')}", lambda: self.shopify.create_discount(**args))
            elif tool == "adjust_inventory":
                data = self._api("shopify", f"inv:{args.get('inventoryItemId')}:{args.get('delta')}", lambda: self.shopify.adjust_inventory(**args))
            elif tool == "write_metafield":
                data = self._api("shopify", f"mf:{args.get('ownerId')}:{args.get('key')}", lambda: self.shopify.write_metafield(**args))
            elif tool == "submit_printful_order":
                data = self._api("printful", f"order:{args.get('orderId')}", lambda: self._do_submit_printful(args["orderId"]))
            elif tool == "generate_product_description":
                data = self._generate_description(args)
            else:
                return {"ok": False, "error": f"unknown tool {tool}"}
        except Exception as exc:  # noqa: BLE001
            self._log_action(tool, args, reasoning, requires_approval, status="error", result={"error": str(exc)})
            self.trace("observe", "error", "↺", f"{tool} failed: {exc}", {"error": str(exc)})
            return {"ok": False, "error": str(exc)}

        self._log_action(tool, args, reasoning, requires_approval, status="executed",
                         result=data, rollback=rollback,
                         approved_by="auto" if (requires_approval and _AUTO_APPROVE) else None)
        self.trace("observe", "result", "⊨", f"{tool} executed",
                   data if isinstance(data, (dict, list)) else str(data))
        return {"ok": True, "tool": tool, "result": data}

    def _api(self, kind, key, fn):
        """Run an external call through the city API budget."""
        ok, reason = budget.allow(self.name, kind, key=key)
        if not ok:
            raise RuntimeError(reason)
        try:
            data = fn()
            budget.record(self.name, kind, key=key, ok=True)
            return data
        except Exception:
            budget.record(self.name, kind, key=key, ok=False)
            raise

    def _capture_rollback(self, tool, args):
        """Best-effort snapshot to reverse a destructive action."""
        if tool == "update_product" and args.get("productId"):
            try:
                cur = self.shopify.get_products(50)
                for e in cur.get("data", {}).get("products", {}).get("edges", []):
                    node = e["node"]
                    if node["id"] == args["productId"]:
                        return {"productId": node["id"], "title": node["title"],
                                "descriptionHtml": node.get("descriptionHtml")}
            except Exception:
                pass
        if tool == "adjust_inventory":
            return {**args, "delta": -args.get("delta", 0)}
        return None

    # ------------------------------------------------------------------
    # tool implementations
    # ------------------------------------------------------------------
    def _do_submit_printful(self, order_id):
        order = self.shopify.admin(
            "query($id: ID!) { order(id: $id) { id email subtotalPrice "
            "shippingAddress { name address1 city provinceCode countryCode zip } "
            "lineItems(first: 10) { edges { node { quantity variant { sku } } } } } }",
            {"id": order_id},
        )
        node = order.get("data", {}).get("order")
        if not node:
            return {"error": "order not found", "detail": order}
        return self.printful.submit_order(node)

    def _generate_description(self, args):
        from city.venice import json_chat
        title = args.get("productTitle", "")
        tone = args.get("tone", "gallery")
        prompt = (f"Write an SEO-optimized Shopify product description for a canvas wall art "
                  f"print titled '{title}'. Tone: {tone}. Include a short title tag, a 2-3 sentence "
                  f"description, and 6 comma-separated SEO tags. Respond strictly as JSON with keys "
                  f"descriptionHtml, tags (array).")
        res = json_chat("You are an e-commerce copywriter for Effata Picks canvas wall art.", prompt)
        if not res.get("ok"):
            return {"error": res.get("error", "venice call failed")}
        return {"description": res.get("parsed"), "raw": res.get("content")}

    # ------------------------------------------------------------------
    # command handlers
    # ------------------------------------------------------------------
    def _c_orders(self, limit=None):
        limit = int(limit) if limit else 10
        return self.execute_tool("get_orders", {"limit": limit}, "manual orders query")

    def _c_products(self):
        return self.execute_tool("get_products", {}, "manual products query")

    def _c_low_stock(self, threshold=None):
        t = int(threshold) if threshold else 5
        return self.execute_tool("get_low_stock", {"threshold": t}, "low stock check")

    def _c_update_product(self, product_id, field, value):
        inp = {"id": product_id}
        if field == "tags":
            inp["tags"] = [t.strip() for t in value.split(",")]
        else:
            inp[field] = value
        return self.execute_tool("update_product", inp, f"update {field}", requires_approval=False)

    def _c_discount(self, code, percentage, expires=None):
        args = {"code": code, "percentage": float(percentage)}
        if expires:
            args["expires_at"] = expires
        return self.execute_tool("create_discount", args, "create discount", requires_approval=True)

    def _c_inventory(self, item_id, loc_id, delta):
        args = {"inventory_item_id": item_id, "location_id": loc_id, "delta": int(delta)}
        return self.execute_tool("adjust_inventory", args, "adjust inventory", requires_approval=True)

    def _c_metafield(self, owner_id, namespace, key, value, mtype=None):
        return self.execute_tool("write_metafield",
                                 {"ownerId": owner_id, "namespace": namespace, "key": key,
                                  "value": value, "type": mtype or "string"},
                                 "write metafield", requires_approval=False)

    def _c_submit_printful(self, order_id):
        return self.execute_tool("submit_printful_order", {"orderId": order_id},
                                 "submit order to printful", requires_approval=False)

    def _c_describe(self, title, tone=None):
        return self.execute_tool("generate_product_description",
                                 {"productTitle": title, "tone": tone or "gallery"},
                                 "generate description")

    def _c_analytics(self, kind=None):
        if kind == "top":
            q = ("FROM sales SHOW product_title, sum(net_sales) AS revenue "
                 "SINCE -30d GROUP BY product_title ORDER BY revenue DESC LIMIT 10")
        else:
            q = ("FROM sales SHOW sum(net_sales) AS total_sales, count(orders) AS order_count "
                 "SINCE -7d UNTIL today ORDER BY total_sales DESC")
        return {"note": "ShopifyQL analytics", "query": q}

    def _c_sync_printful(self):
        if not self.printful.ready:
            return {"ok": False, "error": "Printful not configured"}
        return self.execute_tool_internal_printful()

    def execute_tool_internal_printful(self):
        ok, reason = budget.allow(self.name, "printful", key="store_products")
        if not ok:
            return {"ok": False, "error": reason}
        data = self.printful.list_store_products()
        budget.record(self.name, "printful", key="store_products", ok=True)
        return {"ok": True, "result": data}

    def _c_chat(self, text):
        return self.chat(text)

    def _c_pending(self):
        rows = self.conn.execute(
            "SELECT id, tool_name, args_json, created_at FROM agent_actions WHERE status='pending' ORDER BY id DESC"
        ).fetchall()
        return {"pending_actions": [dict(r) for r in rows]}

    def _c_actions(self, limit=None):
        limit = int(limit) if limit else 20
        rows = self.conn.execute(
            "SELECT id, tool_name, status, created_at FROM agent_actions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return {"actions": [dict(r) for r in rows]}

    def _c_approve_reject(self, action, action_id):
        action_id = int(action_id)
        row = self.conn.execute("SELECT * FROM agent_actions WHERE id=?", (action_id,)).fetchone()
        if not row:
            return {"ok": False, "error": "unknown action id"}
        if action == "reject":
            self.conn.execute("UPDATE agent_actions SET status='rejected' WHERE id=?", (action_id,))
            self.conn.commit()
            return {"ok": True, "status": "rejected"}
        # approve + execute (re-run the tool)
        args = json.loads(row["args_json"]) if row["args_json"] else {}
        self.conn.execute("UPDATE agent_actions SET status='approved', approved_by='owner' WHERE id=?", (action_id,))
        self.conn.commit()
        return self.execute_tool(row["tool_name"], args, row["reasoning"], requires_approval=False)

    def _c_rollback(self, action_id):
        return self.rollback_action(int(action_id))

    def _c_webhook_sim(self, topic):
        return {"note": "Use the live endpoint POST /api/shopify/webhook/<topic> with HMAC header. "
                        "Simulated handling below."}

    def _c_status(self):
        return self.report()

    # ------------------------------------------------------------------
    # chat / ReAct router
    # ------------------------------------------------------------------
    def chat(self, text):
        from city.venice import chat
        self.trace("think", "plan", "♢", f"chat query: {text[:160]}")
        tools = [
            "get_orders(limit)", "get_products()", "get_low_stock(threshold)",
            "update_product(id, field, value)", "create_discount(code, pct)",
            "adjust_inventory(item, loc, delta)", "submit_printful_order(orderId)",
            "generate_product_description(title, tone)",
        ]
        system = (
            "You are the store manager agent for Effata Picks (Shopify canvas wall art POD). "
            "Given the owner's request, either (a) reply with a single JSON object "
            "{\"tool\": <name>, \"args\": {...}} to invoke a tool, or (b) reply with plain advice text. "
            "Destructive tools (create_discount, adjust_inventory) need approval. Tools: " + ", ".join(tools)
        )
        res = chat([{"role": "system", "content": system}, {"role": "user", "content": text}],
                   max_tokens=400, temperature=0.3)
        if not res.get("ok"):
            return {"ok": False, "error": res.get("error")}
        content = (res.get("content") or "").strip()
        if content.startswith("{"):
            try:
                call = json.loads(content)
                tool = call.get("tool")
                known = {"get_orders", "get_products", "get_low_stock", "update_product",
                         "create_discount", "adjust_inventory", "submit_printful_order",
                         "generate_product_description"}
                if tool in known:
                    req_appr = tool in ("create_discount", "adjust_inventory")
                    self.trace("act", "tool", "⋔", f"chat dispatched tool {tool}", call.get("args", {}))
                    return self.execute_tool(tool, call.get("args", {}), "chat", requires_approval=req_appr)
            except json.JSONDecodeError:
                pass
        self.trace("observe", "result", "⊨", "chat returned plain advice")
        return {"ok": True, "reply": content}

    # ------------------------------------------------------------------
    # webhooks
    # ------------------------------------------------------------------
    def handle_webhook(self, topic, body):
        self.log("webhook", f"{topic} received", {"topic": topic})
        self.trace("think", "plan", "♢", f"webhook {topic} received", {"topic": topic})
        if topic == "orders/create":
            node = body.get("data", {}).get("object", body)
            # record locally + auto-submit to Printful
            try:
                self.conn.execute(
                    "INSERT INTO shopify_orders (product, revenue, cost, source, placed_at) "
                    "SELECT ?, COALESCE(json_extract(?,'$.amount'),0), 0, 'pod', ?",
                    ("order", json.dumps(node), now_iso()),
                )
                self.conn.commit()
            except Exception:
                pass
            oid = body.get("id") or (node.get("admin_graphql_api_id"))
            if oid:
                return self.execute_tool("submit_printful_order", {"orderId": oid},
                                         "webhook orders/create", requires_approval=False)
            return {"ok": True, "note": "order recorded, no id to submit"}
        if topic == "products/create":
            node = body.get("data", {}).get("object", body)
            title = node.get("title", "Untitled")
            return self.execute_tool("generate_product_description",
                                     {"productTitle": title}, "webhook products/create",
                                     requires_approval=False)
        if topic == "inventory_levels/update":
            return self.execute_tool("get_low_stock", {"threshold": 5}, "webhook inventory update")
        if topic in ("orders/paid", "orders/updated"):
            node = body.get("data", {}).get("object", body)
            revenue = float(node.get("total_price") or node.get("amount") or 0)
            oid = node.get("id") or body.get("id") or "unknown"
            try:
                self.conn.execute(
                    "INSERT INTO shopify_orders (product, revenue, cost, source, placed_at) "
                    "VALUES (?,?,?,?,?)",
                    (f"order:{oid}", revenue, 0, "paid", now_iso()),
                )
                self.conn.commit()
            except Exception:
                pass
            from city.orchestrator import EventBus
            EventBus.publish("shopify", "shopify.order_paid",
                             f"order {oid} paid ${revenue:.2f}",
                             {"order_id": oid, "revenue": revenue})
            return {"ok": True, "note": "order paid recorded + published"}
        if topic == "checkouts/create":
            node = body.get("data", {}).get("object", body)
            cid = node.get("id") or body.get("id")
            self.conn.execute(
                "INSERT OR IGNORE INTO shopify_checkouts (checkout_id, email, raw_json, created_at) VALUES (?,?,?,?)",
                (str(cid), node.get("email"), json.dumps(body), now_iso()),
            )
            self.conn.commit()
            return {"ok": True, "note": "checkout tracked for abandonment flow"}
        if topic == "orders/cancelled":
            return {"ok": True, "note": "order cancelled — manual restock logged"}
        if topic == "app/uninstalled":
            return {"ok": True, "note": "app uninstalled — cleanup logged"}
        return {"ok": True, "note": f"webhook {topic} accepted (no handler)"}

    # ------------------------------------------------------------------
    # scheduled workflows (called from app.py scheduler)
    # ------------------------------------------------------------------
    def daily_inventory_check(self):
        res = self.execute_tool("get_low_stock", {"threshold": 5}, "scheduled daily inventory")
        low = (res.get("result", {}) or {}).get("result") or res.get("result")
        if isinstance(low, list) and low:
            self.log("alert", f"{len(low)} products low on stock", {"low": low})
        return res

    def weekly_report(self):
        return self._c_analytics("weekly")

    def process_abandoned_carts(self):
        """Run from work_tick: email recovery for checkouts >1h old, once."""
        cutoff = (datetime.now(timezone.utc).timestamp() - 3600)
        rows = self.conn.execute(
            "SELECT checkout_id, email FROM shopify_checkouts WHERE recovered=0"
        ).fetchall()
        acted = 0
        for r in rows:
            # naive age check via created_at parse
            try:
                ts = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")).timestamp()
            except Exception:
                ts = 0
            if ts < cutoff:
                self.log("abandoned_cart", f"recovery due for {r['email'] or r['checkout_id']}")
                self.conn.execute("UPDATE shopify_checkouts SET recovered=1 WHERE checkout_id=?", (r["checkout_id"],))
                acted += 1
        if acted:
            self.conn.commit()
        return {"checked": len(rows), "recovered": acted}

    # ------------------------------------------------------------------
    # background tick
    # ------------------------------------------------------------------
    def work(self):
        if not self.shopify.ready:
            return
        try:
            self.process_abandoned_carts()
        except Exception as exc:  # noqa: BLE001
            self.log("error", f"work tick failed: {exc}")

    # ------------------------------------------------------------------
    # reporting
    # ------------------------------------------------------------------
    def report(self):
        row = self.conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(revenue),0) AS rev, COALESCE(SUM(cost),0) AS cost "
            "FROM shopify_orders"
        ).fetchone()
        pend = self.conn.execute("SELECT COUNT(*) AS c FROM agent_actions WHERE status='pending'").fetchone()["c"]
        return {
            "department": self.name,
            "subject": self.subject,
            "shopify_connected": self.shopify.ready,
            "printful_connected": self.printful.ready,
            "manual_orders_logged": row["n"],
            "revenue_usd": round(row["rev"], 2),
            "profit_usd": round(row["rev"] - row["cost"], 2),
            "pending_approvals": pend,
        }

    def dashboard_payload(self, conn):
        """Self-contained dashboard data for this building."""
        out = {}
        try:
            orders = conn.execute(
                "SELECT * FROM shopify_orders ORDER BY placed_at DESC LIMIT 30"
            ).fetchall()
            out["orders"] = [dict(r) for r in orders]
            top = conn.execute(
                "SELECT product, SUM(revenue) as rev FROM shopify_orders GROUP BY product ORDER BY rev DESC LIMIT 10"
            ).fetchall()
            out["top_products"] = [dict(r) for r in top]
        except Exception:
            out["orders"] = []
        return out
