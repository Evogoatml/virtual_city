from city.department import Department
from city.db import now_iso


class FinanceTreasuryAgent(Department):
    building_name = "finance_building"
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

    def handle_event(self, event_type, message="", data=None):
        """Consume events from other buildings (real cross-building interaction)."""
        data = data or {}
        if event_type == "affiliate.conversion":
            try:
                revenue = float(data.get("revenue", 0) or 0)
                offer = data.get("offer", "")
            except (TypeError, ValueError):
                revenue, offer = 0.0, ""
            if revenue:
                self.conn.execute(
                    "INSERT INTO ledger (source, amount, note, created_at) VALUES (?, ?, ?, ?)",
                    ("affiliate", revenue, f"conversion: {offer}", now_iso()),
                )
                self.conn.commit()
                return {"ledger": "income recorded", "amount": revenue}
        if event_type == "shopify.order_paid":
            try:
                revenue = float(data.get("revenue", 0) or 0)
                oid = data.get("order_id", "")
            except (TypeError, ValueError):
                revenue, oid = 0.0, ""
            if revenue:
                self.conn.execute(
                    "INSERT INTO ledger (source, amount, note, created_at) VALUES (?, ?, ?, ?)",
                    ("shopify", revenue, f"order paid: {oid}", now_iso()),
                )
                self.conn.commit()
                return {"ledger": "income recorded", "amount": revenue}
        return None

    def _aggregate(self):
        """Pull report() from every other registered agent and combine with the manual ledger.

        Guarded against re-entrancy: finance_building.report() calls back into
        this treasury, so a naive loop would infinitely recurse and segfault.
        """
        if getattr(self, "_in_aggregate", False):
            return {"manual_ledger_total_usd": 0.0,
                    "derived_agent_total_usd": 0.0,
                    "grand_total_usd": 0.0, "breakdown": {}}
        self._in_aggregate = True
        try:
            from city.registry import get_registry

            registry = get_registry(self.conn)
            breakdown = {}
            for name, agent in registry.items():
                # Skip self and the parent Finance building: treasury is a
                # department OF finance_building, so re-aggregating the parent
                # would create an infinite cycle.
                if name in (self.name, "finance_building"):
                    continue
                try:
                    breakdown[name] = agent.report()
                except Exception as exc:
                    breakdown[name] = {"error": str(exc)}
        finally:
            self._in_aggregate = False

        ledger_total = self.conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM ledger"
        ).fetchone()["total"]

        # Pull whatever profit/revenue-shaped numbers each agent's report exposes.
        # Prefer profit/margin/pnl keys; fall back to revenue only once per agent.
        PROFIT_KEYS = (
            "profit_usd",
            "realized_pnl_usd",
            "pnl",
            "total_margin_usd",
            "total_realized_pnl_usd",
            "grand_total_usd",
        )
        REVENUE_KEYS = ("revenue_usd", "revenue", "total_revenue_usd")
        derived_total = 0.0
        for name, rep in breakdown.items():
            if not isinstance(rep, dict) or name == "city_hall":
                continue
            added = False
            for key in PROFIT_KEYS:
                if key in rep and isinstance(rep[key], (int, float)):
                    derived_total += float(rep[key])
                    added = True
                    break
            if not added:
                for key in REVENUE_KEYS:
                    if key in rep and isinstance(rep[key], (int, float)):
                        derived_total += float(rep[key])
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
