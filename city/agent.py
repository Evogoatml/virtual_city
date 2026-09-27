"""
Base Agent class. Each building in the city is backed by one Agent
subclass. Processing is rule-based (keyword/regex dispatch) — no LLM
calls, per spec.
"""
import os
import re
from city.db import log_event, set_status, now_iso
from city.cognition import CognitiveOrchestrator


class Agent:
    # --- Override in subclasses ---
    name = "base_agent"          # unique key, also the building id
    subject = "general"          # short label shown on the building
    district = "Downtown"        # grouping label (unused for layout, useful for UI)
    color = "#607d8b"            # building fill color

    def __init__(self, conn):
        self.conn = conn
        self._rules = []  # list of (compiled_regex, handler_name)
        self.skills = []  # list[Skill] for the real Agent Runtime
        self.cognition = CognitiveOrchestrator(self)  # per-building autonomous orchestrator
        self.setup_schema()
        self.register_rules()
        self.register_skills()
        self._register_orchestrator()

    @property
    def cognitive(self):
        """Backwards-compatible alias for self.cognition (per-building orchestrator)."""
        return self.cognition

    def _register_orchestrator(self):
        """Register this agent with the building orchestrator."""
        from city.orchestrator import ORCHESTRATOR
        ORCHESTRATOR.register(self)

    # --- Hooks for subclasses ---
    def setup_schema(self):
        """Create any agent-specific tables. Override as needed."""
        pass

    def register_rules(self):
        """Populate self._rules with (pattern, handler) pairs. Override."""
        pass

    def register_skills(self):
        """Populate self.skills with runtime Skills. Override."""
        pass

    def report(self) -> dict:
        """Summary used by City Hall's daily meeting. Override."""
        return {"agent": self.name, "subject": self.subject, "summary": "no report configured"}

    # Per-building autonomous clock (seconds). Override on any Agent subclass
    # to give that building its own reasoning cadence (#1 chronoschedule).
    cog_interval = 30

    # When True, the work_tick and cog_tick schedulers skip this building entirely.
    # Override on specific agents that should not run continuously.
    paused = False

    # --- Employee operating model ---
    # What this building does as an employee, used for reporting + self-directed
    # to-do lists. Override job_title/mission/routine_commands/employee_duty.
    job_title = "Worker"
    mission = ""
    routine_commands = []  # list of (task_title, auto_command) self-assigned daily work

    def work(self):
        """Called every tick. Domain background work for this building.
        The autonomous reasoning loop is driven separately on the building's
        own chronoschedule via cognitive_tick()."""
        pass

    def employee_duty(self):
        """Proactive initiative this employee takes each shift (its own
        everyday job), beyond any assigned goals/tasks. Override as needed."""
        return None

    def employee_shift(self):
        """Run this building as an employee for one shift.

        Executes the building's existing background work(), then hands off to
        the employee loop which: ensures a self-directed to-do list, picks up
        any assigned goals/tasks, runs the proactive employee_duty(), escalates
        anything it can't safely decide, and files an end-of-shift report.
        """
        try:
            self.work()
        except Exception as exc:  # noqa: BLE001
            self.trace("observe", "error", "↺", f"work(): {exc}")
        from city.employee import run_employee_shift
        return run_employee_shift(self)

    def cognitive_tick(self):
        """Drive this building's autonomous Cognitive Orchestrator once.

        Disabled by default (COGNITION_ENABLED=1 to turn on) — the symbolic
        thought-tree is diagnostic noise and has been known to crash under
        some native/threaded runtimes."""
        if os.environ.get("COGNITION_ENABLED", "").strip() != "1":
            return
        try:
            self.cognition.step()
        except Exception as exc:
            self.trace("observe", "error", "↺", f"cognition step failed: {exc}")

    def run_due_actions(self):
        """Execute this building's deferred scheduled actions (#3)."""
        if os.environ.get("COGNITION_ENABLED", "").strip() != "1":
            return
        try:
            self.cognition.run_due_actions()
        except Exception as exc:
            self.trace("observe", "error", "↺", f"scheduled actions failed: {exc}")

    def start(self):
        """Lifecycle hook when the building is brought online. Override as needed."""
        self.set_status("idle")
        return {"ok": True, "agent": self.name, "status": "started"}

    def stop(self):
        """Lifecycle hook when the building is taken offline. Override as needed."""
        self.set_status("stopped")
        return {"ok": True, "agent": self.name, "status": "stopped"}

    def handle_event(self, event_type: str, message: str = "", data=None):
        """Receive a city event. Default is no-op (interaction wiring is Phase 2)."""
        return None

    # --- Shared mechanics ---
    def rule(self, pattern):
        """Decorator to register a regex rule -> handler on this agent."""
        compiled = re.compile(pattern, re.IGNORECASE)

        def wrap(fn):
            self._rules.append((compiled, fn))
            return fn

        return wrap

    def process(self, query: str) -> dict:
        """Dispatch a natural-language-ish query to the first matching rule."""
        self.set_status("working")
        query = (query or "").strip()
        # Soft rate-limit: identical process() spam (UI double-clicks / monitor loops)
        try:
            from city.api_budget import budget
            # Free for pure local status/help; gate only if query looks like network work
            qlow = query.lower()
            costly = any(w in qlow for w in (
                "scan", "scrape", "http", "https://", "fetch", "start binance",
                "price ", "check now", "generate", "process queue", "import ",
            ))
            if costly:
                ok, reason = budget.allow(self.name, "agent_query", key=qlow[:120], cost=1)
                if not ok:
                    self.set_status("idle")
                    self.trace("observe", "plan", "↺", f"budget denied: {reason}")
                    return {
                        "ok": False,
                        "agent": self.name,
                        "error": reason,
                        "budget": budget.snapshot(self.name),
                        "denied": True,
                    }
        except Exception:
            pass
        try:
            for pattern, handler in self._rules:
                m = pattern.match(query)
                if m:
                    self.trace("think", "plan", "♢", f"rule {handler.__name__} matched", {"query": query})
                    result = handler(**m.groupdict())
                    try:
                        self.cognition.answer_operator(query, max_depth=2)
                    except Exception:
                        pass
                    self.trace("observe", "result", "⊨", f"{handler.__name__} completed")
                    self.log(
                        "query",
                        f"processed: {query!r}",
                        {"query": query, "result": result},
                    )
                    self.set_status("idle")
                    return {"ok": True, "agent": self.name, "result": result}
            self.trace("observe", "plan", "↺", f"no rule matched: {query}")
            self.log("unhandled", f"no rule matched: {query!r}", {"query": query})
            self.set_status("idle")
            return {
                "ok": False,
                "agent": self.name,
                "error": "no matching rule",
                "hint": self.help_text(),
            }
        except Exception as exc:  # keep the building alive even if a rule blows up
            self.set_status("error")
            self.trace("observe", "error", "↺", f"handler raised: {exc}")
            self.log("error", str(exc), {"query": query})
            return {"ok": False, "agent": self.name, "error": str(exc)}

    def help_text(self):
        return f"{self.name} understands {len(self._rules)} command pattern(s). Try 'status' or 'report'."

    # --- Real Agent Runtime hooks (Brain-aware, LLM-driven, budget-gated) ---
    def add_skill(self, name, description, fn, risk="read", cost_kind="local",
                  event=None, default=False):
        """Register a Skill the runtime may invoke. fn(agent, **kwargs) -> result dict."""
        from city.runtime import Skill
        self.skills.append(Skill(
            name=name, description=description, risk=risk, cost_kind=cost_kind,
            event=event, default=default, fn=fn,
        ))
        return self.skills[-1]

    def autonomy_level(self):
        """human_led | human_assisted | autonomous (from agent_config, else default)."""
        try:
            row = self.conn.execute(
                "SELECT value FROM agent_config WHERE agent_name = ? AND key = 'autonomy'",
                (self.name,),
            ).fetchone()
            if row:
                val = str(row["value"]).strip()
                if val in ("human_led", "human_assisted", "autonomous"):
                    return val
        except Exception:
            pass
        return "human_assisted"

    def set_autonomy(self, level):
        from city.orchestrator import AgentConfig
        if level not in ("human_led", "human_assisted", "autonomous"):
            return False
        AgentConfig(self.name).set("autonomy", level, category="runtime", secret=False)
        return True

    def runtime_run(self, intent=None, persona=None):
        """Execute one Brain-aware runtime cycle for this building."""
        from city.runtime import RUNTIME
        from city.persona import active_persona
        persona = persona or active_persona()
        return RUNTIME.run(self, persona, intent)

    def recent_runs(self, limit=30):
        from city.db import recent_runs
        return recent_runs(self.conn, self.name, limit)

    def log(self, event_type, message, data=None):
        log_event(self.conn, self.name, event_type, message, data)

    def trace(self, tag, ctype, ctmsact, content, data=None):
        """Log a causal reasoning step: thought -> action -> observation.

        Format <tag:type:ctmsact> (see city.db.log_trace). Example:
            self.trace("think", "plan", "♢", "invoking get_orders", {"limit": 10})
        """
        from city.db import log_trace
        log_trace(self.conn, self.name, tag, ctype, ctmsact, content, data)

    @property
    def status(self):
        """Current status from the DB (idle / working / stopped / error)."""
        try:
            row = self.conn.execute(
                "SELECT status FROM agents WHERE name = ?", (self.name,)
            ).fetchone()
            if row:
                return row["status"]
        except Exception:
            pass
        return "idle"

    def set_status(self, status):
        set_status(self.conn, self.name, status)

    def recent_events(self, limit=20):
        rows = self.conn.execute(
            "SELECT * FROM events WHERE agent_name = ? ORDER BY id DESC LIMIT ?",
            (self.name, limit),
        ).fetchall()
        return [dict(r) for r in rows]
