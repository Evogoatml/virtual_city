"""
Media Building — Orchestrates Content Creation, Automation, Analytics departments.
Aggregates registry-owned departments (does not re-instantiate them).
"""
from city.agent import Agent


class MediaBuildingAgent(Agent):
    name = "media_building"
    subject = "Media Building"
    district = "Media District"
    color = "#9c27b0"

    DEPT_NAMES = ("content_creation", "content_automation", "content_analytics")

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
        """Pull live department agents from the city registry."""
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
        agg = {
            "ideas": 0,
            "drafts": 0,
            "published": 0,
            "videos": 0,
            "video_cost": 0.0,
            "engagement": 0.0,
            "roi": 0.0,
        }
        depts = self._get_departments()
        eng_n = 0
        for agent in depts.values():
            try:
                r = agent.report()
            except Exception:
                continue
            agg["ideas"] += int(r.get("ideas") or 0)
            agg["drafts"] += int(r.get("drafts") or 0)
            agg["published"] += int(r.get("published") or 0)
            agg["videos"] += int(r.get("total_videos") or r.get("videos") or 0)
            agg["video_cost"] += float(r.get("total_cost_usd") or r.get("video_cost") or 0)
            if "avg_engagement" in r and isinstance(r["avg_engagement"], (int, float)):
                agg["engagement"] += float(r["avg_engagement"])
                eng_n += 1
            if "roi_percentage" in r and isinstance(r["roi_percentage"], (int, float)):
                agg["roi"] = float(r["roi_percentage"])  # last/analytics wins
        return {
            "building": self.name,
            "departments_online": list(depts.keys()),
            "total_ideas": agg["ideas"],
            "total_drafts": agg["drafts"],
            "total_published": agg["published"],
            "total_videos": agg["videos"],
            "total_video_cost_usd": round(agg["video_cost"], 2),
            "avg_engagement": round(agg["engagement"] / eng_n, 2) if eng_n else 0,
            "roi_percentage": round(agg["roi"], 2),
        }

    def _aggregate(self):
        return self._building_status()

    def work(self):
        status = self._building_status()
        self.log(
            "tick",
            f"published={status['total_published']}, videos={status['total_videos']}",
        )

    def report(self):
        return self._building_status()
