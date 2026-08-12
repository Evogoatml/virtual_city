"""
BTC Recovery Building — one mission: find every satoshi across every
recovery artifact on the USB and report confirmed balances to the city.

Pure recovery. No trading, no paper positions, no exchange connections.
"""
from city.department import Department
from city.db import now_iso, log_event
from .store import WalletStore
from .monitor import MempoolMonitor
from . import import_electrum, import_keys
from . import toolkit


class BTCRecoveryAgent(Department):
    name = "btc_recovery"
    subject = "Bitcoin Recovery"
    district = "Financial District"
    color = "#f7931a"

    def __init__(self, conn):
        self._store = None
        self._monitor = None
        super().__init__(conn)

    def setup_schema(self):
        self._store = WalletStore(self.conn)
        self._store.install_schema()

    def register_rules(self):
        self.rule(r"^import\s+wallet\s+(?P<path>.+)$")(self._import_wallet)
        self.rule(r"^import\s+keys\s+(?P<path>.+)$")(self._import_keys)
        self.rule(r"^import\s+all\s+(?P<path>.+)$")(self._import_all)
        self.rule(r"^balance$")(self._balance)
        self.rule(r"^utxos$")(self._utxos)
        self.rule(r"^keys$")(self._keys)
        self.rule(r"^address\s+(?P<addr>[13bc][a-km-zA-HJ-NP-Z0-9]{25,62})$")(self._address)
        self.rule(r"^sweeps$")(self._sweeps)
        self.rule(r"^scan$")(self._scan)
        self.rule(r"^stats$")(self._stats)
        self.rule(r"^status$")(self._status)
        # New recovery kit commands
        self.rule(r"^tools$")(self._tools)
        self.rule(r"^inventory$")(self._inventory)
        self.rule(r"^help$")(self._help)
        self.rule(r"^run\s+(?P<tool>\w+)(?:\s+(?P<args>.+))?$")(self._run_tool)
        self.rule(r"^hunt\s+(?P<path>.+)$")(self._hunt)
        self.rule(r"^ingest\s+(?P<path>.+)$")(self._ingest)
        self.rule(r"^bot\s+status$")(self._bot_status)
        self.rule(r"^bot\s+report$")(self._bot_report)

    def _get_store(self):
        if self._store is None:
            self._store = WalletStore(self.conn)
        return self._store

    def _get_monitor(self):
        if self._monitor is None:
            s = self._get_store()
            self._monitor = MempoolMonitor(s, on_new_utxo=self._on_utxo, on_balance=self._on_balance)
        return self._monitor

    def _on_utxo(self, count):
        log_event(self.conn, self.name, "new_utxo", f"{count} new UTXO(s) on-chain", {"count": count})
#         from city.mosaic.swarm import MOSAIC
#         MOSAIC.tick()
# 
#     def _on_balance(self, sat):
#         log_event(self.conn, self.name, "balance_change", f"Balance now ₿{sat/1e8:.8f}", {"sat": sat})
#         from city.mosaic.swarm import MOSAIC
#         MOSAIC.tick()

    # -- Commands --

    def _import_wallet(self, path):
        r = import_electrum.import_electrum(self._get_store(), path)
        if "error" in r:
            return r
        log_event(self.conn, self.name, "wallet_imported",
                  f"Imported {r['wallet']}: {r['addresses_added']} addr, {r['keypairs_added']} keys", r)
        self._get_monitor().start()
        return r

    def _import_keys(self, path):
        r = import_keys.import_keys_file(self._get_store(), path)
        if "error" in r:
            return r
        log_event(self.conn, self.name, "keys_imported",
                  f"Imported {r['keypairs_added']} keys from {r['file']}", r)
        return r

    def _import_all(self, path):
        from pathlib import Path
        base = Path(path)
        if not base.exists():
            return {"error": f"folder not found: {path}"}
        results = {"wallets": 0, "key_files": 0, "seeds": 0, "errors": []}
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            try:
                sz = p.stat().st_size
                if sz > 5_000_000 or sz < 10:
                    continue
                r = import_keys.detect_and_import(self._get_store(), str(p))
                if "error" not in r:
                    if "wallet" in r:
                        results["wallets"] += 1
                    elif "seed_imported" in r:
                        results["seeds"] += 1
                    elif r.get("wif_found", 0) > 0 or r.get("hex_found", 0) > 0:
                        results["key_files"] += 1
            except Exception as exc:
                results["errors"].append(f"{p.name}: {exc}")
        log_event(self.conn, self.name, "full_import", f"Imported all from {path}", results)
        self._get_monitor().start()
        return results

    def _balance(self):
        return self._get_store().wallet_summary()

    def _utxos(self):
        store = self._get_store()
        rows = store.conn.execute(
            "SELECT * FROM btc_utxos WHERE spent_at IS NULL ORDER BY value_sat DESC LIMIT 100"
        ).fetchall()
        return {"count": len(rows), "utxos": [dict(r) for r in rows]}

    def _keys(self):
        store = self._get_store()
        total = store.conn.execute("SELECT COUNT(*) AS c FROM btc_private_keys").fetchone()["c"]
        by_source = store.conn.execute(
            "SELECT source_file, COUNT(*) AS c FROM btc_private_keys GROUP BY source_file"
        ).fetchall()
        return {"total_keys": total, "by_source": [dict(r) for r in by_source]}

    def _address(self, addr):
        store = self._get_store()
        row = store.conn.execute(
            "SELECT * FROM btc_addresses WHERE address = ?", (addr,)
        ).fetchone()
        if not row:
            return {"error": f"address {addr} not in recovery database"}
        info = dict(row)
        utxos = store.conn.execute(
            "SELECT * FROM btc_utxos WHERE address = ? AND spent_at IS NULL", (addr,)
        ).fetchall()
        info["utxos"] = [dict(r) for r in utxos]
        info["balance_sat"] = sum(u["value_sat"] for u in utxos)
        key = store.conn.execute(
            "SELECT * FROM btc_private_keys WHERE address = ?", (addr,)
        ).fetchone()
        info["has_private_key"] = key is not None
        return info

    def _sweeps(self):
        store = self._get_store()
        rows = store.conn.execute(
            "SELECT * FROM btc_sweep_state WHERE sweep_status = 'pending'"
        ).fetchall()
        return {"pending_sweeps": [dict(r) for r in rows], "count": len(rows)}

    def _scan(self):
        self._get_monitor().start()
        return {"action": "chain monitor started"}

    def _stats(self):
        return self._get_store().wallet_summary()

    def _status(self):
        return self.report()

    # -- Recovery kit (btc-python / btcrecover) --

    def _help(self):
        return {
            "commands": [
                "import wallet <path>", "import keys <path>", "import all <folder>",
                "balance", "utxos", "keys", "address <addr>", "sweeps", "scan", "stats", "status",
                "tools", "inventory",
                "run <tool_id> [args...]",
                "hunt <folder>", "ingest <folder>",
                "bot status", "bot report",
            ],
            "note": "Many scripts under btc-python/ are listed by 'tools'. CLI-ready ones run via 'run'.",
        }

    def _tools(self):
        info = toolkit.list_tools()
        cli = [t for t in info["tools"] if t["kind"] in ("cli", "btcrecover") and t["exists"]]
        manual = [t for t in info["tools"] if t["kind"] == "manual" and t["exists"]]
        return {
            "cli_ready": [{"id": t["id"], "desc": t["desc"], "examples": t["examples"]} for t in cli],
            "manual_edit_first": [{"id": t["id"], "desc": t["desc"], "path": t["path"]} for t in manual],
            "uncatalogued": info.get("uncatalogued_scripts", []),
            "counts": {
                "cli": len(cli),
                "manual": len(manual),
                "uncatalogued": len(info.get("uncatalogued_scripts", [])),
            },
            "roots": {
                "btc_python": info["btc_python"],
                "btcrecover": info["btcrecover"],
            },
        }

    def _inventory(self):
        inv = toolkit.inventory()
        inv["total_mb"] = round(inv["total_bytes"] / (1024 * 1024), 1)
        # don't dump full nested catalog twice
        cat = inv.pop("catalog", {})
        inv["cli_ready"] = cat.get("cli_ready")
        inv["tool_count"] = cat.get("tool_count")
        inv["uncatalogued"] = cat.get("uncatalogued_scripts", [])
        return inv

    def _run_tool(self, tool, args=""):
        import shlex
        arg_list = shlex.split(args) if args else []
        # special: xtractpriv takes a single path as positional
        result = toolkit.run_tool(tool, arg_list, timeout=180, agent=self.name)
        if result.get("ok") or "error" not in result:
            log_event(self.conn, self.name, "tool_run", f"ran {tool}", {
                "tool": tool, "args": arg_list, "returncode": result.get("returncode"),
            })
        return result

    def _hunt(self, path):
        """Scan a folder for private keys using btc_key_finder."""
        path = path.strip()
        return toolkit.run_tool(
            "key_finder",
            [path, "--output", str(toolkit.ROOT / "data_hunt_results.json")],
            timeout=300,
            agent=self.name,
        )

    def _ingest(self, path):
        """Ingest all recovery artifacts via bot v2."""
        path = path.strip()
        return toolkit.run_tool("bot_v2", ["--ingest", path], timeout=300, agent=self.name)

    def _bot_status(self):
        return toolkit.run_tool("bot_v2", ["--status"], timeout=60, agent=self.name)

    def _bot_report(self):
        return toolkit.run_tool("bot_v2", ["--report"], timeout=120, agent=self.name)


    def work(self):
        store = WalletStore(self.conn)
        bal = store.total_balance()
        utxos = store.count_utxos()
        if bal > 0:
            self.log("tick", f"₿{bal/1e8:.4f} over {utxos} UTXO(s)")
        else:
            cnt = store.wallet_summary()["addresses"]
            self.log("tick", f"{cnt} addresses loaded, no balance yet")

    def report(self):
        s = WalletStore(self.conn).wallet_summary()
        try:
            inv = toolkit.inventory()
            kit = {
                "scripts": inv.get("btc_python_scripts", 0),
                "btcrecover_files": inv.get("btcrecover_files", 0),
                "total_mb": round(inv.get("total_bytes", 0) / (1024 * 1024), 1),
                "cli_tools": inv.get("catalog", {}).get("cli_ready", 0),
            }
        except Exception:
            kit = {}
        return {
            "department": self.name,
            "subject": self.subject,
            "addresses": s["addresses"],
            "keys": s["private_keys"],
            "utxos": s["utxos"],
            "btc_confirmed": s["confirmed_btc"],
            "btc_mempool": s["mempool_btc"],
            "btc_total": s["total_btc"],
            "recovery_kit": kit,
        }
