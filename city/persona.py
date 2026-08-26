"""
city/persona.py — Persona system.

A persona selects which buildings are active and sets the north-star metrics the
Conductor rolls up against. Personas live as markdown in brain/vault/personas/
with front-matter:

    ---
    title: Persona — Ecom Operator
    buildings: [shopify, product_flipping, social_affiliates, ...]
    north_star: Monthly net ecommerce revenue
    metrics: [revenue, conversion_rate, margin]
    ---

The currently-loaded persona is stored in the `config` table (key "active_persona").
"""
from __future__ import annotations

import logging
from typing import Optional

from city.db import get_raw_connection, now_iso

logger = logging.getLogger(__name__)

DEFAULT_PERSONA = "full_multistream"
CONFIG_KEY = "active_persona"


def load_persona(name: str) -> Optional[dict]:
    from city.brain import brain
    note = brain().get_note(f"personas/{name}")
    if note is None:
        return None
    return {
        "name": name,
        "title": note.title,
        "buildings": note.meta.get("buildings", []) or [],
        "north_star": note.meta.get("north_star", ""),
        "metrics": note.meta.get("metrics", []) or [],
        "body": note.body,
    }


def list_personas() -> list[str]:
    from city.brain import brain
    out = []
    for n in brain().list_notes():
        if n.slug.startswith("personas/"):
            out.append(n.slug.split("/", 1)[1])
    return sorted(out)


def active_persona() -> str:
    conn = get_raw_connection()
    try:
        row = conn.execute("SELECT value FROM config WHERE key = ?", (CONFIG_KEY,)).fetchone()
        return row["value"] if row else DEFAULT_PERSONA
    finally:
        pass


def set_active_persona(name: str) -> bool:
    if load_persona(name) is None:
        return False
    conn = get_raw_connection()
    try:
        conn.execute(
            "INSERT INTO config (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (CONFIG_KEY, name),
        )
        conn.commit()
        return True
    finally:
        pass


def active_buildings() -> Optional[list[str]]:
    """Return the active building list, or None meaning 'all buildings'."""
    p = load_persona(active_persona())
    if p is None:
        return None
    b = p["buildings"]
    if not b or b == ["*"] or "*" in b:
        return None
    return b


def north_star() -> str:
    p = load_persona(active_persona())
    return (p or {}).get("north_star") or "Optimize the whole city portfolio."
