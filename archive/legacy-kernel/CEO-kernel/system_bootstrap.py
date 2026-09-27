
import logging

logger = logging.getLogger(__name__)

def bootstrap(orchestrator=None):
    logger.info("GhostGoat System Bootstrap starting...")

    try:
        from core.brain.agents.agent_byte_integration import register_agent_byte
        if orchestrator:
            register_agent_byte(orchestrator)
            logger.info("AgentByte wired into orchestrator")
    except Exception as exc:
        logger.warning("AgentByte wiring skipped: %s", exc)

    try:
        from core.bridges.adap_pipeline_bridge import adap_bridge
        adap_bridge.discover()
        count = adap_bridge.register_all()
        logger.info("adap_pipeline bridge: %d tools registered", count)
    except Exception as exc:
        logger.warning("adap_pipeline bridge skipped: %s", exc)

    try:
        from integrations.telegram_agent_byte import telegram_byte_handler
        logger.info("Telegram AgentByte handler ready")
    except Exception as exc:
        logger.warning("Telegram wiring skipped: %s", exc)

    try:
        from core.brain.agents.self_aware_loop_extensions import aware_extensions
        aware_extensions.orchestrator = orchestrator
        logger.info("Self-aware extensions initialised")
    except Exception as exc:
        logger.warning("Self-aware wiring skipped: %s", exc)

    try:
        from api.server import app
        from api.agent_byte_router import router as agent_byte_router, set_agent_byte
        app.include_router(agent_byte_router)
        if orchestrator and orchestrator.agent_byte:
            set_agent_byte(orchestrator.agent_byte)
        logger.info("API routes registered")
    except Exception as exc:
        logger.warning("API wiring skipped: %s", exc)

    logger.info("GhostGoat System Bootstrap complete.")

if __name__ == "__main__":
    bootstrap()
