#!/usr/bin/env python3
"""
Agent Registry
Tracks agent identity, capabilities, health, and active tokens.
"""

import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field


@dataclass
class AgentRecord:
    agent_id: str
    name: str
    capabilities: List[str]
    trust_level: float = 1.0  # 0.0 - 1.0
    registered_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    active_tokens: List[str] = field(default_factory=list)
    tasks_completed: int = 0
    tasks_failed: int = 0
    health_status: str = "healthy"  # healthy, degraded, dead


class AgentRegistry:
    """Central registry for all agents in the swarm."""

    def __init__(self):
        self.agents: Dict[str, AgentRecord] = {}

    def register(self, agent_id: str, name: str, capabilities: List[str], trust_level: float = 1.0):
        if agent_id in self.agents:
            self.agents[agent_id].last_seen = time.time()
            return
        self.agents[agent_id] = AgentRecord(
            agent_id=agent_id,
            name=name,
            capabilities=capabilities,
            trust_level=trust_level,
        )

    def unregister(self, agent_id: str):
        self.agents.pop(agent_id, None)

    def get(self, agent_id: str) -> Optional[AgentRecord]:
        return self.agents.get(agent_id)

    def is_registered(self, agent_id: str) -> bool:
        return agent_id in self.agents

    def add_token(self, agent_id: str, token_id: str):
        rec = self.agents.get(agent_id)
        if rec:
            rec.active_tokens.append(token_id)
            rec.last_seen = time.time()

    def remove_token(self, agent_id: str, token_id: str):
        rec = self.agents.get(agent_id)
        if rec and token_id in rec.active_tokens:
            rec.active_tokens.remove(token_id)

    def record_result(self, agent_id: str, success: bool):
        rec = self.agents.get(agent_id)
        if rec:
            if success:
                rec.tasks_completed += 1
            else:
                rec.tasks_failed += 1
            rec.last_seen = time.time()

    def get_healthy_agents(self, capability: Optional[str] = None) -> List[AgentRecord]:
        healthy = [a for a in self.agents.values() if a.health_status == "healthy"]
        if capability:
            healthy = [a for a in healthy if capability in a.capabilities]
        return sorted(healthy, key=lambda x: x.trust_level, reverse=True)

    def get_status(self) -> Dict[str, Any]:
        return {
            "total": len(self.agents),
            "healthy": len([a for a in self.agents.values() if a.health_status == "healthy"]),
            "agents": {
                aid: {
                    "name": a.name,
                    "capabilities": a.capabilities,
                    "trust": a.trust_level,
                    "tasks": a.tasks_completed,
                    "failed": a.tasks_failed,
                    "tokens": len(a.active_tokens),
                }
                for aid, a in self.agents.items()
            },
        }

