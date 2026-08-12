"""GhostGoat Workflow Engine — Declarative Task Pipelines."""
import json, yaml, logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class WorkflowStep:
    name: str
    agent: str
    action: str
    payload: Dict[str, Any] = field(default_factory=dict)
    condition: Optional[str] = None
    retries: int = 1
    timeout: int = 30

@dataclass
class Workflow:
    name: str
    description: str
    steps: List[WorkflowStep]
    metadata: Dict[str, Any] = field(default_factory=dict)

class WorkflowEngine:
    def __init__(self, workflows_dir: Optional[str] = None):
        self.dir = Path(workflows_dir or Path(__file__).resolve().parent / "definitions")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.workflows: Dict[str, Workflow] = {}
        self._load_all()

    def define(self, name: str, description: str, steps: List[Dict[str, Any]]) -> Workflow:
        wf = Workflow(name=name, description=description, steps=[WorkflowStep(**s) for s in steps])
        self.workflows[name] = wf; self._save(wf)
        return wf

    def get(self, name: str) -> Optional[Workflow]: return self.workflows.get(name)
    def list_workflows(self) -> List[Dict[str, Any]]:
        return [{"name": w.name, "description": w.description, "steps": len(w.steps)} for w in self.workflows.values()]

    async def run(self, name: str, initial_payload: Dict[str, Any], agent_network: Optional[Any] = None) -> Dict[str, Any]:
        wf = self.workflows.get(name)
        if not wf: return {"error": f"Workflow {name} not found"}
        results, context = [], dict(initial_payload)
        for idx, step in enumerate(wf.steps):
            payload = {**context, **step.payload, "step_name": step.name}
            if agent_network and step.agent in agent_network.executors:
                try: result = await agent_network.dispatch(step.agent, payload)
                except Exception as e: result = {"error": str(e), "success": False}
            else:
                result = {"note": f"No agent '{step.agent}'", "payload": payload, "success": True}
            results.append({"step": step.name, "result": result})
            context[f"{step.name}_result"] = result
            if not result.get("success") and step.retries <= 1: break
        return {"workflow": name, "completed_steps": len(results), "total_steps": len(wf.steps),
                "results": results, "final_context": context}

    def _load_all(self):
        for ext in ["*.yaml", "*.json"]:
            for path in self.dir.glob(ext):
                with open(path, "r") as f:
                    data = yaml.safe_load(f) if ext == "*.yaml" else json.load(f)
                if data: self._register(data)

    def _register(self, data: Dict[str, Any]):
        steps = [WorkflowStep(**s) for s in data.get("steps", [])]
        self.workflows[data.get("name", "unnamed")] = Workflow(name=data.get("name", "unnamed"),
                                                                 description=data.get("description", ""), steps=steps,
                                                                 metadata=data.get("metadata", {}))

    def _save(self, wf: Workflow):
        data = {"name": wf.name, "description": wf.description,
                "steps": [{"name": s.name, "agent": s.agent, "action": s.action, "payload": s.payload,
                           "condition": s.condition, "retries": s.retries, "timeout": s.timeout} for s in wf.steps]}
        with open(self.dir / f"{wf.name}.yaml", "w") as f:
            yaml.dump(data, f, default_flow_style=False)

