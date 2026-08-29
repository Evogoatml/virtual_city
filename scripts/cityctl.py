#!/usr/bin/env python3
"""
Virtual City — CLI entry point.

Usage:
  city status                      List all buildings + status
  city query <agent> <command>     Send a command to an agent
  city run <agent>                 Trigger one Brain-aware runtime cycle
  city meeting                     Hold City Hall's daily meeting
  city agenda                      List assigned goals/tasks for all agents
  city assign <agent> <title> [cmd]  Give a building an assigned task
  city shift <agent>               Run one employee shift
  city report <agent>              Show an agent's report
  city brain                       List brain notes
  city persona [name]              Show/set active persona
  city events [agent] [n]          Show recent events
  city ledger                      Show treasury ledger
  city budget                      Show API budget snapshot
  city start                       Start the Flask server
  city repl                        Interactive REPL (type commands)

Examples:
  city status
  city query crypto_trading "buy 0.5 BTC @ 68000"
  city query social_affiliates "campaign instagram FanvueLink"
  city query social_affiliates "convert FanvueLink revenue 42.50"
  city run social_affiliates
  city meeting
  city persona ecom_operator
"""
import sys
import os
import json
import shlex

# Ensure project root is importable
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Bootstrap the city (init DB, discover agents, wire events) before any command
os.environ.setdefault("LLM_MOCK", "0")  # set to 1 to simulate LLM without keys
from app import app, bootstrap  # noqa: E402
from city.registry import get_registry, get_agent  # noqa: E402
from city.db import get_raw_connection, list_escalations, count_open_escalations  # noqa: E402
from city.brain import brain as brain_factory  # noqa: E402
from city.persona import list_personas, active_persona, load_persona, north_star, set_active_persona  # noqa: E402
from city.api_budget import budget  # noqa: E402
from city.orchestrator import GoalTracker  # noqa: E402


def _conn():
    return get_raw_connection()


def _reg():
    conn = _conn()
    get_registry(conn)
    return conn


def _agent(reg, name):
    a = reg.get(name)
    if not a:
        print(f"Unknown agent '{name}'. Available: {', '.join(sorted(reg.keys()))}")
        sys.exit(1)
    a.conn = _conn()
    return a


def cmd_status():
    conn = _reg()
    reg = get_registry(conn)
    print("=" * 70)
    print(f"  VIRTUAL CITY — {len(reg)} buildings")
    print(f"  North star: {north_star() or '—'}")
    print(f"  Persona: {active_persona() or 'none'}")
    print("=" * 70)
    for name in sorted(reg.keys()):
        agent = reg[name]
        agent.conn = conn
        aut = agent.autonomy_level()
        n_skills = len(getattr(agent, "skills", []) or [])
        report = {}
        try:
            report = agent.report() or {}
        except Exception as e:
            report = {"_error": str(e)}
        # Format status dot
        st = agent.status
        dot = {"idle": "●", "working": "◐", "stopped": "✕", "error": "✗"}.get(st, "?")
        print(f"  {dot} {name:25s} {aut:16s} {n_skills:4d} skills")
    print("=" * 70)
    conn.close()


def cmd_query(agent_name, query):
    conn = _reg()
    reg = get_registry(conn)
    agent = _agent(reg, agent_name)
    result = agent.process(query)
    agent.conn = conn
    # Pretty-print
    if isinstance(result, dict):
        if result.get("ok") and "result" in result:
            inner = result["result"]
            if isinstance(inner, (dict, list)):
                print(json.dumps(inner, indent=2, default=str))
            else:
                print(inner)
        elif result.get("error"):
            print(f"Error: {result['error']}")
            if result.get("hint"):
                print(f"Hint: {result['hint']}")
        else:
            print(json.dumps(result, indent=2, default=str))
    else:
        print(result)
    conn.close()


def cmd_run(agent_name, intent=None):
    """Trigger one Brain-aware runtime cycle for a building."""
    conn = _reg()
    reg = get_registry(conn)
    agent = _agent(reg, agent_name)
    result = agent.runtime_run(intent=intent)
    print(json.dumps(result, indent=2, default=str))
    conn.close()


def cmd_meeting():
    conn = _conn()
    get_registry(conn)
    from city.agent import Agent  # just to ensure
    reg = get_registry(conn)
    city_hall = reg.get("city_hall")
    if not city_hall:
        print("city_hall not found")
        sys.exit(1)
    city_hall.conn = conn
    result = city_hall.hold_meeting()
    print(json.dumps(result.get("summary", result), indent=2, default=str))
    conn.close()


def cmd_report(agent_name):
    conn = _reg()
    reg = get_registry(conn)
    agent = _agent(reg, agent_name)
    report = agent.report()
    print(json.dumps(report, indent=2, default=str))
    conn.close()


def cmd_events(agent_name=None, limit=20):
    conn = _reg()
    if agent_name:
        rows = conn.execute(
            "SELECT type, message, timestamp FROM events WHERE agent_name = ? ORDER BY id DESC LIMIT ?",
            (agent_name, limit),
        ).fetchall()
        print(f"Events for {agent_name}:")
    else:
        rows = conn.execute(
            "SELECT agent_name, type, message, timestamp FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        print("Recent events:")
    for r in rows:
        if agent_name:
            print(f"  {r['timestamp'][:19]}  {r['type']}  {r['message']}")
        else:
            print(f"  {r['timestamp'][:19]}  {r['agent_name']:25s} {r['type']:20s} {r['message']}")
    conn.close()


def cmd_ledger(limit=30):
    conn = _reg()
    rows = conn.execute(
        "SELECT source, amount, note, created_at FROM ledger ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    total = sum(float(r["amount"]) for r in rows if r["amount"] >= 0) - sum(
        float(r["amount"]) for r in rows if r["amount"] < 0
    )
    print(f"Treasury ledger (last {len(rows)} entries, net: ${total:.2f}):")
    for r in rows:
        sign = "+" if r["amount"] >= 0 else ""
        print(f"  {r['created_at'][:19]}  {r['source']:15s} {sign}${r['amount']:.2f}  {r['note']}")
    conn.close()


def cmd_agenda():
    conn = _reg()
    reg = get_registry(conn)
    print("Assigned goals/tasks:")
    for name in sorted(reg.keys()):
        goals = GoalTracker.get_goals(name)
        if goals:
            for g in goals:
                pending = [t for t in g.get("tasks", []) if t.get("status") == "pending"]
                if pending:
                    print(f"  {name}: {len(pending)} pending task(s) in goal '{g.get('title', '?')}'")
                    for t in pending:
                        print(f"    - {t.get('title', '?')}")
    conn.close()


def cmd_assign(agent_name, title, command=None):
    conn = _reg()
    reg = get_registry(conn)
    if not reg.get(agent_name):
        print(f"Unknown agent '{agent_name}'")
        sys.exit(1)
    goal_id = GoalTracker.create_goal(agent_name, title)
    GoalTracker.add_task(goal_id, title, auto_command=command)
    print(f"Assigned to {agent_name}: goal #{goal_id} — '{title}'")
    if command:
        print(f"  auto-command: {command}")
    print("  (will execute on next employee shift)")
    conn.close()


def cmd_shift(agent_name):
    conn = _reg()
    reg = get_registry(conn)
    agent = _agent(reg, agent_name)
    result = agent.employee_shift()
    print(json.dumps(result, indent=2, default=str))
    conn.close()


def cmd_brain():
    notes = brain_factory().list_notes()
    print(f"Brain vault: {len(notes)} notes")
    for n in notes:
        tags = ", ".join(n.tags) if n.tags else "—"
        bldgs = ", ".join(n.buildings) if n.buildings else "all"
        print(f"  {n.slug:30s} [{tags:30s}] ({bldgs})")


def cmd_persona(name=None):
    if not name:
        active = active_persona()
        print(f"Active persona: {active or 'none'}")
        print(f"North star: {north_star() or '—'}")
        print(f"Available personas: {', '.join(list_personas())}")
    else:
        if name in list_personas():
            if set_active_persona(name):
                print(f"Persona set to: {name}")
                p = load_persona(name)
                if p:
                    print(f"  title: {p.get('title', name)}")
                    print(f"  buildings: {p.get('buildings', [])}")
                    print(f"  north_star: {p.get('north_star', '')}")
            else:
                print(f"Failed to set persona to '{name}'")
                sys.exit(1)
        else:
            print(f"Unknown persona '{name}'. Available: {', '.join(list_personas())}")
            sys.exit(1)


def cmd_budget(agent_name=None):
    if agent_name:
        snap = budget.snapshot(agent_name)
        print(json.dumps(snap, indent=2, default=str))
    else:
        # Show all agents
        conn = _reg()
        reg = get_registry(conn)
        for name in sorted(reg.keys()):
            snap = budget.snapshot(name)
            print(f"  {name:25s} calls={snap.get('calls_last_min', 0)}/{snap.get('max_per_min', '?')}")
        conn.close()


def cmd_start(host="127.0.0.1", port=5000, debug=False):
    """Start the Flask dev server."""
    print(f"Starting Virtual City on {host}:{port} ...")
    app.run(host=host, port=port, debug=debug)


def cmd_runs(agent_name, limit=40):
    conn = _reg()
    reg = get_registry(conn)
    agent = _agent(reg, agent_name)
    runs = agent.recent_runs(limit)
    print(f"Run history for {agent_name} ({len(runs)} entries):")
    for r in runs:
        status_icon = {"ok": "✓", "blocked": "↡", "error": "✗"}.get(r.get("status", ""), "?")
        print(f"  {status_icon} {r.get('created_at','')[:19]}  {r.get('skill','—'):15s}  {status_icon}")
    conn.close()


def cmd_help():
    print(__doc__)
    print("\nCommands:")
    print("  status                      List all buildings + status")
    print("  query <agent> <command>     Send a command to an agent")
    print("  run <agent> [intent]        Trigger one Brain-aware runtime cycle")
    print("  meeting                     Hold City Hall's daily meeting")
    print("  report <agent>              Show an agent's report")
    print("  events [agent] [n]          Show recent events")
    print("  ledger [n]                  Show treasury ledger")
    print("  agenda                      List assigned goals/tasks")
    print("  assign <agent> <title> [cmd]  Give a building an assigned task")
    print("  shift <agent>               Run one employee shift")
    print("  runs <agent> [n]            Show run history")
    print("  brain                       List brain notes")
    print("  persona [name]              Show/set active persona")
    print("  budget [agent]              Show API budget snapshot")
    print("  start                       Start the Flask server")
    print("  repl                        Interactive REPL")


def cmd_repl():
    """Interactive REPL — type commands like 'query social_affiliates status'."""
    print("Virtual City REPL — type 'help' for commands, 'quit' to exit.")
    conn = _reg()
    reg = get_registry(conn)

    while True:
        try:
            line = input("city> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue
        if line in ("quit", "exit", "q"):
            break
        if line == "help":
            cmd_help()
            continue
        if line == "status":
            conn2 = _reg()
            reg2 = get_registry(conn2)
            for name in sorted(reg2.keys()):
                agent = reg2[name]
                agent.conn = conn2
                print(f"  {agent.status:10s}  {name:25s}  {agent.autonomy_level()}")
            conn2.close()
            continue

        parts = shlex.split(line)
        cmd = parts[0] if parts else ""
        args = parts[1:]

        if cmd == "query" and len(args) >= 2:
            agent_name = args[0]
            query = " ".join(args[1:])
            agent = _agent(reg, agent_name)
            result = agent.process(query)
            print(json.dumps(result, indent=2, default=str) if isinstance(result, dict) else result)
        elif cmd == "report" and len(args) >= 1:
            agent = _agent(reg, args[0])
            print(json.dumps(agent.report(), indent=2, default=str))
        elif cmd == "run" and len(args) >= 1:
            agent = _agent(reg, args[0])
            intent = " ".join(args[1:]) if len(args) > 1 else None
            result = agent.runtime_run(intent=intent)
            print(json.dumps(result, indent=2, default=str))
        elif cmd == "meeting":
            city_hall = reg.get("city_hall")
            if city_hall:
                city_hall.conn = conn
                print(json.dumps(city_hall.hold_meeting().get("summary", {}), indent=2, default=str))
        elif cmd == "events":
            agent_name = args[0] if args else None
            n = int(args[1]) if len(args) > 1 else 20
            cmd_events(agent_name, n)
        elif cmd == "ledger":
            n = int(args[0]) if args else 30
            cmd_ledger(n)
        elif cmd == "brain":
            notes = brain_factory().list_notes()
            for n in notes:
                print(f"  {n.slug:30s} tags={n.tags}")
        elif cmd == "persona":
            if args:
                if set_active_persona(args[0]):
                    print(f"Persona: {args[0]}")
                else:
                    print(f"Unknown persona: {args[0]}")
            else:
                print(f"Active: {active_persona()}")
        elif cmd == "budget":
            agent_name = args[0] if args else None
            if agent_name:
                print(json.dumps(budget.snapshot(agent_name), indent=2))
            else:
                for name in sorted(reg.keys()):
                    snap = budget.snapshot(name)
                    print(f"  {name:25s} {snap.get('calls_last_min',0)}/{snap.get('max_per_min','?')}")
        else:
            print(f"Unknown command '{cmd}'. Type 'help' for available commands.")

    conn.close()


def main():
    if len(sys.argv) < 2:
        cmd_help()
        sys.exit(0)

    cmd = sys.argv[1].lower()
    args = sys.argv[2:]

    if cmd == "status":
        cmd_status()
    elif cmd == "query":
        if len(args) < 2:
            print("Usage: city query <agent> <command...>")
            sys.exit(1)
        cmd_query(args[0], " ".join(args[1:]))
    elif cmd == "run":
        if len(args) < 1:
            print("Usage: city run <agent> [intent]")
            sys.exit(1)
        intent = " ".join(args[1:]) if len(args) > 1 else None
        cmd_run(args[0], intent)
    elif cmd == "meeting":
        cmd_meeting()
    elif cmd == "report":
        if len(args) < 1:
            print("Usage: city report <agent>")
            sys.exit(1)
        cmd_report(args[0])
    elif cmd == "events":
        agent_name = args[0] if args else None
        limit = int(args[1]) if len(args) > 1 else 20
        cmd_events(agent_name, limit)
    elif cmd == "ledger":
        limit = int(args[0]) if args else 30
        cmd_ledger(limit)
    elif cmd == "agenda":
        cmd_agenda()
    elif cmd == "assign":
        if len(args) < 2:
            print("Usage: city assign <agent> <title> [auto-command]")
            sys.exit(1)
        title = args[1]
        command = args[2] if len(args) > 2 else None
        cmd_assign(args[0], title, command)
    elif cmd == "shift":
        if len(args) < 1:
            print("Usage: city shift <agent>")
            sys.exit(1)
        cmd_shift(args[0])
    elif cmd == "runs":
        if len(args) < 1:
            print("Usage: city runs <agent> [n]")
            sys.exit(1)
        limit = int(args[1]) if len(args) > 1 else 40
        cmd_runs(args[0], limit)
    elif cmd == "brain":
        cmd_brain()
    elif cmd == "persona":
        cmd_persona(args[0] if args else None)
    elif cmd == "budget":
        cmd_budget(args[0] if args else None)
    elif cmd == "start":
        host = os.environ.get("CITY_HOST", "127.0.0.1")
        port = int(os.environ.get("PORT", "5000"))
        cmd_start(host=host, port=port, debug="--debug" in sys.argv)
    elif cmd == "repl":
        cmd_repl()
    elif cmd in ("help", "-h", "--help"):
        cmd_help()
    else:
        print(f"Unknown command '{cmd}'. Type 'city help' for available commands.")
        sys.exit(1)


if __name__ == "__main__":
    main()
