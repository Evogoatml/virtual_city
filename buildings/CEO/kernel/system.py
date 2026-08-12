"""
GhostGoat System Bootstrapper
==============================

Start the entire system with one call::

    from core.kernel.system import system
    await system.start()

What it does on start
---------------------
1. Initialises all controllers (LLM, Memory, Tools, Tasks)
2. Registers all specialist agents
3. Wires up the PMMAGO orchestrator with the full NLM unified team
4. Starts the AgentBus (pub/sub + WebSocket server)
5. Starts the TaskController processing loop
6. Publishes a system.ready event

The system then runs autonomously:
- Tasks submitted via Telegram, API, or task_ctrl go into the queue
- PMMAGO plans, the NLM team executes, Gödel critic validates
- Every result is stored in memory and broadcast on the bus
- The skill library grows with every successful execution
- Auto-patch on Gödel failures means the system self-improves over days

Architecture
------------
  Telegram / API
       ↓
  TaskController (priority queue)
       ↓
  PMMAGO Orchestrator (oversees everything)
   ├── PlannerAgent       (decides which team members to activate)
   ├── NLM Unified Team   (all specialists share TeamState)
   │    ├── Agent K        skill recall, code/crypto/system
   │    ├── AgentGPT       research, web search, synthesis
   │    ├── CrewAI         multi-role pipelines
   │    ├── iSwarmsAI      parallel fan-out + consensus
   │    ├── SuperAGI       goal decomposition, meta-planning
   │    └── Synthesiser    merges all into one answer
   └── Gödel Critic       validates quality, triggers auto-patch
       ↓
  AgentBus (broadcasts results to all subscribers + WebSocket)
       ↓
  Memory (ChromaDB + DuckDB — grows richer every run)
"""

from __future__ import annotations
import asyncio
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class GhostGoatSystem:
    """
    Single entry point for the entire GhostGoat system.
    Singleton — import and use `system` directly.
    """

    _instance: Optional["GhostGoatSystem"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._started = False
        return cls._instance

    def __init__(self):
        if self._started:
            return
        self.orchestrator = None
        self._task_loop: Optional[asyncio.Task] = None
        self._ws_server = None

    # ── bootstrap ─────────────────────────────────────────────────────────────

    async def start(self, ws_port: int = 8765):
        if self._started:
            logger.info("[System] already running")
            return

        logger.info("[System] ══════════════════════════════════════")
        logger.info("[System]  GhostGoat starting up…")
        logger.info("[System] ══════════════════════════════════════")

        # 1. Controllers
        from core.controllers.llm_controller import llm  # noqa: F401
        from core.controllers.memory_controller import memory  # noqa: F401
        from core.controllers.tool_controller import tools  # noqa: F401
        from core.controllers.task_controller import task_ctrl
        logger.info("[System] controllers ready")

        # 2. Agent Bus
        from core.bus.agent_bus import bus
        self._ws_server = await bus.start_ws_server(port=ws_port)
        logger.info("[System] AgentBus ready (ws port %d)", ws_port)

        # 3. Build orchestrator (PMMAGO + NLM team)
        from core.brain.adapters.nlm_layer import build_orchestrated_team
        self.orchestrator = build_orchestrated_team(
            llm_call=llm.as_callable(),
            auto_patch=True,
        )
        logger.info("[System] PMMAGO orchestrator ready")

        # 4. Wire task controller → orchestrator
        task_ctrl.set_executor(self.orchestrator.execute_async)
        self._task_loop = asyncio.ensure_future(task_ctrl.run_loop())
        logger.info("[System] TaskController loop started")

        # 5. Register specialist agents on the bus
        self._register_agents(bus)

        # 6. Seed math knowledge in background (non-blocking)
        asyncio.ensure_future(self._seed_math_knowledge(bus))

        # 6b. Ordinance scan — generate AGENT.md in every folder (non-blocking)
        asyncio.ensure_future(self._run_ordinance_scan(bus))

        # 7. Start neural plasticity engine (prevents loop ossification)
        # from core.brain.agent_core.reasoning_core import plasticity
        # plasticity.start()
        # logger.info("[System] NeuralPlasticity engine started")

        # 8. Start loop guardian (liveness + ossification watchdog)
        # from core.kernel.build_loop import guardian
        # self._register_loops_with_guardian(guardian)
        # guardian.start()
        # logger.info("[System] LoopGuardian watchdog started")

        # 9. Ready
        self._started = True
        await bus.publish("system.status", {
            "status": "ready",
            "agents": ["agent_k", "agentgpt", "crewai", "iswarmsai", "superagi", "synthesiser"],
            "features": ["pmmago", "godel_critic", "auto_patch", "skill_library",
                         "vector_memory", "agent_bus", "web_search", "code_execution",
                         "hf_math_datasets", "numeric_validator", "crystal_lattice_pipeline",
                         "neural_plasticity", "loop_guardian"],
        }, source="system")

        logger.info("[System] ✓ GhostGoat is running. All agents active. Math KB seeding in background.")
        logger.info("[System]   WebSocket bus: ws://0.0.0.0:%d", ws_port)
        logger.info("[System]   Submit tasks via task_ctrl or Telegram.")

    def _register_agents(self, bus):
        """Instantiate specialists and announce them on the bus."""
        try:
            from agents.multi_agent_bot import (
                AgentK as AgentK, AgentGPT as AgentGPTAgent, CrewAI as CrewAISpecialist, 
                SwarmsAI as SwarmsSpecialist, SuperAGI as SuperAGIAgent
            )
            self._agents = {
                "agent_k":   AgentK(),
                "agentgpt":  AgentGPTAgent(),
                "crewai":    CrewAISpecialist(),
                "iswarmsai": SwarmsSpecialist(),
                "superagi":  SuperAGIAgent(),
            }
        except ImportError:
            logger.info("[System] External agents module not found, using internal orchestrator only")
            self._agents = {}
        
        for name, agent in self._agents.items():
            bus.publish_sync("system.status", {
                "event": "agent_registered",
                "agent": name,
                "description": agent.description,
                "skills": getattr(agent, "SKILLS", []),
            }, source="system")
        logger.info("[System] %d specialist agents registered", len(self._agents))

    def _register_loops_with_guardian(self, guardian):
        """
        Tell the LoopGuardian about every background loop so it can watch
        for liveness and ossification.
        """
        import asyncio

        # SelfAwareLoop — should heartbeat at least every 130s (it backs off to 120s max)
        try:
            from core.brain.agents.self_aware_loop import SelfAwareLoop
            sal = SelfAwareLoop()
            guardian.register(
                "self_aware_loop",
                restart_fn=lambda: sal.start(),
                max_silence_secs=200,
                heartbeat_fn=lambda: str(sal.health_history[-1]) if sal.health_history else "",
            )
        except Exception as e:
            logger.debug("[System] guardian self_aware_loop register: %s", e)

        # Task controller loop
        guardian.register(
            "task_controller",
            restart_fn=lambda: None,   # managed by asyncio — just alert
            max_silence_secs=300,
        )

        # NeuralPlasticity — cycles every 6h, so TTL = 7h
        try:
            from core.brain.agent_core.reasoning_core import plasticity
            guardian.register(
                "neural_plasticity",
                restart_fn=lambda: plasticity.start(),
                max_silence_secs=7 * 3600,
                heartbeat_fn=lambda: json.dumps(plasticity.status(), default=str),
            )
        except Exception as e:
            logger.debug("[System] guardian neural_plasticity register: %s", e)

        # Math seeder — re-seed if silent for 24h
        guardian.register(
            "math_seeder",
            restart_fn=lambda: asyncio.ensure_future(self._seed_math_knowledge(None)),
            max_silence_secs=24 * 3600,
        )

        # BuildLoop
        try:
            from core.kernel.build_loop import BuildLoop
            bl = BuildLoop()
            guardian.register(
                "build_loop",
                restart_fn=lambda: asyncio.ensure_future(bl.run()),
                max_silence_secs=4 * 3600,
            )
        except Exception as e:
            logger.debug("[System] guardian build_loop register: %s", e)

        logger.info("[System] LoopGuardian: %d loops registered",
                    len(guardian._loops))

    # ── public API ────────────────────────────────────────────────────────────

    async def run_task(self, task: str, domain: str = "general") -> dict:
        """Submit a task directly and await its result."""
        if not self._started:
            await self.start()
        goal = {"description": task, "domain": domain, "context": {}}
        return await self.orchestrator.execute_async(goal)

    async def chat(
        self,
        message: str,
        user_id: str = "default",
        username: str = "friend",
        history: list = None,
    ) -> dict:
        """
        Single entry point for all conversational interfaces (Telegram, API, etc.).

        The orchestrator handles everything:
          - domain detection & persona assignment
          - agent routing & execution
          - response formatting

        Returns
        -------
        dict with keys:
            text  : str   — formatted response ready to send
            persona_name : str  — e.g. "Byte"
            persona_emoji: str  — e.g. "💻"
        """
        if not self._started:
            await self.start()

        goal = {
            "description": message,
            "domain": "general",   # planner will override this
            "context": {
                "user": username,
                "user_id": str(user_id),
                "history": (history or [])[-6:],
            },
        }

        # Always use direct LLM - simplest path, works with Ollama Cloud
        text = ""
        try:
            from core.controllers.llm_controller import llm
            import asyncio as _asyncio
            loop = _asyncio.get_running_loop()
            text = await loop.run_in_executor(None, lambda: llm.call(message))
        except Exception as e:
            logger.warning("[System] LLM call failed: %s", e)
            text = "Sorry, I couldn't process that. Please try again."

        # ── Format ────────────────────────────────────────────────────────
        if text:
            formatted = f"🐐 *GhostGoat*\n\n{text}"
        else:
            formatted = "🐐 *GhostGoat* — I couldn't produce a response. Try rephrasing or check that your LLM API key is set."

        return {
            "text": formatted,
            "persona_name": "GhostGoat",
            "persona_emoji": "🐐",
        }

    async def _seed_math_knowledge(self, bus):
        """Background task: seed HF math datasets into skill library + memory."""
        try:
            from core.bridges.hf_bridge import MathSeeder
            seeder = MathSeeder()
            await bus.publish("system.status",
                              {"event": "math_seeding_started"}, source="system")
            # Seed highest-value domains first, smaller limits on first boot
            priority = {"algebra": 300, "arithmetic": 200, "word_problems": 200,
                        "number_theory": 150, "numeric_reasoning": 150}
            await seeder.seed_all(limits=priority)
            report = seeder.report()
            logger.info("[System] math KB seeded: %d samples across %d domains",
                        report["total"], len(report["domains_seeded"]))
            await bus.publish("system.status", {
                "event": "math_seeding_complete", **report
            }, source="system")
        except Exception as e:
            logger.warning("[System] math seeding failed (non-fatal): %s", e)

    async def _run_ordinance_scan(self, bus):
        """Background task: generate AGENT.md in every folder."""
        try:
            loop = asyncio.get_event_loop()
            from core.ordinance.distributed_system import DistributedAgentSystem
            das = DistributedAgentSystem(root_dir=self.root_dir
                                         if hasattr(self, "root_dir") else None)
            stats = await loop.run_in_executor(None, das.scan)
            logger.info("[System] Ordinance scan: %d files → %d agents",
                        stats["files_indexed"], stats["agents"])
            if bus:
                await bus.publish("system.status", {
                    "event": "ordinance_scan_complete", **stats
                }, source="system")
        except Exception as e:
            logger.warning("[System] ordinance scan failed (non-fatal): %s", e)

    def stop(self):
        if self._task_loop:
            self._task_loop.cancel()
        from core.controllers.task_controller import task_ctrl
        task_ctrl.stop()
        try:
            from core.brain.agent_core.reasoning_core import plasticity
            plasticity.stop()
        except Exception:
            pass
        try:
            from core.kernel.build_loop import guardian
            guardian.stop()
        except Exception:
            pass
        self._started = False
        logger.info("[System] GhostGoat stopped")

    @property
    def is_running(self) -> bool:
        return self._started

    def status(self) -> dict:
        from core.controllers.task_controller import task_ctrl
        from core.bus.agent_bus import bus
        return {
            "running": self._started,
            "recent_tasks": task_ctrl.recent(10),
            "recent_events": bus.recent(10),
            "agents": list(getattr(self, "_agents", {}).keys()),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
system = GhostGoatSystem()


# ── CLI entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    async def _main():
        await system.start()
        # Keep running
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, asyncio.CancelledError):
            system.stop()

    asyncio.run(_main())
