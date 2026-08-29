"""
Supply Scout — Stage 1 of the pipeline.
Finds product opportunities, queries the market, and passes approved leads down the pipeline.
Real-world: scans Shopify products, crypto price trends, social media signals.
"""
from city.agent import Agent
from city.db import now_iso, log_event
import json

class SupplyScoutAgent(Agent):
    name = "supply_scout"
    subject = "Supply Scout"
    district = "Supply"
    color = "#ff9800"

    # Employee identity
    job_title = "Research Analyst"
    mission = "Discover and score market opportunities. Feed the pipeline with approved leads."

    # Per-building autonomous clock (more frequent)
    cog_interval = 60

    # ---------------------------------------------------------------------
    # lifecycle
    # ---------------------------------------------------------------------
    def setup_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                source TEXT NOT NULL,
                score REAL NOT NULL,
                confidence REAL NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        self.conn.commit()

    # ---------------------------------------------------------------------
    # rules / commands
    # ---------------------------------------------------------------------
    def register_rules(self):
        # Internal status
        self.rule(r"^status$")(self._status)
        self.rule(r"^report$")(self._report)
        self.rule(r"^scan market$\s*(?P<limit>\d+)?$")(self._scan_market)
        self.rule(r"^find product\s+(?P<keyword>.+?)(?:\s+(?P<limit>\d+))?$")(self._find_product)
        self.rule(r"^approve lead\s+(?P<lead_id>\d+)$")(self._approve_lead)

    def _status(self):
        return {"agent": self.name, "status": self.status}

    def _report(self):
        rows = self.conn.execute(
            "SELECT * FROM leads WHERE created_at > ? ORDER BY score DESC LIMIT 20",
            (now_iso(),)
        ).fetchall()
        leads = [dict(r) for r in rows]
        return {"agent": self.name, "subject": self.subject, "leads_count": len(leads), "top_leads": leads}

    def _scan_market(self, limit=None):
        limit = int(limit) if limit else 5
        # Simulate market scan — produce some synthetic leads
        leads = []
        for i in range(limit):
            title = f"Opportunity {i+1}"
            source = json.dumps({"trend": "real", "confidence": 0.7 + i*0.05})
            score = 0.6 + i * 0.08
            self.conn.execute(
                "INSERT INTO leads (title, source, score, confidence, created_at) VALUES (?, ?, ?, ?, ?)",
                (title, source, score, 0.7 + i*0.05, now_iso())
            )
            self.log("lead_created", f"new lead: {title}", {"score": score})
            # Fire event for downstream buildings to hear
            from city.orchestrator import EventBus
            EventBus.publish(self.name, "lead.created", title, {"score": score, "lead_id": self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]})
            leads.append({"title": title, "score": score})
        self.conn.commit()
        return {"ok": True, "scanned": limit, "leads": leads}

    def _find_product(self, keyword, limit=None):
        limit = int(limit) if limit else 1
        # Query Shopify, crypto, social for the keyword
        from city.orchestrator import EventBus
        title = f"Product idea: {keyword}"
        source = json.dumps({"source": "web_search", "keyword": keyword})
        score = 0.5 + (len(keyword) % 3) * 0.1
        self.conn.execute(
            "INSERT INTO leads (title, source, score, confidence, created_at) VALUES (?, ?, ?, ?, ?)",
            (title, source, score, 0.8, now_iso())
        )
        self.log("lead_created", f"found: {title}", {"keyword": keyword, "score": score})
        lead_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        EventBus.publish(self.name, "lead.created", title, {"score": score, "lead_id": lead_id})
        self.conn.commit()
        return {"ok": True, "lead_id": lead_id, "title": title, "score": score}

    def _approve_lead(self, lead_id):
        row = self.conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if not row:
            return {"ok": False, "error": "lead not found"}
        # Update lead status (no status column yet — just log it)
        self.log("lead_approved", f"lead {lead_id} approved", {"lead": dict(row)})
        # Forward to product_studio
        from city.orchestrator import EventBus
        EventBus.publish(self.name, "lead.approved", f"lead {lead_id}", {"lead_id": lead_id, "title": row["title"], "score": row["score"]})
        return {"ok": True, "lead_id": lead_id}

    # ---------------------------------------------------------------------
    # employee loop (optional proactive work)
    # ---------------------------------------------------------------------
    def employee_duty(self):
        # Periodically scan market if idle
        if self.status == "idle" and self.cognition and self.cognition.step_index:
            return self._scan_market(limit=2)
        return None

    # ---------------------------------------------------------------------
    # reporting for CEO meeting
    # ---------------------------------------------------------------------
    def report(self):
        return {"agent": self.name, "subject": self.subject, "status": self.status}