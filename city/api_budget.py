"""
Central API budget / call gate for Virtual City agents.

Goals:
- Stop useless/repeated external calls (health pings, identical scans, tick spam)
- Rate-limit per agent and globally
- Short-TTL dedupe/cache for identical request keys
- Allowlist kinds that count as "real" external work vs free local ops

Usage:
    from city.api_budget import budget

    ok, reason = budget.allow("web_check", "http", key="GET /api/headers?url=x")
    if not ok:
        return {"error": reason, "budget": budget.snapshot("web_check")}

    try:
        result = do_call()
        budget.record("web_check", "http", key=..., ok=True)
        return result
    except Exception:
        budget.record("web_check", "http", key=..., ok=False)
        raise

Env knobs (optional):
    CITY_API_MAX_PER_MIN=20
    CITY_API_MAX_PER_HOUR=200
    CITY_API_GLOBAL_PER_MIN=60
    CITY_API_DEDUP_SECONDS=90
    CITY_API_HEALTH_CACHE_SECONDS=45
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Optional, Tuple


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# Kinds that never count against budget (local-only)
FREE_KINDS = frozenset({
    "local", "db", "log", "status_cached", "ui",
})

# Kinds that are external / expensive
COSTLY_KINDS = frozenset({
    "http", "https", "llm", "venice", "exchange", "scrape",
    "webcheck", "signal", "ws", "external",
})


@dataclass
class CallRecord:
    ts: float
    agent: str
    kind: str
    key: str
    ok: bool
    cost: int = 1


class ApiBudget:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.max_per_min = _env_int("CITY_API_MAX_PER_MIN", 20)
        self.max_per_hour = _env_int("CITY_API_MAX_PER_HOUR", 200)
        self.global_per_min = _env_int("CITY_API_GLOBAL_PER_MIN", 60)
        self.dedup_seconds = _env_int("CITY_API_DEDUP_SECONDS", 90)
        self.health_cache_seconds = _env_int("CITY_API_HEALTH_CACHE_SECONDS", 45)

        # agent -> deque of timestamps (costly calls only)
        self._agent_calls: Dict[str, Deque[float]] = defaultdict(deque)
        self._global_calls: Deque[float] = deque()
        # key -> (expires_at, result_payload or True for pure dedupe)
        self._dedupe: Dict[str, Tuple[float, Any]] = {}
        # health cache: name -> (expires_at, value)
        self._health: Dict[str, Tuple[float, Any]] = {}
        # recent history for UI/debug
        self._history: Deque[CallRecord] = deque(maxlen=200)
        self._denied: Deque[Dict[str, Any]] = deque(maxlen=100)
        # blocked agents (manual or auto)
        self._paused: Dict[str, float] = {}  # agent -> until_ts
        self._enabled = os.environ.get("CITY_API_BUDGET", "1") not in ("0", "false", "off")

    # ── public API ─────────────────────────────────────────────

    def allow(
        self,
        agent: str,
        kind: str = "external",
        key: str = "",
        cost: int = 1,
        *,
        force: bool = False,
    ) -> Tuple[bool, str]:
        """Return (allowed, reason). Free kinds always allowed."""
        if not self._enabled or force or kind in FREE_KINDS:
            return True, "ok"

        now = time.time()
        agent = agent or "unknown"
        key = key or f"{kind}:anon"
        dkey = f"{agent}|{kind}|{key}"

        with self._lock:
            # Manual pause
            until = self._paused.get(agent, 0)
            if until > now:
                reason = f"agent '{agent}' paused for API calls ({int(until - now)}s left)"
                self._denied.append({"ts": now, "agent": agent, "kind": kind, "key": key, "reason": reason})
                return False, reason

            # Dedupe: identical in-flight/recent call
            hit = self._dedupe.get(dkey)
            if hit and hit[0] > now:
                reason = f"deduped identical call (retry in {int(hit[0] - now)}s): {key[:80]}"
                self._denied.append({"ts": now, "agent": agent, "kind": kind, "key": key, "reason": reason})
                return False, reason

            # Prune windows
            self._prune(agent, now)

            # Per-agent minute
            if len(self._agent_calls[agent]) + cost > self.max_per_min:
                reason = f"rate limit: {agent} exceeded {self.max_per_min}/min external API calls"
                self._denied.append({"ts": now, "agent": agent, "kind": kind, "key": key, "reason": reason})
                return False, reason

            # Per-agent hour
            hour_count = sum(1 for t in self._agent_calls[agent] if now - t < 3600)
            if hour_count + cost > self.max_per_hour:
                reason = f"rate limit: {agent} exceeded {self.max_per_hour}/hour external API calls"
                self._denied.append({"ts": now, "agent": agent, "kind": kind, "key": key, "reason": reason})
                return False, reason

            # Global minute
            if len(self._global_calls) + cost > self.global_per_min:
                reason = f"global rate limit: city exceeded {self.global_per_min}/min external API calls"
                self._denied.append({"ts": now, "agent": agent, "kind": kind, "key": key, "reason": reason})
                return False, reason

            return True, "ok"

    def record(
        self,
        agent: str,
        kind: str = "external",
        key: str = "",
        ok: bool = True,
        cost: int = 1,
        *,
        result: Any = None,
        cache: bool = True,
    ) -> None:
        """Record a completed external call (and optionally cache for dedupe)."""
        if not self._enabled or kind in FREE_KINDS:
            return
        now = time.time()
        agent = agent or "unknown"
        key = key or f"{kind}:anon"
        dkey = f"{agent}|{kind}|{key}"

        with self._lock:
            for _ in range(max(1, cost)):
                self._agent_calls[agent].append(now)
                self._global_calls.append(now)
            self._history.append(CallRecord(now, agent, kind, key, ok, cost))
            if cache:
                # Successful identical calls: block repeats for dedup window
                # Failed calls: shorter backoff (1/3)
                ttl = self.dedup_seconds if ok else max(15, self.dedup_seconds // 3)
                self._dedupe[dkey] = (now + ttl, result if ok else None)
            self._prune(agent, now)

    def get_cached(self, agent: str, kind: str, key: str) -> Tuple[bool, Any]:
        """Return (hit, value) if a successful result was cached under this key."""
        dkey = f"{agent}|{kind}|{key}"
        with self._lock:
            hit = self._dedupe.get(dkey)
            if not hit:
                return False, None
            exp, val = hit
            if exp < time.time() or val is None:
                return False, None
            return True, val

    def health_get(self, name: str) -> Tuple[bool, Any]:
        with self._lock:
            hit = self._health.get(name)
            if not hit:
                return False, None
            exp, val = hit
            if exp < time.time():
                return False, None
            return True, val

    def health_set(self, name: str, value: Any, ttl: Optional[int] = None) -> None:
        ttl = self.health_cache_seconds if ttl is None else ttl
        with self._lock:
            self._health[name] = (time.time() + ttl, value)

    def pause(self, agent: str, seconds: int = 300) -> None:
        with self._lock:
            self._paused[agent] = time.time() + max(1, seconds)

    def resume(self, agent: str) -> None:
        with self._lock:
            self._paused.pop(agent, None)

    def snapshot(self, agent: Optional[str] = None) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            if agent:
                self._prune(agent, now)
                amin = len(self._agent_calls.get(agent, ()))
                ahour = sum(1 for t in self._agent_calls.get(agent, ()) if now - t < 3600)
                return {
                    "enabled": self._enabled,
                    "agent": agent,
                    "calls_last_min": amin,
                    "calls_last_hour": ahour,
                    "max_per_min": self.max_per_min,
                    "max_per_hour": self.max_per_hour,
                    "paused_for": max(0, int(self._paused.get(agent, 0) - now)),
                    "dedup_seconds": self.dedup_seconds,
                }
            self._prune_global(now)
            by_agent = {
                a: len(q) for a, q in self._agent_calls.items() if q
            }
            return {
                "enabled": self._enabled,
                "global_last_min": len(self._global_calls),
                "global_max_per_min": self.global_per_min,
                "per_agent_max_per_min": self.max_per_min,
                "per_agent_max_per_hour": self.max_per_hour,
                "by_agent_last_min": by_agent,
                "recent_denied": list(self._denied)[-20:],
                "recent_calls": [
                    {
                        "ts": r.ts,
                        "agent": r.agent,
                        "kind": r.kind,
                        "key": r.key[:100],
                        "ok": r.ok,
                    }
                    for r in list(self._history)[-20:]
                ],
                "paused": {a: max(0, int(u - now)) for a, u in self._paused.items() if u > now},
            }

    # ── internals ──────────────────────────────────────────────

    def _prune(self, agent: str, now: float) -> None:
        q = self._agent_calls[agent]
        while q and now - q[0] > 3600:
            q.popleft()
        self._prune_global(now)
        # expire dedupe
        dead = [k for k, (exp, _) in self._dedupe.items() if exp < now]
        for k in dead:
            del self._dedupe[k]

    def _prune_global(self, now: float) -> None:
        while self._global_calls and now - self._global_calls[0] > 60:
            self._global_calls.popleft()


# Process-wide singleton
budget = ApiBudget()


def guarded_call(
    agent: str,
    kind: str,
    key: str,
    fn,
    *,
    cost: int = 1,
    cache_result: bool = False,
):
    """
    Run fn() only if budget allows. Returns:
      {"ok": True, "data": ...} or {"ok": False, "error": ..., "budget": ...}
    If cache_result and a prior success exists for key, returns cached data.
    """
    if cache_result:
        hit, val = budget.get_cached(agent, kind, key)
        if hit:
            return {"ok": True, "data": val, "cached": True}

    ok, reason = budget.allow(agent, kind, key=key, cost=cost)
    if not ok:
        return {"ok": False, "error": reason, "budget": budget.snapshot(agent), "denied": True}

    try:
        data = fn()
        budget.record(agent, kind, key=key, ok=True, cost=cost, result=data if cache_result else None, cache=True)
        return {"ok": True, "data": data, "cached": False}
    except Exception as exc:
        budget.record(agent, kind, key=key, ok=False, cost=cost, cache=True)
        return {"ok": False, "error": str(exc)}
