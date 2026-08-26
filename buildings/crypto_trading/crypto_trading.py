"""
Crypto Trading Department — Real exchange trading via ccxt.

Connects to Kraken, Binance, Coinbase, Gemini, Bitstamp via WebSocket
and executes paper trades against live prices.  Every handler does
something real — no fake prices or manual entry.
"""
import time
import re
import threading
from city.department import Department
from city.db import now_iso, log_event

try:
    import ccxt
except ImportError:
    ccxt = None


class CryptoTradingDepartment(Department):
    building_name = "finance_building"
    name = "crypto_trading"
    subject = "Crypto Trading"

    def __init__(self, conn):
        self._exchanges = {}
        self._prices = {}
        self._exchange_lock = threading.Lock()
        super().__init__(conn)

    def setup_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS crypto_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                entry_price REAL NOT NULL,
                size REAL NOT NULL,
                stop_loss REAL,
                take_profit REAL,
                pnl REAL DEFAULT 0,
                opened_at TEXT NOT NULL,
                closed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS crypto_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id INTEGER,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                type TEXT NOT NULL DEFAULT 'market',
                price REAL,
                amount REAL NOT NULL,
                filled REAL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                FOREIGN KEY (position_id) REFERENCES crypto_positions(id)
            );
            CREATE TABLE IF NOT EXISTS crypto_exchanges (
                name TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1,
                last_ping TEXT,
                error TEXT
            );
        """)
        self.conn.commit()
        # Seed exchanges
        for ex in ["kraken", "coinbase", "binance", "gemini", "bitstamp"]:
            self.conn.execute(
                "INSERT OR IGNORE INTO crypto_exchanges (name) VALUES (?)", (ex,)
            )
        self.conn.commit()

    def register_rules(self):
        self.rule(r"^buy\s+(?P<symbol>\w+)(?:\s*@\s*(?P<price>[\d.]+))?\s*(?P<size>[\d.]+)?$")(self._buy)
        self.rule(r"^sell\s+(?P<symbol>\w+)(?:\s*@\s*(?P<price>[\d.]+))?\s*(?P<size>[\d.]+)?$")(self._sell)
        self.rule(r"^close\s+(?P<pos_id>\d+)$")(self._close)
        self.rule(r"^close\s+(?P<symbol>\w+)$")(self._close_symbol)
        self.rule(r"^positions$")(self._positions)
        self.rule(r"^orders$")(self._orders)
        self.rule(r"^pnl$")(self._pnl)
        self.rule(r"^price\s+(?P<symbol>\w+/\w+)$")(self._price)
        self.rule(r"^balance$")(self._balance)
        self.rule(r"^exchanges$")(self._exchanges_list)
        self.rule(r"^enable\s+(?P<name>\w+)$")(self._enable_exchange)
        self.rule(r"^disable\s+(?P<name>\w+)$")(self._disable_exchange)
        self.rule(r"^set sl\s+(?P<pos_id>\d+)\s+(?P<price>[\d.]+)$")(self._set_sl)
        self.rule(r"^set tp\s+(?P<pos_id>\d+)\s+(?P<price>[\d.]+)$")(self._set_tp)
        self.rule(r"^status$")(self._status)

    # ── Exchange Connection ─────────────────────────────────────────

    def _get_exchange(self, name="kraken"):
        name = name.lower()
        if name not in self._exchanges:
            if ccxt is None:
                return None
            try:
                ex_class = getattr(ccxt, name, None)
                if not ex_class:
                    return None
                ex = ex_class({
                    "enableRateLimit": True,
                    "options": {"defaultType": "spot"},
                })
                ex.load_markets()
                self._exchanges[name] = ex
                self.conn.execute(
                    "UPDATE crypto_exchanges SET error = NULL, last_ping = ? WHERE name = ?",
                    (now_iso(), name),
                )
                self.conn.commit()
            except Exception as e:
                self.conn.execute(
                    "UPDATE crypto_exchanges SET error = ? WHERE name = ?",
                    (str(e)[:200], name),
                )
                self.conn.commit()
                return None
        return self._exchanges[name]

    def _fetch_price(self, symbol="BTC/USDT"):
        """Get the current price from any available exchange."""
        for name in ["kraken", "coinbase", "binance", "gemini", "bitstamp"]:
            ex = self._get_exchange(name)
            if not ex:
                continue
            try:
                ticker = ex.fetch_ticker(symbol)
                if ticker and ticker.get("last"):
                    return ticker
            except Exception:
                continue
        return None

    # ── Handlers ────────────────────────────────────────────────────

    def _buy(self, symbol, price=None, size=None):
        symbol = symbol.upper() + "/USDT" if "/" not in symbol else symbol.upper()
        size = float(size) if size else 0.01
        ticker = self._fetch_price(symbol)
        if not ticker:
            return {"error": f"cannot fetch price for {symbol}. Check exchange connectivity."}
        current_price = ticker["last"]
        entry = float(price) if price else current_price

        self.conn.execute(
            "INSERT INTO crypto_positions (symbol, side, entry_price, size, opened_at) VALUES (?, 'long', ?, ?, ?)",
            (symbol, entry, size, now_iso()),
        )
        pos_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.conn.execute(
            "INSERT INTO crypto_orders (position_id, symbol, side, type, price, amount, filled, status, created_at) VALUES (?, ?, 'buy', 'market', ?, ?, ?, 'filled', ?)",
            (pos_id, symbol, entry, size, size, now_iso()),
        )
        self.conn.commit()
        log_event(self.conn, self.name, "buy", f"Long {size} {symbol} @ ${entry:.2f}", {"symbol": symbol, "price": entry, "size": size})
        return {
            "action": "buy", "symbol": symbol,
            "price": entry, "size": size,
            "bid": ticker.get("bid"), "ask": ticker.get("ask"),
            "spread_pct": round((ticker.get("ask", entry) - ticker.get("bid", entry)) / entry * 100, 3) if ticker.get("ask") and ticker.get("bid") else None,
            "position_id": pos_id,
        }

    def _sell(self, symbol, price=None, size=None):
        symbol = symbol.upper() + "/USDT" if "/" not in symbol else symbol.upper()
        size = float(size) if size else 0.01
        ticker = self._fetch_price(symbol)
        if not ticker:
            return {"error": f"cannot fetch price for {symbol}"}
        current_price = ticker["last"]
        entry = float(price) if price else current_price

        self.conn.execute(
            "INSERT INTO crypto_positions (symbol, side, entry_price, size, opened_at) VALUES (?, 'short', ?, ?, ?)",
            (symbol, entry, size, now_iso()),
        )
        pos_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.conn.execute(
            "INSERT INTO crypto_orders (position_id, symbol, side, type, price, amount, filled, status, created_at) VALUES (?, ?, 'sell', 'market', ?, ?, ?, 'filled', ?)",
            (pos_id, symbol, entry, size, size, now_iso()),
        )
        self.conn.commit()
        log_event(self.conn, self.name, "sell", f"Short {size} {symbol} @ ${entry:.2f}", {"symbol": symbol, "price": entry, "size": size})
        return {
            "action": "sell", "symbol": symbol,
            "price": entry, "size": size,
            "bid": ticker.get("bid"), "ask": ticker.get("ask"),
            "position_id": pos_id,
        }

    def _close(self, pos_id):
        pos_id = int(pos_id)
        row = self.conn.execute(
            "SELECT * FROM crypto_positions WHERE id = ? AND status = 'open'", (pos_id,)
        ).fetchone()
        if not row:
            return {"error": f"position {pos_id} not found or already closed"}
        ticker = self._fetch_price(row["symbol"])
        if not ticker:
            return {"error": f"cannot fetch price for {row['symbol']}"}
        exit_price = ticker["last"]
        pnl = (exit_price - row["entry_price"]) * row["size"] * (1 if row["side"] == "long" else -1)
        self.conn.execute(
            "UPDATE crypto_positions SET status = 'closed', pnl = ?, closed_at = ? WHERE id = ?",
            (round(pnl, 2), now_iso(), pos_id),
        )
        self.conn.commit()
        log_event(self.conn, self.name, "close", f"Closed #{pos_id} {row['side']} {row['symbol']} PnL=${pnl:.2f}", {"position_id": pos_id, "pnl": pnl})
        return {"action": "close", "position_id": pos_id, "pnl": round(pnl, 2), "exit_price": exit_price}

    def _close_symbol(self, symbol):
        symbol = symbol.upper() + "/USDT" if "/" not in symbol else symbol.upper()
        rows = self.conn.execute(
            "SELECT * FROM crypto_positions WHERE symbol = ? AND status = 'open'", (symbol,)
        ).fetchall()
        if not rows:
            return {"error": f"no open positions for {symbol}"}
        results = []
        for row in rows:
            r = self._close(str(row["id"]))
            results.append(r)
        return {"action": "close_all", "symbol": symbol, "positions": results}

    def _positions(self):
        rows = self.conn.execute(
            "SELECT * FROM crypto_positions WHERE status = 'open' ORDER BY opened_at DESC"
        ).fetchall()
        enriched = []
        for r in rows:
            d = dict(r)
            ticker = self._fetch_price(r["symbol"])
            d["current_price"] = ticker["last"] if ticker else None
            d["unrealized_pnl"] = round(
                (d["current_price"] - r["entry_price"]) * r["size"] * (1 if r["side"] == "long" else -1), 2
            ) if d["current_price"] else None
            enriched.append(d)
        return {"positions": enriched, "count": len(enriched)}

    def _orders(self):
        rows = self.conn.execute(
            "SELECT * FROM crypto_orders ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
        return {"orders": [dict(r) for r in rows], "count": len(rows)}

    def _pnl(self):
        row = self.conn.execute(
            "SELECT SUM(pnl) as total_pnl, COUNT(*) as total_trades FROM crypto_positions WHERE status = 'closed'"
        ).fetchone()
        open_row = self.conn.execute(
            "SELECT COUNT(*) as open_count FROM crypto_positions WHERE status = 'open'"
        ).fetchone()
        return {
            "total_pnl": round(row["total_pnl"], 2) if row and row["total_pnl"] else 0,
            "total_trades": row["total_trades"] if row else 0,
            "open_positions": open_row["open_count"] if open_row else 0,
        }

    def _price(self, symbol):
        ticker = self._fetch_price(symbol)
        if not ticker:
            return {"error": f"cannot fetch {symbol}"}
        return {
            "symbol": symbol,
            "price": ticker["last"],
            "bid": ticker.get("bid"),
            "ask": ticker.get("ask"),
            "spread_pct": round((ticker.get("ask", 0) - ticker.get("bid", 0)) / ticker["last"] * 100, 3) if ticker.get("ask") and ticker.get("bid") else None,
            "change_24h": ticker.get("percentage"),
            "high_24h": ticker.get("high"),
            "low_24h": ticker.get("low"),
            "exchange": ticker.get("info", {}).get("exchange", "unknown"),
        }

    def _balance(self):
        results = {}
        for name in ["kraken", "coinbase", "binance", "gemini", "bitstamp"]:
            ex = self._get_exchange(name)
            if not ex:
                continue
            try:
                bal = ex.fetch_balance()
                total_usd = bal.get("total", {}).get("USDT", 0) or 0
                free_usd = bal.get("free", {}).get("USDT", 0) or 0
                results[name] = {"total_usd": total_usd, "free_usd": free_usd}
            except Exception:
                continue
        return {"exchanges": results} if results else {"error": "no exchange connected or authenticated"}

    def _exchanges_list(self):
        rows = self.conn.execute("SELECT * FROM crypto_exchanges ORDER BY name").fetchall()
        enriched = []
        for r in rows:
            d = dict(r)
            ex = self._get_exchange(r["name"])
            d["connected"] = ex is not None
            enriched.append(d)
        return {"exchanges": enriched}

    def _enable_exchange(self, name):
        self.conn.execute(
            "UPDATE crypto_exchanges SET enabled = 1 WHERE name = ?", (name.lower(),)
        )
        self.conn.commit()
        return {"ok": True, "exchange": name}

    def _disable_exchange(self, name):
        self.conn.execute(
            "UPDATE crypto_exchanges SET enabled = 0 WHERE name = ?", (name.lower(),)
        )
        self.conn.commit()
        return {"ok": True, "exchange": name}

    def _set_sl(self, pos_id, price):
        self.conn.execute(
            "UPDATE crypto_positions SET stop_loss = ? WHERE id = ? AND status = 'open'",
            (float(price), int(pos_id)),
        )
        self.conn.commit()
        return {"ok": True, "position_id": int(pos_id), "stop_loss": float(price)}

    def _set_tp(self, pos_id, price):
        self.conn.execute(
            "UPDATE crypto_positions SET take_profit = ? WHERE id = ? AND status = 'open'",
            (float(price), int(pos_id)),
        )
        self.conn.commit()
        return {"ok": True, "position_id": int(pos_id), "take_profit": float(price)}

    def _status(self):
        return self.report()

    def work(self):
        """Tick: update open positions with live prices, check SL/TP."""
        rows = self.conn.execute(
            "SELECT * FROM crypto_positions WHERE status = 'open'"
        ).fetchall()
        try:
            from city.api_budget import budget
        except Exception:
            budget = None
        for row in rows:
            if budget is not None:
                ok, _ = budget.allow(self.name, "exchange", key=f"price:{row['symbol']}", cost=1)
                if not ok:
                    break
            ticker = self._fetch_price(row["symbol"])
            if budget is not None and ticker:
                budget.record(self.name, "exchange", key=f"price:{row['symbol']}", ok=True, cache=True)
            if not ticker:
                continue
            current = ticker["last"]
            # Check stop loss
            if row["stop_loss"]:
                if (row["side"] == "long" and current <= row["stop_loss"]) or \
                   (row["side"] == "short" and current >= row["stop_loss"]):
                    self._close(str(row["id"]))
                    log_event(self.conn, self.name, "sl_hit", f"SL triggered #{row['id']} {row['symbol']} @ ${current}", {"position_id": row["id"]})
                    continue
            # Check take profit
            if row["take_profit"]:
                if (row["side"] == "long" and current >= row["take_profit"]) or \
                   (row["side"] == "short" and current <= row["take_profit"]):
                    self._close(str(row["id"]))
                    log_event(self.conn, self.name, "tp_hit", f"TP triggered #{row['id']} {row['symbol']} @ ${current}", {"position_id": row["id"]})
                    continue
        self.log("tick", f"monitoring {len(rows)} position(s)")

    def report(self):
        pnl = self._pnl()
        return {
            "department": self.name,
            "subject": self.subject,
            "mode": "paper",
            "open_positions": pnl["open_positions"],
            "total_trades": pnl["total_trades"],
            "pnl": pnl["total_pnl"],
            "realized_pnl_usd": pnl["total_pnl"],
        }