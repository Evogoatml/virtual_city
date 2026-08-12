"""
Finance Building — Orchestrates Crypto Trading + Market Data departments.
Departments are internal components, not separate agents.
"""
from city.agent import Agent
from city.db import now_iso

# Import internal departments
from .crypto_trading import CryptoTradingDepartment
from .market_data import MarketDataDepartment


class FinanceBuildingAgent(Agent):
    name = "finance_building"
    subject = "Finance Building"
    district = "Financial District"
    color = "#ff6d00"

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
            "crypto_trading": CryptoTradingDepartment(self.conn),
            "market_data": MarketDataDepartment(self.conn),
        }

    def register_rules(self):
        self.rule(r"^departments$")(self._list_departments)
        self.rule(r"^dept\s+status\s+(?P<dept>\w+)$")(self._dept_status)
        self.rule(r"^building\s+status$")(self._building_status)
        self.rule(r"^aggregate$")(self._aggregate)
        self.rule(r"^status$")(self._status)
        # Delegate to departments: dept <name> <query>
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
        agg = {"pnl": 0, "positions": 0, "exchanges": 0, "pairs": 0, "updates": 0}
        for name, agent in self._get_departments().items():
            try:
                r = agent.report()
                for k in ["realized_pnl_usd", "open_positions", "active_exchanges", "monitored_pairs", "total_updates"]:
                    if k in r:
                        agg[k.replace("realized_pnl_usd", "pnl").replace("open_positions", "positions")
                            .replace("active_exchanges", "exchanges").replace("monitored_pairs", "pairs")
                            .replace("total_updates", "updates")] += r[k]
            except Exception:
                pass
        return {
            "building": self.name,
            "total_realized_pnl_usd": agg["pnl"],
            "total_open_positions": agg["positions"],
            "exchanges_active": agg["exchanges"],
            "pairs_monitored": agg["pairs"],
            "price_updates": agg["updates"],
        }

    def _aggregate(self):
        return self._building_status()

    def work(self):
        status = self._building_status()
        self.log("tick", f"pnl=${status['total_realized_pnl_usd']}, positions={status['total_open_positions']}")

    def report(self):
        return self._building_status()