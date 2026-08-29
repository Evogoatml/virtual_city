"""
Sourcing Research Department — Internal component of Research Building.
Handles scored opportunity leads, category tracking, action/reject workflows.
"""
from city.department import Department
from city.db import now_iso


class SourcingResearchDepartment(Department):
    building_name = "research_building"
    name = "sourcing_research"
    subject = "Sourcing & Research Dept"
    district = "Research Quarter"
    color = "#26a69a"

    def setup_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sourcing_leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                score REAL NOT NULL DEFAULT 0,
                notes TEXT,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open'
            )
        """)
        self.conn.commit()

    def register_rules(self):
        self.rule(r"^lead\s+(?P<name>.+?)\s+category\s+(?P<category>\w+)\s+score\s+(?P<score>[\d.]+)$")(self._lead)
        self.rule(r"^action\s+(?P<name>.+)$")(self._action)
        self.rule(r"^reject\s+(?P<name>.+)$")(self._reject)
        self.rule(r"^top leads$")(self._top_leads)
        self.rule(r"^status$")(self._status)

    def _find(self, name):
        return self.conn.execute(
            "SELECT * FROM sourcing_leads WHERE name = ? AND status='open' ORDER BY id DESC LIMIT 1", (name,)
        ).fetchone()

    def _lead(self, name, category, score):
        self.conn.execute(
            "INSERT INTO sourcing_leads (name, category, score, created_at) VALUES (?, ?, ?, ?)",
            (name, category, float(score), now_iso()),
        )
        self.conn.commit()
        return {"action": "lead logged", "name": name, "category": category, "score": float(score)}

    def _action(self, name):
        row = self._find(name)
        if not row:
            return {"error": f"no open lead '{name}'"}
        self.conn.execute("UPDATE sourcing_leads SET status='actioned' WHERE id=?", (row["id"],))
        self.conn.commit()
        return {"action": "lead actioned", "name": name}

    def _reject(self, name):
        row = self._find(name)
        if not row:
            return {"error": f"no open lead '{name}'"}
        self.conn.execute("UPDATE sourcing_leads SET status='rejected' WHERE id=?", (row["id"],))
        self.conn.commit()
        return {"action": "lead rejected", "name": name}

    def _top_leads(self):
        rows = self.conn.execute(
            "SELECT * FROM sourcing_leads WHERE status='open' ORDER BY score DESC LIMIT 10"
        ).fetchall()
        return {"top_leads": [dict(r) for r in rows]}

    def _status(self):
        return self.report()

    def work(self):
        open_n = self.conn.execute("SELECT COUNT(*) AS n FROM sourcing_leads WHERE status='open'").fetchone()["n"]
        if open_n > 0:
            self.log("tick", f"{open_n} open leads")

    def report(self):
        open_n = self.conn.execute("SELECT COUNT(*) AS n FROM sourcing_leads WHERE status='open'").fetchone()["n"]
        actioned_n = self.conn.execute("SELECT COUNT(*) AS n FROM sourcing_leads WHERE status='actioned'").fetchone()["n"]
        avg_score = self.conn.execute("SELECT AVG(score) AS a FROM sourcing_leads WHERE status='open'").fetchone()["a"]
        return {
            "department": self.name,
            "subject": self.subject,
            "open_leads": open_n,
            "actioned_leads": actioned_n,
            "avg_open_score": round(avg_score, 2) if avg_score else 0,
        }