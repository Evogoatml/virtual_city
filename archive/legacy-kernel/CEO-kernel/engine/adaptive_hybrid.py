#!/usr/bin/env python3
"""
Adaptive Hybrid Intelligence System
Dynamically selects best AI model, strategy, and approach based on task
"""

import os
import json
import time
import logging
import requests
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
from datetime import datetime

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    if GEMINI_API_KEY
    else ""
)

OLLAMA_BASE = os.getenv("OLLAMA_BASE", "http://localhost:11434")

class ModelType(Enum):
    GEMINI = "gemini"
    OLLAMA = "ollama"
    CLAUDE = "claude"
    GPT4 = "gpt4"
    LOCAL = "local"

class ExecutionMode(Enum):
    LAZY = "lazy"           # Minimal compute, basic response
    EAGER = "eager"         # Full analysis
    STREAM = "stream"       # Real-time results
    ASYNC = "async"         # Background processing

class StrategyType(Enum):
    RAG = "rag"            # Knowledge base retrieval
    CHAIN = "chain"        # Sequential processing
    SWARM = "swarm"         # Multi-agent parallel
    TREE = "tree"          # Branch exploration
    REFLECT = "reflect"   # Self-improvement loop

@dataclass
class TaskProfile:
    """Profile of task requirements"""
    complexity: int = 1           # 1-5
    urgency: int = 3               # 1-5 (5=fastest)
    accuracy: int = 3               # 1-5
    creativity: int = 2             # 1-5
    domain: str = "general"         # specialized domain
    has_knowledge: bool = False      # needs knowledge base
    has_agents: bool = False        # needs multiple agents

@dataclass
class ExecutionPlan:
    """Selected execution strategy"""
    model: ModelType = ModelType.GEMINI
    mode: ExecutionMode = ExecutionMode.EAGER
    strategy: StrategyType = StrategyType.RAG
    use_knowledge: bool = True
    use_swarm: bool = False
    iterations: int = 1
    confidence: float = 0.0

class AdaptiveHybrid:
    """Adaptive hybrid execution engine"""
    
    def __init__(self):
        self.ollama_models: List[str] = []
        self.performance_history: List[Dict] = []
        self._init()
    
    def _init(self):
        """Initialize available AI models"""
        try:
            resp = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
            if resp.status_code == 200:
                self.ollama_models = [m['name'] for m in resp.json().get('models', [])]
                logger.info("Ollama models: %s", self.ollama_models)
        except:
            logger.warning("Ollama not available")
        
        self.performance_history = []
    
    def analyze_task(self, task: str) -> TaskProfile:
        """Analyze task to create profile"""
        task_lower = task.lower()
        
        profile = TaskProfile()
        
        # Complexity detection
        if any(w in task_lower for w in ["complex", "advanced", "multi", "full"]):
            profile.complexity = 5
        elif any(w in task_lower for w in ["detailed", "explain", "how"]):
            profile.complexity = 3
        elif any(w in task_lower for w in ["simple", "what", "list"]):
            profile.complexity = 1
        
        # Urgency detection
        if any(w in task_lower for w in ["quick", "fast", "now", "urgent"]):
            profile.urgency = 5
        elif any(w in task_lower for w in ["slow", "thorough", "complete"]):
            profile.urgency = 1
        
        # Domain detection
        if any(w in task_lower for w in ["sql", "injection", "xss", "vuln"]):
            profile.domain = "security"
        elif any(w in task_lower for w in ["code", "debug", "fix"]):
            profile.domain = "development"
        
        # Knowledge requirement
        if any(w in task_lower for w in ["what", "explain", "how", "works"]):
            profile.has_knowledge = True
        
        # Agent requirement
        if any(w in task_lower for w in ["test", "scan", "exploit", "multiple"]):
            profile.has_agents = True
        
        return profile
    
    def select_model(self, profile: TaskProfile) -> ModelType:
        """Select best model based on task"""
        
        if profile.complexity >= 4 and self.ollama_models:
            if any("claude" in m.lower() for m in self.ollama_models):
                return ModelType.OLLAMA
            if any("llama" in m.lower() for m in self.ollama_models):
                return ModelType.OLLAMA
        
        return ModelType.GEMINI
    
    def select_strategy(self, profile: TaskProfile) -> StrategyType:
        """Select best strategy"""
        
        if profile.has_agents:
            return StrategyType.SWARM
        
        if profile.complexity >= 4:
            return StrategyType.TREE
        
        if profile.complexity >= 3:
            return StrategyType.CHAIN
        
        if profile.has_knowledge:
            return StrategyType.RAG
        
        return StrategyType.REFLECT
    
    def select_mode(self, profile: TaskProfile) -> ExecutionMode:
        """Select execution mode"""
        
        if profile.urgency >= 4:
            return ExecutionMode.LAZY
        
        if profile.complexity >= 4:
            return ExecutionMode.STREAM
        
        if profile.complexity >= 3:
            return ExecutionMode.EAGER
        
        return ExecutionMode.LAZY
    
    def create_plan(self, task: str) -> ExecutionPlan:
        """Create full execution plan"""
        profile = self.analyze_task(task)
        
        plan = ExecutionPlan()
        plan.model = self.select_model(profile)
        plan.strategy = self.select_strategy(profile)
        plan.mode = self.select_mode(profile)
        
        # Adjust based on strategy
        if plan.strategy == StrategyType.RAG:
            plan.use_knowledge = True
            plan.iterations = 1
        elif plan.strategy == StrategyType.SWARM:
            plan.use_swarm = True
            plan.iterations = 3
        elif plan.strategy == StrategyType.TREE:
            plan.iterations = 5
        elif plan.strategy == StrategyType.CHAIN:
            plan.iterations = 2
        
        # Calculate confidence
        base_confidence = 0.5
        base_confidence += (profile.complexity / 10)
        base_confidence += (profile.has_knowledge * 0.2)
        plan.confidence = min(base_confidence, 0.95)
        
        logger.info("Plan: %s + %s + %s (conf: %s)", plan.model.value, plan.strategy.value, plan.mode.value, plan.confidence)
        
        return plan
    
    def execute(self, task: str, knowledge: str = "") -> Dict:
        """Execute task with adaptive hybrid approach"""
        
        plan = self.create_plan(task)
        
        result = {
            "task": task[:100],
            "plan": {
                "model": plan.model.value,
                "strategy": plan.strategy.value,
                "mode": plan.mode.value,
                "confidence": plan.confidence
            },
            "execution": {},
            "output": ""
        }
        
        # Build prompt based on strategy
        prompt_context = f"Task: {task}\n\n"
        
        if plan.use_knowledge and knowledge:
            prompt_context += f"Knowledge:\n{knowledge}\n\n"
        
        if plan.strategy == StrategyType.CHAIN:
            prompt_context += "Think step by step:\n1. Analyze\n2. Execute\n3. Verify\n"
        elif plan.strategy == StrategyType.TREE:
            prompt_context += "Explore multiple approaches:\n"
        
        prompt_context += "Provide detailed response:"
        
        # Execute based on model
        if plan.model == ModelType.GEMINI:
            output = self._call_gemini(prompt_context)
            result["execution"]["model"] = "gemini"
        else:
            output = self._call_ollama(prompt_context)
            result["execution"]["model"] = "ollama"
        
        result["output"] = output
        result["success"] = bool(output)
        
        return result
    
    def _call_gemini(self, prompt: str) -> str:
        try:
            temp = 0.7 if self.ollama_models else 0.3
            resp = requests.post(
                GEMINI_URL,
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": temp,
                        "maxOutputTokens": 2048
                    }
                },
                timeout=60
            )
            if resp.status_code == 200:
                return resp.json()['candidates'][0]['content']['parts'][0]['text']
        except Exception as e:
            logger.error("Gemini error: %s", e)
        return ""
    
    def _call_ollama(self, prompt: str) -> str:
        try:
            model = "llama3.2"
            resp = requests.post(
                f"{OLLAMA_BASE}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=120
            )
            if resp.status_code == 200:
                return resp.json().get('response', '')
        except Exception as e:
            logger.error("Ollama error: %s", e)
        return ""
    
    def get_capabilities(self) -> Dict:
        return {
            "models": {
                "gemini": True,
                "ollama": len(self.ollama_models) > 0,
                "local_models": self.ollama_models
            },
            "strategies": [s.value for s in StrategyType],
            "modes": [m.value for m in ExecutionMode]
        }

class AdaptiveSwarmOrchestrator:
    """Orchestrator with adaptive hybrid execution"""
    
    def __init__(self):
        self.adaptive = AdaptiveHybrid()
        self.agents: Dict[str, Any] = {}
        self._init_agents()
    
    def _init_agents(self):
        """Initialize swarm agents"""
        self.agents = {
            "scanner": {"specialty": "vulnerability scanning"},
            "recon": {"specialty": "information gathering"},
            "exploit": {"specialty": "exploitation"},
            "privesc": {"specialty": "privilege escalation"},
            "persist": {"specialty": "persistence"},
            "pivot": {"specialty": "lateral movement"},
            "report": {"specialty": "reporting"}
        }
    
    def process(self, task: str, knowledge: str = "") -> Dict:
        """Process with adaptive hybrid"""
        
        plan = self.adaptive.create_plan(task)
        
        if plan.use_swarm:
            return self._process_swarm(task, plan, knowledge)
        
        return self.adaptive.execute(task, knowledge)
    
    def _process_swarm(self, task: str, plan, knowledge: str) -> Dict:
        """Process with swarm"""
        results = []
        
        for agent_name, info in self.agents.items():
            sub_task = f"{info['specialty']}: {task}"
            result = self.adaptive.execute(sub_task, knowledge)
            results.append({
                "agent": agent_name,
                "result": result.get("output", "")[:200]
            })
        
        return {
            "strategy": "swarm",
            "agents_used": len(results),
            "results": results
        }

adaptive = AdaptiveSwarmOrchestrator()

def explain_system() -> str:
    cap = adaptive.adaptive.get_capabilities()
    
    text = """<b>🧠 Adaptive Hybrid Intelligence</b>

<b>Models:</b>
"""
    for m, available in cap["models"].items():
        status = "✓" if available else "✗"
        text += f"  {status} {m}\n"
    
    if cap.get("local_models"):
        text += f"  Available: {', '.join(cap['local_models'])}\n"
    
    text += """
<b>Strategies:</b>
  • RAG - Knowledge base retrieval
  • CHAIN - Sequential processing  
  • SWARM - Multi-agent parallel
  • TREE - Branch exploration
  • REFLECT - Self-improvement

<b>Execution Modes:</b>
  • LAZY - Fast, minimal compute
  • EAGER - Full analysis
  • STREAM - Real-time
  • ASYNC - Background

<b>How it works:</b>
1. Analyzes your task
2. Selects best model/strategy
3. Executes with chosen approach
4. Returns optimized result
"""
    return text

def process_query(query: str, knowledge: str = "") -> str:
    """Process query with adaptive hybrid"""
    
    if "status" in query.lower() or "capability" in query.lower():
        return explain_system()
    
    if "explain" in query.lower():
        return explain_system()
    
    result = adaptive.process(query, knowledge)
    
    if "strategy" in result and result["strategy"] == "swarm":
        text = "<b>🕷️ Swarm Execution</b>\n\n"
        for r in result.get("results", []):
            text += f"<b>{r['agent']}:</b> {r['result'][:100]}...\n"
        return text
    
    text = f"<b>Plan:</b> {result['plan']['model']} + {result['plan']['strategy']} (conf: {result['plan']['confidence']:.0%})\n\n"
    text += f"<b>Output:</b>\n{result.get('output', 'No output')[:1500]}"
    
    return text

def main():
    logger.info("Testing Adaptive Hybrid...")
    
    test_tasks = [
        "What is SQL injection?",
        "Find vulnerabilities in this web app",
        "Explain privilege escalation on Linux",
    ]
    
    cap = adaptive.adaptive.get_capabilities()
    print("Capabilities:", json.dumps(cap, indent=2))
    
    for task in test_tasks:
        print(f"\n--- Task: {task} ---")
        result = adaptive.adaptive.execute(task)
        print(f"Plan: {result['plan']}")
        print(f"Output: {result.get('output', '')[:150]}...")

if __name__ == '__main__':
    main()