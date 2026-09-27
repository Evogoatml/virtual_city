# Virtual City

Virtual City is a Flask application that presents business agents as buildings. The
server owns the city state, agent registry, SQLite persistence, scheduled work, and
JSON/SSE APIs. The browser UI is server-rendered HTML plus static JavaScript; there
is no root Vite/React build.

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # fill only the providers/integrations you use
python3 app.py
```

The server listens on `CITY_HOST` (default `0.0.0.0`) and `CITY_PORT` or `PORT`
(default `5000`). It creates runtime SQLite state under `data/`, which is ignored
by Git. Do not put real credentials in tracked files.

Environment variables read by the active Flask/Python code include:

- Runtime/server: `CITY_HOST`, `CITY_PORT`, `PORT`, `CITY_API_KEY`,
  `CITY_API_BUDGET`, `COGNITION_ENABLED`, and `LLM_MOCK`.
- LLM providers: `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`,
  `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `DEEPSEEK_API_KEY`,
  `VENICE_API_KEY`, `VENICE_BASE_URL`, `VENICE_MODEL`, and `OPENAI_API_KEY`.
- Commerce/integrations: Shopify, Printful, Venice, Resend, and Slack variables
  documented in `.env.example`; values are read with `os.environ`/`os.getenv`.
- Optional web-check service: `WEB_CHECK_PATH`, `WEBCHECK_PORT`, and
  `WEBCHECK_HOST`. The checkout is external and is not committed to this repo.

## Routes

- `/` — 3D city home page.
- `/operator` — operator dashboard.
- `/manager` — manager dashboard.
- `/health` — health response.
- `/api/city`, `/api/stream`, `/api/agents`, `/api/manager` — city state and live status.
- `/api/agent/<name>`, `/api/agent/<name>/run`, `/api/agent/<name>/runs` — agent details and runtime.
- `/api/building/<name>/dashboard` — building dashboard payload.
- `/api/brain`, `/api/persona`, `/api/budget`, `/api/escalations` — supporting state APIs.
- `/room/webcheck/` and `/api/webcheck/*` — optional external web-check proxy/control.

Mutating API routes may require `X-City-Api-Key` when `CITY_API_KEY` is set.

## CLI

The CLI bootstraps the same Flask application and registry:

```bash
./scripts/city status
./scripts/city query <agent> "status"
./scripts/city run <agent>
./scripts/city meeting
./scripts/city assign <agent> "task title"
./scripts/city shift <agent>
./scripts/city report <agent>
./scripts/city brain
./scripts/city persona [name]
./scripts/city events [agent] [n]
./scripts/city ledger
./scripts/city budget
```

`python3 scripts/cityctl.py` is the underlying entry point. `scripts/start_webcheck.sh`
is an optional helper for an externally installed web-check checkout.

## Repository layout

- `app.py`, `city/`, and `buildings/` — Flask entry point, core runtime, and agents.
- `templates/` and `static/` — active Flask/Jinja pages and browser assets.
- `buildings/storefront/shopify/effata-agent/` — separate nested Next.js/React/TypeScript app.
- `buildings/storefront/shopify/effata-agent/help-agent/` — separate Node/Slack app.
- `brain/` — checked-in knowledge notes used by the runtime.
- `requirements.txt` — Python dependencies; nested Node apps have their own lockfiles.
- `archive/` — superseded code retained for reference and not imported or served.

The nested Node apps are intentionally left in place and are not part of the root
Flask build. Generated state, local checkouts, dependency directories, and build
outputs are ignored; recreate them from source/configuration when needed.
