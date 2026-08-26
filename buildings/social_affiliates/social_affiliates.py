"""
Social Affiliates Department — Internal component of Commerce Building.
Handles affiliate campaigns, clicks, conversions, revenue.
"""
from city.department import Department
from city.db import now_iso


class SocialAffiliatesDepartment(Department):
    name = "social_affiliates"
    subject = "Social Affiliates Dept"
    district = "Media District"
    color = "#e1306c"

    def setup_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS affiliate_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                offer TEXT NOT NULL,
                clicks INTEGER NOT NULL DEFAULT 0,
                conversions INTEGER NOT NULL DEFAULT 0,
                revenue REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def register_rules(self):
        self.rule(r"^campaign\s+(?P<platform>\w+)\s+(?P<offer>.+)$")(self._new_campaign)
        self.rule(r"^click\s+(?P<offer>.+)$")(self._click)
        self.rule(r"^convert\s+(?P<offer>.+?)\s+revenue\s+(?P<revenue>[\d.]+)$")(self._convert)
        self.rule(r"^stats$")(self._stats)
        self.rule(r"^status$")(self._status)

    def _find(self, offer):
        return self.conn.execute(
            "SELECT * FROM affiliate_campaigns WHERE offer = ? ORDER BY id DESC LIMIT 1", (offer,)
        ).fetchone()

    def _new_campaign(self, platform, offer):
        self.conn.execute(
            "INSERT INTO affiliate_campaigns (platform, offer, created_at) VALUES (?, ?, ?)",
            (platform, offer, now_iso()),
        )
        self.conn.commit()
        return {"action": "campaign created", "platform": platform, "offer": offer}

    def _click(self, offer):
        row = self._find(offer)
        if not row:
            return {"error": f"no campaign '{offer}'"}
        self.conn.execute("UPDATE affiliate_campaigns SET clicks = clicks + 1 WHERE id = ?", (row["id"],))
        self.conn.commit()
        return {"action": "click logged", "offer": offer}

    def _convert(self, offer, revenue):
        row = self._find(offer)
        if not row:
            return {"error": f"no campaign '{offer}'"}
        self.conn.execute(
            "UPDATE affiliate_campaigns SET conversions = conversions + 1, revenue = revenue + ? WHERE id = ?",
            (float(revenue), row["id"]),
        )
        self.conn.commit()
        return {"action": "conversion logged", "offer": offer, "revenue": float(revenue)}

    def _stats(self):
        rows = self.conn.execute("SELECT * FROM affiliate_campaigns ORDER BY revenue DESC").fetchall()
        return {"campaigns": [dict(r) for r in rows]}

    def _status(self):
        return self.report()

    # ----------------------------------------------------- runtime skills
    def register_skills(self):
        self.add_skill(
            "summarize", "Report affiliate performance (clicks, conversions, revenue).",
            fn=lambda agent, **kw: agent._stats(), risk="read", cost_kind="local",
            default=True,
        )
        self.add_skill(
            "create_campaign", "Open an affiliate campaign for a platform + offer.",
            fn=lambda agent, **kw: agent._new_campaign(
                kw.get("platform", "social"), kw.get("offer", "default")),
            risk="write", cost_kind="local", event="affiliate.campaign_created",
        )
        self.add_skill(
            "log_click", "Log a click of interest on an offer.",
            fn=lambda agent, **kw: agent._click(kw.get("offer", "default")),
            risk="write", cost_kind="local",
        )
        self.add_skill(
            "log_conversion", "Log a conversion (sale) and its revenue for an offer.",
            fn=lambda agent, **kw: agent._convert(
                kw.get("offer", "default"), float(kw.get("revenue", 0) or 0)),
            risk="write", cost_kind="local", event="affiliate.conversion",
        )

    def handle_event(self, event_type, message="", data=None):
        """React to events from other buildings (real interaction)."""
        data = data or {}
        if event_type == "content.published":
            offer = data.get("offer") or data.get("topic") or "default"
            self._new_campaign("social", offer)
            return {"campaign": "synced from published content", "offer": offer}
        return None

    def work(self):
        row = self.conn.execute(
            "SELECT COALESCE(SUM(clicks),0) AS clicks, COALESCE(SUM(revenue),0) AS rev FROM affiliate_campaigns"
        ).fetchone()
        self.log("tick", f"{row['clicks']} clicks, ${row['rev']:.0f} revenue")

    def report(self):
        row = self.conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(clicks),0) AS clicks, COALESCE(SUM(conversions),0) AS conv, COALESCE(SUM(revenue),0) AS rev FROM affiliate_campaigns"
        ).fetchone()
        conv_rate = (row["conv"] / row["clicks"] * 100) if row["clicks"] else 0.0
        return {
            "department": self.name,
            "subject": self.subject,
            "campaigns": row["n"],
            "clicks": row["clicks"],
            "conversions": row["conv"],
            "conversion_rate": round(conv_rate, 2),
            "revenue": round(row["rev"], 2),
            "revenue_usd": round(row["rev"], 2),
        }