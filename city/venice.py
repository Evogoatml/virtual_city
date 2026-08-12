"""
Venice AI LLM integration for Virtual City.

OpenAI-compatible.  Every building's supervisor() can call this.
"""
from __future__ import annotations

import json
import os
import logging
from typing import Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "zai-org-glm-5-2"


def get_client() -> "OpenAI":
    if OpenAI is None:
        raise ImportError("openai package not installed. Run: pip install openai")
    key = os.environ.get("VENICE_API_KEY")
    if not key:
        raise RuntimeError("VENICE_API_KEY not set in environment or .env")
    base = os.environ.get("VENICE_BASE_URL", "https://api.venice.ai/api/v1")
    return OpenAI(api_key=key, base_url=base)


def chat(
    messages: list[dict],
    model: Optional[str] = None,
    max_tokens: int = 512,
    temperature: float = 0.7,
    response_format: Optional[dict] = None,
) -> dict:
    """Send a chat completion request to Venice.

    Args:
        messages: OpenAI-style message list.
        model: Venice model name.  Default from env or zai-org-glm-5-2.
        max_tokens: Max output tokens.
        temperature: 0-2.  Lower = more deterministic.
        response_format: e.g. {"type": "json_object"} for structured output.

    Returns:
        The parsed response dict from Venice.
    """
    from city.api_budget import budget
    import hashlib
    model_name = model or os.environ.get("VENICE_MODEL", _DEFAULT_MODEL)
    # Stable key: model + last user message (avoid re-spending on identical prompts)
    last_user = ""
    for m in reversed(messages or []):
        if m.get("role") == "user":
            last_user = str(m.get("content", ""))[:400]
            break
    dig = hashlib.sha256(f"{model_name}|{last_user}".encode()).hexdigest()[:16]
    call_key = f"venice:{model_name}:{dig}"
    # Return cached identical LLM response when available
    hit, cached = budget.get_cached("venice", "llm", call_key)
    if hit and isinstance(cached, dict):
        out = dict(cached)
        out["cached"] = True
        return out

    ok, reason = budget.allow("venice", "llm", key=call_key, cost=1)
    if not ok:
        return {"ok": False, "error": reason, "budget": budget.snapshot("venice"), "denied": True}

    client = get_client()
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
        budget.record("venice", "llm", key=call_key, ok=True, result=out, cache=True)
        return out
    except Exception as exc:
        logger.error("Venice chat error: %s", exc)
        budget.record("venice", "llm", key=call_key, ok=False, cache=True)
        return {"ok": False, "error": str(exc)}


def json_chat(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> dict:
    """Shorthand: send a system + user message, expect JSON response."""
    result = chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    if result["ok"]:
        try:
            result["parsed"] = json.loads(result["content"])
        except json.JSONDecodeError:
            result["parsed"] = None
    return result