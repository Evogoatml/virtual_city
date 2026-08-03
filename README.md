# Virtual City

A Flask app where each business function is a building/agent on a city map.
Agents are rule-based (regex command matching) — no LLM calls. City state
streams to the browser in real time via Server-Sent Events.

## Buildings
- **City Hall** — orchestrator; holds the daily meeting (pulls a report from every other agent)
- **Crypto Trading** — buy/short/close positions, portfolio, risk exposure
- **Product Flipping** — source/list/sell inventory, margins
- **Shopify** — orders, revenue/profit, top products
- **Social Affiliates** — campaigns, clicks, conversions, revenue
- **Content Creation** — idea -> draft -> published pipeline
- **Sourcing & Research** — scored opportunity leads
- **Finance & Treasury** — manual ledger + auto-aggregates every other agent's report()

## Run

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000

## Adding a new agent/building

Drop a new file in `agents/` defining one `city.agent.Agent` subclass.
It's auto-discovered at startup and gets a building automatically
(unknown agents get auto-placed on the grid; add a fixed position for it
in `city/city_grid.py`'s `LAYOUT` dict if you want it somewhere specific).

Each agent:
- sets `name`, `subject`, `district`, `color`
- optionally overrides `setup_schema()` to create its own SQLite table(s)
- calls `self.rule(r"regex")(self._handler)` in `register_rules()` for each command it understands
- overrides `report()` — this is what shows up in City Hall's daily meeting
  and Finance & Treasury's aggregation

## Command examples (via the in-app console or `POST /api/query`)

```
crypto_trading:      buy 0.5 BTC @ 65000
crypto_trading:      close BTC @ 68000
product_flipping:    source Nintendo Switch cost 150
product_flipping:    list Nintendo Switch target 280
product_flipping:    sold Nintendo Switch for 275
shopify:              order Copper Hoodie revenue 45 cost 18 pod
social_affiliates:    campaign instagram FanvueLink
social_affiliates:    convert FanvueLink revenue 30
content_creation:     idea EDC photo dump for instagram
content_creation:     publish EDC photo dump
sourcing_research:    lead LED grow light category cannabis score 8.5
finance_treasury:     ledger add manual 500 seed capital
finance_treasury:     summary
city_hall:            meeting
```

## API
- `GET  /api/city` — full city state (buildings, status, positions)
- `GET  /api/stream` — SSE feed of city state, pushes on change
- `GET  /api/agent/<name>` — agent detail: report + recent events
- `POST /api/query` — `{"agent": "...", "query": "..."}`
- `POST /api/meeting` — manually trigger City Hall's daily meeting
  (also runs automatically every 24h via APScheduler)

## Notes
- SQLite DB lives at `data/city_state.db` (WAL mode). Delete it to reset the city.
- Agents are process-wide singletons but rebind to a fresh DB connection
  per request (see `city/registry.py`) since Flask hands out per-request
  SQLite connections.
# virtual_city
