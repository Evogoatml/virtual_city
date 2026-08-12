"""Polls mempool.space REST for UTXO updates on tracked addresses."""
import asyncio
import threading
import logging
import aiohttp

MEMPOOL_API = "https://mempool.space/api"
logger = logging.getLogger(__name__)


class MempoolMonitor:
    """Daemon thread with asyncio loop, polls every 60s."""

    def __init__(self, store, on_new_utxo=None, on_balance=None):
        self.store = store
        self.on_new_utxo = on_new_utxo
        self.on_balance = on_balance
        self._running = False
        self._loop = None
        self._thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        asyncio.run_coroutine_threadsafe(self._poll_loop(), self._loop)

    def stop(self):
        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)

    async def _poll_loop(self):
        session = aiohttp.ClientSession()
        try:
            while self._running:
                try:
                    addrs = self.store.get_addresses()
                    for start in range(0, len(addrs), 50):
                        batch = addrs[start:start + 50]
                        if not batch:
                            continue
                        async with session.post(
                            f"{MEMPOOL_API}/address",
                            json={"addresses": batch},
                            timeout=aiohttp.ClientTimeout(total=15),
                        ) as resp:
                            if resp.status == 200:
                                self._digest(await resp.json())
                except Exception as exc:
                    logger.debug("[BTC] poll: %s", exc)
                await asyncio.sleep(60)
        finally:
            await session.close()

    def _digest(self, data):
        fresh = 0
        items = data if isinstance(data, list) else [data]
        for item in items:
            txid = item.get("txid")
            addr = item.get("address")
            val = item.get("value")
            st = item.get("status", {})
            if not (txid and val and addr):
                continue
            ok = self.store.upsert_utxo(
                txid=txid, vout=item.get("vout", 0),
                address=addr, value=int(val),
                confirmed=1 if st.get("confirmed") else 0,
            )
            if ok:
                fresh += 1
        if fresh and self.on_new_utxo:
            self.on_new_utxo(fresh)
        if self.on_balance:
            self.on_balance(self.store.total_balance())