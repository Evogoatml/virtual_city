# Virtual City — Build Plan (LOCKED)

Last updated: 2026-07-26

---

## The model (user intent — do not rewrite)

**One system: Virtual City** (one product, one company surface).

**Not** one giant orchestrator that runs every building as a single brain.

**Each building has its own orchestrator** — own loop, own work, own state, own decisions within its domain.

**Buildings interact** — handoffs, events, shared money/metrics, CEO meetings — without becoming one process-of-everything.

```
                    ┌─────────────┐
                    │  City Hall  │  coordinates / meetings / rollup
                    │ orchestrator│  (does NOT replace building brains)
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
| **Interaction** | Buildings publish/consume events or call each other (e.g. Media posts with Affiliates offer; Affiliates revenue → Finance) |
| **City Hall** | Ask for reports, hold meetings, surface alerts — **not** micromanage every tick |

### Social Affiliates Studio
Belongs **inside** the Media / Affiliates building orchestrator(s) as engine code for that building — not a second product, and not the whole city’s single brain.

---

## What to build (order)

1. **Building orchestrator contract**  
   Every building: `start/stop`, `tick/work`, `report`, `handle_event`, own config/state.

2. **Interaction bus**  
   Simple city events (e.g. `content.published`, `affiliate.conversion`, `trade.closed`) so buildings react without one shared mega-loop.

3. **Media + Affiliates first**  
   Studio logic under those building orchestrators; they talk (post ↔ offer ↔ revenue).

4. **One operator board**  
   See each building’s health + city totals; send high-level commands; not replace orchestrators.

5. **Treasury + CEO**  
   Consume reports/events; roll up money; meetings.

6. **More buildings**  
   Same contract + bus; never fold into one orchestrator.

---

## Done when

- You start **one city**
- Each building **runs its own orchestrator**
- Buildings **change each other’s world** via interaction
- Board shows the company without editing scripts for normal ops

---

## Tracking rule

- One system, **many building orchestrators**, **explicit interaction**
- Do not propose “one global AutonomousOrchestrator for everything”
- Do not propose fully isolated apps with no interaction
