"""
Lays out buildings on the city grid and syncs positions into the
`agents` table. CEO (City Hall) sits centered; buildings ring it.
"""
from city.db import upsert_building

CELL_W = 160
CELL_H = 160
MARGIN_X = 80
MARGIN_Y = 80
BUILDING_W = 120
BUILDING_H = 120

# (col, row) grid positions. CEO gets double width.
BUILDINGS = {
    "city_hall": (2, 1),           # Center - CEO
    "finance_building": (0, 0),    # NW corner — owns market_data, finance_treasury
    "crypto_trading": (1, 0),       # standalone trading building
    "btc_recovery": (2, 0),         # BTC Recovery above CEO
    "media_building": (4, 0),      # NE corner
    "content_creation": (3, 0),
    "content_automation": (3, 1),
    "content_analytics": (4, 1),
    "research_building": (0, 2),   # SW corner
    "sourcing_research": (1, 2),
    "shopify": (4, 2),             # SE corner
    "product_flipping": (2, 2),
    "social_affiliates": (3, 2),
    "signal": (4, 3),
    "web_check": (1, 3),
    "scraper": (0, 3),
}

# For display: which departments belong to which district
DEPARTMENTS = {
    "finance_building": ["market_data", "finance_treasury"],
    "media_building": ["content_creation", "content_automation", "content_analytics"],
    "research_building": ["sourcing_research", "web_check", "scraper"],
}


def layout_city(conn, agents: dict):
    """agents: {name: Agent instance}. Persists building positions."""
    building_names = set(BUILDINGS.keys())

    for name, agent in agents.items():
        if name not in building_names:
            continue

        col, row = BUILDINGS[name]
        x = MARGIN_X + col * CELL_W
        y = MARGIN_Y + row * CELL_H
        w = BUILDING_W * (2 if name == "city_hall" else 1)
        h = BUILDING_H

        upsert_building(conn, name, agent.subject, agent.district, agent.color, x, y, w, h)


def get_city_state(conn):
    rows = conn.execute("SELECT * FROM agents ORDER BY y, x").fetchall()
    # Only actual buildings (in BUILDINGS) are shown as standalone buildings.
    # Departments (e.g. finance_treasury, market_data) live under their parent.
    buildings = [dict(r) for r in rows if r["name"] in BUILDINGS]

    for building in buildings:
        bname = building["name"]
        if bname in DEPARTMENTS:
            building["departments"] = DEPARTMENTS[bname]

    # Operator context: active persona + north-star + brain size
    try:
        from city.persona import active_persona, north_star, active_buildings
        from city.brain import brain
        state = {
            "buildings": buildings,
            "persona": active_persona(),
            "north_star": north_star(),
            "active_buildings": active_buildings(),
            "brain_notes": len(brain().list_notes()),
        }
        return state
    except Exception:
        return buildings
