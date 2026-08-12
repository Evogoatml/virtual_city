"""
BTC Recovery toolkit registry.

Discovers scripts under btc-python/ and btcrecover/, and runs the ones that
have safe CLI entrypoints. Hardcoded-path one-offs are listed as "manual"
so they show up in the city UI without being executed blindly.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
PY_DIR = ROOT / "btc-python"
BTCR_DIR = ROOT / "btcrecover"
BENCH_DIR = ROOT / "benchmark-lists"
ADDRDB_DIR = ROOT / "addressdb-checklists"
BACKEND = ROOT / ".backend"

# Tools the agent can safely invoke (relative to btc-python unless noted)
# kind: cli | manual | btcrecover
CATALOG: List[Dict[str, Any]] = [
    {
        "id": "bot_v2",
        "file": "btc_recovery_bot_v2.py",
        "kind": "cli",
        "desc": "Ingest folder/file, match, derive, scan chain, report, export",
        "examples": [
            "run bot_v2 --status",
            "run bot_v2 --ingest /path/to/wallets",
            "run bot_v2 --file /path/wallet.json --scan",
            "run bot_v2 --report",
        ],
    },
    {
        "id": "bot_v1",
        "file": "btc_recovery_bot.py",
        "kind": "cli",
        "desc": "Pipeline: wallet/csv/keys/seed/xpub → esplora scan",
        "examples": [
            "run bot_v1 --wallet /path/wallet",
            "run bot_v1 --keys /path/keys.txt --limit 50",
        ],
    },
    {
        "id": "key_finder",
        "file": "btc_key_finder.py",
        "kind": "cli",
        "desc": "Scan a directory for WIF/hex/BIP38 private keys",
        "examples": ["run key_finder /path/to/folder --output /tmp/keys.json"],
    },
    {
        "id": "scan_wallet_keys",
        "file": "scan_wallet_keys.py",
        "kind": "cli",
        "desc": "Scan files/dirs for HD wallet material (mnemonics, xprv)",
        "examples": ["run scan_wallet_keys /path --validate --json"],
    },
    {
        "id": "orchestrator",
        "file": "bitcoin_key_orchestrator.py",
        "kind": "manual",
        "desc": "Full hunter+balance checker (edit ROOT_FOLDERS inside script)",
        "examples": ["edit ROOT_FOLDERS then: run orchestrator"],
    },
    {
        "id": "wallet_hunter_v2",
        "file": "wallet_hunter_v2.py",
        "kind": "manual",
        "desc": "Folder hunter for WIF/hex/seeds (edit ROOT_FOLDER)",
    },
    {
        "id": "wallet_hunter",
        "file": "wallet_hunter.py",
        "kind": "manual",
        "desc": "Earlier wallet hunter variant",
    },
    {
        "id": "xtractpriv",
        "file": "xtractpriv.py",
        "kind": "cli",
        "desc": "Extract priv material from one file: xtractpriv <file>",
        "examples": ["run xtractpriv /path/to/dump.bin"],
    },
    {
        "id": "key_analyzer",
        "file": "key_analyzer.py",
        "kind": "cli",
        "desc": "Analyze key dump files",
        "examples": ["run key_analyzer /path/keys.txt"],
    },
    {
        "id": "check_address",
        "file": "check_address.py",
        "kind": "manual",
        "desc": "Match hard-coded xprvs to addresses (edit script)",
    },
    {
        "id": "check_key",
        "file": "check_key.py",
        "kind": "manual",
        "desc": "Derive address from one hex privkey (edit hex_priv)",
    },
    {
        "id": "derive",
        "file": "derive.py",
        "kind": "manual",
        "desc": "Hex privkey → P2PKH address helper",
    },
    {
        "id": "convert_keys",
        "file": "convert_keys.py",
        "kind": "manual",
        "desc": "Export Electrum keypairs to text (edit wallet path)",
    },
    {
        "id": "get_utxos",
        "file": "get_utxos.py",
        "kind": "manual",
        "desc": "List UTXOs from a wallet JSON (edit path)",
    },
    {
        "id": "check_utxo",
        "file": "check_utxo.py",
        "kind": "manual",
        "desc": "Find keys with current UTXO balance (edit wallet path)",
    },
    {
        "id": "sweep",
        "file": "sweep.py",
        "kind": "manual",
        "desc": "Build sweep txs — review carefully before broadcast",
    },
    {
        "id": "generate_sweep",
        "file": "generate_sweep.py",
        "kind": "manual",
        "desc": "Generate sweep transactions",
    },
    {
        "id": "export",
        "file": "export.py",
        "kind": "manual",
        "desc": "Export recovered material",
    },
    {
        "id": "decrypt",
        "file": "decrypt.py",
        "kind": "manual",
        "desc": "Decrypt wallet blobs",
    },
    {
        "id": "match_xprv",
        "file": "match_xprv.py",
        "kind": "manual",
        "desc": "Match xprv candidates to known addresses",
    },
    {
        "id": "match_xprv_v2",
        "file": "match_xprv_v2.py",
        "kind": "manual",
        "desc": "xprv matcher v2",
    },
    {
        "id": "match_xprv_v3",
        "file": "match_xprv_v3.py",
        "kind": "manual",
        "desc": "xprv matcher v3",
    },
    {
        "id": "parallel_scanner",
        "file": "parallel_scanner.py",
        "kind": "manual",
        "desc": "Parallel address/key scanner",
    },
    {
        "id": "interactive_key_scanner",
        "file": "interactive_key_scanner.py",
        "kind": "cli",
        "desc": "Interactive key scanner session",
    },
    {
        "id": "verify_integrity",
        "file": "verify_integrity.py",
        "kind": "cli",
        "desc": "Verify recovery artifact integrity",
    },
    {
        "id": "parse_torrent",
        "file": "parse_torrent.py",
        "kind": "cli",
        "desc": "Parse torrent metadata for wallet traces",
    },
    {
        "id": "btcrpass",
        "file": "btcrpass.py",
        "dir": "btcrecover",
        "kind": "btcrecover",
        "desc": "btcrecover password recovery library/CLI",
        "examples": ["run btcrpass --help"],
    },
    {
        "id": "btcrseed",
        "file": "btcrseed.py",
        "dir": "btcrecover",
        "kind": "btcrecover",
        "desc": "btcrecover seed recovery library/CLI",
        "examples": ["run btcrseed --help"],
    },
]


def _by_id() -> Dict[str, Dict[str, Any]]:
    return {t["id"]: t for t in CATALOG}


def list_tools(include_missing: bool = False) -> Dict[str, Any]:
    """Return catalog with on-disk status."""
    tools = []
    for t in CATALOG:
        base = BTCR_DIR if t.get("dir") == "btcrecover" else PY_DIR
        path = base / t["file"]
        exists = path.is_file()
        if not exists and not include_missing:
            # still show them
            pass
        tools.append({
            "id": t["id"],
            "file": t["file"],
            "kind": t["kind"],
            "desc": t["desc"],
            "exists": exists,
            "path": str(path) if exists else None,
            "examples": t.get("examples", []),
        })
    # also list uncatalogued py scripts
    known = {t["file"] for t in CATALOG}
    extra = []
    if PY_DIR.is_dir():
        for p in sorted(PY_DIR.glob("*.py")):
            if p.name not in known:
                extra.append(p.name)
    return {
        "root": str(ROOT),
        "btc_python": str(PY_DIR),
        "btcrecover": str(BTCR_DIR),
        "benchmark_lists": str(BENCH_DIR) if BENCH_DIR.is_dir() else None,
        "addressdb": str(ADDRDB_DIR) if ADDRDB_DIR.is_dir() else None,
        "backend": str(BACKEND) if BACKEND.is_dir() else None,
        "tools": tools,
        "uncatalogued_scripts": extra,
        "tool_count": len(tools),
        "cli_ready": sum(1 for t in tools if t["kind"] in ("cli", "btcrecover") and t["exists"]),
    }


def inventory() -> Dict[str, Any]:
    """Filesystem inventory of the recovery kit."""
    def count_files(d: Path, pattern: str = "*") -> int:
        if not d.is_dir():
            return 0
        return sum(1 for _ in d.rglob(pattern) if _.is_file())

    return {
        "btc_python_scripts": count_files(PY_DIR, "*.py"),
        "btcrecover_files": count_files(BTCR_DIR),
        "benchmark_lists": count_files(BENCH_DIR),
        "addressdb_checklists": count_files(ADDRDB_DIR),
        "backend_files": count_files(BACKEND) if BACKEND.is_dir() else 0,
        "total_bytes": sum(f.stat().st_size for f in ROOT.rglob("*") if f.is_file()),
        "catalog": list_tools(),
    }


def run_tool(
    tool_id: str,
    args: Optional[List[str]] = None,
    *,
    timeout: int = 120,
    agent: str = "btc_recovery",
) -> Dict[str, Any]:
    """
    Run a catalogued CLI tool. Manual tools refuse to run (edit first).
    Network-heavy tools go through api_budget.
    """
    args = args or []
    cat = _by_id().get(tool_id)
    if not cat:
        return {"error": f"unknown tool '{tool_id}'", "hint": "tools"}

    if cat["kind"] == "manual":
        return {
            "error": "manual tool — edit hardcoded paths in the script first",
            "file": cat["file"],
            "desc": cat["desc"],
            "path": str((BTCR_DIR if cat.get("dir") == "btcrecover" else PY_DIR) / cat["file"]),
            "examples": cat.get("examples", []),
        }

    base = BTCR_DIR if cat.get("dir") == "btcrecover" else PY_DIR
    script = base / cat["file"]
    if not script.is_file():
        return {"error": f"script missing: {script}"}

    # Budget: treat as external if scan-like args present
    costly = any(
        a in ("--scan", "--ingest") or a.startswith("http") or "/mnt/" in a
        for a in args
    )
    try:
        from city.api_budget import budget
        kind = "scrape" if costly else "local"
        if costly:
            ok, reason = budget.allow(agent, "scrape", key=f"btc_tool:{tool_id}:{' '.join(args)[:80]}", cost=1)
            if not ok:
                return {"error": reason, "denied": True, "budget": budget.snapshot(agent)}
    except Exception:
        budget = None  # type: ignore

    cmd = [sys.executable, str(script), *args]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in [str(base), str(ROOT), str(BTCR_DIR.parent), env.get("PYTHONPATH", "")] if p
    )

    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(base if cat.get("dir") != "btcrecover" else BTCR_DIR),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        out = (proc.stdout or "")[-8000:]
        err = (proc.stderr or "")[-4000:]
        result = {
            "ok": proc.returncode == 0,
            "tool": tool_id,
            "cmd": cmd,
            "returncode": proc.returncode,
            "seconds": round(time.time() - t0, 2),
            "stdout": out,
            "stderr": err,
        }
        if budget is not None and costly:
            budget.record(agent, "scrape", key=f"btc_tool:{tool_id}", ok=result["ok"], cache=True)
        return result
    except subprocess.TimeoutExpired:
        if budget is not None and costly:
            budget.record(agent, "scrape", key=f"btc_tool:{tool_id}", ok=False, cache=True)
        return {"error": f"timeout after {timeout}s", "tool": tool_id, "cmd": cmd}
    except Exception as exc:
        return {"error": str(exc), "tool": tool_id, "cmd": cmd}


def discover_uncatalogued() -> List[str]:
    info = list_tools(include_missing=True)
    return info.get("uncatalogued_scripts", [])
