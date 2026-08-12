"""
Virtual City — Flask entrypoint.

Each business function (crypto trading, flipping, Shopify, affiliates,
content, finance, sourcing, city hall) is a building/agent. Agents are
rule-based (no LLM). City state streams to the frontend in real time
over Server-Sent Events.
"""
import json
import time
import atexit
import os
import sqlite3
from datetime import datetime, timezone

from flask import Flask, render_template, request, jsonify, Response
from apscheduler.schedulers.background import BackgroundScheduler

from dotenv import load_dotenv
from city.db import init_db, get_db, close_db, get_raw_connection
from city.registry import discover_and_build, get_registry, get_agent
from city.city_grid import layout_city, get_city_state

load_dotenv()  # loads .env into os.environ before anything uses it

app = Flask(__name__)


def bootstrap():
    """Init schema, discover agents, lay out the city. Runs once at startup."""
    init_db()
    conn = get_raw_connection()
    agents = discover_and_build(conn)
    layout_city(conn, agents)
    conn.close()


bootstrap()
app.teardown_appcontext(close_db)


# --- Scheduler ---
def work_tick():
    """Called every 30 seconds — tells every agent to do autonomous work.

    External-API heavy work is gated by city.api_budget so ticks cannot
    burn rate limits on useless/repeated calls.
    """
    conn = get_raw_connection()
    try:
        from city.api_budget import budget
        registry = get_registry(conn)
        for agent in registry.values():
            try:
                agent.conn = conn
                # If agent is paused or already over budget, skip network-capable work
                snap = budget.snapshot(agent.name)
                if snap.get("paused_for", 0) > 0:
                    continue
                if snap.get("calls_last_min", 0) >= budget.max_per_min:
                    continue
                agent.work()
            except Exception as exc:
                print(f"[work_tick] {agent.name} error: {exc}")
    finally:
        conn.close()


def scheduled_meeting():
    conn = get_raw_connection()
    try:
        registry = get_registry(conn)
        city_hall = registry.get("city_hall")
        if city_hall:
            city_hall.conn = conn
            city_hall.hold_meeting()
        else:
            print("[scheduled_meeting] city_hall not found")
    except Exception as exc:
        print(f"[scheduled_meeting] error: {exc}")
    finally:
        conn.close()


scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(work_tick, "interval", seconds=30, id="work_tick")
scheduler.add_job(scheduled_meeting, "interval", hours=24, id="daily_meeting")
scheduler.start()
atexit.register(lambda: scheduler.shutdown(wait=False))


# --- Views ---
@app.route("/")
def index():
    return render_template("city.html")


@app.route("/api/city")
def api_city():
    conn = get_db()
    get_registry(conn)  # ensure agents are built against a live conn
    return jsonify(get_city_state(conn))


@app.route("/api/agent/<name>")
def api_agent_detail(name):
    conn = get_db()
    registry = get_registry(conn)
    agent = registry.get(name)
    if not agent:
        return jsonify({"error": f"unknown agent '{name}'"}), 404
    return jsonify(
        {
            "name": agent.name,
            "subject": agent.subject,
            "district": agent.district,
            "report": agent.report(),
            "recent_events": agent.recent_events(20),
        }
    )


@app.route("/api/building/<name>/dashboard")
def api_building_dashboard(name):
    """Per-building dashboard: richer data than the generic agent detail."""
    conn = get_db()
    registry = get_registry(conn)
    agent = registry.get(name)
    if not agent:
        return jsonify({"error": f"unknown agent '{name}'"}), 404

    report = agent.report() if hasattr(agent, "report") else {}
    events = agent.recent_events(30) if hasattr(agent, "recent_events") else []

    payload = {"name": agent.name, "subject": agent.subject, "report": report, "events": events}

    # --- Per-building dashboard data ---
    name = agent.name

    if name == "crypto_trading":
        try:
            positions = agent.conn.execute(
                "SELECT * FROM crypto_positions WHERE status != 'closed' ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
            payload["positions"] = [dict(r) for r in positions]
            row = agent.conn.execute(
                "SELECT SUM(pnl) as total_pnl, COUNT(*) as total_trades FROM crypto_positions WHERE status = 'closed'"
            ).fetchone()
            payload["total_pnl"] = row["total_pnl"] if row else 0
            payload["total_trades"] = row["total_trades"] if row else 0
        except Exception:
            payload["positions"] = []

    elif name == "btc_recovery":
        try:
            payload["address_count"] = agent.conn.execute(
                "SELECT COUNT(*) AS c FROM btc_addresses"
            ).fetchone()["c"]
            payload["key_count"] = agent.conn.execute(
                "SELECT COUNT(*) AS c FROM btc_private_keys"
            ).fetchone()["c"]
            payload["utxo_count"] = agent.conn.execute(
                "SELECT COUNT(*) AS c FROM btc_utxos WHERE spent_at IS NULL"
            ).fetchone()["c"]
            addrs = agent.conn.execute(
                "SELECT address, value_sat, confirmations FROM btc_utxos WHERE spent_at IS NULL ORDER BY value_sat DESC LIMIT 20"
            ).fetchall()
            payload["top_utxos"] = [dict(r) for r in addrs]
        except Exception:
            payload["top_utxos"] = []

    elif name == "shopify":
        try:
            orders = agent.conn.execute(
                "SELECT * FROM shopify_orders ORDER BY created_at DESC LIMIT 30"
            ).fetchall()
            payload["orders"] = [dict(r) for r in orders]
            top = agent.conn.execute(
                "SELECT product, SUM(revenue) as rev FROM shopify_orders GROUP BY product ORDER BY rev DESC LIMIT 10"
            ).fetchall()
            payload["top_products"] = [dict(r) for r in top]
        except Exception:
            payload["orders"] = []

    elif name == "product_flipping":
        try:
            items = agent.conn.execute(
                "SELECT * FROM flip_items ORDER BY created_at DESC LIMIT 30"
            ).fetchall()
            payload["inventory"] = [dict(r) for r in items]
        except Exception:
            payload["inventory"] = []

    elif name == "social_affiliates":
        try:
            camps = agent.conn.execute(
                "SELECT * FROM affiliate_campaigns ORDER BY created_at DESC LIMIT 20"
            ).fetchall()
            payload["campaigns"] = [dict(r) for r in camps]
        except Exception:
            payload["campaigns"] = []

    elif name == "content_creation":
        try:
            items = agent.conn.execute(
                "SELECT * FROM content_pipeline ORDER BY created_at DESC LIMIT 30"
            ).fetchall()
            payload["pipeline"] = [dict(r) for r in items]
        except Exception:
            payload["pipeline"] = []

    elif name == "content_automation":
        try:
            jobs = agent.conn.execute(
                "SELECT * FROM auto_queue ORDER BY created_at DESC LIMIT 30"
            ).fetchall()
            payload["queue"] = [dict(r) for r in jobs]
        except Exception:
            payload["queue"] = []

    elif name == "content_analytics":
        try:
            rows = agent.conn.execute(
                "SELECT * FROM content_video_generations ORDER BY created_at DESC LIMIT 30"
            ).fetchall()
            payload["videos"] = [dict(r) for r in rows]
        except Exception:
            payload["videos"] = []

    elif name == "sourcing_research":
        try:
            leads = agent.conn.execute(
                "SELECT * FROM source_leads ORDER BY score DESC LIMIT 30"
            ).fetchall()
            payload["leads"] = [dict(r) for r in leads]
        except Exception:
            payload["leads"] = []

    elif name == "market_data":
        try:
            prices = agent.conn.execute(
                "SELECT * FROM market_prices ORDER BY updated_at DESC LIMIT 30"
            ).fetchall()
            payload["prices"] = [dict(r) for r in prices]
        except Exception:
            payload["prices"] = []

    elif name == "finance_treasury":
        try:
            entries = agent.conn.execute(
                "SELECT * FROM treasury_ledger ORDER BY created_at DESC LIMIT 30"
            ).fetchall()
            payload["ledger"] = [dict(r) for r in entries]
        except Exception:
            payload["ledger"] = []

    elif name == "city_hall":
        try:
            meetings = agent.conn.execute(
                "SELECT * FROM meetings ORDER BY held_at DESC LIMIT 10"
            ).fetchall()
            payload["meetings"] = [dict(r) for r in meetings]
        except Exception:
            payload["meetings"] = []

    elif name == "signal":
        try:
            alerts = agent.conn.execute(
                "SELECT c.*, w.url, w.label FROM signal_changes c "
                "JOIN signal_watches w ON c.watch_id = w.id "
                "WHERE c.acknowledged = 0 ORDER BY c.detected_at DESC LIMIT 30"
            ).fetchall()
            payload["alerts"] = [dict(r) for r in alerts]
        except Exception:
            payload["alerts"] = []


    elif name == "web_check":
        try:
            rows = agent.conn.execute(
                "SELECT id, target_url, label, status, created_at, finished_at "
                "FROM webcheck_scans ORDER BY id DESC LIMIT 20"
            ).fetchall()
            payload["scans"] = [dict(r) for r in rows]
            from buildings.web_check import service as wc_service
            payload["service"] = wc_service.status()
        except Exception as exc:
            payload["scans"] = []
            payload["service_error"] = str(exc)

    elif name == "finance_building":
        try:
            for dept in ["crypto_trading", "market_data", "btc_recovery", "finance_treasury"]:
                d = registry.get(dept)
                if d and hasattr(d, "report"):
                    payload[dept] = d.report()
        except Exception:
            pass

    elif name == "media_building":
        try:
            for dept in ["content_creation", "content_automation", "content_analytics"]:
                d = registry.get(dept)
                if d and hasattr(d, "report"):
                    payload[dept] = d.report()
        except Exception:
            pass

    elif name == "research_building":
        try:
            d = registry.get("sourcing_research")
            if d and hasattr(d, "report"):
                payload["sourcing_research"] = d.report()
            sd = registry.get("scraper")
            if sd and hasattr(sd, "report"):
                payload["scraper"] = sd.report()
        except Exception:
            pass

    elif name == "scraper":
        try:
            results = agent.conn.execute(
                "SELECT id, url, title, status_code, tier_used, bytes_fetched, fetch_ms, scraped_at "
                "FROM scrape_results ORDER BY id DESC LIMIT 20"
            ).fetchall()
            payload["results_list"] = [dict(r) for r in results]
        except Exception:
            payload["results_list"] = []

    return jsonify(payload)


@app.route("/api/query", methods=["POST"])
def api_query():
    payload = request.get_json(force=True, silent=True) or {}
    agent_name = payload.get("agent")
    query = payload.get("query", "")
    if not agent_name:
        return jsonify({"error": "missing 'agent' field"}), 400

    conn = get_db()
    registry = get_registry(conn)
    agent = registry.get(agent_name)
    if not agent:
        return jsonify({"error": f"unknown agent '{agent_name}'"}), 404

    result = agent.process(query)
    return jsonify(result)


@app.route("/api/meeting", methods=["POST"])
def api_trigger_meeting():
    """Manually trigger City Hall's daily meeting (for demoing outside the 24h schedule)."""
    conn = get_db()
    registry = get_registry(conn)
    city_hall = registry.get("city_hall")
    if not city_hall:
        return jsonify({"error": "city_hall agent not found"}), 500
    return jsonify(city_hall.hold_meeting())


@app.route("/api/stream")
def api_stream():
    """Server-Sent Events: pushes the full city state whenever it changes."""

    def gen():
        conn = get_raw_connection()
        get_registry(conn)
        last_payload = None
        try:
            while True:
                state = get_city_state(conn)
                payload = json.dumps(state, sort_keys=True)
                if payload != last_payload:
                    yield f"data: {payload}\n\n"
                    last_payload = payload
                else:
                    yield ": keep-alive\n\n"
                time.sleep(1)
        finally:
            conn.close()

    return Response(gen(), mimetype="text/event-stream")


# --- Plans ---
PLANS_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "city_state.db")


def get_plan_conn():
    conn = sqlite3.connect(PLANS_DB_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/api/plan/<name>", methods=["GET"])
def api_get_plan(name):
    conn = get_plan_conn()
    try:
        row = conn.execute("SELECT * FROM plans WHERE agent_name = ?", (name,)).fetchone()
        if row:
            return jsonify(dict(row))
        return jsonify({"agent_name": name, "plan_text": "", "status": "active", "created_at": "", "updated_at": ""})
    finally:
        conn.close()


@app.route("/api/plan", methods=["POST"])
def api_save_plan():
    data = request.get_json(force=True, silent=True) or {}
    agent_name = data.get("agent_name")
    plan_text = data.get("plan_text", "")
    if not agent_name:
        return jsonify({"error": "missing agent_name"}), 400
    conn = get_plan_conn()
    try:
        now = datetime.now(timezone.utc).isoformat()
        existing = conn.execute("SELECT created_at FROM plans WHERE agent_name = ?", (agent_name,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE plans SET plan_text = ?, updated_at = ? WHERE agent_name = ?",
                (plan_text, now, agent_name),
            )
        else:
            conn.execute(
                "INSERT INTO plans (agent_name, plan_text, status, created_at, updated_at) VALUES (?, ?, 'active', ?, ?)",
                (agent_name, plan_text, now, now),
            )
        conn.commit()
        return jsonify({"ok": True, "agent_name": agent_name, "plan_text": plan_text, "updated_at": now})
    finally:
        conn.close()


@app.route("/api/plan/<name>/complete", methods=["POST"])
def api_complete_plan(name):
    conn = get_plan_conn()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("UPDATE plans SET status = 'completed', updated_at = ? WHERE agent_name = ?", (now, name))
        conn.commit()
        return jsonify({"ok": True, "status": "completed"})
    finally:
        conn.close()



# --- Web-Check room (proxied into the city) ---
@app.route("/room/webcheck/")
@app.route("/room/webcheck/<path:subpath>")
def room_webcheck(subpath=""):
    """Serve / embed the local web-check instance inside the city room."""
    from buildings.web_check import service as wc_service
    from flask import redirect, stream_with_context
    import urllib.request

    st = wc_service.status()
    if not st.get("running"):
        boot = wc_service.start()
        if not boot.get("ok") and not wc_service.is_up():
            boot_s = str(boot).replace("<", "&lt;")
            return (
                "<!doctype html><html><body style='background:#0b0c15;color:#9fef00;"
                "font-family:monospace;padding:2rem'>"
                "<h1>Web-Check room</h1>"
                "<p>Service is not running yet.</p>"
                f"<pre>{boot_s}</pre>"
                "<p>Or POST <code>/api/webcheck/start</code></p>"
                "</body></html>"
            ), 503

    target = st["url"].rstrip("/") + "/" + subpath
    qs = request.query_string.decode("utf-8", errors="replace")
    if qs:
        target = target + ("&" if "?" in target else "?") + qs

    # HTML entry: simple room shell with iframe (keeps city chrome later)
    if not subpath and request.args.get("embed") != "raw":
        inner = target
        if request.args.get("url"):
            # deep-link into results if GUI supports it; else open root
            inner = st["url"]
        return (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<title>Web-Check Room</title>"
            "<style>html,body{margin:0;height:100%;background:#0b0c15;color:#cfd8dc;"
            "font-family:system-ui,sans-serif}"
            "header{display:flex;gap:1rem;align-items:center;padding:.6rem 1rem;"
            "background:#141625;border-bottom:1px solid #2a2d45}"
            "header a{color:#9fef00;text-decoration:none}"
            "iframe{border:0;width:100%;height:calc(100% - 48px)}</style></head><body>"
            "<header><strong style='color:#9fef00'>Web-Check Room</strong>"
            "<a href='/'>← City</a>"
            f"<a href='{st['url']}' target='_blank' rel='noopener'>Open direct</a>"
            "<span style='opacity:.7'>Research Quarter</span></header>"
            f"<iframe src='{st['url']}/' title='web-check'></iframe>"
            "</body></html>"
        )

    try:
        req = urllib.request.Request(target, method=request.method)
        # forward minimal headers
        for h in ("Accept", "Content-Type", "User-Agent"):
            if h in request.headers:
                req.add_header(h, request.headers[h])
        data = request.get_data() if request.method in ("POST", "PUT", "PATCH") else None
        with urllib.request.urlopen(req, data=data, timeout=60) as resp:
            body = resp.read()
            headers = {"Content-Type": resp.headers.get("Content-Type", "application/octet-stream")}
            return Response(body, status=resp.status, headers=headers)
    except Exception as exc:
        return jsonify({"error": str(exc), "target": target}), 502


@app.route("/api/webcheck/start", methods=["POST"])
def api_webcheck_start():
    from buildings.web_check import service as wc_service
    return jsonify(wc_service.start())


@app.route("/api/webcheck/status")
def api_webcheck_status():
    from buildings.web_check import service as wc_service
    return jsonify(wc_service.status())



@app.route("/api/budget")
def api_budget_status():
    """City-wide external API budget snapshot."""
    from city.api_budget import budget
    agent = request.args.get("agent")
    return jsonify(budget.snapshot(agent))


@app.route("/api/budget/pause", methods=["POST"])
def api_budget_pause():
    from city.api_budget import budget
    data = request.get_json(force=True, silent=True) or {}
    agent = data.get("agent")
    seconds = int(data.get("seconds", 300))
    if not agent:
        return jsonify({"error": "missing agent"}), 400
    budget.pause(agent, seconds)
    return jsonify({"ok": True, "agent": agent, "paused_for": seconds})


@app.route("/api/budget/resume", methods=["POST"])
def api_budget_resume():
    from city.api_budget import budget
    data = request.get_json(force=True, silent=True) or {}
    agent = data.get("agent")
    if not agent:
        return jsonify({"error": "missing agent"}), 400
    budget.resume(agent)
    return jsonify({"ok": True, "agent": agent, "resumed": True})


if __name__ == "__main__":
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
