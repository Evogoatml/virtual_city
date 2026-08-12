"""
Department base class — internal component of a Building.
If building_name is set, events log under that building (FK-safe aggregation).
If not set, events log under the department's own name.
"""
from city.agent import Agent


class Department(Agent):
    """Base class for departments that live inside a building."""

    building_name = None  # Set to the parent building's agent name

    def _log_name(self):
        return self.building_name or self.name

    def log(self, event_type, message, data=None):
        from city.db import log_event
        log_event(self.conn, self._log_name(), event_type, message, data)

    def set_status(self, status):
        from city.db import set_status
        set_status(self.conn, self._log_name(), status)
