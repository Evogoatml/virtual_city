"""
Auto-discovers Agent subclasses under the `buildings/` package and
instantiates one of each, keyed by agent.name. Drop a new .py file in
any buildings/<building>/ directory and it gets a building automatically.
"""
import pkgutil
import importlib
import inspect

from city.agent import Agent

_INSTANCES = {}


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
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj is Agent or not issubclass(obj, Agent):
                continue
            if obj.__module__ != module.__name__:
                continue
            try:
                instance = obj(conn)
                _INSTANCES[instance.name] = instance
            except Exception:
                pass

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
