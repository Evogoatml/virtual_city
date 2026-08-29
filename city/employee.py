"""
city/employee.py — run each building as an autonomous employee.

An employee, like a real hire:
  * has a job (job_title + mission) and, like any good staff member, keeps a
    self-directed to-do list when it has no other assignment yet;
  * picks up ASSIGNED work — goals/tasks given by the boss / a plan — and
    executes the next step of that work on its own clock;
  * also works its OWN pipeline on its own initiative (employee_duty()), the
    everyday work of its job, rather than waiting to be told each step;
  * ESCALATES anything it can't safely decide (a money/irreversible action,
    a missing dependency, an error, being over budget) instead of guessing or
    silently going quiet — that is exactly what a good employee does;
  * files an END-OF-SHIFT report so the operator can see what it did.

It runs *fully inside* the autonomy + API-budget guardrails already built:
destructive money skills stay behind the approval queue, and external work is
rate-limited by city.api_budget. It reuses the existing Goal/Task + events
infrastructure (GoalTracker) rather than inventing a parallel system.
"""
from __future__ import annotations

from city.db import get_raw_connection, record_escalation, log_event
from city.orchestrator import GoalTracker

MAX_TASKS_PER_SHIFT = 3


def _try(agent, fn, label, severity="warn"):
    """Run fn safely; escalate + trace on failure. Returns (ok, result)."""
    try:
        return True, fn()
    except Exception as exc:  # noqa: BLE001
        try:
            record_escalation(agent.conn, agent.name, f"{label} failed",
                              f"{label}: {exc}", severity=severity)
        except Exception:
            pass
        try:
            agent.trace("observe", "error", "↺", f"{label}: {exc}")
        except Exception:
            pass
        return False, {"error": str(exc)}


def _next_pending_task(agent_name):
    """Return the first pending task among the agent's active goals, or None."""
    for goal in GoalTracker.get_goals(agent_name):
        if goal.get("status") != "active":
            continue
        for task in goal.get("tasks", []):
            if task.get("status") == "pending":
                return task
    return None


def _ensure_self_goal(agent):
    """Give the employee a self-directed to-do list when it has no active goal.

    A real employee comes in, looks at an empty queue, and starts on their
    defined job responsibilities. We do the same: once, per role, create a
    goal whose tasks are the building's routine_commands (each with an
    auto-command). We skip if the employee already has active goals (don't
    stack duplicate to-do lists) or has none defined.
    """
    routine = getattr(agent, "routine_commands", None) or []
    if not routine:
        return
    goals = GoalTracker.get_goals(agent.name)
    if goals:
        # The employee already has a to-do list (active or finished this shift);
        # don't stack duplicate copies of the same daily routine.
        return
    title = (getattr(agent, "mission", None)
             or f"{getattr(agent, 'job_title', 'Work')} — daily routine")
    goal_id = GoalTracker.create_goal(agent.name, title)
    for ttask, cmd in routine:
        GoalTracker.add_task(goal_id, ttask, auto_command=cmd)
    log_event(agent.conn, agent.name, "employee", f"created self-directed goal: {title}")


def _execute_command(agent, command):
    """Run a command through the agent's rule engine. Returns (ok, result)."""
    res = agent.process(command)
    return bool(res and res.get("ok")), res


def run_employee_shift(agent) -> dict:
    """One employee shift for an agent. Returns a summary of what it did.

    Steps:
      1. ensure a self-directed to-do list exists (if it has none)
      2. pick up & execute up to MAX_TASKS_PER_SHIFT assigned tasks
      3. run the building's proactive employee_duty()
      4. file an end-of-shift report; any disallowed/blocked work is escalated
         rather than executed silently.
    """
    conn = agent.conn or get_raw_connection()
    agent.conn = conn
    done, escalated = [], 0

    _ensure_self_goal(agent)

    # 2) assigned work — the boss's / plan's tasks
    for _ in range(MAX_TASKS_PER_SHIFT):
        task = _next_pending_task(agent.name)
        if not task or not task.get("auto_command"):
            break
        ok, _ = _try(agent,
                     lambda t=task: _execute_command(agent, t["auto_command"])[0],
                     f"task: {task['title']}", severity="warn")
        if ok:
            GoalTracker.complete_task(task["id"])
            log_event(conn, agent.name, "employee",
                      f"completed assigned task: {task['title']}",
                      {"auto_command": task["auto_command"]})
            done.append(task["title"])
        else:
            escalated += 1

    # 3) proactive job duty (the employee's own everyday initiative)
    duty = getattr(agent, "employee_duty", None)
    if callable(duty):
        ok, _ = _try(agent, duty, "duty", severity="warn")
        if ok:
            done.append(f"duty:{getattr(agent, 'job_title', 'work')}")

    # 4) end-of-shift report
    if done or escalated:
        log_event(conn, agent.name, "shift",
                  f"shift: {len(done)} done, {escalated} escalated",
                  {"done": done, "escalated": escalated})
    return {"agent": agent.name, "done": done, "escalated": escalated}
