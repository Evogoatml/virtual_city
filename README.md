# Virtual City

A Flask app where each business function is a building/agent on a city map.
Agents are rule-based (regex command matching). City state streams to the
browser in real time via Server-Sent Events.

## Buildings

21 agents. Buildings are orchestrator buildings (aggregate departments) or
standalone pipeline buildings. Departments are sub-components of an
orchestrator building — they're registered agents but appear nested under
their parent, not as separate grid cells.

**Command District** — runs the city
- **City Hall** (CEO) — orchestrator; holds the daily meeting, pulls a report from every other agent
- **Controll Panel** — command center, event routing, system metrics
  - `neural_index` — codebase indexing, AGENT.md generation, feeds the brain

**Research & Supply** — sourcing, scraping, product research
- **Research Building** (orchestrator)
  - `sourcing_research` — scored opportunity leads
  - `supply_scout` — lead generation, opportunity discovery
    - `scraper` — three-tier web fetcher (scrapling → requests → httpx)
  - `signal` — change detection on watched URLs
  - `web_check` — website health monitoring
  - `product_flipping` — source + flip inventory, margins

**Studio District** — product creation
- **Product Studio** — turn approved leads into listings, manage drafts

**Commerce District** — sales + revenue
- **Storefront** — publish products, take orders, fulfill
  - `shopify` — Shopify store integration, real orders
- **Treasury** — real money ledger + rollup of all revenue

**Finance District** — trading + data
- **Finance Building** (orchestrator) — crypto trading + market data
  - `crypto_trading` — buy/short/close positions via ccxt
  - `market_data` — price feeds, market snapshots
  - `btc_recovery` — Bitcoin wallet recovery toolkit
  - `finance_treasury` — manual ledger + auto-aggregates every agent's report()

**Media District** — marketing + growth
- **Media Building** (orchestrator)
  - `social_affiliates` — campaigns, clicks, conversions, revenue

### Pipeline flow (real money, no simulations)

```
supply_scout → product_studio → storefront → treasury
  find products   make listings   take orders   count money
```

Handoffs are wired on the EventBus: `lead.approved` → `listing.drafted` →
`shopify.order_paid` → ledger entry.

## CLI

A CLI wrapper lives at `scripts/city` (shell wrapper around `scripts/cityctl.py`):

```bash
./scripts/city status                          # list all buildings + status
./scripts/city query <agent> '<command>'       # send a command to any agent
./scripts/city run <agent>                      # trigger one Brain-aware runtime cycle
./scripts/city meeting                        # hold City Hall's daily meeting
./scripts/city report <agent>                   # show an agent's report
./scripts/city events [agent] [n]               # recent city events
./scripts/city ledger                           # treasury ledger
./scripts/city persona [name]                   # show/set active persona
./scripts/city agenda                           # list assigned tasks
./scripts/city assign <agent> '<title>' [cmd]   # give a building a task
./scripts/city shift <agent>                    # run one employee shift
./scripts/city runs <agent>                      # run history
./scripts/city repl                             # interactive REPL
./scripts/city start                            # start the Flask server
```

## Run

```bash
cp .env.example .env   # optional keys: VENICE_API_KEY, CITY_API_KEY, video providers
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000 (binds `127.0.0.1` by default; set `CITY_HOST=0.0.0.0` only with `CITY_API_KEY` set).

When `CITY_API_KEY` is set, mutating POSTs require header `X-City-Api-Key`.

## 3D Metaverse Interface (`city.html`)

Click any building card to open its window. Each window has 4 tabs:

- **Chat** — type commands, click preset buttons
- **Plan** — write and save a plan for this building
- **Monitor** — live dashboard rendered from `/api/building/<name>/dashboard`
- **Interior** — enter the building to see its interior dashboard

**Entering a building** — the Interior tab works for ALL buildings. Click a building
card → open its window → click the "Interior" tab, or use the `__enter:` command
in chat:

```
finance_building: __enter:crypto_trading   → opens crypto_trading, enters interior
research_building: __enter:supply_scout     → opens supply_scout, enters interior
```

Departments not on the grid (like `scraper` under `supply_scout`) are registered
as virtual buildings so they can be entered too. The Controll Panel's Interior
opens a WebGL 3D command room with avatar stations.

## Adding a new agent/building

Drop a new file in `buildings/` defining one `city.agent.Agent` subclass.
It's auto-discovered at startup and gets a building automatically.

To make a department of an existing building, subclass
`city.department.Department` and set `building_name` to the parent's
name (see `scraper` for the pattern — `building_name = "supply_scout"`).

Each agent:
- sets `name`, `subject`, `district`, `color`
- optionally overrides `setup_schema()` to create its own SQLite table(s)
- calls `self.rule(r"regex")(self._handler)` in `register_rules()` for each command it understands
- overrides `report()` — this is what shows up in City Hall's daily meeting
  and Finance & Treasury's aggregation

## Command examples (via the in-app console or `POST /api/query`)

```
social_affiliates:    campaign instagram FanvueLink
social_affiliates:    convert FanvueLink revenue 30
social_affiliates:    summary
scraper:              scrape https://example.com label homepage
product_flipping:     source Nintendo Switch cost 150
product_flipping:     list Nintendo Switch target 280
product_flipping:     sold Nintendo Switch for 275
shopify:              order Copper Hoodie revenue 45 cost 18 pod
sourcing_research:    lead LED grow light category cannabis score 8.5
crypto_trading:       buy 0.5 BTC @ 65000
crypto_trading:       close BTC @ 68000
finance_treasury:     ledger add manual 500 seed capital
finance_treasury:     summary
neural_index:         index
controll_panel:       status
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