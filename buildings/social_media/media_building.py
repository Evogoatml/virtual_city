"""
Media Building — Orchestrates Content Creation, Automation, Analytics departments.
Departments are internal components, not separate agents.
"""
from city.agent import Agent
from city.db import now_iso

# Import internal departments
from .content_creation import ContentCreationDepartment
from .content_automation import ContentAutomationDepartment
from .content_analytics import ContentAnalyticsDepartment


class MediaBuildingAgent(Agent):
    name = "media_building"
    subject = "Media Building"
    district = "Media District"
    color = "#9c27b0"

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
            "content_creation": ContentCreationDepartment(self.conn),
            "content_automation": ContentAutomationDepartment(self.conn),
            "content_analytics": ContentAnalyticsDepartment(self.conn),
        }

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
        agg = {"ideas": 0, "drafts": 0, "published": 0, "videos": 0, "video_cost": 0, "engagement": 0, "roi": 0}
        for name, agent in self._get_departments().items():
            try:
                r = agent.report()
                for k in agg:
                    if k in r:
                        agg[k] += r[k]
            except Exception:
                pass
        return {
            "building": self.name,
            "total_ideas": agg["ideas"],
            "total_drafts": agg["drafts"],
            "total_published": agg["published"],
            "total_videos": agg["videos"],
            "total_video_cost_usd": agg["video_cost"],
            "avg_engagement": agg["engagement"],
            "roi_percentage": agg["roi"],
        }

    def _aggregate(self):
        return self._building_status()

    def work(self):
        status = self._building_status()
        self.log("tick", f"published={status['total_published']}, videos={status['total_videos']}")

    def report(self):
        return self._building_status()