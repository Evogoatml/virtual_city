"""
The city IS the business pipeline. Buildings are laid out left → right in the
exact order work flows through the company (Effata Picks, print-on-demand):

    [research_building] → [product_studio] → [storefront] → [treasury]
     (supply_scout+scraper)  make listings      take orders     count money
     find+score products     (draft products)   + fulfill       (real only)

City Hall (CEO) sits above the pipeline and runs the weekly loop: one target,
Friday report. No simulated businesses — every building produces a real,
inspectable artifact or real money movement.

Buildings are organized into districts. Orchestrator buildings (finance_building,
media_building, research_building) aggregate their departments — those departments
are sub-components of the orchestrator, not standalone grid cells.
"""
from city.db import upsert_building

CELL_W = 160
CELL_H = 160
MARGIN_X = 80
MARGIN_Y = 80
BUILDING_W = 120
BUILDING_H = 120

# (col, row) grid positions. Only standalone buildings and orchestrator
# buildings appear as grid cells. Departments are nested under their
# orchestrator parent — see DEPARTMENTS below.
BUILDINGS = {
    # Command center (row 0)
    "city_hall":          (2, 0),  # CEO — above the pipeline, runs the weekly loop
    "controll_panel":     (3, 0),  # Command center — central hub connecting all routes
                                  # (neural_index is a department under controll_panel)

    # Pipeline (row 3)
    "product_studio":     (0, 3),  # Stage 2 — turn approved leads into listings
    "storefront":         (2, 3),  # Stage 3 — publish, take real orders, fulfill
                                  # (shopify is a department under storefront)
    "treasury":           (4, 3),  # Stage 4 — real money only

    # Finance district (row 1)
    "finance_building":   (0, 1),  # Orchestrator — crypto_trading + market_data + btc_recovery + finance_treasury

    # Media & Growth district (row 2)
    "media_building":     (3, 2),  # Orchestrator — social_affiliates is a department

    # Research & Discovery district (row 4)
    "research_building":  (0, 4),  # Orchestrator — sourcing_research + supply_scout + product_flipping + web_check + signal
}

# Department → parent building mapping (for org-chart display)
DEPARTMENTS = {
    "neural_index":        "controll_panel",
    "scraper":             "supply_scout",
    "supply_scout":        "research_building",
    "product_flipping":    "research_building",
    "shopify":             "storefront",
    "crypto_trading":      "finance_building",
    "market_data":         "finance_building",
    "btc_recovery":        "finance_building",
    "finance_treasury":    "finance_building",
    "social_affiliates":   "media_building",
    "sourcing_research":   "research_building",
    "web_check":           "research_building",
    "signal":              "research_building",
}

# Pipeline flow (display + docs). Handoffs are wired on the EventBus in app.bootstrap().
PIPELINE = [
    ("supply_scout", "product_studio", "lead.approved"),
    ("product_studio", "storefront", "listing.drafted"),
    ("storefront", "treasury", "shopify.order_paid"),
]


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
    buildings = [dict(r) for r in rows if r["name"] in BUILDINGS]

    # Attach sub-department list to each building (reverse of DEPARTMENTS)
    dept_parents = {}
    for dept_name, parent_name in DEPARTMENTS.items():
        dept_parents.setdefault(parent_name, []).append(dept_name)
    for b in buildings:
        b["departments"] = dept_parents.get(b["name"], [])

    # Load paused flags from agent_config
    paused_rows = conn.execute(
        "SELECT agent_name FROM agent_config WHERE key = 'paused' AND value = '1'"
    ).fetchall()
    paused_set = {r["agent_name"] for r in paused_rows}
    for b in buildings:
        b["paused"] = b["name"] in paused_set

    # Operator context: active persona + north-star + brain size + the pipeline
    try:
        from city.persona import active_persona, north_star, active_buildings
        from city.brain import brain
        from city.db import count_open_escalations
        state = {
            "buildings": buildings,
            "persona": active_persona(),
            "north_star": north_star(),
            "active_buildings": active_buildings(),
            "brain_notes": len(brain().list_notes()),
            "open_escalations": count_open_escalations(conn),
            "pipeline": [
                {"from": f, "to": t, "event": ev} for f, t, ev in PIPELINE
            ],
            "departments": DEPARTMENTS,
        }
        return state
    except Exception:
        return buildings
