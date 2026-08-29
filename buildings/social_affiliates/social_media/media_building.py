"""
Media Building — Aggregates content creation, automation, and analytics departments.
"""
from city.agent import Agent
from city.db import now_iso

class MediaBuildingAgent(Agent):
    name = "media_building"
    subject = "Media Building"
    district = "Media"
    color = "#ff9800"

    job_title = "Media Director"
    mission = "Drive content creation, automation, and viral analytics."
    cog_interval = 120

    def setup_schema(self):
        pass

    def register_rules(self):
        self.rule(r"^status$")(self._status)
        self.rule(r"^report$")(self._report)
        self.rule(r"^departments$")(self._departments)

    def _status(self):
        return {"agent": self.name, "status": self.status}

    def _report(self):
        from city.registry import get_registry
        registry = get_registry(self.conn)
        dept_status = {}
        for name, agent in registry.items():
            if getattr(agent, "building_name", None) == "media_building":
                dept_status[name] = agent.report()
        return {"building": self.name, "departments": dept_status}

    def _departments(self):
        return {"building": self.name, "departments": ["social_affiliates"]}

    def report(self):
        return {"agent": self.name, "subject": self.subject, "status": self.status}
