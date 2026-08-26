# Virtual City — Build Plan (LOCKED)

Last updated: 2026-08-25
Status: v2 architecture — adds Shared Knowledge Core, real Agent Runtime, Personas,
and a multi-view Operator UI on top of the original charter.

---

## 0. The charter (user intent — DO NOT rewrite)

**One system: Virtual City** (one product, one company surface).

**Not** one giant orchestrator that runs every building as a single brain.

**Each building has its own orchestrator** — own loop, own work, own state, own decisions within its domain.

**Buildings interact** — handoffs, events, shared money/metrics, CEO meetings — without becoming one process-of-everything.

```
                     ┌─────────────┐
                     │  City Hall  │  Conductor — coordinates / meetings / rollup
                     │ (Conductor) │  (does NOT replace building brains)
                     └──────┬──────┘
            interact │ events / reports / requests
      ┌─────────────┼─────────────┬─────────────┐
      ▼             ▼             ▼             ▼
 ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐
 │ Finance │  │  Media  │  │Affiliates│  │Commerce │ ...
 │  orch.  │◄►│  orch.  │◄►│  orch.  │◄►│  orch.  │
 └─────────┘  └─────────┘  └─────────┘  └─────────┘
    own loop     own loop     own loop     own loop
```

| Layer | Responsibility |
|-------|----------------|
| **City (one system)** | UI board, map status, registry, shared DB/events bus, treasury rollup, start/stop city |
| **Building orchestrator** | Domain autonomy: schedule, act, queue, optimize inside that building |
| **Interaction** | Buildings publish/consume events or call each other |
| **City Hall / Conductor** | Ask for reports, hold meetings, surface alerts — **not** micromanage every tick |

**Tracking rule (immutable):** one system, **many building orchestrators**, **explicit interaction**.
Never propose "one global AutonomousOrchestrator for everything." Never propose fully isolated apps with no interaction.

---

## 0.5 Building Contract (STRUCTURE RULE — added 2026-08-26)

Every building MUST follow this shape. Two crashes (a segfault recursion and a
"closed database" segfault) were both caused by violating these rules.

1. **One building per external domain / integration.** Shopify is its own building.
   Finance is its own building. Crypto is its own building. Do not split one domain
   across multiple top-level buildings, and do not let a department also register
   as a peer building.

2. **A building handles its own domain natively.** Shopify handles Shopify (webhooks,
   store queries, Printful). Finance handles money. It does NOT embed another
   building's logic.

3. **Cross-domain needs go through the bus or the registry — never by reaching into
   another building's internals.** Publish/consume events (`EventBus`) or call the
   other building via `get_registry()`. A building may read *peer* reports for a
   rollup, but it must **never re-aggregate its own parent/container** (that creates
   an infinite cycle).

4. **Departments live inside one building.** A building may contain departments
   (e.g. `finance_building` owns `market_data` + `finance_treasury`). Trading is
   its own domain, so `crypto_trading` is a standalone building, NOT a finance
   department. Departments are NOT separately registered on the city grid.

5. **DB access is owned by the framework, not the building.** Use the thread-local
   connection from `city.db` (`get_raw_connection()` / `get_db()`). Never store a
   connection on a shared attribute and close it from another thread. Connections are
   per-thread and intentionally never explicitly closed.

6. **Single registration.** Each building/department is discovered and registered
   exactly once. Double-registration (same agent appearing as both a department and a
   top-level building) is forbidden — it is what produced the finance recursion.

---

## 1. What we are adding (the new model)

The original plan gave us buildings + interaction. It did **not** specify (a) a shared
memory every agent reads before acting, (b) real LLM-driven `run()` with budget awareness,
(c) personas that enable/disable buildings + set north-star metrics, or (d) a multi-view
operator UI. Those are added here and are fully compatible with the charter.

### 1.1 Shared Knowledge Core — "the Brain" (CRITICAL)

A markdown vault that **every agent reads before it acts**. This is the system's single
source of truth for strategy, SOPs, north-star metrics, domain knowledge, and decisions.

- Location: `brain/vault/` — flat or lightly nested markdown files.
- Each note: `# Title`, optional YAML front-matter (`tags`, `buildings`, `personas`, `priority`),
  body in plain markdown.
- Loader (`city/brain/vault.py`): scans the vault at boot (and on edit), parses front-matter,
  builds an in-memory index keyed by tag / building / persona / keyword.
- Retrieval (RAG-lite, no vectors required to start): `brain.context_for(agent, persona, query)`
  returns the most relevant notes (front-matter match → keyword overlap → recency).
  Pluggable later to embeddings if needed.
- Write path: agents can **propose** brain updates (decisions, learned SOPs) via
  `brain.propose_note(...)`; Conductor or human approves. Brain is append-friendly, never
  truncates its own history.
- Seed notes (shipped): `strategy.md`, `north_star.md`, `domains/crypto.md`,
  `domains/ecommerce.md`, `domains/content.md`, `sops/affiliate_funnel.md`, `decisions/` log.

> This replaces the *symbolic* `city/cognition.py` thought-tree (which produced fake glyph
> traces and did no real work). The Brain is real, persistent, and inspectable.

### 1.2 Agent Runtime (replaces symbolic cognition)

A real per-building runtime that turns "think → act → observe" into actual work, budget-aware
and LLM-backed. Keeps the **per-building** ownership the charter demands.

```
AgentRuntime.run(agent, persona):
    ctx = brain.context_for(agent, persona)          # 1. read the Brain
    plan = llm.decide(system=agent.role, user=ctx+state)  # 2. decide via LLM
    for skill in plan.skills:                          # 3. execute skills
        if autonomy_blocks(agent, skill): request_human(); continue
        result = skill.execute(budget_aware=True)
        bus.publish(agent, skill.event, result)        # 4. emit interaction events
        log_run(agent, skill, result)                  # 5. run history
    return summary
```

- `city/runtime.py`: `AgentRuntime` + `RunRecord` (history in `agent_runs` table).
- `city/llm.py`: thin provider abstraction over the **existing** `city/venice.py`
  (OpenAI-compatible; works with Venice, OpenAI, OpenRouter, or a local Ollama/LLM gateway
  by swapping `base_url`/`api_key`). All calls routed through `city.api_budget`.
- **Autonomy levels** per building (stored in `agent_config`):
  - `human_led` — only plans, never executes external skills without approval.
  - `human_assisted` — executes cheap skills; asks for destructive/expensive ones.
  - `autonomous` — executes within budget; logs everything; can self-correct.
- **Skills**: each building declares `skills = [Skill(...)]`; a Skill is a typed callable
  with `name`, `cost_kind` (llm/http/exchange/...), `risk` (read/write/destructive), and
  `run(**kwargs)`. The LLM chooses among them; the runtime enforces budget + autonomy.

### 1.3 Persona system

A persona = a named operating mode that **enables a subset of buildings** and sets
**north-star metrics**. Stored as markdown in `brain/vault/personas/` (or `personas` table).

- Examples: `ecom_operator` (Shopify, Product Flipping, Affiliates, Content, Finance),
  `crypto_operator` (Crypto Trading, Market Data, BTC Recovery, Finance),
  `full_multistream` (everything on).
- Loading a persona: sets active buildings, injects north-star into Brain context,
  and City Hall rolls up only active buildings against those metrics.
- `city/persona.py`: `load_persona(name)`, `active_buildings()`, `north_star()`.

### 1.4 Conductor / City Hall (lightweight coordinator)

- Reads Brain `north_star.md` + active persona → derives the daily focus.
- Holds meetings: collects `report()` from active buildings, publishes a rollup event.
- Can dispatch a high-level intent ("grow affiliate revenue 10%") → each building's
  runtime plans locally. Conductor never executes domain skills itself.
- Surfaces alerts when a building is over budget, blocked, or off north-star.

### 1.5 Interaction bus (make it real)

The `EventBus` already exists (`city/orchestrator.py`). We wire concrete events:
`content.published`, `affiliate.conversion`, `trade.closed`, `flip.listed`,
`lead.found`, `treasury.moved`. Buildings subscribe and react (e.g. Content publishes →
Affiliates picks up the link; Affiliate conversion → Finance ledger entry).

### 1.6 Multi-view Operator UI (dark, cyber, high-density)

Views (original build — see §3 about the `os/` clone):
`Home/Operator` · `Agents/Org` · `Funnel/Pipeline` · `Social/Growth` ·
`Knowledge/Brain` · `Skills` · `Personas`. All consume the Flask JSON + SSE APIs.

---

## 2. What stays vs what changes

| Keep | Change / Rewrite |
|------|------------------|
| Building/agent metaphor & domain logic | Pure regex as primary interface → LLM runtime + skills |
| Real-time SSE state streaming | Symbolic `cognition.py` → real Brain-backed `runtime.py` |
| API budget / rate limiting (`api_budget`) | Frontend → original multi-view operator UI |
| Per-agent reports & dashboards | Add run history + autonomy + persona scoping |
| Event bus, registry auto-discovery | Wire real cross-building events |
| `venice.py` LLM client, `orchestrator.EventBus` | (reuse as-is) |

---

## 3. Decisions pending (must confirm before UI build)

- **`os/` directory**: it is a *verbatim copy of the Founder OS open-source demo*
  (own `README.md`, `LICENSE`, `package.json: founder-os`). This conflicts with the
  "build our own, don't clone/fork" instruction and carries a third-party license.
  **Recommendation: do not ship it.** Build an original operator UI (see §1.6) that
  consumes the Virtual City Flask backend. Keep it only as temporary visual reference,
  then delete before committing.
- **Frontend stack**: original React/Next app vs enhanced Flask+JS templates.
- **LLM default**: Venice (already wired) vs OpenAI/OpenRouter/local.
- **Integration depth**: real LLM + simulated domain APIs first (recommended), then
  wire real external APIs where keys exist.

---

## 4. Build order (phased, highest-leverage first)

1. **Shared Knowledge Core** — `city/brain/` package + seed vault. (no UI needed)
2. **Agent Runtime + LLM + autonomy + skills + run history** — `city/runtime.py`,
   `city/llm.py`, `agent_runs` table; refactor ONE building to use it end-to-end.
3. **One strong persona** — `ecom_operator` (or `full_multistream`) loading active
   buildings + north-star; Conductor rollup respects it.
4. **Real interaction wiring** — concrete events across Content↔Affiliates↔Finance.
5. **Operator UI** — original multi-view dark dashboard over existing JSON/SSE APIs.
6. **More buildings onto the runtime** — same contract, never fold into one brain.

---

## 5. Done when

- One city boots; each building runs its **own Brain-aware runtime** with `run()` history.
- Buildings **change each other's world** via real published events.
- A **persona** selects active buildings + north-star; Conductor rolls up against it.
- The operator sees the company across all views without editing scripts for normal ops.
- The **Brain** is the single read-before-act memory for every agent.
