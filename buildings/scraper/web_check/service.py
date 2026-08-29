"""
Manage the local Lissy93 web-check Node process for Virtual City.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CITY_ROOT = Path(__file__).resolve().parents[2]
# Prefer env override, then city symlink/folder, then home clone
_env = os.environ.get("WEBCHECK_ROOT")
if _env:
    WEBCHECK_ROOT = Path(_env).expanduser().resolve()
elif (CITY_ROOT / "web-check").exists():
    WEBCHECK_ROOT = (CITY_ROOT / "web-check").resolve()
else:
    WEBCHECK_ROOT = (Path.home() / "web-check").resolve()
PID_FILE = CITY_ROOT / "data" / "webcheck.pid"
LOG_FILE = CITY_ROOT / "data" / "webcheck.log"
DEFAULT_PORT = int(os.environ.get("WEBCHECK_PORT", "3000"))
DEFAULT_HOST = os.environ.get("WEBCHECK_HOST", "127.0.0.1")


def base_url(port: int = DEFAULT_PORT) -> str:
    return f"http://{DEFAULT_HOST}:{port}"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def read_pid() -> Optional[int]:
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text().strip())
    except ValueError:
        return None
    if _pid_alive(pid):
        return pid
    try:
        PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass
    return None


def is_up(port: int = DEFAULT_PORT, timeout: float = 2.0) -> bool:
    """Cached health check — avoids hammering :3000 every UI/monitor tick."""
    try:
        from city.api_budget import budget
        hit, val = budget.health_get(f"webcheck_up:{port}")
        if hit:
            return bool(val)
    except Exception:
        budget = None  # type: ignore

    alive = False
    try:
        req = Request(base_url(port) + "/api", method="GET")
        with urlopen(req, timeout=timeout) as resp:
            alive = 200 <= resp.status < 500
    except Exception:
        try:
            req = Request(base_url(port) + "/", method="GET")
            with urlopen(req, timeout=timeout) as resp:
                alive = 200 <= resp.status < 500
        except Exception:
            alive = False

    try:
        from city.api_budget import budget as b2
        b2.health_set(f"webcheck_up:{port}", alive)
    except Exception:
        pass
    return alive


def status(port: int = DEFAULT_PORT) -> Dict[str, Any]:
    pid = read_pid()
    up = is_up(port)
    return {
        "running": up,
        "pid": pid,
        "port": port,
        "url": base_url(port),
        "room_url": "/room/webcheck/",
        "root": str(WEBCHECK_ROOT),
        "log": str(LOG_FILE),
        "installed": (WEBCHECK_ROOT / "node_modules").is_dir(),
        "built": (WEBCHECK_ROOT / "dist" / "client").is_dir()
        or (WEBCHECK_ROOT / "dist").is_dir(),
    }


def ensure_installed() -> Dict[str, Any]:
    if not WEBCHECK_ROOT.is_dir():
        return {"ok": False, "error": f"web-check not found at {WEBCHECK_ROOT}"}
    if (WEBCHECK_ROOT / "node_modules").is_dir():
        return {"ok": True, "already": True}
    env = os.environ.copy()
    hermes_node = Path.home() / ".hermes" / "node" / "bin"
    if hermes_node.is_dir():
        env["PATH"] = f"{hermes_node}:{env.get('PATH', '')}"
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "ab") as log:
        log.write(b"\n--- yarn install ---\n")
        proc = subprocess.run(
            ["yarn", "install", "--network-timeout", "120000"],
            cwd=str(WEBCHECK_ROOT),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=600,
        )
    if proc.returncode != 0:
        return {"ok": False, "error": "yarn install failed", "log": str(LOG_FILE)}
    return {"ok": True, "installed": True}


def start(port: int = DEFAULT_PORT) -> Dict[str, Any]:
    if is_up(port):
        return {"ok": True, "already_running": True, **status(port)}

    pid = read_pid()
    if pid:
        return {"ok": True, "already_running": True, "pid": pid, **status(port)}

    inst = ensure_installed()
    if not inst.get("ok"):
        return inst

    env = os.environ.copy()
    hermes_node = Path.home() / ".hermes" / "node" / "bin"
    if hermes_node.is_dir():
        env["PATH"] = f"{hermes_node}:{env.get('PATH', '')}"
    env["PORT"] = str(port)
    env["WC_SERVER"] = "true"
    env["API_CORS_ORIGIN"] = "*"
    # city room runs behind flask proxy
    env.setdefault("SITE_URL", f"http://127.0.0.1:{port}")

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_f = open(LOG_FILE, "ab")
    log_f.write(b"\n--- start ---\n")
    log_f.flush()

    # Prefer API-only if GUI not built (faster); full server if dist exists
    cmd = ["node", "server.js"]
    proc = subprocess.Popen(
        cmd,
        cwd=str(WEBCHECK_ROOT),
        env=env,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    PID_FILE.write_text(str(proc.pid))

    # wait for boot
    for _ in range(30):
        if is_up(port):
            return {"ok": True, "started": True, **status(port)}
        if proc.poll() is not None:
            return {
                "ok": False,
                "error": "web-check exited early",
                "returncode": proc.returncode,
                "log": str(LOG_FILE),
            }
        time.sleep(0.5)

    return {
        "ok": False,
        "error": "web-check did not become ready in time",
        "pid": proc.pid,
        "log": str(LOG_FILE),
        **status(port),
    }


def stop() -> Dict[str, Any]:
    pid = read_pid()
    if not pid:
        # best-effort: nothing tracked
        return {"ok": True, "stopped": False, "reason": "no pid file"}
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        PID_FILE.unlink(missing_ok=True)
        return {"ok": True, "stopped": True, "already_dead": True}
    # wait
    for _ in range(20):
        if not _pid_alive(pid):
            break
        time.sleep(0.2)
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    PID_FILE.unlink(missing_ok=True)
    return {"ok": True, "stopped": True, "pid": pid}


def call_api(path: str, port: int = DEFAULT_PORT, timeout: float = 45.0,
             agent: str = "web_check") -> Dict[str, Any]:
    """GET a web-check API path like /api/headers?url=https://example.com

    Rate-limited + short-TTL deduped via city.api_budget.
    """
    if not path.startswith("/"):
        path = "/" + path
    url = base_url(port) + path
    call_key = path.split("?")[0] + "?" + ("url=" + path.split("url=")[-1][:120] if "url=" in path else path[:80])

    try:
        from city.api_budget import budget
        hit, cached = budget.get_cached(agent, "webcheck", call_key)
        if hit and isinstance(cached, dict):
            out = dict(cached)
            out["cached"] = True
            return out
        ok, reason = budget.allow(agent, "webcheck", key=call_key, cost=1)
        if not ok:
            return {"ok": False, "error": reason, "budget": budget.snapshot(agent), "denied": True, "url": url}
    except Exception:
        budget = None  # type: ignore

    try:
        req = Request(url, headers={"Accept": "application/json", "User-Agent": "VirtualCity-WebCheck/1.0"})
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            try:
                data = json.loads(body.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                data = {"raw": body.decode("utf-8", errors="replace")[:4000]}
            out = {"ok": True, "status": resp.status, "data": data, "url": url}
            if budget is not None:
                budget.record(agent, "webcheck", key=call_key, ok=True, result=out, cache=True)
            return out
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:2000]
        out = {"ok": False, "status": e.code, "error": body, "url": url}
        if budget is not None:
            budget.record(agent, "webcheck", key=call_key, ok=False, cache=True)
        return out
    except URLError as e:
        out = {"ok": False, "error": str(e.reason), "url": url, "hint": "start webcheck first"}
        if budget is not None:
            budget.record(agent, "webcheck", key=call_key, ok=False, cache=True)
        return out
    except Exception as e:
        out = {"ok": False, "error": str(e), "url": url}
        if budget is not None:
            budget.record(agent, "webcheck", key=call_key, ok=False, cache=True)
        return out


# Useful first-pass endpoints (fast enough for room dashboard)
QUICK_CHECKS = ("get-ip", "headers", "ssl", "dns", "status", "robots-txt", "security-txt", "tech-stack")
