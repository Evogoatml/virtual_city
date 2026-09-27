#!/usr/bin/env python3
"""
Policy Engine & Execution Tokens
Enforces bounds before any agent code runs.
NOW IN PERMISSIVE MODE: audits everything, blocks only truly dangerous commands.
"""

import uuid
import time
import re
import ipaddress
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum


class Verdict(Enum):
    APPROVE = "approve"
    DENY = "deny"
    MODIFY = "modify"
    ESCALATE = "escalate"


@dataclass
class ExecutionToken:
    """Revocable, bounded permission to execute."""
    token_id: str = field(default_factory=lambda: str(uuid.uuid4())[:16])
    agent_id: str = ""
    task_hash: str = ""
    issued_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    max_runtime: int = 60
    max_memory_mb: int = 512
    network: bool = False
    allowed_paths: List[str] = field(default_factory=list)
    allowed_tools: List[str] = field(default_factory=list)
    revoked: bool = False
    warnings: List[str] = field(default_factory=list)

    def is_valid(self) -> bool:
        if self.revoked:
            return False
        return time.time() < self.expires_at

    def revoke(self):
        self.revoked = True


@dataclass
class TaskIntent:
    """Parsed intent from an agent request."""
    agent_id: str
    raw_command: str
    target: Optional[str]
    tool: Optional[str]
    intent_type: str = "unknown"


class PolicyEngine:
    """
    PERMISSIVE MODE: allows all pentest operations.
    Blocks only system-destruction commands.
    Everything is logged for audit.
    """

    NETWORK_TOOLS = {
        "nmap", "nikto", "gobuster", "dirb", "ffuf", "whatweb", "sqlmap",
        "curl", "wget", "nc", "netcat", "masscan", "zmap", "theharvester",
        "dig", "nslookup", "host", "whois", "amass", "subfinder"
    }

    # Only block commands that destroy the host OS itself
    DESTRUCTION_PATTERNS = [
        r";\s*rm\s+-rf\s+/\s*($|&|;)",
        r">\s*/dev/sda",
        r"mkfs\.ext4\s+/dev/sda",
        r"dd\s+if=/dev/zero\s+of=/dev/sda",
        r"shutdown\s+-h\s+now",
        r"reboot\s+-f",
    ]

    def __init__(self, paradox_kernel=None):
        self.paradox = paradox_kernel
        self.audit_log: List[Dict[str, Any]] = []
        self.agent_rates: Dict[str, List[float]] = {}
        self.max_requests_per_minute = 30  # generous

    def evaluate(self, intent: TaskIntent) -> Dict[str, Any]:
        """Full policy evaluation. Permissive: warns instead of denying."""
        agent_id = intent.agent_id
        cmd = intent.raw_command
        warnings = []

        # 1. Rate limiting
        if self._rate_exceeded(agent_id):
            return self._deny("Rate limit exceeded")

        # 2. Destruction pattern scan (the ONLY hard block)
        dangerous = self._scan_destruction(cmd)
        if dangerous:
            return self._deny(f"Host destruction blocked: {dangerous}")

        # 3. Tool extraction
        tool = self._extract_tool(cmd)

        # 4. Paradox kernel check (informational)
        if self.paradox:
            paradox_result = self._paradox_check(intent)
            if paradox_result.get("verdict") == "deny":
                warnings.append(f"Paradox: {paradox_result.get('reason')}")

        # 5. Bounds determination
        bounds = self._determine_bounds(cmd, tool)

        # 6. Issue token with warnings attached
        token = ExecutionToken(
            agent_id=agent_id,
            task_hash=self._hash_cmd(cmd),
            expires_at=time.time() + bounds["timeout"],
            max_runtime=bounds["timeout"],
            max_memory_mb=bounds["memory"],
            network=bounds["network"],
            allowed_paths=bounds.get("paths", ["/tmp/bot-scans"]),
            allowed_tools=[tool] if tool else [],
            warnings=warnings,
        )

        self._log_audit(agent_id, cmd, Verdict.APPROVE, token.token_id, warnings=warnings)

        return {
            "verdict": Verdict.APPROVE,
            "token": token,
            "reason": "Approved",
            "bounds": bounds,
            "warnings": warnings,
        }

    def revoke_token(self, token: ExecutionToken):
        token.revoke()

    def _deny(self, reason: str) -> Dict[str, Any]:
        self._log_audit("", "", Verdict.DENY, "", reason=reason)
        return {"verdict": Verdict.DENY, "token": None, "reason": reason}

    def _rate_exceeded(self, agent_id: str) -> bool:
        now = time.time()
        window = [t for t in self.agent_rates.get(agent_id, []) if now - t < 60]
        self.agent_rates[agent_id] = window
        if len(window) >= self.max_requests_per_minute:
            return True
        window.append(now)
        return False

    def _scan_destruction(self, cmd: str) -> Optional[str]:
        for pattern in self.DESTRUCTION_PATTERNS:
            if re.search(pattern, cmd, re.IGNORECASE):
                return pattern
        return None

    def _extract_tool(self, cmd: str) -> Optional[str]:
        parts = cmd.strip().split()
        if parts:
            return parts[0].lower()
        return None

    def _paradox_check(self, intent: TaskIntent) -> Dict[str, Any]:
        if hasattr(self.paradox, "arbitrate"):
            return self.paradox.arbitrate(intent)
        return {"verdict": "approve"}

    def _determine_bounds(self, cmd: str, tool: Optional[str]) -> Dict[str, Any]:
        bounds = {
            "timeout": 60,
            "memory": 512,
            "network": False,
            "paths": ["/tmp/bot-scans"],
        }
        if tool in self.NETWORK_TOOLS:
            bounds["network"] = True
        if tool in {"nmap", "nikto", "dirb", "gobuster"}:
            bounds["timeout"] = 120
        if "masscan" in cmd or "zmap" in cmd:
            bounds["timeout"] = 300
        if "hydra" in cmd or "john" in cmd:
            bounds["timeout"] = 600
        return bounds

    def _hash_cmd(self, cmd: str) -> str:
        import hashlib
        return hashlib.sha256(cmd.encode()).hexdigest()[:16]

    def _log_audit(self, agent_id: str, cmd: str, verdict: Verdict, token_id: str, reason: str = "", warnings: list = None):
        self.audit_log.append({
            "timestamp": time.time(),
            "agent_id": agent_id,
            "command": cmd,
            "verdict": verdict.value,
            "token_id": token_id,
            "reason": reason,
            "warnings": warnings or [],
        })

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return self.audit_log

    def save_audit(self, path: str = "/home/popic/telegram-bot/logs/audit.jsonl"):
        import os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            for entry in self.audit_log:
                f.write(__import__("json").dumps(entry) + "\n")

