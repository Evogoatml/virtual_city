"""
CEO Building — Central orchestration (City Hall)
The CEO sits at the center and coordinates all buildings.
"""
import json
from city.agent import Agent
from city.db import now_iso


class CEOBuildingAgent(Agent):
    name = "city_hall"
    subject = "CEO Building"
    district = "Civic Center"
    color = "#d4af37"  # Gold

    def register_rules(self):
        self.rule(r"^meeting$")(self._hold_meeting)
        self.rule(r"^last meeting$")(self._last_meeting)
        self.rule(r"^city status$")(self._city_status)
        self.rule(r"^building status$")(self._building_status)
        self.rule(r"^departments$")(self._all_departments)
        self.rule(r"^status$")(self._status)

    def _hold_meeting(self):
        return self.hold_meeting()

    def hold_meeting(self):
        """Pull report() from every building (not department)."""
        from city.registry import get_registry

        registry = get_registry(self.conn)
        reports = {}
        for name, agent in registry.items():
            if name == self.name:
                continue
            try:
                reports[name] = agent.report()
            except Exception as exc:
                reports[name] = {"error": str(exc)}

        summary = {"timestamp": now_iso(), "reports": reports}
        self.conn.execute(
            "INSERT INTO meetings (timestamp, summary_json) VALUES (?, ?)",
            (summary["timestamp"], json.dumps(summary)),
        )
        self.conn.commit()
        self.log("meeting", "CEO daily meeting held", summary)
        return {"action": "meeting held", "buildings": list(reports.keys()), "summary": summary}

    def _last_meeting(self):
        row = self.conn.execute("SELECT * FROM meetings ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return {"error": "no meetings held yet"}
        return json.loads(row["summary_json"])

    def _city_status(self):
        rows = self.conn.execute("SELECT name, subject, status, activity_count FROM agents").fetchall()
        return {"buildings": [dict(r) for r in rows]}

    def _building_status(self):
        """Get status of all buildings (orchestrators only)."""
        from city.registry import get_registry
        registry = get_registry(self.conn)
        buildings = {}
        for name, agent in registry.items():
            if name.endswith("_building") or name == "city_hall":
                try:
                    buildings[name] = agent.report()
                except Exception as exc:
                    buildings[name] = {"error": str(exc)}
        return {"buildings": buildings}

    def _all_departments(self):
        """Get status of all departments across all buildings."""
        from city.registry import get_registry
        registry = get_registry(self.conn)
        depts = {}
        for name, agent in registry.items():
            if not name.endswith("_building") and name != "city_hall":
                try:
                    depts[name] = agent.report()
                except Exception as exc:
                    depts[name] = {"error": str(exc)}
        return {"departments": depts}

    def work(self):
        from city.registry import get_registry
        registry = get_registry(self.conn)
        report_count = len(registry) - 1
        self.log("tick", f"{report_count} buildings reporting")

    def _status(self):
        return self.report()

    def report(self):
        meeting_count = self.conn.execute("SELECT COUNT(*) AS n FROM meetings").fetchone()["n"]
        return {
            "building": self.name,
            "subject": self.subject,
            "meetings_held": meeting_count,
            "role": "CEO",
        }