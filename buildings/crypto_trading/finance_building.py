"""
Finance Building — Orchestrates Crypto Trading + Market Data departments.
Aggregates registry-owned departments (does not re-instantiate them).
"""
from city.agent import Agent


class FinanceBuildingAgent(Agent):
    name = "finance_building"
    subject = "Finance Building"
    district = "Financial District"
    color = "#ff6d00"

    DEPT_NAMES = ("market_data", "finance_treasury")

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
        self.rule(r"^dept\s+(?P<dept>\w+)\s+(?P<query>.+)$")(self._delegate_to_dept)

    def _delegate_to_dept(self, dept: str, query: str):
        dept_agent = self._get_departments().get(dept)
        if not dept_agent:
            return {"error": f"department {dept} not found"}
        return dept_agent.process(query)

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
        agg = {"pnl": 0.0, "positions": 0, "exchanges": 0, "pairs": 0, "updates": 0}
        for agent in self._get_departments().values():
            try:
                r = agent.report()
            except Exception:
                continue
            for key, dest in (
                ("realized_pnl_usd", "pnl"),
                ("pnl", "pnl"),
                ("open_positions", "positions"),
                ("active_exchanges", "exchanges"),
                ("monitored_pairs", "pairs"),
                ("total_updates", "updates"),
            ):
                if key in r and isinstance(r[key], (int, float)):
                    agg[dest] += r[key]
        return {
            "building": self.name,
            "mode": "paper",
            "total_realized_pnl_usd": round(agg["pnl"], 2),
            "total_open_positions": int(agg["positions"]),
            "exchanges_active": int(agg["exchanges"]),
            "pairs_monitored": int(agg["pairs"]),
            "price_updates": int(agg["updates"]),
        }

    def _aggregate(self):
        return self._building_status()

    def work(self):
        status = self._building_status()
        self.log(
            "tick",
            f"pnl=${status['total_realized_pnl_usd']}, positions={status['total_open_positions']}",
        )

    def report(self):
        return self._building_status()
