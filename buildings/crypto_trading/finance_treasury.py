from city.agent import Agent
from city.db import now_iso


class FinanceTreasuryAgent(Agent):
    name = "finance_treasury"
    subject = "Finance & Treasury"
    district = "Financial District"
    color = "#2e7d32"

    def setup_schema(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                amount REAL NOT NULL,   -- positive = income, negative = expense
                note TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def register_rules(self):
        self.rule(r"^ledger\s+add\s+(?P<source>\w+)\s+(?P<amount>[+-]?[\d.]+)\s*(?P<note>.*)$")(self._add)
        self.rule(r"^summary$")(self._summary)
        self.rule(r"^ledger$")(self._ledger)
        self.rule(r"^status$")(self._status)

    def _add(self, source, amount, note=""):
        self.conn.execute(
            "INSERT INTO ledger (source, amount, note, created_at) VALUES (?, ?, ?, ?)",
            (source, float(amount), note.strip(), now_iso()),
        )
        self.conn.commit()
        return {"action": "ledger entry added", "source": source, "amount": float(amount), "note": note.strip()}

    def _ledger(self):
        rows = self.conn.execute("SELECT * FROM ledger ORDER BY id DESC LIMIT 50").fetchall()
        return {"entries": [dict(r) for r in rows]}

    def _summary(self):
        return self._aggregate()

    def _status(self):
        return self.report()

    def _aggregate(self):
        """Pull report() from every other registered agent and combine with the manual ledger."""
        from city.registry import get_registry

        registry = get_registry(self.conn)
        breakdown = {}
        for name, agent in registry.items():
            if name == self.name:
                continue
            try:
                breakdown[name] = agent.report()
            except Exception as exc:
                breakdown[name] = {"error": str(exc)}

        ledger_total = self.conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM ledger"
        ).fetchone()["total"]

        # Pull whatever profit/revenue-shaped numbers each agent's report exposes.
        derived_total = 0.0
        for rep in breakdown.values():
            for key in ("profit_usd", "realized_pnl_usd", "total_margin_usd", "revenue_usd"):
                if isinstance(rep, dict) and key in rep and isinstance(rep[key], (int, float)):
                    derived_total += rep[key]
                    break

        return {
            "manual_ledger_total_usd": round(ledger_total, 2),
            "derived_agent_total_usd": round(derived_total, 2),
            "grand_total_usd": round(ledger_total + derived_total, 2),
            "breakdown": breakdown,
        }

    def work(self):
        row = self.conn.execute("SELECT COALESCE(SUM(amount),0) AS total FROM ledger").fetchone()
        self.log("tick", f"ledger: ${row['total']:.0f}")

    def report(self):
        agg = self._aggregate()
        return {
            "agent": self.name,
            "subject": self.subject,
            "grand_total_usd": agg["grand_total_usd"],
            "manual_ledger_total_usd": agg["manual_ledger_total_usd"],
        }
