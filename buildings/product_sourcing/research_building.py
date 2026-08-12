"""
Research Building — Orchestrates Sourcing & Research department.
Departments are internal components, not separate agents.
"""
from city.agent import Agent
from city.db import now_iso

# Import internal department
from .sourcing_research import SourcingResearchDepartment


class ResearchBuildingAgent(Agent):
    name = "research_building"
    subject = "Research Building"
    district = "Research Quarter"
    color = "#00bcd4"

    def setup_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS building_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                department TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL
            )
        """)
        self.conn.commit()

    def _get_departments(self):
        """Lazy-create departments with current connection."""
        return {
            "sourcing_research": SourcingResearchDepartment(self.conn),
        }

    def register_rules(self):
        self.rule(r"^departments$")(self._list_departments)
        self.rule(r"^dept\s+status\s+(?P<dept>\w+)$")(self._dept_status)
        self.rule(r"^building\s+status$")(self._building_status)
        self.rule(r"^aggregate$")(self._aggregate)
        self.rule(r"^status$")(self._status)

    def _status(self):
        return self.report()

    def _list_departments(self):
        return {"building": self.name, "departments": list(self._get_departments().keys())}

    def _dept_status(self, dept: str):
        dept_agent = self._get_departments().get(dept)
        if not dept_agent:
            return {"error": f"department {dept} not found"}
        return {"department": dept, "status": dept_agent.report()}

    def _building_status(self):
        agg = {"open_leads": 0, "actioned_leads": 0, "avg_score": 0}
        for name, agent in self._get_departments().items():
            try:
                r = agent.report()
                for k in agg:
                    if k in r:
                        agg[k] += r[k]
            except Exception:
                pass
        return {
            "building": self.name,
            "open_leads": agg["open_leads"],
            "actioned_leads": agg["actioned_leads"],
            "avg_open_score": agg["avg_score"],
        }

    def _aggregate(self):
        return self._building_status()

    def work(self):
        status = self._building_status()
        self.log("tick", f"{status['open_leads']} open leads")

    def report(self):
        status = self._building_status()
        try:
            from city.registry import get_registry
            wc = get_registry(self.conn).get("web_check")
            if wc:
                status["web_check"] = wc.report()
        except Exception:
            pass
        return status