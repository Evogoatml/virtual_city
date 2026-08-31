"""
SQLite persistence layer for the Virtual City.

Provides a per-request connection (via Flask's `g`) plus schema init
for the shared tables. Each agent additionally owns its own domain
table(s), created lazily by the agent itself on first use.
"""
import sqlite3
import json
import os
import threading
from datetime import datetime, timezone
from flask import g

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "city_state.db")

# One SQLite connection per thread. Connections are reused for the thread's
# lifetime and never explicitly closed — this avoids the "operate on a closed
# database" native crash that happened when scheduler/request threads closed
# each other's shared connections. Recreated automatically if somehow closed.
_local = threading.local()


def _new_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    """Per-thread SQLite connection (row factory = dict-like)."""
    return get_raw_connection()


def close_db(e=None):
    # Connections are thread-local and intentionally never closed; no-op.
    return


def get_raw_connection():
    """Thread-local SQLite connection for scheduler jobs / background threads."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _new_conn()
        _local.conn = conn
    else:
        try:
            conn.execute("SELECT 1")
        except Exception:
            conn = _new_conn()
            _local.conn = conn
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_raw_connection()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS agents (
            name TEXT PRIMARY KEY,
            subject TEXT NOT NULL,
            district TEXT NOT NULL,
            color TEXT NOT NULL,
            x INTEGER NOT NULL,
            y INTEGER NOT NULL,
            w INTEGER NOT NULL DEFAULT 90,
            h INTEGER NOT NULL DEFAULT 90,
            status TEXT NOT NULL DEFAULT 'idle',
            last_updated TEXT NOT NULL,
            activity_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            type TEXT NOT NULL,
            message TEXT NOT NULL,
            data_json TEXT
        );

        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            summary_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS plans (
            agent_name TEXT PRIMARY KEY,
            plan_text TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            progress REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            auto_command TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY (goal_id) REFERENCES goals(id)
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscriber_name TEXT NOT NULL,
            publisher_name TEXT NOT NULL,
            event_type TEXT NOT NULL DEFAULT '*',
            created_at TEXT NOT NULL,
            UNIQUE(subscriber_name, publisher_name, event_type)
        );

        CREATE TABLE IF NOT EXISTS agent_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT 'general',
            secret INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(agent_name, key)
        );

        CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent_name);
        CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp);

        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            tag TEXT NOT NULL,
            type TEXT NOT NULL,
            ctmsact TEXT NOT NULL,
            content TEXT NOT NULL,
            data_json TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chronolog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            depth INTEGER NOT NULL DEFAULT 0,
            nodes INTEGER NOT NULL DEFAULT 0,
            step_index INTEGER NOT NULL DEFAULT 0,
            focus TEXT,
            summary TEXT
        );

        CREATE TABLE IF NOT EXISTS cog_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            due_at TEXT NOT NULL,
            action_type TEXT NOT NULL,
            payload TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            done_at TEXT
        );

        CREATE TABLE IF NOT EXISTS agent_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            persona TEXT,
            intent TEXT,
            skill TEXT NOT NULL,
            status TEXT NOT NULL,
            result_json TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS escalations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'info',
            subject TEXT NOT NULL,
            detail TEXT,
            resolved INTEGER NOT NULL DEFAULT 0,
            resolution TEXT,
            resolved_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_esc_open ON escalations(agent_name, resolved);

        CREATE INDEX IF NOT EXISTS idx_runs_agent ON agent_runs(agent_name);
        """
    )
    conn.commit()
    # Do NOT close the thread-local connection — init_db may run on the main
    # thread while scheduler threads share the same connection. Closing it
    # here would cause "Cannot operate on a closed database" in background
    # ticks. The connection is thread-local and intentionally never closed
    # (see get_raw_connection).
    return conn


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def log_event(conn, agent_name, event_type, message, data=None):
    conn.execute(
        "INSERT INTO events (agent_name, timestamp, type, message, data_json) VALUES (?, ?, ?, ?, ?)",
        (agent_name, now_iso(), event_type, message, json.dumps(data or {})),
    )
    conn.execute(
        "UPDATE agents SET activity_count = activity_count + 1, last_updated = ? WHERE name = ?",
        (now_iso(), agent_name),
    )
    conn.commit()


def set_status(conn, agent_name, status):
    conn.execute(
        "UPDATE agents SET status = ?, last_updated = ? WHERE name = ?",
        (status, now_iso(), agent_name),
    )
    conn.commit()


def log_trace(conn, agent_name, tag, ctype, ctmsact, content, data=None):
    """Append a causal reasoning step in <tag:type:ctmsact> form.

    tag      – phase: think | act | observe | branch | error
    type     – category: plan | result | error | split
    ctmsact  – operator glyph: ♢ next · ⊨ truth · ↺ abandon · ⋔ split · ↑ transcend
    """
    conn.execute(
        "INSERT INTO traces (agent_name, tag, type, ctmsact, content, data_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (agent_name, tag, ctype, ctmsact, content, json.dumps(data or {}), now_iso()),
    )
    conn.commit()


def log_chronolog(conn, agent_name, depth, nodes, step_index, focus, summary):
    """Append a chronological snapshot of a building's reasoning state."""
    try:
        conn.execute(
            "INSERT INTO chronolog (agent_name, created_at, depth, nodes, step_index, focus, summary) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (agent_name, now_iso(), depth, nodes, step_index, focus, summary),
        )
        conn.commit()
    except Exception:
        pass


def recent_chronolog(conn, agent_name, limit=50):
    rows = conn.execute(
        "SELECT created_at, depth, nodes, step_index, focus, summary "
        "FROM chronolog WHERE agent_name = ? ORDER BY id DESC LIMIT ?",
        (agent_name, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def schedule_action(conn, agent_name, due_at, action_type, payload):
    """Queue a deferred autonomous action for this building."""
    conn.execute(
        "INSERT INTO cog_schedule (agent_name, due_at, action_type, payload, status, created_at) "
        "VALUES (?, ?, ?, ?, 'pending', ?)",
        (agent_name, due_at, action_type, payload, now_iso()),
    )
    conn.commit()


def due_actions(conn, agent_name):
    """Return pending actions whose due_at has passed."""
    now = now_iso()
    rows = conn.execute(
        "SELECT * FROM cog_schedule WHERE agent_name = ? AND status = 'pending' AND due_at <= ? "
        "ORDER BY due_at ASC",
        (agent_name, now),
    ).fetchall()
    return [dict(r) for r in rows]


def complete_action(conn, action_id):
    conn.execute(
        "UPDATE cog_schedule SET status = 'done', done_at = ? WHERE id = ?",
        (now_iso(), action_id),
    )
    conn.commit()


def log_run(conn, agent_name, persona, intent, skill, status, result, created_at=None):
    """Append one executed skill step to the agent run history."""
    try:
        conn.execute(
            "INSERT INTO agent_runs (agent_name, persona, intent, skill, status, result_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (agent_name, persona, intent, skill, status,
             json.dumps(result if isinstance(result, (dict, list)) else {"value": str(result)}),
             created_at or now_iso()),
        )
        conn.commit()
    except Exception:
        pass


def recent_runs(conn, agent_name=None, limit=30):
    if agent_name:
        rows = conn.execute(
            "SELECT * FROM agent_runs WHERE agent_name = ? ORDER BY id DESC LIMIT ?",
            (agent_name, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM agent_runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def render_trace(row) -> str:
    """Render a trace row as '<tag:type:ctmsact> content'."""
    return f"<{row['tag']}:{row['type']}:{row['ctmsact']}> {row['content']}"


# ---------------------------------------------------------------------------
# Escalations — an employee raises these when it can't safely decide
# ---------------------------------------------------------------------------

def record_escalation(conn, agent_name, subject, detail="", severity="info", data=None):
    """Log an escalation (an employee flagging something for a human/boss)."""
    conn.execute(
        "INSERT INTO escalations (agent_name, created_at, severity, subject, detail) "
        "VALUES (?, ?, ?, ?, ?)",
        (agent_name, now_iso(), severity, subject, detail),
    )
    conn.commit()
    try:
        log_event(conn, agent_name, "escalation", f"{severity}: {subject}",
                  {"detail": detail, **(data or {})})
    except Exception:
        pass


def list_escalations(conn, agent_name=None, open_only=False, limit=100):
    q = "SELECT * FROM escalations"
    where, args = [], []
    if agent_name:
        where.append("agent_name = ?")
        args.append(agent_name)
    if open_only:
        where.append("resolved = 0")
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    return [dict(r) for r in conn.execute(q, args).fetchall()]


def count_open_escalations(conn):
    return conn.execute(
        "SELECT COUNT(*) AS c FROM escalations WHERE resolved = 0"
    ).fetchone()["c"]


def resolve_escalation(conn, esc_id, resolution=""):
    conn.execute(
        "UPDATE escalations SET resolved = 1, resolution = ?, resolved_at = ? WHERE id = ?",
        (resolution, now_iso(), esc_id),
    )
    conn.commit()
    return conn.total_changes > 0


def upsert_building(conn, name, subject, district, color, x, y, w=90, h=90):
    conn.execute(
        """
        INSERT INTO agents (name, subject, district, color, x, y, w, h, status, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'idle', ?)
        ON CONFLICT(name) DO UPDATE SET
            subject=excluded.subject, district=excluded.district, color=excluded.color,
            x=excluded.x, y=excluded.y, w=excluded.w, h=excluded.h
        """,
        (name, subject, district, color, x, y, w, h, now_iso()),
    )
    conn.commit()
