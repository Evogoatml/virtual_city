"""
Signal Building — monitors external web pages for content changes.

Every tick it checks watched URLs, diffs against the last known hash,
and logs changes as city events.  Alerts feed into sourcing_research,
product_flipping, and the CEO's daily meeting.
"""
import hashlib
import time
import re
from urllib.request import urlopen, Request
from urllib.error import URLError
from city.department import Department
from city.db import log_event, now_iso


class SignalAgent(Department):
    name = "signal"
    subject = "Change Detection"
    district = "Research Quarter"
    color = "#00e5ff"

    def __init__(self, conn):
        super().__init__(conn)
        self._checking = False

    def setup_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS signal_watches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                label TEXT DEFAULT '',
                interval_min INTEGER DEFAULT 15,
                last_checked TEXT,
                last_hash TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS signal_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                watch_id INTEGER NOT NULL,
                old_hash TEXT,
                new_hash TEXT,
                content_snippet TEXT,
                detected_at TEXT NOT NULL,
                acknowledged INTEGER DEFAULT 0,
                FOREIGN KEY (watch_id) REFERENCES signal_watches(id)
            );
            CREATE INDEX IF NOT EXISTS idx_signal_active ON signal_watches(status);
        """)
        self.conn.commit()

    def register_rules(self):
        self.rule(r"^add watch\s+(?P<url>\S+)\s*(?P<label>.*)$")(self._add_watch)
        self.rule(r"^remove watch\s+(?P<id>\d+)$")(self._remove_watch)
        self.rule(r"^watches$")(self._watches)
        self.rule(r"^alerts$")(self._alerts)
        self.rule(r"^check now$")(self._check_now)
        self.rule(r"^ack\s+(?P<id>\d+)$")(self._ack)
        self.rule(r"^stats$")(self._stats)
        self.rule(r"^status$")(self._status)

    def _add_watch(self, url, label=""):
        url = url.strip().rstrip("/")
        label = label.strip() or url.split("//")[-1][:60]
        try:
            self.conn.execute(
                "INSERT INTO signal_watches (url, label, created_at) VALUES (?, ?, ?)",
                (url, label, now_iso()),
            )
            self.conn.commit()
            return {"ok": True, "watch": label, "url": url}
        except Exception as e:
            return {"error": str(e)}

    def _remove_watch(self, id):
        self.conn.execute("DELETE FROM signal_watches WHERE id = ?", (int(id),))
        self.conn.commit()
        return {"ok": True}

    def _watches(self):
        rows = self.conn.execute(
            "SELECT * FROM signal_watches ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
        return {"watches": [dict(r) for r in rows], "count": len(rows)}

    def _alerts(self):
        rows = self.conn.execute("""
            SELECT c.*, w.url, w.label
            FROM signal_changes c
            JOIN signal_watches w ON c.watch_id = w.id
            WHERE c.acknowledged = 0
            ORDER BY c.detected_at DESC
            LIMIT 30
        """).fetchall()
        return {"alerts": [dict(r) for r in rows], "count": len(rows)}

    def _check_now(self):
        changed = self._check_all()
        return {"checked": True, "changes_found": changed}

    def _ack(self, id):
        self.conn.execute(
            "UPDATE signal_changes SET acknowledged = 1 WHERE id = ?", (int(id),)
        )
        self.conn.commit()
        return {"ok": True, "acked": int(id)}

    def _stats(self):
        total = self.conn.execute("SELECT COUNT(*) AS c FROM signal_watches WHERE status = 'active'").fetchone()["c"]
        changes = self.conn.execute("SELECT COUNT(*) AS c FROM signal_changes WHERE acknowledged = 0").fetchone()["c"]
        last = self.conn.execute(
            "SELECT detected_at FROM signal_changes ORDER BY detected_at DESC LIMIT 1"
        ).fetchone()
        return {
            "active_watches": total,
            "unread_alerts": changes,
            "last_change": last["detected_at"] if last else None,
        }

    def _status(self):
        return self.report()

    # ── Tick ──

    def work(self):
        if self._checking:
            return
        due = self.conn.execute("""
            SELECT * FROM signal_watches
            WHERE status = 'active'
              AND (last_checked IS NULL
                   OR datetime(last_checked, '+' || interval_min || ' minutes') < datetime('now'))
            ORDER BY last_checked ASC NULLS FIRST
            LIMIT 3
        """).fetchall()
        if due:
            self._checking = True
            try:
                for row in due:
                    self._check_one(dict(row))
            finally:
                self._checking = False

    # ── Core ──

    def _check_all(self):
        rows = self.conn.execute(
            "SELECT * FROM signal_watches WHERE status = 'active'"
        ).fetchall()
        changed = 0
        for row in rows:
            if self._check_one(dict(row)):
                changed += 1
        return changed

    def _check_one(self, watch):
        try:
            from city.api_budget import budget
            key = f"signal:{watch.get('id')}:{watch.get('url','')[:100]}"
            ok, reason = budget.allow(self.name, "signal", key=key, cost=1)
            if not ok:
                log_event(self.conn, self.name, "budget_deny", reason, {"url": watch["url"]})
                return False
        except Exception:
            budget = None  # type: ignore
            key = ""

        try:
            req = Request(
                watch["url"],
                headers={"User-Agent": "Mozilla/5.0 VirtualCity/1.0", "Accept": "text/html,text/plain,*/*"},
            )
            with urlopen(req, timeout=15) as resp:
                body = resp.read()
            content = body.decode("utf-8", errors="replace")
            if budget is not None:
                budget.record(self.name, "signal", key=key, ok=True, cache=True)
        except Exception as exc:
            if budget is not None:
                budget.record(self.name, "signal", key=key, ok=False, cache=True)
            log_event(self.conn, self.name, "watch_error", f"{watch['label']}: {exc}", {"url": watch["url"]})
            return False

        new_hash = hashlib.sha256(content.encode()).hexdigest()
        old_hash = watch.get("last_hash", "")

        self.conn.execute(
            "UPDATE signal_watches SET last_checked = ?, last_hash = ? WHERE id = ?",
            (now_iso(), new_hash, watch["id"]),
        )
        self.conn.commit()

        if old_hash and new_hash != old_hash:
            snippet = self._snippet(content)
            self.conn.execute(
                "INSERT INTO signal_changes (watch_id, old_hash, new_hash, content_snippet, detected_at) VALUES (?, ?, ?, ?, ?)",
                (watch["id"], old_hash, new_hash, snippet, now_iso()),
            )
            self.conn.commit()
            log_event(
                self.conn, self.name, "change_detected",
                f"{watch['label']} changed",
                {"url": watch["url"], "snippet": snippet},
            )
            return True
        return False

    @staticmethod
    def _snippet(content, max_len=200):
        clean = re.sub(r"\s+", " ", content.strip())[:max_len]
        return clean

    def report(self):
        stats = self._stats()
        rows = self.conn.execute(
            "SELECT label, last_checked, status FROM signal_watches ORDER BY last_checked DESC NULLS LAST LIMIT 10"
        ).fetchall()
        return {
            **stats,
            "watches": [dict(r) for r in rows],
        }