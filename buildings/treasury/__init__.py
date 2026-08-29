"""
Treasury — Stage 4 of the pipeline.
Tracks all real money movement, aggregates revenue, manages the company ledger.
Real-world: Consolidates all financial data, produces weekly reports.
"""
from city.agent import Agent
from city.db import now_iso, log_event
import json

class TreasuryAgent(Agent):
    name = "treasury"
    subject = "Treasury"
    district = "Finance"
    color = "#673ab7"

    job_title = "Chief Financial Officer"
    mission = "Track all money in/out, balance sheet, and weekly financial reports."
    cog_interval = 120

    def setup_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS ledger_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                amount REAL NOT NULL,
                type TEXT NOT NULL,  -- 'income' or 'expense'
                timestamp TEXT NOT NULL,
                description TEXT,
                balance_after REAL
            )
        """)
        self.conn.commit()

    def register_rules(self):
        self.rule(r"^status$")(self._status)
        self.rule(r"^report$")(self._report)
        self.rule(r"^balance$")(self._balance)
        self.rule(r"^ledger(?:\s+(?P<limit>\d+))?$")(self._ledger)
        self.rule(r"^add entry\s+(?P<type>income|expense)\s+(?P<amount>\d+(?:\.\d+)?)\s+(?P<description>.+?)$")(self._add_entry)
        self.rule(r"^weekly report$")(self._weekly_report)

    def _status(self):
        return {"agent": self.name, "status": self.status}

    def _report(self):
        rows = self.conn.execute(
            "SELECT * FROM ledger_entries ORDER BY timestamp DESC LIMIT 50"
        ).fetchall()
        entries = [dict(r) for r in rows]
        total_income = sum(e["amount"] if e["type"] == "income" else 0 for e in entries)
        total_expense = sum(e["amount"] if e["type"] == "expense" else 0 for e in entries)
        balance = total_income - total_expense
        return {"agent": self.name, "subject": self.subject, "total_income": total_income, "total_expense": total_expense, "current_balance": balance, "entries_count": len(entries), "recent_entries": entries}

    def _balance(self):
        row = self.conn.execute(
            "SELECT SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) - SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) AS balance FROM ledger_entries"
        ).fetchone()
        balance = row["balance"] if row and row["balance"] is not None else 0.0
        return {"agent": self.name, "balance": balance}

    def _ledger(self, limit=None):
        limit = int(limit) if limit else 20
        rows = self.conn.execute(
            "SELECT * FROM ledger_entries ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        entries = [dict(r) for r in rows]
        return {"ledger": entries}

    def _add_entry(self, entry_type, amount, description):
        amount = float(amount)
        # Get current balance
        row = self.conn.execute("SELECT SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) - SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) AS balance FROM ledger_entries").fetchone()
        balance = row["balance"] if row and row["balance"] is not None else 0.0
        if entry_type == "income":
            new_balance = balance + amount
        else:
            new_balance = balance - amount
        # Insert record
        self.conn.execute(
            "INSERT INTO ledger_entries (source, amount, type, timestamp, description, balance_after) VALUES (?, ?, ?, ?, ?, ?)",
            (f"manual_{entry_type}", amount, entry_type, now_iso(), description, new_balance)
        )
        entry_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.log("ledger_entry_added", f"{entry_type} entry {entry_id}: {description}", {"amount": amount, "balance": new_balance})
        self.conn.commit()
        return {"ok": True, "entry_id": entry_id, "balance": new_balance}

    def _weekly_report(self):
        # Query all real money movement via EventBus? For now, aggregate from ledger
        rows = self.conn.execute(
            "SELECT SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END) AS income, SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END) AS expense FROM ledger_entries WHERE date(timestamp) >= date('now', '-7 days')"
        ).fetchone()
        income = rows["income"] if rows and rows["income"] is not None else 0.0
        expense = rows["expense"] if rows and rows["expense"] is not None else 0.0
        net = income - expense
        # Simulate treasury heat-beat by logging a meeting event
        from city.orchestrator import EventBus
        EventBus.publish(self.name, "treasury.weekly", f"weekly report: ${net:.2f}", {"income": income, "expense": expense, "net": net})
        self.log("weekly_report_generated", f"weekly treasury: net ${net:.2f}", {"income": income, "expense": expense, "net": net})
        return {"agent": self.name, "period": "last 7 days", "income": income, "expense": expense, "net": net}

    def employee_duty(self):
        if self.status == "idle" and self.cognitive.step_index:
            # Auto-generate weekly report on Friday
            from datetime import datetime
            if datetime.today().weekday() == 4:  # Friday
                return self._weekly_report()
        return None

    def report(self):
        return {"agent": self.name, "subject": self.subject, "status": self.status}