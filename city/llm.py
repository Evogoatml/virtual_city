"""
city/llm.py — Provider-agnostic LLM client for the Virtual City Agent Runtime.

OpenAI-compatible: works with OpenRouter, xAI/Grok, Gemini, DeepSeek, Venice,
OpenAI, or a local Ollama/LLM gateway.

HOW IT PICKS A PROVIDER (auto-fallback, no manual key copying needed):
    1. If LLM_API_KEY is set, it wins (use LLM_BASE_URL / LLM_MODEL, or defaults).
    2. Otherwise it scans your other keys in this priority:
       OPENROUTER_API_KEY -> GEMINI_API_KEY -> DEEPSEEK_API_KEY ->
       VENICE_API_KEY -> OPENAI_API_KEY.
    For OpenRouter it live-queries the model list and picks a currently-free
    model, so it keeps working even when a free slug is retired.

All calls are routed through city.api_budget so autonomous loops never blow
rate limits or money on repeated/identical prompts.

Env (all optional — auto-fallback covers most cases):
    LLM_API_KEY      explicit override (highest priority)
    LLM_BASE_URL     default https://openrouter.ai/api/v1
    LLM_MODEL        default openai/gpt-4o-mini (ignored if auto-free picks)
    LLM_MOCK=1       offline echo mode (runtime runs read/default skills)
"""
from __future__ import annotations

import json
import os
import hashlib
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-4o-mini"

_lock = threading.Lock()
_client_cache: dict = {}
_free_model_cache: Optional[str] = None


def _openrouter_free_model() -> str:
    """Return a currently-free OpenRouter model id (live query, cached)."""
    global _free_model_cache
    if _free_model_cache:
        return _free_model_cache
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)
        free = {
            m["id"] for m in data.get("data", [])
            if str(m.get("pricing", {}).get("prompt", "1")) in ("0", "0.0", "0.00")
        }
        prefs = [
            "nvidia/nemotron-3-super-120b-a12b:free",
            "google/gemma-4-31b-it:free",
            "nvidia/nemotron-3-nano-30b-a3b:free",
            "meta-llama/llama-3.1-8b-instruct:free",
            "mistralai/mistral-7b-instruct:free",
        ]
        for p in prefs:
            if p in free:
                _free_model_cache = p
                return p
        for mid in free:
            if mid.endswith(":free"):
                _free_model_cache = mid
                return mid
    except Exception as exc:
        logger.warning("openrouter free-model discovery failed: %s", exc)
    return "nvidia/nemotron-3-super-120b-a12b:free"  # last-resort default


def _providers():
    """Ordered candidate (name, key, base_url, model) from available env keys."""
    cands = []
    if os.environ.get("LLM_API_KEY"):
        cands.append((
            "explicit", os.environ["LLM_API_KEY"],
            os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL),
            os.environ.get("LLM_MODEL", DEFAULT_MODEL),
        ))
    if os.environ.get("OPENROUTER_API_KEY"):
        cands.append(("openrouter", os.environ["OPENROUTER_API_KEY"],
                      "https://openrouter.ai/api/v1", _openrouter_free_model()))
    if os.environ.get("GEMINI_API_KEY"):
        cands.append(("gemini", os.environ["GEMINI_API_KEY"],
                      "https://generativelanguage.googleapis.com/v1beta/openai/",
                      os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")))
    if os.environ.get("DEEPSEEK_API_KEY"):
        cands.append(("deepseek", os.environ["DEEPSEEK_API_KEY"],
                      "https://api.deepseek.com/v1", "deepseek-chat"))
    if os.environ.get("VENICE_API_KEY"):
        cands.append(("venice", os.environ["VENICE_API_KEY"],
                      os.environ.get("VENICE_BASE_URL", "https://api.venice.ai/api/v1"),
                      os.environ.get("VENICE_MODEL", "zai-org-glm-5-2")))
    if os.environ.get("OPENAI_API_KEY"):
        cands.append(("openai", os.environ["OPENAI_API_KEY"],
                      "https://api.openai.com/v1", "gpt-4o-mini"))
    return cands


def _resolve():
    """Return the highest-priority available (name, key, base_url, model) or None."""
    cands = _providers()
    return cands[0] if cands else None


def enabled() -> bool:
    return bool(_resolve()) or os.environ.get("LLM_MOCK") == "1"


def _client():
    if os.environ.get("LLM_MOCK") == "1":
        return None
    cfg = _resolve()
    if not cfg:
        return None
    _, key, base, _model = cfg
    cache_key = (key, base)
    with _lock:
        if cache_key in _client_cache:
            return _client_cache[cache_key]
    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package missing; LLM disabled")
        return None
    client = OpenAI(api_key=key, base_url=base)
    with _lock:
        _client_cache[cache_key] = client
    return client


def _active_model() -> str:
    cfg = _resolve()
    return cfg[3] if cfg else DEFAULT_MODEL


def chat(
    messages: list[dict],
    model: Optional[str] = None,
    max_tokens: int = 512,
    temperature: float = 0.7,
    agent: str = "runtime",
    response_format: Optional[dict] = None,
) -> dict:
    """OpenAI-style chat completion, budget-gated. Never raises.

    Returns dict with keys: ok, content, model, usage, cached, denied,
    not_configured.
    """
    from city.api_budget import budget

    model_name = model or _active_model()
    last_user = ""
    for m in reversed(messages or []):
        if m.get("role") == "user":
            last_user = str(m.get("content", ""))[:400]
            break
    dig = hashlib.sha256(f"{model_name}|{last_user}".encode()).hexdigest()[:16]
    call_key = f"llm:{model_name}:{dig}"

    hit, cached = budget.get_cached(agent, "llm", call_key)
    if hit and isinstance(cached, dict):
        out = dict(cached)
        out["cached"] = True
        return out

    ok, reason = budget.allow(agent, "llm", key=call_key, cost=1)
    if not ok:
        return {"ok": False, "error": reason, "denied": True, "budget": budget.snapshot(agent)}

    client = _client()
    if client is None:
        return {
            "ok": False,
            "not_configured": True,
            "error": "No LLM provider configured (set LLM_API_KEY or a provider key)",
        }

    kwargs = dict(
        model=model_name,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if response_format:
        kwargs["response_format"] = response_format
    try:
        resp = client.chat.completions.create(**kwargs)
        out = {
            "ok": True,
            "content": resp.choices[0].message.content,
            "model": resp.model,
            "usage": resp.usage.__dict__ if resp.usage else {},
        }
        budget.record(agent, "llm", key=call_key, ok=True, result=out, cache=True)
        return out
    except Exception as exc:
        logger.error("LLM chat error: %s", exc)
        budget.record(agent, "llm", key=call_key, ok=False, cache=True)
        return {"ok": False, "error": str(exc)}


def json_chat(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    max_tokens: int = 1024,
    temperature: float = 0.3,
    agent: str = "runtime",
) -> dict:
    """Shorthand for a system+user turn expecting JSON. Parses `content` into `parsed`."""
    result = chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        agent=agent,
        response_format={"type": "json_object"},
    )
    if result.get("ok"):
        try:
            result["parsed"] = json.loads(result["content"])
        except json.JSONDecodeError:
            result["parsed"] = None
    return result
