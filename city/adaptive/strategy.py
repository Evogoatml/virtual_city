"""
Adaptation Engine — Strategy shapes, feedback processing, parameter tuning.

Each building has a strategy shape that governs its behavior mode:
- Explore: try new things, gather data
- Exploit: optimize what works
- Recover: fix issues, reduce risk
- Learn: reflect and adjust

Shape transitions are driven by the feedback processor.
"""

import json
import time
import random
from city.db import get_raw_connection, now_iso, log_event


SHAPES = {
    "explore": {
        "label": "Explore",
        "description": "Trying new approaches, gathering data",
        "activity_boost": 1.5,
        "risk_tolerance": 0.8,
        "auto_task_frequency": 2,
    },
    "exploit": {
        "label": "Exploit",
        "description": "Optimizing known successful patterns",
        "activity_boost": 1.0,
        "risk_tolerance": 0.3,
        "auto_task_frequency": 3,
    },
    "recover": {
        "label": "Recover",
        "description": "Resolving issues, reducing risk",
        "activity_boost": 0.5,
        "risk_tolerance": 0.1,
        "auto_task_frequency": 1,
    },
    "learn": {
        "label": "Learn",
        "description": "Reflecting, analyzing, adjusting strategy",
        "activity_boost": 0.7,
        "risk_tolerance": 0.5,
        "auto_task_frequency": 1,
    },
}


class StrategyShape:
    """Current operational shape for a building. Persisted in agent_config."""

    def __init__(self, agent):
        self.agent = agent
        self._current = None

    @property
    def current(self):
        if self._current is None:
            conn = get_raw_connection()
            try:
                row = conn.execute(
                    "SELECT value FROM agent_config WHERE agent_name = ? AND key = 'strategy_shape'",
                    (self.agent.name,),
                ).fetchone()
                self._current = row["value"] if row else "explore"
            finally:
                conn.close()
        return self._current

    def set(self, shape):
        if shape not in SHAPES:
            return False
        conn = get_raw_connection()
        try:
            now = now_iso()
            conn.execute(
                """INSERT INTO agent_config (agent_name, key, value, category, secret, created_at, updated_at)
                   VALUES (?, 'strategy_shape', ?, 'orchestration', 0, ?, ?)
                   ON CONFLICT(agent_name, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (self.agent.name, shape, now, now),
            )
            conn.commit()
            self._current = shape
            log_event(conn, self.agent.name, "shape_change", f"Strategy changed to {shape}: {SHAPES[shape]['description']}")
            return True
        finally:
            conn.close()

    @property
    def params(self):
        return SHAPES.get(self.current, SHAPES["explore"])

    def to_dict(self):
        return {"shape": self.current, "params": self.params}


# ---------------------------------------------------------------------------
# Feedback Processor — collects KPIs, evaluates performance, triggers shape changes
# ---------------------------------------------------------------------------

class FeedbackProcessor:
    """Collects performance feedback and suggests strategy adjustments."""

    def __init__(self, agent):
        self.agent = agent
        self._last_evaluation = 0
        self._eval_interval = 180  # evaluate every 3 minutes

    def tick(self):
        """Called during work(). Periodically evaluates performance and may shift shape."""
        now_time = time.time()
        if now_time - self._last_evaluation < self._eval_interval:
            return
        self._last_evaluation = now_time

        shape = StrategyShape(self.agent)
        conn = get_raw_connection()
        try:
            # Gather KPIs
            stats = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN type = 'error' THEN 1 ELSE 0 END) as errors,
                    SUM(CASE WHEN type = 'query' THEN 1 ELSE 0 END) as queries,
                    SUM(CASE WHEN type = 'plan_step' THEN 1 ELSE 0 END) as plan_steps,
                    SUM(CASE WHEN type = 'reflection' THEN 1 ELSE 0 END) as reflections
                FROM events
                WHERE agent_name = ? AND timestamp > datetime('now', '-1 hour')
            """, (self.agent.name,)).fetchone()

            total = stats["total"] or 0
            errors = stats["errors"] or 0
            queries = stats["queries"] or 0
            plan_steps = stats["plan_steps"] or 0
            error_rate = errors / max(total, 1)

            # Decision logic for shape transition
            current_shape = shape.current
            suggested = current_shape

            if error_rate > 0.3 and total > 5:
                suggested = "recover"
            elif error_rate < 0.05 and queries > 10 and plan_steps > 5:
                suggested = "exploit"
            elif queries < 3 and total > 0:
                suggested = "explore"
            elif plan_steps == 0 and queries > 5:
                suggested = "learn"

            if suggested != current_shape and random.random() < 0.4:
                shape.set(suggested)

            # Log evaluation
            log_event(conn, self.agent.name, "evaluation", 
                      f"Shape={current_shape}, errors={errors}/{total}, queries={queries}, steps={plan_steps}",
                      {"shape": current_shape, "suggested": suggested, "error_rate": error_rate})
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Auto task generator — creates tasks from the current strategy shape
# ---------------------------------------------------------------------------

class AutoTaskGenerator:
    """Generates tasks based on current strategy shape and domain."""

    TASK_TEMPLATES = {
        "crypto_trading": {
            "explore": ["Check BTC price", "Check ETH price", "Review market snapshot"],
            "exploit": ["Run positions report", "Run PnL report", "Optimize open positions"],
            "recover": ["Check for errors", "Review recent trades", "Stabilize portfolio"],
            "learn": ["Analyze trading patterns", "Review strategy performance", "Plan next trades"],
        },
        "market_data": {
            "explore": ["Add new trading pair", "Start stream on new exchange", "Take market snapshot"],
            "exploit": ["Monitor active pairs", "Review data freshness", "Optimize streams"],
            "recover": ["Restart streams", "Check exchange connections", "Clear stale data"],
            "learn": ["Analyze data patterns", "Review exchange performance", "Plan data strategy"],
        },
        "shopify": {
            "explore": ["Review product catalog", "Check order trends", "Research new products"],
            "exploit": ["Run revenue report", "Find top products", "Optimize pricing"],
            "recover": ["Check order errors", "Review returns", "Fix product listings"],
            "learn": ["Analyze sales patterns", "Review customer trends", "Plan promotions"],
        },
        "product_flipping": {
            "explore": ["Find new items to source", "Review market prices", "Research categories"],
            "exploit": ["List top inventory", "Run margin report", "Optimize pricing"],
            "recover": ["Review unsold items", "Check sourcing errors", "Clear dead stock"],
            "learn": ["Analyze flip patterns", "Review profit trends", "Plan sourcing strategy"],
        },
        "social_affiliates": {
            "explore": ["Review campaign options", "Check platform trends", "Research new offers"],
            "exploit": ["Run campaign stats", "Optimize best campaigns", "Scale top performers"],
            "recover": ["Check campaign errors", "Review low performers", "Fix broken links"],
            "learn": ["Analyze conversion patterns", "Review revenue trends", "Plan campaign strategy"],
        },
        "content_creation": {
            "explore": ["Brainstorm content ideas", "Research trending topics", "Plan content series"],
            "exploit": ["Publish queued content", "Review published performance", "Optimize pipeline"],
            "recover": ["Review stalled drafts", "Check pipeline errors", "Clear backlog"],
            "learn": ["Analyze engagement patterns", "Review content strategy", "Plan editorial calendar"],
        },
        "content_automation": {
            "explore": ["Test new AI provider", "Queue test video", "Review provider options"],
            "exploit": ["Process video queue", "Optimize generation params", "Review cost efficiency"],
            "recover": ["Check failed jobs", "Review budget status", "Retry stuck tasks"],
            "learn": ["Analyze generation patterns", "Review cost trends", "Plan automation strategy"],
        },
        "content_analytics": {
            "explore": ["Analyze trending content", "Research viral patterns", "Review platform insights"],
            "exploit": ["Run ROI analysis", "Optimize content strategy", "Review top performers"],
            "recover": ["Check alert status", "Review budget warnings", "Fix data gaps"],
            "learn": ["Deep analyze trends", "Review prediction accuracy", "Plan analytics focus"],
        },
        "sourcing_research": {
            "explore": ["Search for new leads", "Research categories", "Review scoring criteria"],
            "exploit": ["Action top leads", "Review high scorers", "Optimize search"],
            "recover": ["Check old leads", "Review rejected items", "Clean lead database"],
            "learn": ["Analyze lead patterns", "Review success rates", "Plan research focus"],
        },
        "finance_treasury": {
            "explore": ["Review all ledger entries", "Check revenue sources", "Research allocations"],
            "exploit": ["Run treasury summary", "Optimize allocations", "Track revenue trends"],
            "recover": ["Check ledger errors", "Review outstanding items", "Balance accounts"],
            "learn": ["Analyze financial patterns", "Review revenue streams", "Plan treasury strategy"],
        },
        "city_hall": {
            "explore": ["Review city status", "Check all building reports", "Assess city health"],
            "exploit": ["Hold coordination meeting", "Optimize inter-building flow", "Review city metrics"],
            "recover": ["Check building errors", "Identify issues", "Coordinate recovery"],
            "learn": ["Analyze city patterns", "Review building intelligence", "Plan city strategy"],
        },
    }

    def __init__(self, agent):
        self.agent = agent
        self._last_task = 0
        self._task_interval = 120

    def tick(self):
        """Generate a task if enough time has passed since last auto-task."""
        now_time = time.time()
        if now_time - self._last_task < self._task_interval:
            return
        self._last_task = now_time

        shape = StrategyShape(self.agent)
        templates = self.TASK_TEMPLATES.get(self.agent.name, {})
        tasks = templates.get(shape.current, templates.get("explore", ["Check status"]))
        task_text = random.choice(tasks)

        # Try to execute the task
        try:
            self.agent.conn = get_raw_connection()
            result = self.agent.process(task_text)
            if result and result.get("ok"):
                log_event(self.agent.conn, self.agent.name, "auto_task",
                          f"Auto task '{task_text}' completed", {"shape": shape.current, "task": task_text})
            else:
                log_event(self.agent.conn, self.agent.name, "auto_task",
                          f"Auto task '{task_text}' returned: {result}", {"shape": shape.current, "task": task_text})
        except Exception:
            pass