"""
Content Automation Department — Internal component of Media Building.
Multi-provider video generation (Kling, Pika, Runway, HeyGen), queue, budget tracking.
"""
import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from city.department import Department as BaseAgent
from city.db import now_iso, log_event, set_status

from buildings.crypto_trading.market_data import (
    ExchangeConnector, PredictionMarketConnector, PriceUpdate, FundingUpdate,
    PerpPriceUpdate, PredictionMarketPrice
)


class QueuePriority(Enum):
    LOW = 3
    NORMAL = 2
    HIGH = 1
    URGENT = 0


class VideoStatus(Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class VideoGenerationRequest:
    request_id: str
    prompt: str
    params: Dict[str, Any]
    priority: QueuePriority = QueuePriority.NORMAL
    created_at: str = field(default_factory=now_iso)
    retry_count: int = 0
    max_retries: int = 3
    provider: Optional[str] = None
    status: VideoStatus = VideoStatus.QUEUED
    job_id: str = ""
    result: Optional[Dict] = None
    error: str = ""

    def __lt__(self, other):
        return self.priority.value < other.priority.value


class VideoProvider:
    def __init__(self, name: str, api_key: str, config: Dict):
        self.name = name
        self.api_key = api_key
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.daily_count = 0
        self.last_reset = datetime.now().date()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            )
        return self.session

    def _check_rate_limit(self) -> bool:
        today = datetime.now().date()
        if today != self.last_reset:
            self.daily_count = 0
            self.last_reset = today
        daily_limit = self.config.get("rate_limit_per_day", 100)
        return self.daily_count < daily_limit

    def _increment_usage(self):
        self.daily_count += 1

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def generate_video(self, prompt: str, **kwargs) -> Dict:
        raise NotImplementedError

    async def generate_from_image(self, image_url: str, animation_prompt: str, **kwargs) -> Dict:
        raise NotImplementedError

    async def get_status(self, job_id: str) -> Dict:
        raise NotImplementedError

    async def estimate_cost(self, params: Dict) -> float:
        raise NotImplementedError

    def get_max_duration(self) -> int:
        return self.config.get("max_duration", 60)

    def get_supported_styles(self) -> List[str]:
        return self.config.get("supported_styles", ["default"])


class KlingProvider(VideoProvider):
    API_BASE = "https://api.klingai.com/v1"

    async def generate_video(self, prompt: str, style: str = "default", duration: int = 15, **kwargs) -> Dict:
        if not self._check_rate_limit():
            return {"status": VideoStatus.FAILED.value, "error": "Daily rate limit exceeded"}
        session = await self._get_session()
        payload = {"prompt": prompt, "duration": duration, "aspect_ratio": kwargs.get("aspect_ratio", "9:16"), "style": style}
        async with session.post(f"{self.API_BASE}/videos/generate", json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                self._increment_usage()
                return {"status": VideoStatus.QUEUED.value, "job_id": data.get("job_id", ""), "cost_usd": 0.0, "metadata": data}
            return {"status": VideoStatus.FAILED.value, "error": f"API error: {resp.status}"}

    async def generate_from_image(self, image_url: str, animation_prompt: str, duration: int = 15, **kwargs) -> Dict:
        if not self._check_rate_limit():
            return {"status": VideoStatus.FAILED.value, "error": "Daily rate limit exceeded"}
        session = await self._get_session()
        payload = {"image_url": image_url, "animation_prompt": animation_prompt, "duration": duration, "aspect_ratio": kwargs.get("aspect_ratio", "9:16")}
        async with session.post(f"{self.API_BASE}/videos/image-to-video", json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                self._increment_usage()
                return {"status": VideoStatus.QUEUED.value, "job_id": data.get("job_id", ""), "cost_usd": 0.0, "metadata": data}
            return {"status": VideoStatus.FAILED.value, "error": f"API error: {resp.status}"}

    async def get_status(self, job_id: str) -> Dict:
        session = await self._get_session()
        async with session.get(f"{self.API_BASE}/videos/{job_id}") as resp:
            if resp.status == 200:
                data = await resp.json()
                status_map = {"queued": VideoStatus.QUEUED, "processing": VideoStatus.PROCESSING, "completed": VideoStatus.COMPLETED, "failed": VideoStatus.FAILED, "cancelled": VideoStatus.CANCELLED}
                return {"status": status_map.get(data.get("status", "processing"), VideoStatus.PROCESSING).value, "video_url": data.get("video_url"), "thumbnail_url": data.get("thumbnail_url"), "duration": data.get("duration"), "cost_usd": 0.0, "metadata": data}
            return {"status": VideoStatus.FAILED.value, "error": f"Status check failed: {resp.status}"}

    async def estimate_cost(self, params: Dict) -> float:
        return 0.0


class PikaProvider(VideoProvider):
    API_BASE = "https://api.pika.art/v1"

    async def generate_video(self, prompt: str, style: str = "default", duration: int = 15, **kwargs) -> Dict:
        if not self._check_rate_limit():
            return {"status": VideoStatus.FAILED.value, "error": "Daily rate limit exceeded"}
        cost_per_sec = self.config.get("cost_per_second", 0.033)
        est_cost = cost_per_sec * duration
        if est_cost > self.config.get("per_video_max_usd", 2.0):
            return {"status": VideoStatus.FAILED.value, "error": f"Estimated cost ${est_cost:.2f} exceeds limit"}
        session = await self._get_session()
        payload = {"prompt": prompt, "duration": duration, "aspect_ratio": kwargs.get("aspect_ratio", "9:16"), "style": style}
        async with session.post(f"{self.API_BASE}/videos/generate", json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                self._increment_usage()
                return {"status": VideoStatus.QUEUED.value, "job_id": data.get("job_id", ""), "cost_usd": est_cost, "metadata": data}
            return {"status": VideoStatus.FAILED.value, "error": f"API error: {resp.status}"}

    async def generate_from_image(self, image_url: str, animation_prompt: str, duration: int = 15, **kwargs) -> Dict:
        if not self._check_rate_limit():
            return {"status": VideoStatus.FAILED.value, "error": "Daily rate limit exceeded"}
        session = await self._get_session()
        payload = {"image_url": image_url, "animation_prompt": animation_prompt, "duration": duration, "aspect_ratio": kwargs.get("aspect_ratio", "9:16")}
        async with session.post(f"{self.API_BASE}/videos/image-to-video", json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                self._increment_usage()
                return {"status": VideoStatus.QUEUED.value, "job_id": data.get("job_id", ""), "cost_usd": self.config.get("cost_per_second", 0.033) * duration, "metadata": data}
            return {"status": VideoStatus.FAILED.value, "error": f"API error: {resp.status}"}

    async def get_status(self, job_id: str) -> Dict:
        session = await self._get_session()
        async with session.get(f"{self.API_BASE}/videos/{job_id}") as resp:
            if resp.status == 200:
                data = await resp.json()
                status_map = {"queued": VideoStatus.QUEUED, "processing": VideoStatus.PROCESSING, "completed": VideoStatus.COMPLETED, "failed": VideoStatus.FAILED, "cancelled": VideoStatus.CANCELLED}
                cost = self.config.get("cost_per_second", 0.033) * data.get("duration", 0)
                return {"status": status_map.get(data.get("status", "processing"), VideoStatus.PROCESSING).value, "video_url": data.get("video_url"), "thumbnail_url": data.get("thumbnail_url"), "duration": data.get("duration"), "cost_usd": cost, "metadata": data}
            return {"status": VideoStatus.FAILED.value, "error": f"Status check failed: {resp.status}"}

    async def estimate_cost(self, params: Dict) -> float:
        duration = params.get("duration", 15)
        return self.config.get("cost_per_second", 0.033) * duration


class RunwayProvider(VideoProvider):
    API_BASE = "https://api.runwayml.com/v1"

    async def generate_video(self, prompt: str, style: str = "default", duration: int = 15, **kwargs) -> Dict:
        if not self._check_rate_limit():
            return {"status": VideoStatus.FAILED.value, "error": "Daily rate limit exceeded"}
        cost_per_sec = self.config.get("cost_per_second", 0.1)
        est_cost = cost_per_sec * duration
        if est_cost > self.config.get("per_video_max_usd", 2.0):
            return {"status": VideoStatus.FAILED.value, "error": f"Estimated cost ${est_cost:.2f} exceeds limit"}
        session = await self._get_session()
        payload = {"prompt": prompt, "duration": duration, "aspect_ratio": kwargs.get("aspect_ratio", "9:16"), "style": style}
        async with session.post(f"{self.API_BASE}/videos/generate", json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                self._increment_usage()
                return {"status": VideoStatus.QUEUED.value, "job_id": data.get("job_id", ""), "cost_usd": est_cost, "metadata": data}
            return {"status": VideoStatus.FAILED.value, "error": f"API error: {resp.status}"}

    async def generate_from_image(self, image_url: str, animation_prompt: str, duration: int = 15, **kwargs) -> Dict:
        if not self._check_rate_limit():
            return {"status": VideoStatus.FAILED.value, "error": "Daily rate limit exceeded"}
        session = await self._get_session()
        payload = {"image_url": image_url, "animation_prompt": animation_prompt, "duration": duration, "aspect_ratio": kwargs.get("aspect_ratio", "9:16")}
        async with session.post(f"{self.API_BASE}/videos/image-to-video", json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                self._increment_usage()
                return {"status": VideoStatus.QUEUED.value, "job_id": data.get("job_id", ""), "cost_usd": self.config.get("cost_per_second", 0.1) * duration, "metadata": data}
            return {"status": VideoStatus.FAILED.value, "error": f"API error: {resp.status}"}

    async def get_status(self, job_id: str) -> Dict:
        session = await self._get_session()
        async with session.get(f"{self.API_BASE}/videos/{job_id}") as resp:
            if resp.status == 200:
                data = await resp.json()
                status_map = {"queued": VideoStatus.QUEUED, "processing": VideoStatus.PROCESSING, "completed": VideoStatus.COMPLETED, "failed": VideoStatus.FAILED, "cancelled": VideoStatus.CANCELLED}
                cost = self.config.get("cost_per_second", 0.1) * data.get("duration", 0)
                return {"status": status_map.get(data.get("status", "processing"), VideoStatus.PROCESSING).value, "video_url": data.get("video_url"), "thumbnail_url": data.get("thumbnail_url"), "duration": data.get("duration"), "cost_usd": cost, "metadata": data}
            return {"status": VideoStatus.FAILED.value, "error": f"Status check failed: {resp.status}"}

    async def estimate_cost(self, params: Dict) -> float:
        duration = params.get("duration", 15)
        return self.config.get("cost_per_second", 0.1) * duration


class HeyGenProvider(VideoProvider):
    API_BASE = "https://api.heygen.com/v2"

    async def generate_video(self, prompt: str, style: str = "default", duration: int = 15, **kwargs) -> Dict:
        if not self._check_rate_limit():
            return {"status": VideoStatus.FAILED.value, "error": "Daily rate limit exceeded"}
        cost_per_min = self.config.get("cost_per_minute", 8.0)
        est_cost = cost_per_min * (duration / 60)
        if est_cost > self.config.get("per_video_max_usd", 2.0):
            return {"status": VideoStatus.FAILED.value, "error": f"Estimated cost ${est_cost:.2f} exceeds limit"}
        session = await self._get_session()
        avatar_id = kwargs.get("avatar_id", self.config.get("default_avatar_id", "default"))
        voice_id = kwargs.get("voice_id", self.config.get("default_voice_id", "en-US-JennyNeural"))
        payload = {"text": prompt, "avatar_id": avatar_id, "voice_id": voice_id, "duration": duration}
        async with session.post(f"{self.API_BASE}/video/generate", json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                self._increment_usage()
                return {"status": VideoStatus.QUEUED.value, "job_id": data.get("job_id", ""), "cost_usd": est_cost, "metadata": data}
            return {"status": VideoStatus.FAILED.value, "error": f"API error: {resp.status}"}

    async def generate_from_image(self, image_url: str, animation_prompt: str, duration: int = 15, **kwargs) -> Dict:
        return {"status": VideoStatus.FAILED.value, "error": "HeyGen does not support image-to-video"}

    async def get_status(self, job_id: str) -> Dict:
        session = await self._get_session()
        async with session.get(f"{self.API_BASE}/video/status", params={"job_id": job_id}) as resp:
            if resp.status == 200:
                data = await resp.json()
                status_map = {"pending": VideoStatus.QUEUED, "processing": VideoStatus.PROCESSING, "completed": VideoStatus.COMPLETED, "failed": VideoStatus.FAILED}
                cost = self.config.get("cost_per_minute", 8.0) * (data.get("duration", 0) / 60)
                return {"status": status_map.get(data.get("status", "pending"), VideoStatus.PROCESSING).value, "video_url": data.get("video_url"), "thumbnail_url": data.get("thumbnail_url"), "duration": data.get("duration"), "cost_usd": cost, "metadata": data}
            return {"status": VideoStatus.FAILED.value, "error": f"Status check failed: {resp.status}"}

    async def estimate_cost(self, params: Dict) -> float:
        duration = params.get("duration", 15)
        return self.config.get("cost_per_minute", 8.0) * (duration / 60)


PROVIDER_CLASSES = {
    "kling": KlingProvider,
    "pika": PikaProvider,
    "runway": RunwayProvider,
    "heygen": HeyGenProvider,
}


class ContentAutomationDepartment(BaseAgent):
    name = "content_automation"
    subject = "Content Automation Dept"
    district = "Media District"
    color = "#7c4dff"

    def setup_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS content_video_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT UNIQUE NOT NULL,
                prompt TEXT NOT NULL,
                params_json TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 2,
                provider TEXT,
                status TEXT NOT NULL DEFAULT 'queued',
                job_id TEXT,
                result_json TEXT,
                error TEXT,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS content_video_generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                job_id TEXT NOT NULL,
                prompt TEXT NOT NULL,
                video_url TEXT,
                thumbnail_url TEXT,
                duration INTEGER,
                cost_usd REAL DEFAULT 0,
                status TEXT NOT NULL,
                metadata_json TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS content_budget (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE NOT NULL,
                daily_spent_usd REAL DEFAULT 0,
                monthly_spent_usd REAL DEFAULT 0,
                daily_limit_usd REAL DEFAULT 10,
                monthly_limit_usd REAL DEFAULT 200,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_queue_status ON content_video_queue(status);
            CREATE INDEX IF NOT EXISTS idx_gen_request ON content_video_generations(request_id);
        """)
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(content_video_generations)").fetchall()}
        for col, decl in (
            ("duration_seconds", "INTEGER"),
            ("views", "INTEGER DEFAULT 0"),
            ("likes", "INTEGER DEFAULT 0"),
            ("comments", "INTEGER DEFAULT 0"),
            ("shares", "INTEGER DEFAULT 0"),
            ("engagement_rate", "REAL DEFAULT 0"),
            ("metadata", "TEXT"),
        ):
            if col not in cols:
                try:
                    self.conn.execute(f"ALTER TABLE content_video_generations ADD COLUMN {col} {decl}")
                except Exception:
                    pass
        self.conn.commit()

    def register_rules(self):
        self.rule(r"^queue\s+(?P<prompt>.+?)\s+duration\s+(?P<duration>\d+)\s+(?P<provider>\w+)$")(self._queue_video)
        self.rule(r"^queue\s+(?P<prompt>.+?)\s+duration\s+(?P<duration>\d+)$")(self._queue_video)
        self.rule(r"^schedule\s+(?P<prompt>.+?)\s+at\s+(?P<time>\d{2}:\d{2})\s+duration\s+(?P<duration>\d+)\s+(?P<provider>\w+)$")(self._schedule_video)
        self.rule(r"^status\s+(?P<request_id>\S+)$")(self._check_status)
        self.rule(r"^queue\s+status$")(self._queue_status)
        self.rule(r"^budget$")(self._show_budget)
        self.rule(r"^budget\s+set\s+daily\s+(?P<daily>[\d.]+)\s+monthly\s+(?P<monthly>[\d.]+)$")(self._set_budget)
        self.rule(r"^retry\s+(?P<request_id>\S+)$")(self._retry_failed)
        self.rule(r"^cancel\s+(?P<request_id>\S+)$")(self._cancel_request)
        self.rule(r"^providers$")(self._list_providers)
        self.rule(r"^stats$")(self._stats)
        self.rule(r"^process\s+queue$")(self._process_queue)
        self.rule(r"^status$")(self._status)

    def _queue_video(self, prompt, duration, provider="kling"):
        provider = provider.lower()
        if provider not in PROVIDER_CLASSES:
            return {"error": f"Unknown provider: {provider}. Available: {list(PROVIDER_CLASSES.keys())}"}
        request_id = f"vid_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        params = {"duration": int(duration), "aspect_ratio": "9:16", "style": "trendy"}
        est_cost = asyncio.run(self._estimate_cost(provider, params))
        budget = self._get_budget()
        if est_cost > budget["per_video_max_usd"]:
            return {"error": f"Estimated cost ${est_cost:.2f} exceeds per-video limit ${budget['per_video_max_usd']:.2f}"}
        if budget["daily_spent_usd"] + est_cost > budget["daily_limit_usd"]:
            return {"error": f"Daily budget would be exceeded (${budget['daily_spent_usd']:.2f} + ${est_cost:.2f} > ${budget['daily_limit_usd']:.2f})"}

        self.conn.execute(
            "INSERT INTO content_video_queue (request_id, prompt, params_json, priority, provider, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (request_id, prompt, json.dumps(params), QueuePriority.NORMAL.value, provider, VideoStatus.QUEUED.value, now_iso()),
        )
        self.conn.commit()
        self.log("queue", f"Video queued: {request_id}", {"request_id": request_id, "provider": provider, "est_cost": est_cost})
        return {"action": "queued", "request_id": request_id, "provider": provider, "estimated_cost_usd": round(est_cost, 2)}

    def _schedule_video(self, prompt, time, duration, provider):
        provider = provider.lower()
        if provider not in PROVIDER_CLASSES:
            return {"error": f"Unknown provider: {provider}"}
        request_id = f"sched_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        params = {"duration": int(duration), "aspect_ratio": "9:16", "style": "trendy", "scheduled_for": time}
        self.conn.execute(
            "INSERT INTO content_video_queue (request_id, prompt, params_json, priority, provider, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (request_id, prompt, json.dumps(params), QueuePriority.HIGH.value, provider, VideoStatus.QUEUED.value, now_iso()),
        )
        self.conn.commit()
        return {"action": "scheduled", "request_id": request_id, "scheduled_for": time, "provider": provider}

    def _check_status(self, request_id):
        row = self.conn.execute("SELECT * FROM content_video_queue WHERE request_id = ?", (request_id,)).fetchone()
        if not row:
            return {"error": f"Request not found: {request_id}"}
        return dict(row)

    def _queue_status(self):
        rows = self.conn.execute("SELECT request_id, prompt, provider, status, priority, created_at FROM content_video_queue WHERE status IN ('queued','processing') ORDER BY priority, created_at").fetchall()
        return {"queue": [dict(r) for r in rows], "count": len(rows)}

    def _show_budget(self):
        budget = self._get_budget()
        return {"budget": budget}

    def _set_budget(self, daily, monthly):
        self.conn.execute(
            "INSERT OR REPLACE INTO content_budget (date, daily_limit_usd, monthly_limit_usd, updated_at) VALUES (?, ?, ?, ?)",
            (datetime.now().date().isoformat(), float(daily), float(monthly), now_iso()),
        )
        self.conn.commit()
        return {"action": "budget updated", "daily_limit": float(daily), "monthly_limit": float(monthly)}

    def _retry_failed(self, request_id):
        row = self.conn.execute("SELECT * FROM content_video_queue WHERE request_id = ?", (request_id,)).fetchone()
        if not row:
            return {"error": f"Request not found: {request_id}"}
        if row["status"] not in (VideoStatus.FAILED.value, VideoStatus.CANCELLED.value):
            return {"error": f"Request is not failed/cancelled: {row['status']}"}
        if row["retry_count"] >= row["max_retries"]:
            return {"error": f"Max retries ({row['max_retries']}) exceeded"}
        self.conn.execute(
            "UPDATE content_video_queue SET status = ?, retry_count = retry_count + 1, error = '' WHERE request_id = ?",
            (VideoStatus.QUEUED.value, request_id),
        )
        self.conn.commit()
        return {"action": "retry queued", "request_id": request_id, "retry_count": row["retry_count"] + 1}

    def _cancel_request(self, request_id):
        row = self.conn.execute("SELECT * FROM content_video_queue WHERE request_id = ?", (request_id,)).fetchone()
        if not row:
            return {"error": f"Request not found: {request_id}"}
        if row["status"] in (VideoStatus.COMPLETED.value, VideoStatus.FAILED.value):
            return {"error": f"Cannot cancel completed/failed request: {row['status']}"}
        self.conn.execute("UPDATE content_video_queue SET status = ? WHERE request_id = ?", (VideoStatus.CANCELLED.value, request_id))
        self.conn.commit()
        return {"action": "cancelled", "request_id": request_id}

    def _list_providers(self):
        return {"providers": list(PROVIDER_CLASSES.keys())}

    def _stats(self):
        stats = {}
        stats["queued"] = self.conn.execute("SELECT COUNT(*) AS n FROM content_video_queue WHERE status = 'queued'").fetchone()["n"]
        stats["processing"] = self.conn.execute("SELECT COUNT(*) AS n FROM content_video_queue WHERE status = 'processing'").fetchone()["n"]
        stats["completed"] = self.conn.execute("SELECT COUNT(*) AS n FROM content_video_queue WHERE status = 'completed'").fetchone()["n"]
        stats["failed"] = self.conn.execute("SELECT COUNT(*) AS n FROM content_video_queue WHERE status = 'failed'").fetchone()["n"]
        stats["total_generations"] = self.conn.execute("SELECT COUNT(*) AS n FROM content_video_generations").fetchone()["n"]
        stats["total_cost_usd"] = round(self.conn.execute("SELECT COALESCE(SUM(cost_usd),0) AS c FROM content_video_generations").fetchone()["c"], 2)
        budget = self._get_budget()
        stats["budget"] = budget
        return {"stats": stats}

    def _process_queue(self):
        return asyncio.run(self._process_queue_async())

    async def _process_queue_async(self):
        queued = self.conn.execute(
            "SELECT * FROM content_video_queue WHERE status = 'queued' ORDER BY priority, created_at LIMIT 5"
        ).fetchall()
        if not queued:
            return {"processed": 0, "message": "Queue empty"}

        processed = 0
        for row in queued:
            request_id = row["request_id"]
            provider_name = row["provider"]
            params = json.loads(row["params_json"])
            prompt = row["prompt"]

            self.conn.execute(
                "UPDATE content_video_queue SET status = ?, started_at = ? WHERE request_id = ?",
                (VideoStatus.PROCESSING.value, now_iso(), request_id),
            )
            self.conn.commit()

            provider_cls = PROVIDER_CLASSES[provider_name]
            api_key = self._get_api_key(provider_name)
            if not api_key:
                self._mark_failed(request_id, f"No API key for provider: {provider_name}")
                continue

            provider = provider_cls(provider_name, api_key, self._get_provider_config(provider_name))
            try:
                result = await provider.generate_video(prompt, **params)
                if result["status"] == VideoStatus.QUEUED.value:
                    final = await self._poll_job(provider, result["job_id"], request_id)
                    if final["status"] == VideoStatus.COMPLETED.value:
                        self._mark_completed(request_id, provider_name, result["job_id"], final)
                        self._update_budget(final.get("cost_usd", 0))
                        processed += 1
                    else:
                        self._mark_failed(request_id, final.get("error", "Generation failed"))
                else:
                    self._mark_failed(request_id, result.get("error", "Generation failed"))
            except Exception as e:
                self._mark_failed(request_id, str(e))
            finally:
                await provider.close()

        return {"processed": processed, "message": f"Processed {processed} items"}

    async def _poll_job(self, provider: VideoProvider, job_id: str, request_id: str, timeout: int = 300, interval: int = 5) -> Dict:
        start = datetime.now()
        while (datetime.now() - start).seconds < timeout:
            await asyncio.sleep(interval)
            result = await provider.get_status(job_id)
            if result["status"] in (VideoStatus.COMPLETED.value, VideoStatus.FAILED.value, VideoStatus.CANCELLED.value):
                return result
        return {"status": VideoStatus.FAILED.value, "error": "Timeout waiting for completion"}

    def _mark_completed(self, request_id: str, provider: str, job_id: str, result: Dict):
        self.conn.execute(
            "UPDATE content_video_queue SET status = ?, completed_at = ?, result_json = ? WHERE request_id = ?",
            (VideoStatus.COMPLETED.value, now_iso(), json.dumps(result), request_id),
        )
        self.conn.execute(
            "INSERT INTO content_video_generations (request_id, provider, job_id, prompt, video_url, thumbnail_url, duration, duration_seconds, cost_usd, status, metadata_json, created_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                request_id,
                provider,
                job_id,
                self.conn.execute(
                    "SELECT prompt FROM content_video_queue WHERE request_id = ?", (request_id,)
                ).fetchone()["prompt"],
                result.get("video_url"),
                result.get("thumbnail_url"),
                result.get("duration"),
                result.get("duration"),
                result.get("cost_usd", 0),
                VideoStatus.COMPLETED.value,
                json.dumps(result.get("metadata", {})),
                self.conn.execute(
                    "SELECT created_at FROM content_video_queue WHERE request_id = ?", (request_id,)
                ).fetchone()["created_at"],
                now_iso(),
            ),
        )
        self.conn.commit()
        self.log("generation", f"Video completed: {request_id}", {"request_id": request_id, "video_url": result.get("video_url")})

    def _mark_failed(self, request_id: str, error: str):
        self.conn.execute("UPDATE content_video_queue SET status = ?, error = ?, completed_at = ? WHERE request_id = ?", (VideoStatus.FAILED.value, error, now_iso(), request_id))
        self.conn.commit()
        self.log("error", f"Video failed: {request_id}", {"request_id": request_id, "error": error})

    def _get_budget(self) -> Dict:
        today = datetime.now().date().isoformat()
        row = self.conn.execute("SELECT * FROM content_budget WHERE date = ?", (today,)).fetchone()
        if not row:
            return {"daily_spent_usd": 0, "monthly_spent_usd": 0, "daily_limit_usd": 10, "monthly_limit_usd": 200, "daily_remaining_usd": 10, "monthly_remaining_usd": 200, "per_video_max_usd": 2.0}
        return {
            "daily_spent_usd": row["daily_spent_usd"],
            "monthly_spent_usd": row["monthly_spent_usd"],
            "daily_limit_usd": row["daily_limit_usd"],
            "monthly_limit_usd": row["monthly_limit_usd"],
            "daily_remaining_usd": row["daily_limit_usd"] - row["daily_spent_usd"],
            "monthly_remaining_usd": row["monthly_limit_usd"] - row["monthly_spent_usd"],
            "per_video_max_usd": 2.0,
        }

    def _update_budget(self, cost: float):
        today = datetime.now().date().isoformat()
        self.conn.execute(
            "INSERT INTO content_budget (date, daily_spent_usd, monthly_spent_usd, daily_limit_usd, monthly_limit_usd, updated_at) VALUES (?, ?, ?, 10, 200, ?) ON CONFLICT(date) DO UPDATE SET daily_spent_usd = daily_spent_usd + ?, monthly_spent_usd = monthly_spent_usd + ?, updated_at = ?",
            (today, cost, cost, now_iso(), cost, cost, now_iso()),
        )
        self.conn.commit()

    def _get_api_key(self, provider: str) -> Optional[str]:
        import os
        env_map = {
            "kling": "KLING_API_KEY",
            "pika": "PIKA_API_KEY",
            "runway": "RUNWAY_API_KEY",
            "heygen": "HEYGEN_API_KEY",
        }
        env_name = env_map.get((provider or "").lower())
        if env_name:
            val = os.environ.get(env_name, "").strip()
            if val:
                return val
        # Fallback: agent_config table / video_config.json
        try:
            from city.orchestrator import AgentConfig
            cfg = AgentConfig(self.name)
            for key in (f"{provider}_api_key", f"{provider}_key", env_name or ""):
                if not key:
                    continue
                val = cfg.get(key)
                if val:
                    return str(val).strip()
        except Exception:
            pass
        cfg = self._get_provider_config(provider)
        return (cfg.get("api_key") or cfg.get("key") or None)

    def _get_provider_config(self, provider: str) -> Dict:
        config_path = Path(__file__).parent.parent / "config" / "video_config.json"
        if config_path.exists():
            with open(config_path) as f:
                data = json.load(f)
                return data.get("video_generation", {}).get("providers", {}).get(provider, {})
        return {}

    async def _estimate_cost(self, provider: str, params: Dict) -> float:
        api_key = self._get_api_key(provider)
        if not api_key:
            return 0.0
        provider_cls = PROVIDER_CLASSES[provider]
        prov = provider_cls(provider, api_key, self._get_provider_config(provider))
        cost = await prov.estimate_cost(params)
        await prov.close()
        return cost

    def _status(self):
        queue = self._queue_status()
        budget = self._show_budget()
        stats = self._stats()
        return {"queue": queue, "budget": budget["budget"], "stats": stats["stats"]}

    def work(self):
        stats = self._stats()["stats"]
        if stats["queued"] > 0:
            providers_needed = self.conn.execute(
                "SELECT DISTINCT provider FROM content_video_queue WHERE status='queued'"
            ).fetchall()
            missing = [r["provider"] for r in providers_needed if not self._get_api_key(r["provider"])]
            if missing:
                self.log(
                    "tick",
                    f"queue blocked: missing API keys for {', '.join(sorted(set(missing)))}",
                )
            else:
                try:
                    result = self._process_queue()
                    self.log("tick", f"processed queue: {result}")
                except Exception as exc:
                    self.log("error", f"queue process failed: {exc}")
        elif stats["processing"] > 0:
            self.log(
                "tick",
                f"queue: {stats['processing']} processing, {stats['completed']} completed",
            )

    def report(self):
        budget = self._get_budget()
        stats = self._stats()["stats"]
        return {
            "department": self.name,
            "subject": self.subject,
            "queue_pending": stats["queued"],
            "queue_processing": stats["processing"],
            "completed_today": stats["completed"],
            "failed_today": stats["failed"],
            "total_cost_usd": stats["total_cost_usd"],
            "daily_budget_remaining_usd": budget["daily_remaining_usd"],
            "monthly_budget_remaining_usd": budget["monthly_remaining_usd"],
        }