"""Shopify Respond + Schedule playbooks for Effata Picks.

Respond  — interpret a Slack / operator query and run read-only store ops.
Schedule — daily inventory, abandoned-cart sweep, public storefront health,
           and (on weekly) a sales snapshot.

Standalone (Cursor automations / CLI):

    python -m buildings.storefront.shopify.automate respond --query "low stock"
    python -m buildings.storefront.shopify.automate schedule
    python -m buildings.storefront.shopify.automate schedule --weekly

Inside the city the same functions are used by the shopify department
commands, HTTP routes, and APScheduler jobs.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Optional


DEFAULT_STORE_DOMAIN = "effataprints.myshopify.com"
DEFAULT_HEALTH_PATHS = (
    "/",
    "/collections/all",
    "/pages/about-us",
    "/policies/shipping-policy",
    "/policies/refund-policy",
    "/policies/privacy-policy",
    "/cart",
)
PASSWORD_MARKERS = (
    "storefront_password",
    "password-page",
    "opening soon",
    "this store is password protected",
)
USER_AGENT = "virtual-city-shopify-automate/1.0"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def storefront_base_url() -> str:
    explicit = _env("SHOPIFY_STOREFRONT_URL")
    if explicit:
        return explicit.rstrip("/")
    domain = (
        _env("SHOPIFY_STORE_DOMAIN")
        or _env("SHOPIFY_SHOP_DOMAIN")
        or DEFAULT_STORE_DOMAIN
    )
    domain = domain.replace("https://", "").replace("http://", "").strip("/")
    return f"https://{domain}"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# Public storefront health (works without an admin token)
# ---------------------------------------------------------------------------
def check_storefront_health(
    base_url: Optional[str] = None,
    paths: Optional[tuple[str, ...]] = None,
    opener: Optional[Callable[..., Any]] = None,
) -> dict:
    """GET the public storefront pages and flag 404s / password walls."""
    base = (base_url or storefront_base_url()).rstrip("/")
    paths = paths or DEFAULT_HEALTH_PATHS
    fetch = opener or _http_get
    pages = []
    broken = []
    password = False
    for path in paths:
        url = base if path == "/" else f"{base}{path}"
        page = fetch(url)
        pages.append(page)
        if page.get("password"):
            password = True
        if not page.get("ok"):
            broken.append(page)
    return {
        "ok": not broken and not password,
        "base_url": base,
        "checked": len(pages),
        "broken": broken,
        "password_wall": password,
        "pages": pages,
    }


def _http_get(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(80_000).decode("utf-8", errors="replace")
            status = resp.getcode()
            final = resp.geturl()
    except urllib.error.HTTPError as exc:
        body = exc.read(80_000).decode("utf-8", errors="replace") if exc.fp else ""
        status = exc.code
        final = url
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "url": url, "error": str(exc), "password": False}

    lowered = body.lower()
    password = any(marker in lowered for marker in PASSWORD_MARKERS)
    ok = 200 <= status < 400 and not password
    return {
        "ok": ok,
        "url": url,
        "final_url": final,
        "status": status,
        "password": password,
        "title": _html_title(body),
    }


def _html_title(html: str) -> str:
    start = html.lower().find("<title")
    if start < 0:
        return ""
    gt = html.find(">", start)
    end = html.lower().find("</title>", gt)
    if gt < 0 or end < 0:
        return ""
    return " ".join(html[gt + 1 : end].split())[:120]


# ---------------------------------------------------------------------------
# Admin / department snapshots (token optional)
# ---------------------------------------------------------------------------
def _client():
    from buildings.storefront.shopify.clients import ShopifyClient

    return ShopifyClient()


def snapshot_connection(shopify=None) -> dict:
    client = shopify or _client()
    return {
        "domain": getattr(client, "domain", "") or DEFAULT_STORE_DOMAIN,
        "admin_ready": bool(getattr(client, "ready", False)),
        "storefront_url": storefront_base_url(),
    }


def snapshot_orders(shopify=None, limit: int = 8) -> dict:
    client = shopify or _client()
    if not getattr(client, "ready", False):
        return {"ok": False, "skipped": True, "reason": "Shopify admin not connected"}
    data = client.get_orders(limit)
    if data.get("errors"):
        return {"ok": False, "errors": data["errors"]}
    edges = (
        data.get("data", {}).get("orders", {}).get("edges", [])
        if isinstance(data, dict)
        else []
    )
    orders = []
    for edge in edges:
        node = edge.get("node", edge)
        money = (node.get("totalPriceSet") or {}).get("shopMoney") or {}
        orders.append({
            "name": node.get("name"),
            "email": node.get("email"),
            "total": money.get("amount"),
            "currency": money.get("currencyCode"),
            "fulfillment": node.get("displayFulfillmentStatus"),
            "financial": node.get("displayFinancialStatus"),
            "created_at": node.get("createdAt"),
        })
    return {"ok": True, "count": len(orders), "orders": orders}


def snapshot_products(shopify=None, limit: int = 20) -> dict:
    client = shopify or _client()
    if not getattr(client, "ready", False):
        return {"ok": False, "skipped": True, "reason": "Shopify admin not connected"}
    data = client.get_products(limit)
    if data.get("errors"):
        return {"ok": False, "errors": data["errors"]}
    edges = (
        data.get("data", {}).get("products", {}).get("edges", [])
        if isinstance(data, dict)
        else []
    )
    products = []
    for edge in edges:
        node = edge.get("node", edge)
        variants = node.get("variants", {}).get("edges", [])
        products.append({
            "title": node.get("title"),
            "status": node.get("status"),
            "tags": node.get("tags") or [],
            "variants": len(variants),
        })
    return {"ok": True, "count": len(products), "products": products}


def snapshot_low_stock(shopify=None, threshold: int = 5) -> dict:
    client = shopify or _client()
    if not getattr(client, "ready", False):
        return {"ok": False, "skipped": True, "reason": "Shopify admin not connected"}
    items = client.get_low_stock(threshold)
    if isinstance(items, dict) and items.get("errors"):
        return {"ok": False, "errors": items["errors"]}
    return {"ok": True, "threshold": threshold, "count": len(items), "items": items}


def snapshot_abandoned_carts(department=None) -> dict:
    if department is None:
        return {"ok": False, "skipped": True, "reason": "city department not attached"}
    try:
        return {"ok": True, **department.process_abandoned_carts()}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def snapshot_analytics(department=None, kind: str = "weekly") -> dict:
    if department is not None and hasattr(department, "_c_analytics"):
        return {"ok": True, **department._c_analytics(kind)}
    query = (
        "FROM sales SHOW sum(net_sales) AS total_sales, count(orders) AS order_count "
        "SINCE -7d UNTIL today ORDER BY total_sales DESC"
    )
    return {"ok": True, "note": "ShopifyQL analytics (run when admin token is connected)", "query": query}


# ---------------------------------------------------------------------------
# Intent routing
# ---------------------------------------------------------------------------
_INTENT_KEYWORDS = (
    ("orders", ("order", "sale", "sold", "purchase", "fulfill")),
    ("inventory", ("stock", "inventory", "low stock", "sku")),
    ("products", ("product", "catalog", "listing", "collection")),
    ("analytics", ("analytics", "report", "weekly", "revenue", "sales")),
    ("carts", ("cart", "abandon")),
    ("health", ("health", "status", "check", "broken", "404", "password")),
)


def detect_intents(query: str) -> list[str]:
    q = (query or "").strip().lower()
    if not q or q in ("status", "report", "help", "respond"):
        return ["health", "inventory"]
    hits = [name for name, words in _INTENT_KEYWORDS if any(w in q for w in words)]
    return hits or ["health", "inventory"]


# ---------------------------------------------------------------------------
# Playbooks
# ---------------------------------------------------------------------------
def run_respond(
    query: str = "status",
    shopify=None,
    department=None,
    notify: bool = False,
) -> dict:
    """Respond playbook: answer a store question with live checks."""
    intents = detect_intents(query)
    sections: dict[str, Any] = {"connection": snapshot_connection(shopify)}
    if "health" in intents:
        sections["health"] = check_storefront_health()
    if "orders" in intents:
        sections["orders"] = snapshot_orders(shopify)
    if "products" in intents:
        sections["products"] = snapshot_products(shopify)
    if "inventory" in intents:
        sections["inventory"] = snapshot_low_stock(shopify)
    if "analytics" in intents:
        sections["analytics"] = snapshot_analytics(department)
    if "carts" in intents:
        sections["carts"] = snapshot_abandoned_carts(department)

    report = {
        "mode": "respond",
        "query": query,
        "intents": intents,
        "ran_at": now_iso(),
        "sections": sections,
        "ok": _sections_ok(sections),
    }
    report["markdown"] = format_report(report)
    if notify:
        report["notified"] = notify_slack(report["markdown"])
    return report


def run_schedule(
    weekly: bool = False,
    shopify=None,
    department=None,
    notify: bool = True,
) -> dict:
    """Schedule playbook: daily ops, plus weekly analytics when asked."""
    sections: dict[str, Any] = {
        "connection": snapshot_connection(shopify),
        "health": check_storefront_health(),
        "inventory": snapshot_low_stock(shopify),
        "carts": snapshot_abandoned_carts(department),
    }
    if weekly:
        sections["orders"] = snapshot_orders(shopify, limit=15)
        sections["analytics"] = snapshot_analytics(department, "weekly")

    report = {
        "mode": "schedule",
        "weekly": weekly,
        "ran_at": now_iso(),
        "sections": sections,
        "ok": _sections_ok(sections),
    }
    report["markdown"] = format_report(report)
    if notify:
        report["notified"] = notify_slack(report["markdown"])
    return report


def _sections_ok(sections: dict) -> bool:
    for key, value in sections.items():
        if key == "connection" or not isinstance(value, dict):
            continue
        if value.get("skipped"):
            continue
        if value.get("ok") is False:
            return False
    return True


# ---------------------------------------------------------------------------
# Formatting + Slack
# ---------------------------------------------------------------------------
def format_report(report: dict) -> str:
    mode = report.get("mode", "report")
    title = "Shopify schedule" if mode == "schedule" else "Shopify respond"
    if report.get("weekly"):
        title += " (weekly)"
    lines = [f"*{title}* — {report.get('ran_at', now_iso())}"]
    if report.get("query"):
        lines.append(f"Query: {report['query']}")
    if report.get("intents"):
        lines.append("Intents: " + ", ".join(report["intents"]))

    sections = report.get("sections") or {}
    conn = sections.get("connection") or {}
    lines.append(
        f"Store: `{conn.get('domain') or DEFAULT_STORE_DOMAIN}` · "
        f"admin {'connected' if conn.get('admin_ready') else 'not connected'}"
    )

    health = sections.get("health")
    if health:
        if health.get("password_wall"):
            lines.append("Health: password wall is up — storefront is not public")
        elif health.get("broken"):
            bits = [f"{p.get('status', '?')} {p.get('url')}" for p in health["broken"]]
            lines.append("Health: " + "; ".join(bits))
        else:
            lines.append(f"Health: {health.get('checked', 0)} public pages ok")

    inventory = sections.get("inventory")
    if inventory:
        if inventory.get("skipped"):
            lines.append(f"Inventory: skipped ({inventory.get('reason')})")
        elif inventory.get("ok") is False:
            lines.append(f"Inventory: error {inventory.get('errors') or inventory.get('error')}")
        elif inventory.get("count"):
            preview = ", ".join(
                f"{i.get('product')} ({i.get('inventory')})"
                for i in inventory.get("items", [])[:6]
            )
            lines.append(f"Low stock ({inventory['count']}): {preview}")
        else:
            lines.append("Inventory: no SKUs at or below threshold")

    orders = sections.get("orders")
    if orders:
        if orders.get("skipped"):
            lines.append(f"Orders: skipped ({orders.get('reason')})")
        elif orders.get("ok") is False:
            lines.append(f"Orders: error {orders.get('errors') or orders.get('error')}")
        elif orders.get("orders"):
            preview = ", ".join(
                f"{o.get('name')} ${o.get('total') or '?'}"
                for o in orders["orders"][:5]
            )
            lines.append(f"Recent orders ({orders.get('count')}): {preview}")
        else:
            lines.append("Orders: none returned")

    products = sections.get("products")
    if products:
        if products.get("skipped"):
            lines.append(f"Products: skipped ({products.get('reason')})")
        elif products.get("ok") is False:
            lines.append(f"Products: error {products.get('errors') or products.get('error')}")
        else:
            lines.append(f"Products: {products.get('count', 0)} listed")

    carts = sections.get("carts")
    if carts:
        if carts.get("skipped"):
            lines.append(f"Abandoned carts: skipped ({carts.get('reason')})")
        elif carts.get("ok") is False:
            lines.append(f"Abandoned carts: error {carts.get('error')}")
        else:
            lines.append(
                f"Abandoned carts: checked {carts.get('checked', 0)}, "
                f"marked {carts.get('recovered', 0)}"
            )

    analytics = sections.get("analytics")
    if analytics:
        if analytics.get("query"):
            lines.append(f"Analytics query: `{analytics['query']}`")
        if analytics.get("note"):
            lines.append(analytics["note"])

    if not report.get("ok"):
        lines.append("Outcome: needs attention")
    elif not conn.get("admin_ready"):
        lines.append("Outcome: public storefront checked; connect a Shopify admin token for orders/stock")
    else:
        lines.append("Outcome: clean")
    return "\n".join(lines)


def notify_slack(markdown: str, webhook_url: Optional[str] = None) -> dict:
    url = webhook_url or _env("SLACK_WEBHOOK_URL") or _env("SHOPIFY_SLACK_WEBHOOK_URL")
    if not url:
        return {"ok": False, "skipped": True, "reason": "SLACK_WEBHOOK_URL not set"}
    payload = json.dumps({"text": markdown}).encode()
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"ok": 200 <= resp.getcode() < 300, "status": resp.getcode()}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Shopify respond + schedule automations")
    parser.add_argument("mode", choices=("respond", "schedule"), help="Playbook to run")
    parser.add_argument("--query", default="status", help="Respond query (Slack text)")
    parser.add_argument("--weekly", action="store_true", help="Include the weekly sales block")
    parser.add_argument("--notify", action="store_true", help="Force Slack webhook notify")
    parser.add_argument("--no-notify", action="store_true", help="Skip Slack notify")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of markdown")
    args = parser.parse_args(argv)

    notify = bool(args.notify) if args.mode == "respond" else not args.no_notify
    if args.mode == "respond":
        report = run_respond(query=args.query, notify=notify)
    else:
        report = run_schedule(weekly=args.weekly, notify=notify)

    if args.json:
        printable = {k: v for k, v in report.items() if k != "markdown"}
        print(json.dumps(printable, indent=2, default=str))
    else:
        print(report["markdown"])
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
