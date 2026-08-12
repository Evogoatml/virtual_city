"""
Base Agent class. Each building in the city is backed by one Agent
subclass. Processing is rule-based (keyword/regex dispatch) — no LLM
calls, per spec.
"""
import re
from city.db import log_event, set_status, now_iso


class Agent:
    # --- Override in subclasses ---
    name = "base_agent"          # unique key, also the building id
    subject = "general"          # short label shown on the building
    district = "Downtown"        # grouping label (unused for layout, useful for UI)
    color = "#607d8b"            # building fill color

    def __init__(self, conn):
        self.conn = conn
        self._rules = []  # list of (compiled_regex, handler_name)
        self.setup_schema()
        self.register_rules()
        self._register_orchestrator()

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

    def report(self) -> dict:
        """Summary used by City Hall's daily meeting. Override."""
        return {"agent": self.name, "subject": self.subject, "summary": "no report configured"}

    def work(self):
        """Called every tick — override to do autonomous background work."""
        pass

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
                    result = handler(**m.groupdict())
                    self.log(
                        "query",
                        f"processed: {query!r}",
                        {"query": query, "result": result},
                    )
                    self.set_status("idle")
                    return {"ok": True, "agent": self.name, "result": result}
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
            self.log("error", str(exc), {"query": query})
            return {"ok": False, "agent": self.name, "error": str(exc)}

    def help_text(self):
        return f"{self.name} understands {len(self._rules)} command pattern(s). Try 'status' or 'report'."

    def log(self, event_type, message, data=None):
        log_event(self.conn, self.name, event_type, message, data)

    def set_status(self, status):
        set_status(self.conn, self.name, status)

    def recent_events(self, limit=20):
        rows = self.conn.execute(
            "SELECT * FROM events WHERE agent_name = ? ORDER BY id DESC LIMIT ?",
            (self.name, limit),
        ).fetchall()
        return [dict(r) for r in rows]
