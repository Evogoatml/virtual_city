"""
Meta-Cognition Layer — Self-awareness, goal synthesis, utility evaluation.

Each building maintains a self-profile: its capabilities, goals, performance
history, and current strategy shape. The CEO defines the full meta stack;
other buildings pull what they need.
"""

import json
import time
from datetime import datetime, timezone
from city.db import get_raw_connection, now_iso, log_event


# ---------------------------------------------------------------------------
# Self-Profile — what the building knows about itself
# ---------------------------------------------------------------------------

class SelfProfile:
    """Persistent self-knowledge: capabilities, stats, performance trends."""

    def __init__(self, agent):
        self.agent = agent
        self._cache = {}

    def get_capabilities(self):
        """Return list of command patterns this agent handles."""
        return [p.pattern for p, _ in self.agent._rules]

    def get_performance_summary(self):
        """Aggregate own performance from events table."""
        conn = get_raw_connection()
        try:
            row = conn.execute("""
                SELECT
                    COUNT(*) as total_events,
                    SUM(CASE WHEN type = 'error' THEN 1 ELSE 0 END) as errors,
                    SUM(CASE WHEN type = 'query' THEN 1 ELSE 0 END) as queries,
                    SUM(CASE WHEN type = 'plan_step' THEN 1 ELSE 0 END) as plan_steps
                FROM events WHERE agent_name = ?
            """, (self.agent.name,)).fetchone()
            return dict(row) if row else {"total_events": 0, "errors": 0, "queries": 0, "plan_steps": 0}
        finally:
            conn.close()

    def get_performance_trend(self, hours=24):
        """Get event counts per hour for trend analysis."""
        conn = get_raw_connection()
        try:
            rows = conn.execute("""
                SELECT type, COUNT(*) as count
                FROM events
                WHERE agent_name = ? AND timestamp > datetime('now', ?)
                GROUP BY type
            """, (self.agent.name, f'-{hours} hours')).fetchall()
            return {r["type"]: r["count"] for r in rows}
        finally:
            conn.close()

    def to_dict(self):
        return {
            "name": self.agent.name,
            "subject": self.agent.subject,
            "district": self.agent.district,
            "capabilities": self.get_capabilities(),
            "performance": self.get_performance_summary(),
        }


# ---------------------------------------------------------------------------
# Goal Synthesis — building generates its own goals from context
# ---------------------------------------------------------------------------

class GoalSynthesizer:
    """Generates new goals based on performance, time since last goal, and strategy shape."""

    def __init__(self, agent):
        self.agent = agent

    def synthesize(self):
        """Check if new goals are needed. Returns list of suggested goal titles."""
        conn = get_raw_connection()
        try:
            active = conn.execute(
                "SELECT COUNT(*) as c FROM goals WHERE agent_name = ? AND status = 'active'",
                (self.agent.name,),
            ).fetchone()["c"]
            if active > 0:
                return []  # already has active goals

            # No active goals — generate from context
            profile = SelfProfile(self.agent)
            perf = profile.get_performance_summary()

            suggestions = []

            # If few queries happened, suggest exploration
            if perf["queries"] < 5:
                suggestions.append(f"Explore new {self.agent.subject} opportunities")

            # If errors exist, suggest recovery
            if perf["errors"] > 0:
                suggestions.append(f"Resolve {perf['errors']} outstanding issue(s)")

            # Default growth goal per agent type
            domain_goals = {
                "crypto_trading": ["Build balanced portfolio", "Optimize position sizing"],
                "market_data": ["Expand monitored pairs", "Improve data freshness"],
                "finance_treasury": ["Optimize capital allocation", "Track all revenue streams"],
                "shopify": ["Increase order volume", "Find top-performing products"],
                "product_flipping": ["Source high-margin items", "Clear slow inventory"],
                "social_affiliates": ["Launch new campaigns", "Improve conversion rates"],
                "content_creation": ["Grow content pipeline", "Increase publishing cadence"],
                "content_automation": ["Test new AI providers", "Reduce generation costs"],
                "content_analytics": ["Deepen viral pattern analysis", "Improve ROI tracking"],
                "sourcing_research": ["Find high-scoring leads", "Action top opportunities"],
                "city_hall": ["Coordinate city-wide strategy", "Improve inter-building flow"],
            }
            suggestions.extend(domain_goals.get(self.agent.name, ["Optimize operations"])[:2])

            return suggestions[:3]
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Utility Evaluator — evaluates outcomes, makes trade-off decisions
# ---------------------------------------------------------------------------

class UtilityEvaluator:
    """Evaluates outcomes using a utility function. Supports trade-off decisions."""

    def __init__(self, agent):
        self.agent = agent
        self.weights = {"revenue": 1.0, "efficiency": 0.8, "growth": 0.6, "stability": 0.9}

    def evaluate_outcome(self, result_dict):
        """Score a result (0-1) based on utility weights."""
        score = 0.0
        total_weight = 0.0
        for key, weight in self.weights.items():
            val = result_dict.get(key, None)
            if val is not None:
                score += weight * min(1.0, max(0.0, float(val)))
                total_weight += weight
        return score / total_weight if total_weight > 0 else 0.5

    def choose_best_action(self, options):
        """Given list of (action_name, expected_utility) tuples, pick best."""
        if not options:
            return None
        return max(options, key=lambda x: x[1])[0]

    def to_dict(self):
        return {"weights": self.weights}


# ---------------------------------------------------------------------------
# Reflection Loop — periodic self-analysis
# ---------------------------------------------------------------------------

class ReflectionLoop:
    """Periodic self-reflection: analyze recent performance, adjust goals, log insights."""

    def __init__(self, agent):
        self.agent = agent
        self._last_reflection = 0
        self._reflection_interval = 300  # every 5 minutes

    def tick(self):
        """Called during work(). Reflects periodically."""
        now = time.time()
        if now - self._last_reflection < self._reflection_interval:
            return
        self._last_reflection = now

        profile = SelfProfile(self.agent)
        perf = profile.get_performance_summary()
        trend = profile.get_performance_trend(24)

        insight_parts = []
        if perf["errors"] > 0:
            insight_parts.append(f"{perf['errors']} errors in recent activity")
        if perf["queries"] > 0:
            insight_parts.append(f"{perf['queries']} commands processed")
        if perf["plan_steps"] > 0:
            insight_parts.append(f"{perf['plan_steps']} plan steps auto-executed")

        if insight_parts:
            insight = f"Self-reflection: {', '.join(insight_parts)}"
            conn = get_raw_connection()
            try:
                log_event(conn, self.agent.name, "reflection", insight, {
                    "performance": perf,
                    "trend": trend,
                })
            finally:
                conn.close()

            # Synthesize new goals if needed
            synth = GoalSynthesizer(self.agent)
            new_goals = synth.synthesize()
            if new_goals:
                from city.orchestrator import GoalTracker
                for title in new_goals:
                    gid = GoalTracker.create_goal(self.agent.name, title)
                    log_event(conn or get_raw_connection(), self.agent.name, "goal_synthesized",
                              f"Auto-generated goal: {title}", {"goal_id": gid})