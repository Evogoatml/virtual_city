"""
Auto-discovers Agent subclasses under the `buildings/` package and
instantiates one of each, keyed by agent.name. Drop a new .py file in
any buildings/<building>/ directory and it gets a building automatically.
"""
import logging
import pkgutil
import importlib
import inspect

from city.agent import Agent

log = logging.getLogger("city.registry")

_INSTANCES = {}

# Vendored / standalone trees — not city Agent modules. Skip so boot stays
# fast and discovery failures stay visible for real buildings.
_SKIP_PREFIXES = (
    "buildings.btc_recovery.btcrecover",
    "buildings.btc_recovery.btc-python",
    "buildings.btc_recovery.btc_python",
    "buildings.social_media.viral",
    "buildings.CEO.kernel",
    "buildings.storefront.shopify.test_automate",
)


def _should_skip(module_name: str) -> bool:
    return any(module_name == p or module_name.startswith(p + ".") for p in _SKIP_PREFIXES)
def discover_and_build(conn):
    """Import every module in the buildings package tree, instantiate any Agent
    subclasses found, and return {name: instance}."""
    global _INSTANCES
    if _INSTANCES:
        return _INSTANCES

    import buildings as buildings_pkg

    for importer, module_name, is_pkg in pkgutil.walk_packages(
        buildings_pkg.__path__, prefix="buildings.", onerror=lambda x: None
    ):
        if _should_skip(module_name):
            continue
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            log.warning("discovery import failed: %s — %s", module_name, exc)
            continue
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj is Agent or not issubclass(obj, Agent):
                continue
            if obj.__module__ != module.__name__:
                continue
            try:
                instance = obj(conn)
                if instance.name in _INSTANCES:
                    log.warning(
                        "duplicate agent name %r from %s (keeping first)",
                        instance.name,
                        module_name,
                    )
                    continue
                _INSTANCES[instance.name] = instance
                log.info("registered agent %s (%s)", instance.name, obj.__name__)
            except Exception as exc:
                log.warning(
                    "discovery instantiate failed: %s.%s — %s",
                    module_name,
                    obj.__name__,
                    exc,
                )

    log.info("discovery complete: %d agents", len(_INSTANCES))
    return _INSTANCES


def get_registry(conn=None):
    if not _INSTANCES and conn is not None:
        discover_and_build(conn)
    if conn is not None:
        for agent in _INSTANCES.values():
            agent.conn = conn
    return _INSTANCES


def get_agent(name):
    return _INSTANCES.get(name)
