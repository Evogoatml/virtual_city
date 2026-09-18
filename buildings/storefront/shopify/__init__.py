"""Shopify building — self-contained.

Owns its HTTP routes (Flask blueprint) and its scheduler jobs so the
building's wiring lives next to its logic instead of in app.py.
"""
from flask import Blueprint, request, jsonify
import json
import os
import re
import threading

shopify_bp = Blueprint("shopify", __name__)


def _write_env(kv: dict):
    """Update/append key=value pairs in the local .env file (persists across restarts)."""
    path = ".env"
    try:
        with open(path) as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        lines = []
    out, seen = [], set()
    for ln in lines:
        m = re.match(r"^\s*([A-Z0-9_]+)\s*=", ln)
        if m and m.group(1) in kv:
            out.append(f"{m.group(1)}={kv[m.group(1)]}")
            seen.add(m.group(1))
        else:
            out.append(ln)
    for k, v in kv.items():
        if k not in seen:
            out.append(f"{k}={v}")
    with open(path, "w") as f:
        f.write("\n".join(out).rstrip() + "\n")


@shopify_bp.route("/connect", methods=["POST"])
def connect():
    """One-call setup: accept credentials, apply live, persist to .env, register webhooks."""
    from city.db import get_db
    from city.registry import get_registry

    data = request.get_json(force=True, silent=True) or {}
    domain = data.get("shop_domain") or data.get("domain") or ""
    token = data.get("access_token") or data.get("admin_token") or ""
    base = data.get("base_url") or data.get("webhook_base_url") or ""
    if not domain or not token:
        return jsonify({"error": "shop_domain and access_token are required"}), 400

    os.environ["SHOPIFY_STORE_DOMAIN"] = domain
    os.environ["SHOPIFY_ADMIN_API_ACCESS_TOKEN"] = token
    if base:
        os.environ["SHOPIFY_WEBHOOK_BASE_URL"] = base

    conn = get_db()
    agent = get_registry(conn).get("shopify")
    client = getattr(agent, "shopify", None) if agent else None
    if client:
        client.domain = domain
        client.admin_token = token
        client.webhook_base_url = base
        client.ready = True

    kv = {"SHOPIFY_STORE_DOMAIN": domain, "SHOPIFY_ADMIN_API_ACCESS_TOKEN": token}
    if base:
        kv["SHOPIFY_WEBHOOK_BASE_URL"] = base
    _write_env(kv)

    topics = ["orders/create", "orders/paid", "orders/updated",
              "products/create", "inventory_levels/update", "checkouts/create"]
    results = []
    if client:
        for t in topics:
            addr = f"{(base or '').rstrip('/')}/api/shopify/webhook/{t}"
            results.append({"topic": t, "result": client.register_webhook(addr, t)})

    return jsonify({"ok": True, "shopify_ready": bool(client and client.ready), "results": results})


@shopify_bp.route("/webhook/<path:topic>", methods=["POST"])
def webhook(topic):
    """Receive a Shopify webhook; HMAC-verified, then ack-first + process async.

    Returns 200 immediately so Shopify's 5s delivery timeout is never hit;
    the actual handling runs in a background thread with its own DB connection.
    """
    from city.db import get_db, get_raw_connection
    from city.registry import get_registry

    raw = request.get_data()
    hmac_header = request.headers.get("X-Shopify-Hmac-SHA256", "")
    conn = get_db()
    agent = get_registry(conn).get("shopify")
    if not agent:
        return jsonify({"error": "shopify agent not found"}), 500
    if not agent.shopify.verify_webhook(raw, hmac_header):
        return jsonify({"error": "invalid signature"}), 401
    try:
        body = json.loads(raw or b"{}")
    except Exception:
        body = {}

    def _process():
        c = get_raw_connection()
        try:
            agent.conn = c
            agent.handle_webhook(topic, body)
        except Exception as exc:
            try:
                agent.log("webhook_error", f"{topic}: {exc}")
            except Exception:
                pass
        finally:
            c.close()

    threading.Thread(target=_process, daemon=True).start()
    return jsonify({"ok": True, "accepted": topic})


@shopify_bp.route("/automate/respond", methods=["GET", "POST"])
def automate_respond():
    """Respond playbook: answer a store question (read-only)."""
    from buildings.storefront.shopify.automate import run_respond
    from city.db import get_db
    from city.registry import get_registry

    data = request.get_json(force=True, silent=True) or {}
    query = data.get("query") or request.args.get("query") or "status"
    notify = bool(data.get("notify") or request.args.get("notify"))
    conn = get_db()
    agent = get_registry(conn).get("shopify")
    if agent:
        agent.conn = conn
    report = run_respond(
        query=query,
        shopify=getattr(agent, "shopify", None) if agent else None,
        department=agent,
        notify=notify,
    )
    return jsonify(report)


@shopify_bp.route("/automate/schedule", methods=["GET", "POST"])
def automate_schedule():
    """Schedule playbook: daily health, optional weekly sales block."""
    from buildings.storefront.shopify.automate import run_schedule
    from city.db import get_db
    from city.registry import get_registry

    data = request.get_json(force=True, silent=True) or {}
    weekly = bool(data.get("weekly") or request.args.get("weekly"))
    notify = True
    if "notify" in data:
        notify = bool(data.get("notify"))
    elif request.args.get("notify") in ("0", "false", "no"):
        notify = False
    conn = get_db()
    agent = get_registry(conn).get("shopify")
    if agent:
        agent.conn = conn
    report = run_schedule(
        weekly=weekly,
        shopify=getattr(agent, "shopify", None) if agent else None,
        department=agent,
        notify=notify,
    )
    return jsonify(report)


@shopify_bp.route("/register-webhooks", methods=["POST"])
def register_webhooks():
    """Create Shopify webhook subscriptions via the Admin API.

    Body: {"base_url": "https://your-public-host", "topics": [...]}
    or set SHOPIFY_WEBHOOK_BASE_URL in .env and omit base_url.
    """
    from city.db import get_db
    from city.registry import get_registry

    data = request.get_json(force=True, silent=True) or {}
    base_url = data.get("base_url") or os.environ.get("SHOPIFY_WEBHOOK_BASE_URL")
    if not base_url:
        return jsonify({"error": "set SHOPIFY_WEBHOOK_BASE_URL or pass base_url"}), 400
    topics = data.get("topics") or [
        "orders/create", "orders/paid", "orders/updated",
        "products/create", "inventory_levels/update", "checkouts/create",
    ]
    conn = get_db()
    agent = get_registry(conn).get("shopify")
    if not agent:
        return jsonify({"error": "shopify agent not found"}), 500
    results = []
    for t in topics:
        address = f"{base_url.rstrip('/')}/api/shopify/webhook/{t}"
        results.append({"topic": t, "result": agent.shopify.register_webhook(address, t)})
    return jsonify({"ok": True, "results": results})


def register_scheduler(scheduler):
    """Register the shopify building's scheduled jobs on the shared scheduler."""
    from apscheduler.triggers.cron import CronTrigger
    from city.db import get_raw_connection
    from city.registry import get_registry

    def daily_inventory():
        conn = get_raw_connection()
        try:
            agent = get_registry(conn).get("shopify")
            if agent:
                agent.conn = conn
                agent.daily_inventory_check()
        except Exception as exc:
            print(f"[shopify_daily_inventory] error: {exc}")
        finally:
            conn.close()

    def weekly_report():
        conn = get_raw_connection()
        try:
            agent = get_registry(conn).get("shopify")
            if agent:
                agent.conn = conn
                agent.weekly_report()
        except Exception as exc:
            print(f"[shopify_weekly_report] error: {exc}")
        finally:
            conn.close()

    scheduler.add_job(daily_inventory, CronTrigger(hour=8, minute=0), id="shopify_inventory")
    scheduler.add_job(weekly_report, CronTrigger(day_of_week="mon", hour=9, minute=0), id="shopify_weekly")
