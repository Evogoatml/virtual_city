"""
Mosaic Intelligence — cross-building pattern detection, collective optimization,
swarm coordination.

The mosaic layer detects emergent patterns across buildings (e.g.,
"content goes viral -> affiliates get clicks") and facilitates
coordinated action.
"""

import json
from city.db import get_raw_connection, now_iso, log_event


class MosaicDetector:
    """Detects cross-building event patterns and relationships."""

    def __init__(self):
        self._patterns = {}

    def scan(self):
        """Scan recent events across all agents for cross-building patterns."""
        conn = get_raw_connection()
        try:
            # Find event clusters: events with matching data types across agents
            rows = conn.execute("""
                SELECT e1.agent_name as source, e2.agent_name as target,
                       e1.type as event_type, COUNT(*) as frequency
                FROM events e1
                JOIN events e2 ON e2.timestamp > e1.timestamp
                    AND e2.timestamp < datetime(e1.timestamp, '+5 minutes')
                    AND e2.agent_name != e1.agent_name
                    AND e2.type != 'keep-alive'
                WHERE e1.timestamp > datetime('now', '-1 hour')
                GROUP BY e1.agent_name, e2.agent_name, e1.type
                HAVING frequency > 2
                ORDER BY frequency DESC
                LIMIT 20
            """).fetchall()

            patterns = []
            for r in rows:
                pattern = {
                    "source": r["source"],
                    "target": r["target"],
                    "event_type": r["event_type"],
                    "frequency": r["frequency"],
                    "strength": min(1.0, r["frequency"] / 10),
                }
                patterns.append(pattern)

            return patterns
        finally:
            conn.close()

    def get_mosaic_state(self):
        patterns = self.scan()
        return {
            "patterns": patterns,
            "active_links": len(patterns),
            "timestamp": now_iso(),
        }


class MosaicOrchestrator:
    """Coordinates multi-building actions based on mosaic patterns."""

    def __init__(self):
        self.detector = MosaicDetector()

    def tick(self):
        """Periodic mosaic coordination. Called from CEO's work()."""
        patterns = self.detector.scan()
        if not patterns:
            return

        conn = get_raw_connection()
        try:
            for p in patterns[:3]:  # top 3 patterns
                if p["strength"] > 0.5:
                    log_event(conn, "city_hall", "mosaic_pattern",
                              f"Mosaic: {p['source']} -> {p['target']} ({p['event_type']}, freq={p['frequency']})",
                              {"pattern": p})
        finally:
            conn.close()


class SwarmCoordinator:
    """Coordinates collective behavior when multiple buildings share a goal."""

    def __init__(self):
        pass

    def find_synergies(self):
        """Find buildings that should collaborate based on their active goals."""
        conn = get_raw_connection()
        try:
            goals = conn.execute("""
                SELECT g.agent_name, g.title, g.progress
                FROM goals g
                WHERE g.status = 'active'
                ORDER BY g.agent_name
            """).fetchall()

            # Map goal keywords to building groups
            synergies = {
                "revenue": ["shopify", "crypto_trading", "social_affiliates", "finance_treasury"],
                "content": ["content_creation", "content_automation", "content_analytics", "media_building"],
                "data": ["market_data", "content_analytics", "sourcing_research"],
                "growth": ["product_flipping", "shopify", "social_affiliates", "sourcing_research"],
            }

            active_groups = set()
            for g in goals:
                for keyword, members in synergies.items():
                    if keyword in g["title"].lower():
                        active_groups.add(tuple(sorted(members)))

            return [list(g) for g in active_groups]
        finally:
            conn.close()


# Singleton
MOSAIC = MosaicOrchestrator()
SWARM = SwarmCoordinator()