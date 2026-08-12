"""
Orchestration engine for Virtual City.

Each building gets a full lifecycle: plan-driven behavior, event
publish/subscribe, goal/task tracking, and config management.
"""
import json
import re
from datetime import datetime, timezone
from city.db import get_raw_connection, now_iso, log_event, set_status


# ---------------------------------------------------------------------------
# Config — per-agent key/value store for accounts, API keys, preferences
# ---------------------------------------------------------------------------

class AgentConfig:
    """Read/write config for any agent (API keys, account connections, preferences)."""

    def __init__(self, agent_name):
        self.agent_name = agent_name

    def get(self, key, default=None):
        conn = get_raw_connection()
        try:
            row = conn.execute(
                "SELECT value FROM agent_config WHERE agent_name = ? AND key = ?",
                (self.agent_name, key),
            ).fetchone()
            return row["value"] if row else default
        finally:
            conn.close()

    def get_all(self):
        conn = get_raw_connection()
        try:
            rows = conn.execute(
                "SELECT key, value, category, secret FROM agent_config WHERE agent_name = ? ORDER BY category, key",
                (self.agent_name,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def set(self, key, value, category="general", secret=False):
        conn = get_raw_connection()
        try:
            now = now_iso()
            conn.execute(
                """INSERT INTO agent_config (agent_name, key, value, category, secret, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(agent_name, key) DO UPDATE SET
                       value=excluded.value, category=excluded.category,
                       secret=excluded.secret, updated_at=excluded.updated_at""",
                (self.agent_name, key, str(value), category, 1 if secret else 0, now, now),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def delete(self, key):
        conn = get_raw_connection()
        try:
            conn.execute(
                "DELETE FROM agent_config WHERE agent_name = ? AND key = ?",
                (self.agent_name, key),
            )
            conn.commit()
            return conn.total_changes > 0
        finally:
            conn.close()

    def get_accounts(self):
        """Return only non-secret config keys (for UI display)."""
        return [c for c in self.get_all() if not c["secret"]]

    def get_categories(self):
        """Group config by category."""
        groups = {}
        for item in self.get_all():
            groups.setdefault(item["category"], []).append(item)
        return groups


# ---------------------------------------------------------------------------
# Event Bus — agents publish events, subscribers get notified
# ---------------------------------------------------------------------------

class EventBus:
    """Inter-agent pub/sub event bus. Events are persisted and routed."""

    @staticmethod
    def publish(agent_name, event_type, message, data=None):
        """Publish an event. Logs it and routes to subscribers."""
        conn = get_raw_connection()
        try:
            log_event(conn, agent_name, event_type, message, data)
            subscribers = conn.execute(
                """SELECT subscriber_name FROM subscriptions
                   WHERE publisher_name = ? AND (event_type = ? OR event_type = '*')""",
                (agent_name, event_type),
            ).fetchall()
            for row in subscribers:
                conn.execute(
                    """INSERT INTO events (agent_name, timestamp, type, message, data_json)
                       VALUES (?, ?, ?, ?, ?)""",
                    (row["subscriber_name"], now_iso(),
                     f"from:{agent_name}:{event_type}",
                     f"Event from {agent_name}: {message}",
                     json.dumps({"source": agent_name, "event_type": event_type, "data": data or {}})),
                )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def subscribe(subscriber, publisher, event_type="*"):
        """Subscribe subscriber to all events from publisher (or a specific type)."""
        conn = get_raw_connection()
        try:
            now = now_iso()
            conn.execute(
                """INSERT OR IGNORE INTO subscriptions
                   (subscriber_name, publisher_name, event_type, created_at)
                   VALUES (?, ?, ?, ?)""",
                (subscriber, publisher, event_type, now),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def unsubscribe(subscriber, publisher, event_type="*"):
        conn = get_raw_connection()
        try:
            conn.execute(
                "DELETE FROM subscriptions WHERE subscriber_name=? AND publisher_name=? AND event_type=?",
                (subscriber, publisher, event_type),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def get_subscriptions(agent_name):
        conn = get_raw_connection()
        try:
            rows = conn.execute(
                """SELECT s.*, a.subject as publisher_subject
                   FROM subscriptions s
                   JOIN agents a ON a.name = s.publisher_name
                   WHERE s.subscriber_name = ?
                   ORDER BY s.publisher_name""",
                (agent_name,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Goal / Task tracking — plans become actionable goals with measurable tasks
# ---------------------------------------------------------------------------

class GoalTracker:
    """Break a plan into goals, each with auto-executable tasks."""

    @staticmethod
    def create_goal(agent_name, title):
        conn = get_raw_connection()
        try:
            now = now_iso()
            cur = conn.execute(
                "INSERT INTO goals (agent_name, title, status, progress, created_at, updated_at) VALUES (?, ?, 'active', 0, ?, ?)",
                (agent_name, title, now, now),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    @staticmethod
    def add_task(goal_id, title, description="", auto_command=""):
        conn = get_raw_connection()
        try:
            now = now_iso()
            cur = conn.execute(
                "INSERT INTO tasks (goal_id, title, description, status, auto_command, created_at) VALUES (?, ?, ?, 'pending', ?, ?)",
                (goal_id, title, description, auto_command, now),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    @staticmethod
    def complete_task(task_id):
        conn = get_raw_connection()
        try:
            now = now_iso()
            conn.execute(
                "UPDATE tasks SET status = 'completed', completed_at = ? WHERE id = ?",
                (now, task_id),
            )
            conn.commit()
            # recalculate goal progress
            task = conn.execute("SELECT goal_id FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if task:
                GoalTracker._recalc_progress(task["goal_id"])
        finally:
            conn.close()

    @staticmethod
    def _recalc_progress(goal_id):
        conn = get_raw_connection()
        try:
            total = conn.execute("SELECT COUNT(*) as c FROM tasks WHERE goal_id = ?", (goal_id,)).fetchone()["c"]
            done = conn.execute("SELECT COUNT(*) as c FROM tasks WHERE goal_id = ? AND status = 'completed'", (goal_id,)).fetchone()["c"]
            progress = (done / total * 100) if total > 0 else 0
            now = now_iso()
            status = "completed" if done >= total and total > 0 else "active"
            conn.execute(
                "UPDATE goals SET progress = ?, status = ?, updated_at = ? WHERE id = ?",
                (progress, status, now, goal_id),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def get_goals(agent_name):
        conn = get_raw_connection()
        try:
            goals = conn.execute(
                "SELECT * FROM goals WHERE agent_name = ? ORDER BY created_at DESC",
                (agent_name,),
            ).fetchall()
            result = []
            for g in goals:
                tasks = conn.execute(
                    "SELECT * FROM tasks WHERE goal_id = ? ORDER BY id",
                    (g["id"],),
                ).fetchall()
                result.append({**dict(g), "tasks": [dict(t) for t in tasks]})
            return result
        finally:
            conn.close()

    @staticmethod
    def parse_plan_into_goals(agent_name, plan_text):
        """Auto-parse a plan text into goals and tasks using simple heuristics.
        Lines starting with # are goal titles. Lines with - or * are tasks.
        If a task contains a known command pattern, set it as auto_command."""
        goals_created = 0
        current_goal_id = None
        for line in plan_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                title = line.lstrip("#").strip()
                if title:
                    current_goal_id = GoalTracker.create_goal(agent_name, title)
                    goals_created += 1
            elif line.startswith("-") or line.startswith("*"):
                if current_goal_id is None:
                    current_goal_id = GoalTracker.create_goal(agent_name, "Plan Tasks")
                    goals_created += 1
                task_text = line.lstrip("-*").strip()
                auto_cmd = _detect_command(task_text)
                GoalTracker.add_task(current_goal_id, task_text, auto_command=auto_cmd)
        return goals_created


def _detect_command(text):
    """Try to extract a runnable command from task text."""
    patterns = [
        (r"\b(buy|sell)\s+(\w+)\s*@?\s*([\d.]+)", lambda m: f"{m.group(1)} {m.group(2)} @ {m.group(3)}"),
        (r"\bclose\s+(\w+)", lambda m: f"close {m.group(1)}"),
        (r"\bpositions\b", lambda _: "positions"),
        (r"\bpnl\b", lambda _: "pnl"),
        (r"\b(revenue|summary|ledger)\b", lambda m: m.group(1)),
        (r"\border\b", lambda _: "revenue"),
        (r"\binventory\b", lambda _: "inventory"),
        (r"\bqueue\b", lambda _: "queue"),
        (r"\bpublish\b", lambda _: "queue"),
        (r"\bstats\b", lambda _: "stats"),
        (r"\bmeeting\b", lambda _: "meeting"),
        (r"\bstatus\b", lambda _: "status"),
    ]
    for pattern, handler in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return handler(m)
    return ""


# ---------------------------------------------------------------------------
# Plan Executor — runs plan steps during work() ticks
# ---------------------------------------------------------------------------

class PlanExecutor:
    """Reads the active plan, auto-executes pending tasks during work ticks."""

    def __init__(self, agent):
        self.agent = agent

    def tick(self):
        """Called during agent.work(). Executes next pending task if plan is active."""
        conn = get_raw_connection()
        try:
            plan = conn.execute(
                "SELECT * FROM plans WHERE agent_name = ? AND status = 'active'",
                (self.agent.name,),
            ).fetchone()
            if not plan or not plan["plan_text"]:
                return

            # Parse plan into goals/tasks if no goals exist yet
            goals = GoalTracker.get_goals(self.agent.name)
            if not goals:
                GoalTracker.parse_plan_into_goals(self.agent.name, plan["plan_text"])
                goals = GoalTracker.get_goals(self.agent.name)

            # Find next pending task across all active goals
            for goal in goals:
                if goal["status"] != "active":
                    continue
                for task in goal["tasks"]:
                    if task["status"] == "pending":
                        if task["auto_command"]:
                            try:
                                self.agent.conn = conn
                                result = self.agent.process(task["auto_command"])
                                if result and result.get("ok"):
                                    GoalTracker.complete_task(task["id"])
                                    log_event(conn, self.agent.name, "plan_step",
                                              f"Auto-executed: {task['auto_command']}",
                                              {"task": task["title"], "goal": goal["title"]})
                            except Exception:
                                pass
                        return  # one task per tick
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Building Orchestrator — manages lifecycle for all buildings
# ---------------------------------------------------------------------------

class BuildingOrchestrator:
    """Top-level orchestrator. Manages all buildings' lifecycle, plan execution,
    event routing, and provides aggregate status."""

    def __init__(self):
        self._plan_executors = {}

    def register(self, agent):
        self._plan_executors[agent.name] = PlanExecutor(agent)

    def tick_all(self):
        """Called on each work_tick (30s). Runs plan executors for all agents."""
        for executor in self._plan_executors.values():
            try:
                executor.tick()
            except Exception:
                pass

    def get_orchestrator_state(self):
        """Return orchestration state for all agents."""
        conn = get_raw_connection()
        try:
            rows = conn.execute("""
                SELECT g.agent_name,
                       COUNT(g.id) as total_goals,
                       SUM(CASE WHEN g.status = 'completed' THEN 1 ELSE 0 END) as completed_goals,
                       AVG(g.progress) as avg_progress,
                       COUNT(t.id) as total_tasks,
                       SUM(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) as completed_tasks
                FROM goals g
                LEFT JOIN tasks t ON t.goal_id = g.id
                GROUP BY g.agent_name
            """).fetchall()
            state = {}
            for r in rows:
                state[r["agent_name"]] = {
                    "total_goals": r["total_goals"],
                    "completed_goals": r["completed_goals"],
                    "avg_progress": round(r["avg_progress"] or 0, 1),
                    "total_tasks": r["total_tasks"],
                    "completed_tasks": r["completed_tasks"],
                }
            return state
        finally:
            conn.close()


# Singleton
ORCHESTRATOR = BuildingOrchestrator()