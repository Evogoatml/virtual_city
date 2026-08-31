"""Finance Building — Central orchestration for all money-related activities.
Handles ledger, crypto trading integration, and revenue rollup.
"""

from city.agent import Agent
from city.db import now_iso, log_event
import json


class FinanceBuildingAgent(Agent):
    name = "finance_building"
    subject = "Finance Building"
    district = "Finance District"
    color = "#1a237e"  # Deep blue
    
    def setup_schema(self):
        """Create tables for finance tracking.

        Includes a lightweight migration: if ``ledger_entries`` exists with
        the old schema (columns ``source``/``type``/``balance_after`` and no
        ``status``), the table is rebuilt with the current schema so the
        report() queries don't crash on missing columns.
        """
        # Detect a stale ledger_entries schema (no `building` column means
        # the old layout from before the finance_building rewrite).
        cols = [r[1] for r in self.conn.execute(
            "PRAGMA table_info(ledger_entries)"
        ).fetchall()]
        if cols and "building" not in cols:
            # Old table: source, amount, type, timestamp, description, balance_after
            self.conn.execute("DROP TABLE ledger_entries")

        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS ledger_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                building TEXT NOT NULL,
                event_type TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'USD',
                description TEXT,
                timestamp TEXT NOT NULL,
                status TEXT DEFAULT 'pending'
            );

            CREATE TABLE IF NOT EXISTS finance_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name TEXT NOT NULL,
                metric_value REAL,
                recorded_at TEXT NOT NULL,
                building TEXT
            );
        """)
        self.conn.commit()
    
    def register_rules(self):
        self.rule(r"^ledger add (?P<building>\w+) (?P<event>\w+) (?P<amount>\d+(?:\.\d+)?) (?P<currency>\w+)? (?P<description>.+)$")(self._add_to_ledger)
        self.rule(r"^ledger (?P<limit>\d+)?$")(self._query_ledger)
        self.rule(r"^transfer (?P<from>\w+) (?P<to>\w+) (?P<amount>\d+(?:\.\d+)?)$")(self._transfer_between_buildings)
        self.rule(r"^metrics$")(self._get_finance_metrics)
        self.rule(r"^status$")(self._status)
    
    def _add_to_ledger(self, building, event, amount, currency, description):
        """Add an entry to the finance ledger."""
        self.conn.execute("""
            INSERT INTO ledger_entries 
            (building, event_type, amount, currency, description, timestamp, status)
            VALUES (?, ?, ?, ?, ?, ?, 'confirmed')
        """, (building, event, float(amount), currency or 'USD', description, now_iso()))
        self.conn.commit()
        
        # Publish event for other buildings to react to
        from city.orchestrator import EventBus
        EventBus.publish("finance_building", "ledger.moved", f"{building}.{event}", {
            "building": building,
            "event": event, 
            "amount": float(amount),
            "currency": currency or 'USD',
            "description": description
        })
        
        return {"action": "added to ledger", "building": building, "event": event, "amount": float(amount)}
    
    def _query_ledger(self, limit):
        """Query ledger entries with optional limit."""
        query = "SELECT * FROM ledger_entries ORDER BY timestamp DESC"
        if limit:
            query += f" LIMIT {limit}"
            
        rows = self.conn.execute(query).fetchall()
        return {"entries": [dict(r) for r in rows], "count": len(rows)}
    
    def _transfer_between_buildings(self, from_building, to_building, amount):
        """Handle transfers between buildings."""
        if from_building == to_building:
            return {"error": "source and destination cannot be the same"}
            
        # Check if source has sufficient balance
        source_balance = self._get_building_balance(from_building)
        if source_balance < float(amount):
            return {"error": f"insufficient balance in {from_building}: {source_balance} < {amount}"}
            
        # Transfer the money
        self.conn.execute(
            "UPDATE ledger_entries SET status = ? WHERE building = ? AND status = ? AND amount = ?",
            ("transferred", from_building, "confirmed", -float(amount))
        )
        
        self.conn.execute(
            "INSERT INTO ledger_entries (building, event_type, amount, currency, description, timestamp, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (to_building, "transfer_in", float(amount), "USD", f"transfer from {from_building}", now_iso(), "confirmed")
        )
        self.conn.commit()
        
        from city.orchestrator import EventBus
        EventBus.publish("finance_building", "transfer.completed", f"{from_building}→{to_building}", {
            "from": from_building,
            "to": to_building, 
            "amount": float(amount)
        })
        
        return {"action": "transfer completed", "from": from_building, "to": to_building, "amount": float(amount)}
    
    def _get_building_balance(self, building):
        """Get current balance for a building."""
        row = self.conn.execute("""
            SELECT COALESCE(SUM(CASE WHEN building = ? THEN amount ELSE 0 END) -
                            SUM(CASE WHEN building = ? THEN amount ELSE 0 END), 0) as balance
            FROM ledger_entries 
            WHERE (building = ? OR building = ?) AND status = 'confirmed'
        """, (building, building, building, building)).fetchone()
        return row["balance"] or 0.0
    
    def _get_finance_metrics(self):
        """Get finance system metrics."""
        metrics = {}
        
        # Total volume
        row = self.conn.execute(
            "SELECT COALESCE(SUM(ABS(amount)), 0) AS total_volume FROM ledger_entries WHERE status = 'confirmed'"
        ).fetchone()
        metrics["total_volume_usd"] = row[0] if row else 0.0
        
        # Active buildings
        active_buildings = self.conn.execute(
            "SELECT DISTINCT building FROM ledger_entries WHERE status = 'confirmed' AND building != 'finance_building'"
        ).fetchall()
        metrics["active_buildings"] = len(active_buildings)
        
        # Pending transactions
        row = self.conn.execute(
            "SELECT COUNT(*) AS c FROM ledger_entries WHERE status = 'pending'"
        ).fetchone()
        metrics["pending_transactions"] = row[0] if row else 0
        
        # Record metrics
        now = now_iso()
        for key, value in metrics.items():
            self.conn.execute(
                "INSERT INTO finance_metrics (metric_name, metric_value, recorded_at, building) VALUES (?, ?, ?, ?)",
                (key, value, now, "finance_building")
            )
        self.conn.commit()
        
        return metrics
    
    def work(self):
        """Periodic maintenance and metrics."""
        # Auto-confirm pending transactions older than 24 hours
        self.conn.execute("""
            UPDATE ledger_entries 
            SET status = 'confirmed' 
            WHERE status = 'pending' AND timestamp < datetime('now', '-1 day')
        """)
        self.conn.commit()
        
        self.log("tick", "finance building processing complete")
    
    def report(self):
        """Finance department report for City Hall."""
        metrics = self._get_finance_metrics()
        return {
            "building": self.name,
            "subject": self.subject,
            "total_volume_usd": metrics.get("total_volume_usd", 0),
            "active_buildings": metrics.get("active_buildings", 0),
            "pending_transactions": metrics.get("pending_transactions", 0),
            "role": "orchestrator"
        }

    def _status(self):
        """Return status information for the agent."""
        return self.report()
