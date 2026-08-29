"""Controll Panel — the massive computer command center of Virtual City.

A single building that connects all routes, subscribes to every inter-building
event, and serves as the central monitoring + command surface. Think of it as
Mission Control: it wires up the EventBus subscriptions, tracks the full
pipeline flow, and gives the operator a unified view of every system component.

Layout (per city_grid): sits at the center of the grid, connecting the supply
pipeline (supply_scout → product_studio → storefront → treasury) with the
finance, media, and research hubs.
"""
from city.agent import Agent
from city.db import now_iso, log_event
import json


class ControllPanelAgent(Agent):
    """Central command and control building for the entire Virtual City."""

    name = "controll_panel"
    subject = "Controll Panel"
    district = "Command Center"
    color = "#0d47a1"  # Deep blue — command center

    job_title = "Command Center Operator"
    mission = "Monitor and route all city traffic — track events, subscriptions, " \
               "pipeline health, and system-wide metrics from a single console."

    cog_interval = 60  # tick every minute

    # The canonical pipeline routes (mirrors city_grid.PIPELINE)
    PIPELINE_ROUTES = [
        ("supply_scout", "product_studio", "lead.approved"),
        ("product_studio", "storefront", "listing.drafted"),
        ("storefront", "treasury", "shopify.order_paid"),
    ]

    # Container buildings that aggregate departments
    HUB_BUILDINGS = ["finance_building", "media_building", "research_building"]

    def setup_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS route_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                destination TEXT NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT,
                data_json TEXT,
                received_at TEXT NOT NULL,
                acknowledged INTEGER DEFAULT 0
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS controll_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name TEXT NOT NULL,
                metric_value REAL,
                recorded_at TEXT NOT NULL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS system_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                building TEXT NOT NULL,
                severity TEXT NOT NULL,  -- info / warning / error
                message TEXT NOT NULL,
                acknowledged INTEGER DEFAULT 0,
                detected_at TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def register_rules(self):
        self.rule(r"^status$")(self._status)
        self.rule(r"^report$")(self._report)
        self.rule(r"^routes$")(self._routes)
        self.rule(r"^subscriptions$")(self._subscriptions)
        self.rule(r"^pipeline$")(self._pipeline_health)
        self.rule(r"^alerts$")(self._alerts)
        self.rule(r"^acknowledge alert\s+(?P<alert_id>\d+)$")(self._ack_alert)
        self.rule(r"^route log(?:s)?(?:\s+(?P<limit>\d+))?$")(self._route_log)
        self.rule(r"^metrics$")(self._metrics)
        self.rule(r"^command\s+(?P<target>\w+)\s+(?P<query>.+)$")(self._command)
        self.rule(r"^wire routes$")(self._wire_routes)

    # ── rule handlers ─────────────────────────────────────────────

    def _status(self):
        return self.report()

    def report(self):
        """Summary for City Hall's daily meeting."""
        metrics = self._compute_metrics()
        return {
            "agent": self.name,
            "subject": self.subject,
            "district": self.district,
            "mode": "command_center",
            "metrics": metrics,
        }

    def _report(self):
        return self.report()

    def _routes(self):
        """Show all known pipeline routes and their health."""
        rows = self.conn.execute(
            """SELECT source, destination, event_type, COUNT(*) AS event_count,
                  MAX(received_at) AS last_seen
               FROM route_logs
               GROUP BY source, destination, event_type
               ORDER BY last_seen DESC"""
        ).fetchall()
        route_status = []
        for src, dst, evt, count, last in rows:
            route_status.append({
                "source": src, "destination": dst,
                "event_type": evt, "count": count, "last_seen": last,
            })
        return {
            "agent": self.name,
            "pipeline_routes": self.PIPELINE_ROUTES,
            "observed_routes": route_status,
        }

    def _subscriptions(self):
        """Show all EventBus subscriptions in the city."""
        rows = self.conn.execute(
            """SELECT subscriber_name, publisher_name, event_type, created_at
               FROM subscriptions
               ORDER BY publisher_name, event_type"""
        ).fetchall()
        return {
            "agent": self.name,
            "subscriptions": [dict(r) for r in rows],
            "count": len(rows),
        }

    def _pipeline_health(self):
        """Check the health of each pipeline route — are events flowing?"""
        from city.db import now_iso
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(hours=1)).isoformat()
        results = []
        for src, dst, evt in self.PIPELINE_ROUTES:
            row = self.conn.execute(
                """SELECT COUNT(*) AS recent_count FROM route_logs
                   WHERE source = ? AND event_type = ? AND received_at > ?""",
                (src, evt, cutoff),
            ).fetchone()
            recent = row["recent_count"] if row else 0
            status = "healthy" if recent > 0 else "stale"
            results.append({
                "route": f"{src} -> {dst} ({evt})",
                "events_last_hour": recent,
                "status": status,
            })
        return {
            "agent": self.name,
            "pipeline_health": results,
        }

    def _alerts(self):
        rows = self.conn.execute(
            """SELECT id, building, severity, message, acknowledged, detected_at
               FROM system_alerts
               ORDER BY detected_at DESC LIMIT 50"""
        ).fetchall()
        return {
            "agent": self.name,
            "alerts": [dict(r) for r in rows],
        }

    def _ack_alert(self, alert_id):
        self.conn.execute(
            "UPDATE system_alerts SET acknowledged = 1 WHERE id = ?", (int(alert_id),)
        )
        self.conn.commit()
        return {"ok": True, "acknowledged": int(alert_id)}

    def _route_log(self, limit=None):
        limit = int(limit) if limit else 30
        rows = self.conn.execute(
            """SELECT id, source, destination, event_type, message, received_at
               FROM route_logs
               ORDER BY received_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return {
            "agent": self.name,
            "route_logs": [dict(r) for r in rows],
        }

    def _metrics(self):
        rows = self.conn.execute(
            """SELECT metric_name, metric_value, recorded_at
               FROM controll_metrics
               ORDER BY recorded_at DESC LIMIT 50"""
        ).fetchall()
        return {
            "agent": self.name,
            "metrics": [dict(r) for r in rows],
        }

    def _command(self, target, query):
        """Forward a command to another building and route the response back."""
        from city.registry import get_agent
        agent = get_agent(target)
        if agent is None:
            return {"error": f"unknown building: {target}"}
        try:
            agent.conn = self.conn
            result = agent.process(query)
        except Exception as exc:
            result = {"error": str(exc)}
        return {"agent": target, "command": query, "result": result}

    def _wire_routes(self):
        """Ensure all canonical pipeline EventBus subscriptions exist."""
        from city.orchestrator import EventBus
        wired = 0
        for src, dst, evt in self.PIPELINE_ROUTES:
            EventBus.subscribe(dst, src, evt)
            self.log("route", f"wired {src} -> {dst} on {evt}")
            wired += 1
        return {"ok": True, "routes_wired": wired}

    # ── event handling ──
    def handle_event(self, event_type, message="", data=None):
        """Observe every event that flows through the city — log it for analysis."""
        data = data or {}
        source = data.get("source", "unknown")
        destination = self.name  # events addressed to us

        self.conn.execute(
            """INSERT INTO route_logs
               (source, destination, event_type, message, data_json, received_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (source, destination, event_type, message,
             json.dumps(data) if isinstance(data, (dict, list)) else str(data),
             now_iso()),
        )

        # Auto-alert on pipeline events that don't get acknowledged downstream
        if event_type in ("shopify.order_paid", "lead.approved", "listing.drafted"):
            self._maybe_alert(event_type, message, data)

        self.conn.commit()
        return None

    def _maybe_alert(self, event_type, message, data):
        """Flag unusual pipeline events."""
        pass  # could implement heuristics here

    # ── metrics ──
    def _compute_metrics(self):
        """Compute system-wide metrics and persist them."""
        from city.registry import get_registry
        registry = get_registry(self.conn)

        active_buildings = len(registry)
        error_buildings = 0
        for agent in registry.values():
            st = agent.status if hasattr(agent, "status") else "unknown"
            if st == "error":
                error_buildings += 1

        # Event rate: events in last hour
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(hours=1)).isoformat()
        recent_events = self.conn.execute(
            "SELECT COUNT(*) AS n FROM events WHERE timestamp > ?", (cutoff,)
        ).fetchone()
        event_rate = recent_events["n"] if recent_events else 0

        # Route log volume
        route_count = self.conn.execute(
            "SELECT COUNT(*) AS n FROM route_logs"
        ).fetchone()
        route_logs = route_count["n"] if route_count else 0

        metrics = {
            "active_buildings": active_buildings,
            "error_buildings": error_buildings,
            "event_rate_last_hour": event_rate,
            "route_log_entries": route_logs,
        }

        now = now_iso()
        for k, v in metrics.items():
            self.conn.execute(
                "INSERT INTO controll_metrics (metric_name, metric_value, recorded_at) VALUES (?, ?, ?)",
                (k, float(v) if not isinstance(v, str) else v, now),
            )
        self.conn.commit()
        return metrics

    # ── background work ──
    def work(self):
        """Periodic health check of all pipeline routes."""
        metrics = self._compute_metrics()
        if metrics["error_buildings"] > 0:
            self._raise_alert(
                "controll_panel", "warning",
                f"{metrics['error_buildings']} building(s) in error state"
            )
        self.log("tick", f"monitoring {metrics['active_buildings']} buildings, "
                        f"route_logs={metrics['route_log_entries']}")

    def _raise_alert(self, building, severity, message):
        self.conn.execute(
            """INSERT INTO system_alerts
               (building, severity, message, detected_at)
               VALUES (?, ?, ?, ?)""",
            (building, severity, message, now_iso()),
        )
        self.conn.commit()
        log_event(self.conn, self.name, "alert", message,
                  {"severity": severity, "building": building})

    def employee_duty(self):
        """Every shift: ensure routes are wired and compute system metrics."""
        self._wire_routes()
        self._compute_metrics()
        return None

    def dashboard_payload(self, conn):
        """Rich dashboard data — the command center console."""
        metrics = self._compute_metrics()

        # Pipeline route health
        pipeline = []
        for src, dst, evt in self.PIPELINE_ROUTES:
            row = conn.execute(
                """SELECT COUNT(*) AS c FROM route_logs
                   WHERE source = ? AND event_type = ?""",
                (src, evt),
            ).fetchone()
            pipeline.append({
                "from": src, "to": dst, "event": evt,
                "total_events": row["c"] if row else 0,
            })

        # Subscriptions (the wiring map)
        subs = conn.execute(
            """SELECT subscriber_name, publisher_name, event_type
               FROM subscriptions ORDER BY publisher_name"""
        ).fetchall()

        # Recent route logs
        logs = conn.execute(
            """SELECT id, source, destination, event_type, message, received_at
               FROM route_logs ORDER BY received_at DESC LIMIT 30"""
        ).fetchall()

        # Active buildings with their reports
        from city.registry import get_registry
        registry = get_registry(conn)
        building_reports = {}
        for name, agent in registry.items():
            if name == self.name:
                continue
            try:
                agent.conn = conn
                building_reports[name] = agent.report()
            except Exception as exc:
                building_reports[name] = {"error": str(exc)}

        # Recent alerts
        alerts = conn.execute(
            """SELECT id, building, severity, message, acknowledged, detected_at
               FROM system_alerts
               ORDER BY detected_at DESC LIMIT 20"""
        ).fetchall()

        return {
            "pipeline_routes": pipeline,
            "subscriptions": [dict(s) for s in subs],
            "route_logs": [dict(l) for l in logs],
            "building_reports": building_reports,
            "metrics": metrics,
            "alerts": [dict(a) for a in alerts],
        }
