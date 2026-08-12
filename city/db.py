"""
SQLite persistence layer for the Virtual City.

Provides a per-request connection (via Flask's `g`) plus schema init
for the shared tables. Each agent additionally owns its own domain
table(s), created lazily by the agent itself on first use.
"""
import sqlite3
import json
import os
from datetime import datetime, timezone
from flask import g

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "city_state.db")


def get_db():
    """Return a request-scoped SQLite connection (row factory = dict-like)."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def get_raw_connection():
    """Standalone connection for use outside a Flask request context (e.g. scheduler jobs)."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
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
            data_json TEXT,
            FOREIGN KEY (agent_name) REFERENCES agents(name)
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
            updated_at TEXT NOT NULL,
            FOREIGN KEY (agent_name) REFERENCES agents(name)
        );

        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            progress REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (agent_name) REFERENCES agents(name)
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
            FOREIGN KEY (subscriber_name) REFERENCES agents(name),
            FOREIGN KEY (publisher_name) REFERENCES agents(name)
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
            FOREIGN KEY (agent_name) REFERENCES agents(name),
            UNIQUE(agent_name, key)
        );

        CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent_name);
        CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp);

        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );
        """
    )
    conn.commit()
    conn.close()


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
