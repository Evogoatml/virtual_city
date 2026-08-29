"""
Scraper Building — web data extraction with anti-bot resilience.

Three-tier fetcher:
  Tier 1 — scrapling (StealthScraper — anti-detection)
  Tier 2 — requests with rotating headers + 403 bypass mutations
  Tier 3 — httpx with browser-like fingerprints (fallback)

Output is always structured: markdown body + extracted metadata + raw HTML
stored for re-processing.  Queue persists in SQLite so crawls survive restarts.
"""
import json
import re
import time
import hashlib
from urllib.parse import urlparse, urljoin
from city.department import Department
from city.db import now_iso, log_event

# ── Fetcher tiers ───────────────────────────────────────────────────
try:
    import scrapling
    from scrapling import Fetcher
    HAS_SCRAPLE = True
except ImportError:
    HAS_SCRAPLE = False

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    import markdownify
    HAS_MD = True
except ImportError:
    HAS_MD = False


class ScraperDepartment(Department):
    building_name = "supply_scout"
    name = "scraper"
    subject = "Web Scraper"
    color = "#00c853"

    def __init__(self, conn):
        self._client = None
        self._session = None
        super().__init__(conn)

    def setup_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS scrape_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                depth INTEGER DEFAULT 0,
                max_depth INTEGER DEFAULT 1,
                status TEXT DEFAULT 'pending',
                priority INTEGER DEFAULT 0,
                label TEXT,
                error TEXT,
                queued_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS scrape_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                queue_id INTEGER,
                url TEXT NOT NULL,
                title TEXT,
                body_md TEXT,
                body_text TEXT,
                extracted JSON DEFAULT '{}',
                status_code INTEGER,
                tier_used INTEGER,
                bytes_fetched INTEGER,
                fetch_ms INTEGER,
                scraped_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS scrape_robots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                steps JSON NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_queue_status ON scrape_queue(status);
            CREATE INDEX IF NOT EXISTS idx_queue_priority ON scrape_queue(priority DESC);
        """)
        self.conn.commit()

    def register_rules(self):
        self.rule(r"^scrape\s+(?P<url>\S+)(?:\s+label\s+(?P<label>.+))?$")(self._scrape)
        self.rule(r"^crawl\s+(?P<url>\S+)\s*(?P<depth>\d+)?$")(self._crawl)
        self.rule(r"^queue$")(self._queue)
        self.rule(r"^results\s*(?P<limit>\d+)?$")(self._results)
        self.rule(r"^record\s+(?P<name>\w+)\s+(?P<steps_json>.+)$")(self._record_robot)
        self.rule(r"^run\s+(?P<name>\w+)\s+(?P<target_url>\S+)$")(self._run_robot)
        self.rule(r"^robots$")(self._robots)
        self.rule(r"^retry\s+(?P<queue_id>\d+)$")(self._retry)
        self.rule(r"^clear\s+(?P<status>\w+)$")(self._clear_queue)
        self.rule(r"^stats$")(self._stats)
        self.rule(r"^status$")(self._status)

    # ═══════════════════════════════════════════════════════════════════
    # Fetcher Pipeline
    # ═══════════════════════════════════════════════════════════════════

    def _fetch(self, url, tier=1):
        """Three-tier fetch.  Tier 1 = scrapling Fetcher (anti-detection fingerprints).
        Tier 2 = requests with 403 bypass mutations.
        Tier 3 = httpx with browser-like fingerprints (fallback).
        Returns (status_code, body_bytes, tier_used, error, ms)."""
        start = time.perf_counter()

        if tier <= 1 and HAS_SCRAPLE:
            try:
                resp = Fetcher.get(url, timeout=20, headers=self._base_headers())
                ms = int((time.perf_counter() - start) * 1000)
                body = resp.body or b""
                if isinstance(body, str):
                    body = body.encode("utf-8")
                return resp.status or 0, body, 1, None, ms
            except Exception as e:
                if tier == 1:
                    return self._fetch(url, tier=2)

        if tier <= 2 and HAS_REQUESTS:
            try:
                if not self._session:
                    self._session = requests.Session()
                # 403 bypass: try different path variants, header mutations
                urls_to_try = self._403_bypass_urls(url)
                headers_bank = self._403_bypass_headers()

                for u in urls_to_try:
                    for h in headers_bank[:2]:
                        try:
                            resp = self._session.get(u, headers={**self._base_headers(), **h}, timeout=20)
                            if resp.status_code == 200:
                                ms = int((time.perf_counter() - start) * 1000)
                                return resp.status_code, resp.content, 2, None, ms
                        except Exception:
                            continue
                # Last attempt with default
                resp = self._session.get(url, headers=self._base_headers(), timeout=20)
                ms = int((time.perf_counter() - start) * 1000)
                return resp.status_code, resp.content, 2, None, ms
            except Exception as e:
                return 0, b"", 2, str(e), int((time.perf_counter() - start) * 1000)

        if tier <= 3 and HAS_HTTPX:
            try:
                if not self._client:
                    self._client = httpx.Client(
                        follow_redirects=True,
                        timeout=20.0,
                        headers=self._base_headers(),
                    )
                resp = self._client.get(url)
                ms = int((time.perf_counter() - start) * 1000)
                return resp.status_code, resp.content, 3, None, ms
            except Exception as e:
                return 0, b"", 3, str(e), int((time.perf_counter() - start) * 1000)

        return 0, b"", 0, "no fetcher available (install scrapling, requests, or httpx)", int((time.perf_counter() - start) * 1000)

    @staticmethod
    def _base_headers():
        return {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    @staticmethod
    def _403_bypass_urls(url):
        """Path mutations to bypass 403 blocks."""
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path or "/"
        variants = [url]
        # Try adding / to end
        if not path.endswith("/"):
            variants.append(url + "/")
        # Try different path cases
        if path != path.lower():
            variants.append(base + path.lower())
        # Try adding ? bypass param
        variants.append(url + ("&" if parsed.query else "?") + "bypass=1")
        return variants

    @staticmethod
    def _403_bypass_headers():
        return [
            {"X-Forwarded-For": "127.0.0.1"},
            {"X-Forwarded-For": "10.0.0.1"},
            {"Accept": "*/*"},
            {"Accept-Encoding": "identity"},
            {"Cache-Control": "no-cache", "Pragma": "no-cache"},
        ]

    def _parse(self, html, url):
        """Extract title, body_md, body_text from HTML."""
        if not HAS_BS4:
            return {"title": url, "body_text": html[:5000], "body_md": ""}
        soup = BeautifulSoup(html, "html.parser")
        title = ""
        if soup.title:
            title = soup.title.get_text(strip=True)
        # Remove scripts, styles
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        body_text = soup.get_text(separator="\n", strip=True)
        body_md = body_text[:20000]
        if HAS_MD:
            try:
                body_md = markdownify.markdownify(str(soup.body or soup), heading_style="ATX")
            except Exception:
                pass
        return {
            "title": title or url,
            "body_text": body_text[:50000],
            "body_md": body_md[:30000],
        }

    # ═══════════════════════════════════════════════════════════════════
    # Handlers
    # ═══════════════════════════════════════════════════════════════════

    def _scrape(self, url, label=""):
        """Single URL scrape."""
        qid = self._enqueue(url, label=label, priority=1)
        return self._process_queue_item(qid)

    def _crawl(self, url, depth=1):
        """Enqueue URL with depth for recursive crawling."""
        depth = int(depth) if depth else 1
        qid = self._enqueue(url, depth=0, max_depth=depth)
        return {"queued": url, "depth": depth, "queue_id": qid}

    def _enqueue(self, url, depth=0, max_depth=1, priority=0, label=""):
        self.conn.execute(
            "INSERT INTO scrape_queue (url, depth, max_depth, status, priority, label, queued_at) VALUES (?, ?, ?, 'pending', ?, ?, ?)",
            (url, depth, max_depth, priority, label or url[:80], now_iso()),
        )
        self.conn.commit()
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def _process_queue_item(self, qid):
        """Fetch, parse, store one queue item."""
        row = self.conn.execute("SELECT * FROM scrape_queue WHERE id = ?", (qid,)).fetchone()
        if not row:
            return {"error": f"queue item {qid} not found"}
        url = row["url"]
        self.conn.execute("UPDATE scrape_queue SET status = 'fetching', started_at = ? WHERE id = ?", (now_iso(), qid))
        self.conn.commit()

        try:
            from city.api_budget import budget
            ok, reason = budget.allow(self.name, "scrape", key=f"fetch:{url[:120]}", cost=1)
            if not ok:
                return {"ok": False, "error": reason, "denied": True, "url": url}
        except Exception:
            budget = None
        status_code, body, tier, error, ms = self._fetch(url)
        try:
            from city.api_budget import budget as b2
            b2.record(self.name, "scrape", key=f"fetch:{url[:120]}", ok=(error is None or error == ""), cache=True)
        except Exception:
            pass

        if status_code != 200 or not body:
            self.conn.execute(
                "UPDATE scrape_queue SET status = 'error', error = ? WHERE id = ?",
                (error or f"HTTP {status_code}", qid),
            )
            self.conn.commit()
            return {"error": f"HTTP {status_code}: {error}", "tier": tier, "ms": ms}

        parsed = self._parse(body, url)
        extracted = {}
        # Auto-detect: numbers, prices, emails
        prices = re.findall(r'\$\s*[\d,]+\.?\d{0,2}', parsed["body_text"])
        emails = re.findall(r'[\w.+-]+@[\w-]+\.[\w.]+', parsed["body_text"])
        if prices:
            extracted["prices_found"] = prices[:5]
        if emails:
            extracted["emails_found"] = emails[:5]

        self.conn.execute(
            "INSERT INTO scrape_results (queue_id, url, title, body_md, body_text, extracted, status_code, tier_used, bytes_fetched, fetch_ms, scraped_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (qid, url, parsed["title"], parsed["body_md"][:30000], parsed["body_text"][:50000],
             json.dumps(extracted), status_code, tier, len(body), ms, now_iso()),
        )
        self.conn.execute("UPDATE scrape_queue SET status = 'done', completed_at = ? WHERE id = ?", (now_iso(), qid))
        self.conn.commit()

        log_event(self.conn, self.name, "scraped", f"{parsed['title'][:60]} ({len(body)}b)", {"url": url, "tier": tier, "ms": ms})

        result = {
            "title": parsed["title"],
            "url": url,
            "tier": tier,
            "bytes": len(body),
            "ms": ms,
            "body_md_preview": parsed["body_md"][:200],
        }
        if extracted:
            result["extracted"] = extracted
        return result

    def _queue(self):
        rows = self.conn.execute(
            "SELECT id, url, status, priority, label, queued_at, completed_at FROM scrape_queue ORDER BY priority DESC, id DESC LIMIT 50"
        ).fetchall()
        return {"queue": [dict(r) for r in rows], "count": len(rows)}

    def _results(self, limit=20):
        limit = int(limit) if limit else 20
        rows = self.conn.execute(
            "SELECT id, url, title, status_code, tier_used, bytes_fetched, fetch_ms, scraped_at FROM scrape_results ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return {"results": [dict(r) for r in rows], "count": len(rows)}

    def _record_robot(self, name, steps_json):
        steps = json.loads(steps_json)
        self.conn.execute(
            "INSERT INTO scrape_robots (name, steps, created_at) VALUES (?, ?, ?)",
            (name, json.dumps(steps), now_iso()),
        )
        self.conn.commit()
        return {"ok": True, "robot": name, "steps": len(steps)}

    def _run_robot(self, name, target_url):
        row = self.conn.execute(
            "SELECT * FROM scrape_robots WHERE name = ?", (name,)
        ).fetchone()
        if not row:
            return {"error": f"robot '{name}' not found"}
        steps = json.loads(row["steps"])
        results = []
        for step in steps:
            action = step.get("action", "scrape")
            if action == "scrape":
                url = step.get("url", target_url)
                selector = step.get("selector")
                r = self._scrape(url)
                results.append(r)
            elif action == "extract":
                # Future: CSS selector extraction
                r = self._scrape(target_url)
                results.append(r)
        return {"robot": name, "steps_run": len(steps), "results": results}

    def _robots(self):
        rows = self.conn.execute("SELECT id, name, created_at FROM scrape_robots ORDER BY created_at DESC").fetchall()
        return {"robots": [dict(r) for r in rows]}

    def _retry(self, queue_id):
        return self._process_queue_item(int(queue_id))

    def _clear_queue(self, status):
        self.conn.execute("DELETE FROM scrape_queue WHERE status = ?", (status,))
        self.conn.commit()
        return {"cleared": status}

    def _stats(self):
        total = self.conn.execute("SELECT COUNT(*) AS c FROM scrape_results").fetchone()["c"]
        queue_pending = self.conn.execute("SELECT COUNT(*) AS c FROM scrape_queue WHERE status = 'pending'").fetchone()["c"]
        queue_done = self.conn.execute("SELECT COUNT(*) AS c FROM scrape_queue WHERE status = 'done'").fetchone()["c"]
        queue_errors = self.conn.execute("SELECT COUNT(*) AS c FROM scrape_queue WHERE status = 'error'").fetchone()["c"]
        tiers = self.conn.execute(
            "SELECT tier_used, COUNT(*) AS c FROM scrape_results GROUP BY tier_used ORDER BY tier_used"
        ).fetchall()
        robots = self.conn.execute("SELECT COUNT(*) AS c FROM scrape_robots").fetchone()["c"]
        return {
            "total_scrapes": total,
            "queue_pending": queue_pending,
            "queue_done": queue_done,
            "queue_errors": queue_errors,
            "tiers": [dict(r) for r in tiers],
            "robots": robots,
        }

    def _status(self):
        return self.report()

    def work(self):
        """Tick: process next pending queue item (budget-gated)."""
        try:
            from city.api_budget import budget
            ok, reason = budget.allow(self.name, "scrape", key="queue_tick", cost=1)
            if not ok:
                return
        except Exception:
            pass
        row = self.conn.execute(
            "SELECT id FROM scrape_queue WHERE status = 'pending' ORDER BY priority DESC, id ASC LIMIT 1"
        ).fetchone()
        if row:
            self._process_queue_item(row["id"])

    def report(self):
        s = self._stats()
        return {
            "department": self.name,
            "subject": self.subject,
            **s,
        }