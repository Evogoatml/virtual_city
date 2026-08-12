"""
Web-Check room — OSINT website analyzer (Lissy93/web-check) inside Virtual City.

Lives in Research Quarter. Starts the local web-check server, runs scans,
and exposes results to City Hall + the /room/webcheck/ portal.
"""
from __future__ import annotations

import json
from urllib.parse import quote

from city.department import Department
from city.db import now_iso, log_event

from . import service


class WebCheckAgent(Department):
    name = "web_check"
    subject = "Web Check"
    district = "Research Quarter"
    color = "#9fef00"
    building_name = "research_building"

    def setup_schema(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS webcheck_scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_url TEXT NOT NULL,
                label TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                summary_json TEXT,
                created_at TEXT NOT NULL,
                finished_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_webcheck_scans_created
                ON webcheck_scans(created_at DESC);
            """
        )
        self.conn.commit()

    def register_rules(self):
        self.rule(r"^start$")(self._start)
        self.rule(r"^stop$")(self._stop)
        self.rule(r"^status$")(self._status)
        self.rule(r"^room$")(self._room)
        self.rule(r"^install$")(self._install)
        self.rule(r"^scan\s+(?P<url>\S+)\s*(?P<label>.*)$")(self._scan)
        self.rule(r"^quick\s+(?P<url>\S+)$")(self._quick)
        self.rule(r"^history$")(self._history)
        self.rule(r"^show\s+(?P<id>\d+)$")(self._show)
        self.rule(r"^help$")(self._help)

    def _help(self):
        return {
            "commands": [
                "start",
                "stop",
                "status",
                "room",
                "install",
                "scan <url> [label]",
                "quick <url>",
                "history",
                "show <id>",
            ],
            "room": "/room/webcheck/",
        }

    def _install(self):
        return service.ensure_installed()

    def _start(self):
        result = service.start()
        if result.get("ok"):
            log_event(self.conn, self.name, "service_start", "web-check started", result)
        return result

    def _stop(self):
        result = service.stop()
        log_event(self.conn, self.name, "service_stop", "web-check stop", result)
        return result

    def _status(self):
        st = service.status()
        n = self.conn.execute("SELECT COUNT(*) AS c FROM webcheck_scans").fetchone()["c"]
        st["scans_total"] = n
        return st

    def _room(self):
        st = service.status()
        return {
            "room_url": "/room/webcheck/",
            "direct_url": st["url"],
            "running": st["running"],
            "hint": "Open /room/webcheck/ in the city UI (proxied into your room).",
        }

    def _history(self):
        rows = self.conn.execute(
            "SELECT id, target_url, label, status, created_at, finished_at "
            "FROM webcheck_scans ORDER BY id DESC LIMIT 30"
        ).fetchall()
        return {"scans": [dict(r) for r in rows], "count": len(rows)}

    def _show(self, id):
        row = self.conn.execute(
            "SELECT * FROM webcheck_scans WHERE id = ?", (int(id),)
        ).fetchone()
        if not row:
            return {"error": "scan not found"}
        d = dict(row)
        if d.get("summary_json"):
            try:
                d["summary"] = json.loads(d["summary_json"])
            except json.JSONDecodeError:
                pass
        return d

    def _ensure_running(self):
        st = service.status()
        if st["running"]:
            return st
        return service.start()

    def _quick(self, url):
        return self._scan(url, label="quick", checks=service.QUICK_CHECKS[:4])

    def _scan(self, url, label="", checks=None):
        url = url.strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        label = (label or "").strip() or url.split("//")[-1][:60]
        checks = list(checks or service.QUICK_CHECKS)

        boot = self._ensure_running()
        if not boot.get("ok", True) and not boot.get("running"):
            # start() returns ok key; status doesn't
            if not service.is_up():
                return {"error": "web-check service not running", "boot": boot}

        cur = self.conn.execute(
            "INSERT INTO webcheck_scans (target_url, label, status, created_at) VALUES (?, ?, 'running', ?)",
            (url, label, now_iso()),
        )
        self.conn.commit()
        scan_id = cur.lastrowid

        results = {}
        errors = {}
        q = quote(url, safe="")
        for name in checks:
            path = f"/api/{name}?url={q}"
            r = service.call_api(path, agent=self.name)
            if r.get("ok"):
                results[name] = r.get("data")
            else:
                errors[name] = r.get("error") or r.get("status")
                if r.get("denied"):
                    errors["_budget"] = r.get("error")
                    break  # stop burning more quota

        summary = {
            "target": url,
            "checks_ok": list(results.keys()),
            "checks_failed": list(errors.keys()),
            "results": results,
            "errors": errors,
            "room": f"/room/webcheck/?url={q}",
        }
        self.conn.execute(
            "UPDATE webcheck_scans SET status = ?, summary_json = ?, finished_at = ? WHERE id = ?",
            ("done" if results else "error", json.dumps(summary), now_iso(), scan_id),
        )
        self.conn.commit()
        log_event(
            self.conn,
            self.name,
            "scan_complete",
            f"scan {label}: {len(results)} ok / {len(errors)} failed",
            {"scan_id": scan_id, "url": url},
        )
        return {
            "ok": True,
            "scan_id": scan_id,
            "label": label,
            "target": url,
            "checks_ok": summary["checks_ok"],
            "checks_failed": summary["checks_failed"],
            "room": summary["room"],
            "preview": {k: results[k] for k in list(results)[:3]},
        }

    def work(self):
        # No network on tick — only local pid file check (budget-safe)
        pid = service.read_pid()
        if pid:
            # at most one tick log per 5 minutes via health cache
            try:
                from city.api_budget import budget
                hit, _ = budget.health_get("web_check_tick_log")
                if not hit:
                    self.log("tick", f"web-check pid {pid} (no health HTTP)")
                    budget.health_set("web_check_tick_log", True, ttl=300)
            except Exception:
                pass

    def report(self):
        st = service.status()
        total = self.conn.execute("SELECT COUNT(*) AS c FROM webcheck_scans").fetchone()["c"]
        last = self.conn.execute(
            "SELECT id, target_url, status, created_at FROM webcheck_scans ORDER BY id DESC LIMIT 5"
        ).fetchall()
        return {
            "building": self.name,
            "subject": self.subject,
            "service_running": st["running"],
            "room_url": "/room/webcheck/",
            "direct_url": st["url"],
            "scans_total": total,
            "recent": [dict(r) for r in last],
        }
