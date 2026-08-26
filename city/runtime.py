"""
city/runtime.py — The real Agent Runtime (replaces symbolic cognition).

A building's runtime loop:
    ctx   = Brain.context_for(agent, persona)     # read before acting
    plan  = LLM decides among the building's skills
    for skill in plan:
        if autonomy_blocks(agent, skill): request_human(); continue
        result = skill.run(budget_aware=True)
        if skill.event: EventBus.publish(agent, skill.event, result)
        log_run(agent, skill, result)             # run history

Autonomy levels (stored in agent_config "autonomy"):
    human_led      -> read skills only (never executes writes/destructive)
    human_assisted -> read + write; destructive still needs approval
    autonomous      -> read + write + destructive (within budget, fully logged)

All external calls inside skills must go through city.api_budget.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)

AUTONOMY_LEVELS = ("human_led", "human_assisted", "autonomous")
DEFAULT_AUTONOMY = "human_assisted"


@dataclass
class Skill:
    name: str
    description: str
    risk: str = "read"          # read | write | destructive
    cost_kind: str = "local"     # local | http | llm | exchange | scrape
    event: Optional[str] = None  # event type published on success
    default: bool = False        # included in the offline fallback plan
    fn: Optional[Callable] = None

    def run(self, agent, **kwargs):
        if self.fn is None:
            return {"error": f"skill {self.name} has no implementation"}
        return self.fn(agent, **kwargs)


def can_execute(agent, skill: Skill) -> bool:
    level = getattr(agent, "autonomy_level", lambda: DEFAULT_AUTONOMY)()
    if skill.risk == "read":
        return True
    if skill.risk == "write":
        return level in ("human_assisted", "autonomous")
    if skill.risk == "destructive":
        return level == "autonomous"
    return False


class AgentRuntime:
    def __init__(self):
        self._last_summary: dict = {}

    # ------------------------------------------------------------------ prompt
    def _build_system(self, agent, persona, ctx, skills) -> str:
        from city.api_budget import budget

        skill_lines = "\n".join(
            f"- {s.name} (risk={s.risk}, cost={s.cost_kind}): {s.description}" for s in skills
        )
        budget_snap = budget.snapshot(agent.name)
        return (
            "You are the autonomous orchestrator for ONE building in Virtual City, a multi-agent "
            "business OS. You own your domain; you do NOT control other buildings. You read the "
            "Shared Knowledge Core before acting, then pick the skills that advance the north-star.\n\n"
            f"BUILDING: {agent.name} ({getattr(agent, 'subject', '')})\n"
            f"PERSONA: {persona or 'full_multistream'}\n"
            f"AUTONOMY: {agent.autonomy_level()}\n"
            f"API BUDGET: {json.dumps(budget_snap)}\n\n"
            "SHARED KNOWLEDGE CORE (read this first):\n"
            f"{ctx}\n\n"
            "AVAILABLE SKILLS (call by exact name):\n"
            f"{skill_lines}\n\n"
            "Respond ONLY with JSON: {\"think\": str, \"skills\": [{\"name\": str, \"args\": {}}]}. "
            "Prefer read/low-risk skills when budget is tight. Do not invent skill names."
        )

    # -------------------------------------------------------------- planning
    def _plan(self, agent, persona, intent, skills) -> list[dict]:
        from city import llm
        from city.brain import brain

        ctx = brain().context_for(agent.name, persona, query=intent)
        system = self._build_system(agent, persona, ctx, skills)
        user = intent or (
            f"Autonomous tick for {getattr(agent, 'subject', agent.name)}. "
            "Choose skills that advance the north-star and respect budget + autonomy."
        )
        decision = llm.json_chat(system, user, agent=agent.name, max_tokens=700)
        if not decision.get("ok") or not decision.get("parsed"):
            logger.info("[runtime] %s LLM unavailable -> fallback plan", agent.name)
            return self._fallback_plan(skills)
        plan = decision["parsed"].get("skills") or []
        if not isinstance(plan, list):
            return self._fallback_plan(skills)
        # keep only known skills
        known = {s.name: s for s in skills}
        out = []
        for step in plan:
            name = (step or {}).get("name")
            if name in known:
                out.append({"name": name, "args": (step or {}).get("args") or {}})
        return out[:6]

    def _fallback_plan(self, skills) -> list[dict]:
        """Used when the LLM is unconfigured/offline: run default + read skills."""
        return [{"name": s.name, "args": {}} for s in skills if s.default or s.risk == "read"]

    # ------------------------------------------------------------------- run
    def run(self, agent, persona: Optional[str] = None, intent: Optional[str] = None,
            max_skills: int = 6) -> dict:
        from city.orchestrator import EventBus
        from city.db import log_run

        skills = list(getattr(agent, "skills", []) or [])
        if not skills:
            return {"ok": True, "agent": agent.name, "summary": "no skills registered", "results": []}

        plan = self._plan(agent, persona, intent, skills)
        known = {s.name: s for s in skills}
        results = []
        executed, blocked = 0, 0
        for step in plan[:max_skills]:
            skill = known.get(step["name"])
            if skill is None:
                continue
            if not can_execute(agent, skill):
                blocked += 1
                results.append({"skill": skill.name, "status": "blocked",
                                 "reason": f"autonomy {agent.autonomy_level()} < risk {skill.risk}"})
                agent.trace("act", "plan", "↺",
                            f"blocked {skill.name}: autonomy {agent.autonomy_level()} < {skill.risk}")
                continue
            try:
                agent.set_status("working")
                res = skill.run(agent, **(step.get("args") or {}))
            except Exception as exc:
                res = {"error": str(exc)}
                agent.trace("observe", "error", "↺", f"{skill.name} raised: {exc}")
            status = "ok" if not (isinstance(res, dict) and res.get("error")) else "error"
            if skill.event and status == "ok":
                EventBus.publish(agent.name, skill.event, f"{skill.name} -> {skill.event}", res)
            results.append({"skill": skill.name, "status": status, "result": res})
            executed += 1
            log_run(agent.conn, agent.name, persona, intent, skill.name, status, res)

        summary = self._summarize(agent, plan, results, executed, blocked)
        agent.trace("act", "result", "⊤", summary)
        agent.set_status("idle")
        payload = {
            "ok": True, "agent": agent.name, "persona": persona,
            "planned": [p["name"] for p in plan], "executed": executed,
            "blocked": blocked, "results": results, "summary": summary,
        }
        self._last_summary[agent.name] = payload
        return payload

    def _summarize(self, agent, plan, results, executed, blocked) -> str:
        names = ", ".join(p["name"] for p in plan) or "none"
        return (f"ran {executed} skill(s) ({blocked} blocked) for {agent.name}; "
                f"plan: {names}")


RUNTIME = AgentRuntime()
