"""
Market Data Department — Internal component of Finance Building.
Real-time WebSocket streams, funding rates, perp basis, prediction markets.
"""
import asyncio
import time
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
from pathlib import Path

from city.department import Department as BaseAgent
from city.db import now_iso, log_event, set_status

logger = logging.getLogger(__name__)

WS_CAPABLE = {
    "binance", "okx", "bybit", "kraken", "coinbase",
    "bitget", "kucoin", "gateio", "backpack",
}
FUNDING_CAPABLE = {"binance", "bybit", "okx", "bitget", "kucoin", "gateio"}
PREDICTION_MARKETS = {"polymarket", "kalshi", "hyperliquid", "limitless", "myriad"}

try:
    import ccxt.pro as ccxtpro
    CCXT_PRO_AVAILABLE = True
except ImportError:
    CCXT_PRO_AVAILABLE = False

try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False


@dataclass
class PriceUpdate:
    pair: str
    exchange: str
    price: float
    bid: float
    ask: float
    volume_24h: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class FundingUpdate:
    pair: str
    exchange: str
    rate: float
    timestamp: float = field(default_factory=time.time)
    next_funding_time: Optional[float] = None
    predicted_rate: Optional[float] = None


@dataclass
class PerpPriceUpdate:
    pair: str
    exchange: str
    price: float
    mark_price: float
    index_price: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class PredictionMarketPrice:
    market: str
    condition_id: str
    question: str
    yes_price: float
    no_price: float
    volume_24h: float
    liquidity: float
    end_time: Optional[float]
    timestamp: float = field(default_factory=time.time)


class ExchangeConnector:
    def __init__(self, name: str, pairs: List[str], on_price: Callable, on_funding: Optional[Callable] = None, on_perp: Optional[Callable] = None):
        self.name = name
        self.pairs = pairs
        self.on_price = on_price
        self.on_funding = on_funding
        self.on_perp = on_perp
        self.exchange = None
        self.running = True
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 30.0
        self._tasks: List[asyncio.Task] = []

    def _adapt_pair(self, pair: str) -> str:
        if self.name in ("kraken", "coinbase", "gemini", "bitstamp"):
            return pair.replace("/USDT", "/USD")
        return pair

    def _perp_symbol(self, pair: str) -> str:
        base, quote = pair.split("/")
        return f"{base}/{quote}:{quote}"

    async def start(self):
        if not CCXT_PRO_AVAILABLE or self.name not in WS_CAPABLE:
            return
        while self.running:
            try:
                exchange_class = getattr(ccxtpro, self.name)
                self.exchange = exchange_class({"enableRateLimit": True})
                logger.info(f"[+] WS stream started: {self.name}")
                self._reconnect_delay = 1.0
                price_task = asyncio.create_task(self._run_price_stream())
                self._tasks.append(price_task)
                if self.name in FUNDING_CAPABLE and self.on_funding:
                    funding_task = asyncio.create_task(self._run_funding_stream())
                    self._tasks.append(funding_task)
                await asyncio.gather(*self._tasks, return_exceptions=True)
            except Exception as e:
                logger.warning(f"[!] WS stream error for {self.name}: {e}")
            finally:
                if self.exchange:
                    try:
                        await self.exchange.close()
                    except Exception:
                        pass
                self._tasks.clear()
            if not self.running:
                break
            logger.info(f"[*] Reconnecting {self.name} in {self._reconnect_delay:.0f}s...")
            await asyncio.sleep(self._reconnect_delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)

    async def _run_price_stream(self):
        while self.running:
            for pair in self.pairs:
                try:
                    adapted = self._adapt_pair(pair)
                    ticker = await self.exchange.watch_ticker(adapted)
                    if ticker and ticker.get("last"):
                        self.on_price(PriceUpdate(
                            pair=pair, exchange=self.name, price=ticker["last"],
                            bid=ticker.get("bid", ticker["last"]), ask=ticker.get("ask", ticker["last"]),
                            volume_24h=ticker.get("baseVolume", 0),
                        ))
                except Exception as e:
                    logger.debug(f"[!] WS {self.name} {pair}: {e}")
                    await asyncio.sleep(0.5)

    async def _run_funding_stream(self):
        while self.running:
            try:
                for pair in self.pairs:
                    perp = self._perp_symbol(pair)
                    try:
                        funding = await self.exchange.fetch_funding_rate(perp)
                        if funding and funding.get("fundingRate") is not None:
                            self.on_funding(FundingUpdate(
                                pair=pair, exchange=self.name, rate=funding["fundingRate"],
                                next_funding_time=funding.get("nextFundingTimestamp"),
                                predicted_rate=funding.get("fundingRate"),
                            ))
                    except Exception:
                        pass
                await asyncio.sleep(30)
            except Exception as e:
                logger.debug(f"[!] Funding {self.name}: {e}")
                await asyncio.sleep(10)

    def stop(self):
        self.running = False
        for task in self._tasks:
            task.cancel()


class PredictionMarketConnector:
    def __init__(self, name: str, on_update: Callable[[PredictionMarketPrice], None]):
        self.name = name
        self.on_update = on_update
        self.exchange = None
        self.running = True
        self._task: Optional[asyncio.Task] = None
        self._markets_cache: Dict[str, Dict] = {}

    async def start(self, poll_interval: int = 30):
        if not CCXT_AVAILABLE or self.name not in PREDICTION_MARKETS:
            return
        try:
            exchange_class = getattr(ccxt, self.name)
            self.exchange = exchange_class({"enableRateLimit": True})
            await self.exchange.load_markets()
            self._markets_cache = self.exchange.markets
            logger.info(f"[+] Prediction market REST started: {self.name}")
        except Exception as e:
            logger.warning(f"[!] Failed to init {self.name}: {e}")
            return
        while self.running:
            try:
                await self._poll_markets()
            except Exception as e:
                logger.warning(f"[!] {self.name} poll error: {e}")
            await asyncio.sleep(poll_interval)

    async def _poll_markets(self):
        if not self.exchange:
            return
        try:
            tickers = await self.exchange.fetch_tickers()
            for symbol, ticker in tickers.items():
                if not ticker.get("last"):
                    continue
                market = self._markets_cache.get(symbol, {})
                info = market.get("info", {})
                yes_price = ticker.get("last")
                no_price = 1 - yes_price if yes_price <= 1 else ticker.get("bid", 0)
                condition_id = info.get("condition_id") or info.get("question_id") or symbol
                question = info.get("question") or info.get("title") or symbol
                end_time = info.get("end_date_iso") or info.get("expiration") or info.get("endTime")
                if isinstance(end_time, str):
                    try:
                        end_time = datetime.fromisoformat(end_time.replace("Z", "+00:00")).timestamp()
                    except Exception:
                        end_time = None
                self.on_update(PredictionMarketPrice(
                    market=self.name, condition_id=str(condition_id), question=str(question),
                    yes_price=float(yes_price), no_price=float(no_price),
                    volume_24h=float(ticker.get("baseVolume", 0)),
                    liquidity=float(info.get("liquidity", info.get("liquidity_num", 0))),
                    end_time=end_time,
                ))
        except Exception as e:
            logger.debug(f"[{self.name}] Poll error: {e}")

    def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
        if self.exchange:
            asyncio.create_task(self.exchange.close())


class MarketDataDepartment(BaseAgent):
    building_name = "finance_building"
    name = "market_data"
    subject = "Market Data Dept"
    district = "Financial District"
    color = "#00bcd4"

    def setup_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS market_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                snapshot_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS market_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                pair TEXT NOT NULL,
                exchange TEXT,
                value REAL,
                threshold REAL,
                message TEXT
            );
            CREATE TABLE IF NOT EXISTS exchange_status (
                exchange TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                last_update TEXT,
                pairs_monitored INTEGER DEFAULT 0,
                errors INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS monitored_pairs (
                pair TEXT PRIMARY KEY,
                active INTEGER DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON market_snapshots(timestamp);
            CREATE INDEX IF NOT EXISTS idx_alerts_ts ON market_alerts(timestamp);
        """)
        self.conn.commit()

    def register_rules(self):
        self.rule(r"^start\s+(?P<exchanges>[\w,\s]+)$")(self._start_streams)
        self.rule(r"^stop$")(self._stop_streams)
        self.rule(r"^pairs$")(self._list_pairs)
        self.rule(r"^pairs\s+add\s+(?P<pair>\S+)$")(self._add_pair)
        self.rule(r"^pairs\s+remove\s+(?P<pair>\S+)$")(self._remove_pair)
        self.rule(r"^price\s+(?P<pair>\S+)$")(self._get_price)
        self.rule(r"^spread\s+(?P<pair>\S+)$")(self._get_spread)
        self.rule(r"^funding\s+(?P<pair>\S+)$")(self._get_funding)
        self.rule(r"^basis\s+(?P<pair>\S+)$")(self._get_basis)
        self.rule(r"^snapshot$")(self._get_snapshot)
        self.rule(r"^status$")(self._status)
        self.rule(r"^stats$")(self._stats)

    _engine = None
    _engine_task = None
    _loop = None
    _loop_thread = None

    def _get_engine(self):
        if self._engine is None:
            self._engine = MarketDataEngine(pairs=self._get_pairs())
        return self._engine

    def _ensure_loop(self):
        if self._loop is None or not self._loop.is_running():
            import threading
            self._loop = asyncio.new_event_loop()
            self._loop_thread = threading.Thread(target=self._loop.run_forever, daemon=True)
            self._loop_thread.start()

    def _start_async(self, coro):
        self._ensure_loop()
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def work(self):
        engine = self._get_engine()
        if not engine.running:
            # Only auto-start if user has active pairs AND budget allows (avoid restart loops)
            try:
                from city.api_budget import budget
                hit, _ = budget.health_get("market_data_autostart")
                if hit:
                    return
                ok, _ = budget.allow(self.name, "exchange", key="autostart", cost=1)
                if not ok:
                    return
                budget.health_set("market_data_autostart", True, ttl=300)  # at most once / 5 min
            except Exception:
                pass
            self._start_async(self._ensure_engine_started())
            self.log("tick", "starting market data streams")
        # when running: no log spam every 30s

    def _get_pairs(self):
        rows = self.conn.execute("SELECT pair FROM monitored_pairs WHERE active = 1").fetchall()
        return [r["pair"] for r in rows] if rows else ["BTC/USDT", "ETH/USDT", "SOL/USDT", "ARB/USDT", "OP/USDT"]

    async def _ensure_engine_started(self, exchanges=None, prediction_markets=None):
        engine = self._get_engine()
        if not self._engine_task or self._engine_task.done():
            self._engine_task = asyncio.create_task(engine.start(exchanges, prediction_markets))
            logger.info("[MarketData] Engine task started")

    def _start_streams(self, exchanges: str):
        ex_list = [e.strip().lower() for e in exchanges.split(",")]
        self._start_async(self._ensure_engine_started(exchanges=ex_list))
        return {"action": "starting", "exchanges": ex_list, "pairs": self._get_pairs()}

    def _stop_streams(self):
        if self._engine:
            self._engine.stop()
        if self._engine_task:
            self._engine_task.cancel()
        return {"action": "stopped"}

    def _list_pairs(self):
        return {"pairs": self._get_pairs()}

    def _add_pair(self, pair: str):
        self.conn.execute("INSERT OR IGNORE INTO monitored_pairs (pair, active) VALUES (?, 1)", (pair.upper(),))
        self.conn.commit()
        if self._engine and pair not in self._engine.pairs:
            self._engine.pairs.append(pair)
        return {"action": "added", "pair": pair.upper()}

    def _remove_pair(self, pair: str):
        self.conn.execute("UPDATE monitored_pairs SET active = 0 WHERE pair = ?", (pair.upper(),))
        self.conn.commit()
        return {"action": "removed", "pair": pair.upper()}

    def _get_price(self, pair: str):
        import asyncio
        engine = self._get_engine()
        price = engine.get_spot_price(pair.upper())
        if not price:
            return {"error": f"No data for {pair}"}
        return {
            "pair": pair.upper(),
            "price": price.price,
            "bid": price.bid,
            "ask": price.ask,
            "volume_24h": price.volume_24h,
            "source": price.exchange,
            "age_sec": round(time.time() - price.timestamp, 1),
        }

    def _get_spread(self, pair: str):
        engine = self._get_engine()
        return engine.get_spread_matrix(pair.upper())

    def _get_funding(self, pair: str):
        engine = self._get_engine()
        return engine.get_funding_divergence(pair.upper())

    def _get_basis(self, pair: str):
        engine = self._get_engine()
        return engine.get_basis_matrix(pair.upper())

    def _get_snapshot(self):
        engine = self._get_engine()
        return engine.get_snapshot()

    def _status(self):
        engine = self._get_engine()
        return {
            "running": engine.running,
            "connectors": list(engine.connectors.keys()),
            "prediction_connectors": list(engine.prediction_connectors.keys()),
            "pairs": engine.pairs,
            "stats": engine.stats,
        }

    def _stats(self):
        engine = self._get_engine()
        return engine.stats

    def report(self):
        engine = self._get_engine()
        return {
            "department": self.name,
            "subject": self.subject,
            "running": engine.running,
            "active_exchanges": len(engine.connectors),
            "monitored_pairs": len(engine.pairs),
            "total_updates": engine.stats["total_updates"],
            "updates_per_exchange": dict(engine.stats["updates_per_exchange"]),
        }


class MarketDataEngine:
    """Central market data hub managing all exchange connectors."""

    def __init__(self, pairs: List[str] = None):
        self.pairs = pairs or ["BTC/USDT", "ETH/USDT", "SOL/USDT", "ARB/USDT", "OP/USDT"]
        self.connectors: Dict[str, ExchangeConnector] = {}
        self.prediction_connectors: Dict[str, PredictionMarketConnector] = {}
        self.running = True

        self.spot_prices: Dict[str, Dict[str, PriceUpdate]] = defaultdict(dict)
        self.perp_prices: Dict[str, Dict[str, PerpPriceUpdate]] = defaultdict(dict)
        self.funding_rates: Dict[str, Dict[str, FundingUpdate]] = defaultdict(dict)
        self.prediction_markets: Dict[str, Dict[str, PredictionMarketPrice]] = defaultdict(dict)

        self._price_subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._funding_subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._perp_subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._prediction_subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._all_price_subscribers: List[Callable] = []
        self._all_funding_subscribers: List[Callable] = []

        self.stats = {
            "total_updates": 0,
            "updates_per_exchange": defaultdict(int),
            "staleness": defaultdict(dict),
            "started_at": time.time(),
        }

    def subscribe_prices(self, pair: str, callback: Callable[[PriceUpdate], None]):
        self._price_subscribers[pair].append(callback)

    def subscribe_all_prices(self, callback: Callable[[PriceUpdate], None]):
        self._all_price_subscribers.append(callback)

    def subscribe_funding(self, pair: str, callback: Callable[[FundingUpdate], None]):
        self._funding_subscribers[pair].append(callback)

    def subscribe_all_funding(self, callback: Callable[[FundingUpdate], None]):
        self._all_funding_subscribers.append(callback)

    def subscribe_perp(self, pair: str, callback: Callable[[PerpPriceUpdate], None]):
        self._perp_subscribers[pair].append(callback)

    def subscribe_prediction(self, market: str, callback: Callable[[PredictionMarketPrice], None]):
        self._prediction_subscribers[market].append(callback)

    def unsubscribe_all(self):
        self._price_subscribers.clear()
        self._funding_subscribers.clear()
        self._perp_subscribers.clear()
        self._prediction_subscribers.clear()
        self._all_price_subscribers.clear()
        self._all_funding_subscribers.clear()

    def _notify_price(self, update: PriceUpdate):
        self.spot_prices[update.pair][update.exchange] = update
        self.stats["total_updates"] += 1
        self.stats["updates_per_exchange"][update.exchange] += 1
        self.stats["staleness"][update.pair][update.exchange] = 0.0
        for cb in self._price_subscribers.get(update.pair, []):
            try: cb(update)
            except Exception as e: logger.debug(f"Price callback error: {e}")
        for cb in self._all_price_subscribers:
            try: cb(update)
            except Exception: pass

    def _notify_funding(self, update: FundingUpdate):
        self.funding_rates[update.pair][update.exchange] = update
        for cb in self._funding_subscribers.get(update.pair, []):
            try: cb(update)
            except Exception: pass
        for cb in self._all_funding_subscribers:
            try: cb(update)
            except Exception: pass

    def _notify_perp(self, update: PerpPriceUpdate):
        self.perp_prices[update.pair][update.exchange] = update
        for cb in self._perp_subscribers.get(update.pair, []):
            try: cb(update)
            except Exception: pass

    def _notify_prediction(self, update: PredictionMarketPrice):
        self.prediction_markets[update.market][update.condition_id] = update
        for cb in self._prediction_subscribers.get(update.market, []):
            try: cb(update)
            except Exception: pass

    async def start(self, exchange_names: List[str] = None, prediction_markets: List[str] = None):
        if exchange_names is None:
            exchange_names = list(WS_CAPABLE)
        if prediction_markets is None:
            prediction_markets = list(PREDICTION_MARKETS)

        logger.info(f"[MarketData] Starting WS streams for {len(exchange_names)} exchanges...")
        tasks = []
        for name in exchange_names:
            if name in WS_CAPABLE:
                connector = ExchangeConnector(
                    name=name, pairs=self.pairs,
                    on_price=self._notify_price,
                    on_funding=self._notify_funding,
                    on_perp=self._notify_perp,
                )
                self.connectors[name] = connector
                tasks.append(asyncio.create_task(connector.start()))

        for name in prediction_markets:
            if name in PREDICTION_MARKETS:
                connector = PredictionMarketConnector(
                    name=name, on_update=self._notify_prediction,
                )
                self.prediction_connectors[name] = connector
                tasks.append(asyncio.create_task(connector.start()))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def stop(self):
        self.running = False
        for connector in self.connectors.values():
            connector.stop()
        for connector in self.prediction_connectors.values():
            connector.stop()

    def get_spot_price(self, pair: str, exchange: str = None) -> Optional[PriceUpdate]:
        if exchange:
            return self.spot_prices.get(pair, {}).get(exchange)
        prices = self.spot_prices.get(pair, {})
        if not prices:
            return None
        best_bid = max(prices.values(), key=lambda p: p.bid)
        best_ask = min(prices.values(), key=lambda p: p.ask)
        return PriceUpdate(
            pair=pair, exchange="aggregated",
            price=(best_bid.price + best_ask.price) / 2,
            bid=best_bid.bid, ask=best_ask.ask,
            volume_24h=sum(p.volume_24h for p in prices.values()),
        )

    def get_funding_rate(self, pair: str, exchange: str = None) -> Optional[FundingUpdate]:
        if exchange:
            return self.funding_rates.get(pair, {}).get(exchange)
        rates = self.funding_rates.get(pair, {})
        return max(rates.values(), key=lambda r: r.rate) if rates else None

    def get_perp_price(self, pair: str, exchange: str = None) -> Optional[PerpPriceUpdate]:
        if exchange:
            return self.perp_prices.get(pair, {}).get(exchange)
        prices = self.perp_prices.get(pair, {})
        return list(prices.values())[0] if prices else None

    def get_prediction_market(self, market: str, condition_id: str = None) -> Optional[PredictionMarketPrice]:
        markets = self.prediction_markets.get(market, {})
        if condition_id:
            return markets.get(condition_id)
        return list(markets.values())[0] if markets else None

    def get_snapshot(self) -> Dict:
        now = time.time()
        return {
            "spot": {
                pair: {ex: {"price": p.price, "bid": p.bid, "ask": p.ask, "vol": p.volume_24h, "age": round(now - p.timestamp, 1)}
                       for ex, p in exchanges.items()}
                for pair, exchanges in self.spot_prices.items()
            },
            "perp": {
                pair: {ex: {"price": p.price, "mark": p.mark_price, "index": p.index_price, "age": round(now - p.timestamp, 1)}
                       for ex, p in exchanges.items()}
                for pair, exchanges in self.perp_prices.items()
            },
            "funding": {
                pair: {ex: {"rate": f.rate, "next": f.next_funding_time, "pred": f.predicted_rate, "age": round(now - f.timestamp, 1)}
                       for ex, f in exchanges.items()}
                for pair, exchanges in self.funding_rates.items()
            },
            "prediction": {
                market: {
                    cid: {"question": p.question, "yes_price": p.yes_price, "no_price": p.no_price,
                          "volume_24h": p.volume_24h, "liquidity": p.liquidity, "end_time": p.end_time, "age": round(now - p.timestamp, 1)}
                    for cid, p in markets.items()
                }
                for market, markets in self.prediction_markets.items()
            },
            "stats": self.stats,
        }

    def get_spread_matrix(self, pair: str) -> Dict:
        prices = self.spot_prices.get(pair, {})
        if len(prices) < 2:
            return {"pair": pair, "exchanges": len(prices), "error": "need 2+ exchanges"}
        ex_prices = [(ex, p.price, p.bid, p.ask) for ex, p in prices.items()]
        ex_prices.sort(key=lambda x: x[1])
        best_bid_ex, best_bid = ex_prices[-1][0], ex_prices[-1][2]
        best_ask_ex, best_ask = ex_prices[0][0], ex_prices[0][3]
        spread_pct = (best_bid - best_ask) / best_ask * 100
        return {
            "pair": pair,
            "exchanges": len(prices),
            "best_bid": {"exchange": best_bid_ex, "price": best_bid},
            "best_ask": {"exchange": best_ask_ex, "price": best_ask},
            "spread_pct": round(spread_pct, 4),
            "all_prices": {ex: {"price": p, "bid": b, "ask": a} for ex, p, b, a in ex_prices},
        }

    def get_funding_divergence(self, pair: str) -> Dict:
        rates = self.funding_rates.get(pair, {})
        if len(rates) < 2:
            return {"pair": pair, "exchanges": len(rates), "error": "need 2+ exchanges"}
        sorted_rates = sorted(rates.items(), key=lambda x: x[1].rate)
        low_ex, low = sorted_rates[0]
        high_ex, high = sorted_rates[-1]
        divergence = high.rate - low.rate
        return {
            "pair": pair,
            "lowest": {"exchange": low_ex, "rate": low.rate, "annualized": round(low.rate * 3 * 365 * 100, 2)},
            "highest": {"exchange": high_ex, "rate": high.rate, "annualized": round(high.rate * 3 * 365 * 100, 2)},
            "divergence_bps": round(divergence * 10000, 2),
            "divergence_pct": round(divergence * 100, 4),
            "all_rates": {ex: {"rate": f.rate, "annualized": round(f.rate * 3 * 365 * 100, 2)} for ex, f in rates.items()},
        }

    def get_basis_matrix(self, pair: str) -> Dict:
        spot = self.spot_prices.get(pair, {})
        perp = self.perp_prices.get(pair, {})
        if not spot or not perp:
            return {"pair": pair, "error": "missing spot or perp data"}
        avg_spot = sum(p.price for p in spot.values()) / len(spot)
        basis = {}
        for ex, p in perp.items():
            basis_pct = (p.mark_price - avg_spot) / avg_spot * 100
            basis[ex] = {"basis_pct": round(basis_pct, 4), "perp_price": p.mark_price, "spot_avg": round(avg_spot, 2)}
        return {"pair": pair, "avg_spot": round(avg_spot, 2), "basis": basis}