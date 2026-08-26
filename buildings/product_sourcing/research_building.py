"""
Research Building — Orchestrates Sourcing & Research department.
Aggregates registry-owned departments (does not re-instantiate them).
"""
from city.agent import Agent


class ResearchBuildingAgent(Agent):
    name = "research_building"
    subject = "Research Building"
    district = "Research Quarter"
    color = "#00bcd4"

    DEPT_NAMES = ("sourcing_research",)

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
        from city.registry import get_registry
        registry = get_registry(self.conn)
        return {name: registry[name] for name in self.DEPT_NAMES if name in registry}

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
        agg = {"open_leads": 0, "actioned_leads": 0, "avg_score": 0.0}
        n = 0
        for agent in self._get_departments().values():
            try:
                r = agent.report()
            except Exception:
                continue
            agg["open_leads"] += int(r.get("open_leads") or 0)
            agg["actioned_leads"] += int(r.get("actioned_leads") or 0)
            score = r.get("avg_open_score", r.get("avg_score"))
            if isinstance(score, (int, float)):
                agg["avg_score"] += float(score)
                n += 1
        return {
            "building": self.name,
            "open_leads": agg["open_leads"],
            "actioned_leads": agg["actioned_leads"],
            "avg_open_score": round(agg["avg_score"] / n, 2) if n else 0,
        }

    def _aggregate(self):
        return self._building_status()

    def work(self):
        status = self._building_status()
        self.log("tick", f"{status['open_leads']} open leads")

    def report(self):
        return self._building_status()
