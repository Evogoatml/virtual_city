#!/usr/bin/env python3
"""
🛡️ PARADOX KERNEL
Backend daemon integrating paradox governance, policy enforcement,
sandboxed execution, and agent lifecycle management.
"""

import os
import sys
import json
import time
import signal
import hashlib
import threading
from typing import Dict, Any, Optional

# Import our components
from .policy import PolicyEngine, TaskIntent, ExecutionToken, Verdict
from .sandbox import SandboxManager, SandboxResult
from .agent_registry import AgentRegistry
from .ipc_server import IPCServer

# Import paradox orchestrator
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from brain.paradox_aware_orchestrator import ParadoxAwareOrchestrator, ParadoxType


class ParadoxKernel:
    """
    Unified kernel daemon.
    - Receives agent requests via IPC
    - Evaluates policy + paradox constraints
    - Issues execution tokens
    - Spawns sandboxed executions
    - Tracks causal execution log
    - Adjusts axioms based on observed violations
    """

    def __init__(self, socket_path: str = "/tmp/paradox_kernel.sock"):
        self.orchestrator = ParadoxAwareOrchestrator()
        self.policy = PolicyEngine(paradox_kernel=self)
        self.sandbox = SandboxManager()
        self.registry = AgentRegistry()
        self.ipc = IPCServer(socket_path=socket_path, handler=self.handle_request)
        self.ipc.on_shutdown = self.stop

        self.execution_log: list = []
        self.belief_state: Dict[str, Any] = {}
        self.active_tokens: Dict[str, ExecutionToken] = {}
        self.running = False
        self._lock = threading.Lock()

        # Policy is now permissive; no target whitelist required

    def start(self):
        """Start the kernel daemon."""
        self.ipc.start()
        self.running = True
        print(f"🛡️  Paradox Kernel started on {self.ipc.socket_path}")
        print(f"   Agents registered: {len(self.registry.agents)}")
        print(f"   Sandbox backend: {self.sandbox.backend}")
        # Register self as agent for internal operations
        self.registry.register("kernel", "ParadoxKernel", ["governance", "audit"])

    def stop(self):
        """Graceful shutdown."""
        self.running = False
        # Revoke all active tokens
        for token in self.active_tokens.values():
            token.revoke()
        self.ipc.stop()
        self._save_audit()
        print("🛡️  Paradox Kernel stopped")

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main request handler for IPC.
        Expected request format:
        {
            "action": "execute" | "register" | "status" | "report",
            "agent_id": "...",
            ...
        }
        """
        action = request.get("action")
        agent_id = request.get("agent_id", "unknown")

        if action == "register":
            return self._handle_register(request)
        elif action == "execute":
            return self._handle_execute(request)
        elif action == "status":
            return self._handle_status(request)
        elif action == "report":
            return self._handle_report(request)
        else:
            return {"status": "error", "reason": f"Unknown action: {action}"}

    def _handle_register(self, request: Dict[str, Any]) -> Dict[str, Any]:
        agent_id = request.get("agent_id")
        name = request.get("name", agent_id)
        capabilities = request.get("capabilities", [])
        trust = request.get("trust_level", 1.0)
        self.registry.register(agent_id, name, capabilities, trust)
        return {"status": "ok", "agent_id": agent_id, "registered": True}

    def _handle_execute(self, request: Dict[str, Any]) -> Dict[str, Any]:
        agent_id = request.get("agent_id")
        command = request.get("command", "")
        target = request.get("target")

        if not self.registry.is_registered(agent_id):
            return {"status": "denied", "reason": "Agent not registered"}

        # Build intent
        intent = TaskIntent(
            agent_id=agent_id,
            raw_command=command,
            target=target,
            tool=self.policy._extract_tool(command),
        )

        # Policy evaluation
        result = self.policy.evaluate(intent)
        verdict = result["verdict"]

        if verdict != Verdict.APPROVE:
            return {
                "status": "denied",
                "reason": result["reason"],
                "verdict": verdict.value,
            }

        token = result["token"]
        bounds = result["bounds"]

        with self._lock:
            self.active_tokens[token.token_id] = token
            self.registry.add_token(agent_id, token.token_id)

        # Execute in sandbox
        sandbox_result = self.sandbox.execute(
            command=command,
            timeout=bounds["timeout"],
            memory_mb=bounds["memory"],
            network=bounds["network"],
            allowed_paths=bounds.get("paths"),
        )

        # Cleanup token
        with self._lock:
            token.revoke()
            self.active_tokens.pop(token.token_id, None)
            self.registry.remove_token(agent_id, token.token_id)

        # Determine success
        success = sandbox_result.exit_code == 0 and not sandbox_result.killed
        self.registry.record_result(agent_id, success)

        # Log to causal execution graph
        self._log_execution(agent_id, command, token, sandbox_result, success)

        return {
            "status": "completed" if success else "failed",
            "token_id": token.token_id,
            "exit_code": sandbox_result.exit_code,
            "stdout": sandbox_result.stdout[:4000],  # Truncate for IPC
            "stderr": sandbox_result.stderr[:2000],
            "duration_ms": sandbox_result.duration_ms,
            "killed": sandbox_result.killed,
            "kill_reason": sandbox_result.kill_reason,
            "warnings": getattr(token, "warnings", []),
        }

    def _handle_status(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "ok",
            "kernel": "ParadoxKernel",
            "agents": self.registry.get_status(),
            "active_tokens": len(self.active_tokens),
            "sandbox_backend": self.sandbox.backend,
        }

    def _handle_report(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Agent reports a result or contradiction for memory consolidation."""
        agent_id = request.get("agent_id")
        finding = request.get("finding", {})
        self._update_belief(agent_id, finding)
        return {"status": "ok", "belief_updated": True}

    def arbitrate(self, intent: TaskIntent) -> Dict[str, Any]:
        """
        Paradox-level arbitration.
        Called by PolicyEngine during evaluation.
        Returns verdict dict that policy respects.
        """
        # Halting check: is task bounded?
        if not self._is_bounded(intent.raw_command):
            return {
                "verdict": "deny",
                "reason": "Task appears unbounded (Halting Problem)",
                "paradox": ParadoxType.HALTING_PROBLEM.value,
            }

        # Infinite regress check: recursive agent calls
        if self._detects_recursion(intent.agent_id, intent.raw_command):
            return {
                "verdict": "deny",
                "reason": "Infinite regress detected in agent delegation",
                "paradox": ParadoxType.INFINITE_REGRESS.value,
            }

        # Observer effect: if target already measured recently, note uncertainty
        if intent.target and intent.target in self.belief_state:
            last = self.belief_state[intent.target].get("last_scan")
            if last and (time.time() - last) < 300:
                # Allow but flag uncertainty
                pass  # Policy handles the bounds; belief tracks the uncertainty

        return {"verdict": "approve", "reason": "Paradox checks passed"}

    def _is_bounded(self, command: str) -> bool:
        """Heuristic: does command have bounded execution?"""
        dangerous_unbounded = ["masscan", "while true", "for (;;)", "cat /dev/zero"]
        cmd_lower = command.lower()
        for pat in dangerous_unbounded:
            if pat in cmd_lower:
                return False
        return True

    def _detects_recursion(self, agent_id: str, command: str) -> bool:
        """Check if agent is calling itself in last N executions."""
        recent = [e for e in self.execution_log[-20:] if e["agent_id"] == agent_id]
        if len(recent) >= 3:
            # Simple check: same command repeated rapidly
            last_cmds = [e["command"] for e in recent[-3:]]
            if len(set(last_cmds)) == 1:
                return True
        return False

    def _log_execution(self, agent_id: str, command: str, token: ExecutionToken, result: SandboxResult, success: bool):
        entry = {
            "timestamp": time.time(),
            "agent_id": agent_id,
            "command": command,
            "token_id": token.token_id,
            "success": success,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "killed": result.killed,
            "kill_reason": result.kill_reason,
        }
        self.execution_log.append(entry)

    def _update_belief(self, agent_id: str, finding: Dict[str, Any]):
        target = finding.get("target")
        if target:
            if target not in self.belief_state:
                self.belief_state[target] = {"findings": [], "last_scan": time.time()}
            self.belief_state[target]["findings"].append({
                "agent_id": agent_id,
                "timestamp": time.time(),
                **finding,
            })
            self.belief_state[target]["last_scan"] = time.time()

    def _save_audit(self, path: str = "/home/popic/telegram-bot/logs/kernel_audit.jsonl"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            for entry in self.execution_log:
                f.write(json.dumps(entry) + "\n")

    def get_execution_log(self) -> list:
        return self.execution_log

    def get_belief_state(self) -> Dict[str, Any]:
        return self.belief_state


# CLI entrypoint
if __name__ == "__main__":
    kernel = ParadoxKernel()
    kernel.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        kernel.stop()




