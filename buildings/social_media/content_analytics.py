"""
Content Analytics Department — Internal component of Media Building.
Viral intelligence, video performance/ROI tracking, budget alerts, cost reports.
"""
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import Counter

from city.department import Department as BaseAgent
from city.db import now_iso, log_event, set_status


class ViralIntelligence:
    def __init__(self, conn):
        self.conn = conn

    async def analyze_and_optimize(self, current_strategy: Dict, platforms: List[str] = None) -> Dict:
        if platforms is None:
            platforms = ["instagram", "tiktok", "twitter"]
        viral_data = await self._gather_viral_data(platforms)
        patterns = self._analyze_patterns(viral_data)
        insights = await self._generate_ai_insights(patterns, current_strategy)
        optimized = self._create_optimized_strategy(current_strategy, patterns, insights)
        for insight in insights:
            self._save_insight(insight)
        return {"optimized_strategy": optimized, "patterns": patterns, "insights": insights}

    async def get_content_recommendations(self, niche: str = "lifestyle", platform: str = "instagram") -> List[Dict]:
        """Heuristic recommendations from stored viral/video data (no external API required)."""
        strategy = {"niche": niche, "target_audience": "general", "content_plan": {"themes": [niche]}}
        result = await self.analyze_and_optimize(strategy, platforms=[platform])
        patterns = result.get("patterns") or {}
        recs = []
        ct = patterns.get("content_types") or {}
        if ct.get("recommendation"):
            recs.append({"type": "content_type", "platform": platform, "niche": niche, "text": ct["recommendation"]})
        timing = patterns.get("optimal_timing") or {}
        if timing.get("recommendation"):
            recs.append({"type": "timing", "platform": platform, "niche": niche, "text": timing["recommendation"]})
        tags = patterns.get("hashtag_patterns") or {}
        if tags.get("recommendation"):
            recs.append({"type": "hashtags", "platform": platform, "niche": niche, "text": tags["recommendation"]})
        for insight in (result.get("insights") or [])[:5]:
            if isinstance(insight, dict):
                recs.append({
                    "type": "insight",
                    "platform": platform,
                    "niche": niche,
                    "text": insight.get("recommendation") or insight.get("pattern") or str(insight),
                })
        if not recs:
            recs.append({
                "type": "default",
                "platform": platform,
                "niche": niche,
                "text": f"Seed viral_content / content_video_generations data, then re-run recommendations for {niche} on {platform}.",
            })
        return recs

    async def _gather_viral_data(self, platforms: List[str]) -> Dict:
        data = {"content": [], "hashtags": [], "stats": {}}
        for platform in platforms:
            rows = self.conn.execute(
                "SELECT * FROM viral_content WHERE platform = ? ORDER BY engagement_rate DESC LIMIT 50",
                (platform,),
            ).fetchall()
            data["content"].extend([dict(r) for r in rows])
            tags = self.conn.execute(
                "SELECT * FROM trending_hashtags WHERE platform = ? ORDER BY avg_engagement_rate DESC LIMIT 30",
                (platform,),
            ).fetchall()
            data["hashtags"].extend([dict(r) for r in tags])
            stats = self.conn.execute(
                "SELECT * FROM viral_stats WHERE platform = ? AND date >= ?",
                (platform, (datetime.now() - timedelta(days=7)).isoformat()),
            ).fetchall()
            data["stats"][platform] = [dict(r) for r in stats]
        return data

    def _analyze_patterns(self, viral_data: Dict) -> Dict:
        return {
            "content_types": self._analyze_content_types(viral_data["content"]),
            "optimal_timing": self._analyze_posting_times(viral_data["content"]),
            "hashtag_patterns": self._analyze_hashtag_patterns(viral_data["hashtags"]),
            "caption_length": self._analyze_caption_length(viral_data["content"]),
            "engagement_drivers": self._identify_engagement_drivers(viral_data["content"]),
            "trending_topics": self._extract_trending_topics(viral_data["content"]),
            "platform_performance": self._analyze_platform_performance(viral_data["stats"]),
        }

    def _analyze_content_types(self, content: List[Dict]) -> Dict:
        type_perf = {}
        for item in content:
            ctype = item.get("content_type", item.get("type", "unknown"))
            type_perf.setdefault(ctype, {"count": 0, "total_engagement": 0})
            type_perf[ctype]["count"] += 1
            type_perf[ctype]["total_engagement"] += item.get("engagement_rate", 0)
        for ctype in type_perf:
            c = type_perf[ctype]["count"]
            type_perf[ctype]["avg_engagement"] = type_perf[ctype]["total_engagement"] / c if c else 0
        sorted_types = sorted(type_perf.items(), key=lambda x: x[1]["avg_engagement"], reverse=True)
        return {"performance": dict(sorted_types), "top_type": sorted_types[0][0] if sorted_types else "video", "recommendation": self._content_type_rec(sorted_types)}

    def _content_type_rec(self, sorted_types: List) -> str:
        if not sorted_types:
            return "Create varied content types"
        top_type, data = sorted_types[0]
        if data["avg_engagement"] > 10:
            return f"Focus heavily on {top_type} content (very high engagement)"
        elif data["avg_engagement"] > 5:
            return f"Prioritize {top_type} content (strong engagement)"
        return f"Include more {top_type} content in mix"

    def _analyze_posting_times(self, content: List[Dict]) -> Dict:
        hourly = {}
        for item in content:
            if item.get("posted_at"):
                try:
                    dt = datetime.fromisoformat(item["posted_at"].replace("Z", "+00:00"))
                    hour = dt.hour
                    hourly.setdefault(hour, {"count": 0, "total_engagement": 0})
                    hourly[hour]["count"] += 1
                    hourly[hour]["total_engagement"] += item.get("engagement_rate", 0)
                except Exception:
                    pass
        for hour in hourly:
            c = hourly[hour]["count"]
            hourly[hour]["avg_engagement"] = hourly[hour]["total_engagement"] / c if c else 0
        sorted_hours = sorted(hourly.items(), key=lambda x: x[1].get("avg_engagement", 0), reverse=True)
        top_hours = [f"{h:02d}:00" for h, _ in sorted_hours[:3]]
        if top_hours:
            rec = f"Post at {', '.join(top_hours)} for maximum engagement"
        else:
            rec = "Not enough posted_at data to recommend timing"
        return {"hourly_performance": hourly, "top_posting_times": top_hours, "recommendation": rec}

    def _analyze_hashtag_patterns(self, hashtags: List[Dict]) -> Dict:
        top_usage = sorted(hashtags, key=lambda x: x.get("usage_count", 0), reverse=True)[:10]
        top_eng = sorted(hashtags, key=lambda x: x.get("avg_engagement_rate", 0), reverse=True)[:10]
        usage_set = {h["hashtag"] for h in top_usage}
        eng_set = {h["hashtag"] for h in top_eng}
        sweet = [h for h in hashtags if h["hashtag"] in usage_set & eng_set]
        return {"top_by_usage": [h["hashtag"] for h in top_usage], "top_by_engagement": [h["hashtag"] for h in top_eng], "sweet_spot": [h["hashtag"] for h in sweet], "recommendation": f"Use hashtags: {', '.join(['#' + h['hashtag'] for h in sweet[:5]])}"}

    def _analyze_caption_length(self, content: List[Dict]) -> Dict:
        buckets = {"short": {"range": (0, 100), "engagement": [], "count": 0}, "medium": {"range": (100, 300), "engagement": [], "count": 0}, "long": {"range": (300, 1000), "engagement": [], "count": 0}}
        for item in content:
            caption = item.get("caption", "")
            length = len(caption)
            eng = item.get("engagement_rate", 0)
            if length < 100:
                buckets["short"]["engagement"].append(eng)
                buckets["short"]["count"] += 1
            elif length < 300:
                buckets["medium"]["engagement"].append(eng)
                buckets["medium"]["count"] += 1
            else:
                buckets["long"]["engagement"].append(eng)
                buckets["long"]["count"] += 1
        for b in buckets.values():
            b["avg_engagement"] = sum(b["engagement"]) / len(b["engagement"]) if b["engagement"] else 0
        best = max(buckets.items(), key=lambda x: x[1]["avg_engagement"])
        return {"performance_by_length": buckets, "optimal_length": best[0], "recommendation": f"Use {best[0]} captions ({best[1]['range'][0]}-{best[1]['range'][1]} chars)"}

    def _identify_engagement_drivers(self, content: List[Dict]) -> Dict:
        drivers = {"has_call_to_action": {"yes": [], "no": []}, "uses_emojis": {"yes": [], "no": []}, "asks_question": {"yes": [], "no": []}}
        for item in content:
            cap = item.get("caption", "").lower()
            eng = item.get("engagement_rate", 0)
            drivers["has_call_to_action"]["yes" if any(w in cap for w in ["click", "link", "bio", "comment", "share", "tag"]) else "no"].append(eng)
            drivers["uses_emojis"]["yes" if any(ord(c) > 127 for c in cap) else "no"].append(eng)
            drivers["asks_question"]["yes" if "?" in cap else "no"].append(eng)
        impact = {}
        for d, v in drivers.items():
            yes_avg = sum(v["yes"]) / len(v["yes"]) if v["yes"] else 0
            no_avg = sum(v["no"]) / len(v["no"]) if v["no"] else 0
            impact[d] = {"with": yes_avg, "without": no_avg, "impact": yes_avg - no_avg, "recommendation": "Include" if yes_avg > no_avg else "Optional"}
        return impact

    def _extract_trending_topics(self, content: List[Dict]) -> List[str]:
        words = []
        for item in content:
            cap = item.get("caption", "")
            words.extend([w.lower() for w in cap.split() if len(w) > 4 and not w.startswith("#")])
        counts = Counter(words)
        return [w for w, c in counts.most_common(20) if c > 5]

    def _analyze_platform_performance(self, stats: Dict) -> Dict:
        if not stats:
            return {"stats": {}, "top_platform": "instagram", "recommendation": "Focus on Instagram"}

        def _score(val):
            if isinstance(val, dict):
                return float(val.get("avg_engagement", 0) or 0)
            if isinstance(val, list) and val:
                engs = []
                for row in val:
                    if isinstance(row, dict):
                        engs.append(float(row.get("avg_engagement", 0) or 0))
                return sum(engs) / len(engs) if engs else 0.0
            return 0.0

        top = max(stats.items(), key=lambda x: _score(x[1]))[0]
        return {"stats": stats, "top_platform": top, "recommendation": f"Focus more content on {top}"}

    async def _generate_ai_insights(self, patterns: Dict, current_strategy: Dict) -> List[Dict]:
        openai_key = self._get_openai_key()
        if not openai_key:
            return self._rule_based_insights(patterns)
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            prompt = f"""Analyze viral content data and provide 5 actionable insights:
PATTERNS:
- Top Content Type: {patterns['content_types']['top_type']}
- Best Posting Times: {', '.join(patterns['optimal_timing']['top_posting_times'])}
- Trending Hashtags: {', '.join(patterns['hashtag_patterns']['sweet_spot'][:5])}
- Optimal Caption Length: {patterns['caption_length']['optimal_length']}
- Trending Topics: {', '.join(patterns['trending_topics'][:10])}

CURRENT STRATEGY:
- Niche: {current_strategy.get('niche', 'lifestyle')}
- Target: {current_strategy.get('target_audience', 'general')}
- Themes: {', '.join(current_strategy.get('content_plan', {}).get('themes', []))}

Return JSON: [{{"type": "...", "pattern": "...", "confidence": 0.9, "recommendation": "..."}}]"""
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a social media strategy expert."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1000,
                temperature=0.7,
            )
            try:
                parsed = json.loads(resp.choices[0].message.content.strip())
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass
            return self._rule_based_insights(patterns)
        except Exception:
            return self._rule_based_insights(patterns)

    def _rule_based_insights(self, patterns: Dict) -> List[Dict]:
        drivers = patterns.get("engagement_drivers") or {}
        if drivers:
            top_driver = max(drivers.items(), key=lambda x: x[1].get("impact", 0))[0]
            driver_rec = f"Include {top_driver.replace('_', ' ')}"
            driver_pattern = f"Content with '{top_driver}' shows higher engagement"
        else:
            top_driver = "call to action"
            driver_rec = "Include a clear call to action"
            driver_pattern = "No engagement-driver data yet"
        return [
            {"type": "content_type", "platform": "all", "pattern": f"'{patterns['content_types']['top_type']}' content performs best", "confidence": 0.8, "recommendation": patterns['content_types']['recommendation']},
            {"type": "timing", "platform": "all", "pattern": "Optimal posting times identified", "confidence": 0.75, "recommendation": patterns['optimal_timing']['recommendation']},
            {"type": "hashtags", "platform": "all", "pattern": "High-performing hashtags identified", "confidence": 0.85, "recommendation": patterns['hashtag_patterns']['recommendation']},
            {"type": "caption", "platform": "all", "pattern": f"'{patterns['caption_length']['optimal_length']}' captions drive more engagement", "confidence": 0.7, "recommendation": patterns['caption_length']['recommendation']},
            {"type": "engagement", "platform": "all", "pattern": driver_pattern, "confidence": 0.8, "recommendation": driver_rec},
        ]

    def _create_optimized_strategy(self, current: Dict, patterns: Dict, insights: List[Dict]) -> Dict:
        optimized = current.copy()
        optimized.setdefault("content_plan", {})
        optimized["content_plan"]["content_mix"] = self._optimize_mix(patterns["content_types"]["top_type"])
        optimized.setdefault("platforms", {})
        for p in ["instagram", "twitter", "tiktok"]:
            optimized["platforms"].setdefault(p, {})["optimal_times"] = patterns["optimal_timing"]["top_posting_times"]
        optimized["hashtag_strategy"] = {"recommended_hashtags": patterns["hashtag_patterns"]["sweet_spot"][:15], "count_per_platform": {"instagram": 20, "twitter": 5, "tiktok": 10}}
        trending = patterns["trending_topics"][:5]
        current_themes = optimized.get("content_plan", {}).get("themes", [])
        optimized["content_plan"]["themes"] = trending + [t for t in current_themes if t not in trending][:7]
        optimized["optimized_at"] = now_iso()
        optimized["optimization_source"] = "viral_intelligence"
        optimized["insights_applied"] = len(insights)
        optimized["confidence_score"] = sum(i.get("confidence", 0) for i in insights) / len(insights) if insights else 0
        return optimized

    def _optimize_mix(self, top_type: str) -> Dict:
        if top_type in ("video", "reel"):
            return {"video": 0.5, "carousel": 0.3, "image": 0.2}
        if top_type == "carousel":
            return {"carousel": 0.5, "video": 0.3, "image": 0.2}
        return {"image": 0.4, "video": 0.3, "carousel": 0.3}

    def _save_insight(self, insight: Dict):
        self.conn.execute(
            "INSERT INTO content_insights (type, platform, niche, pattern, confidence, recommendation, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (insight.get("type"), insight.get("platform", "all"), insight.get("niche"), insight.get("pattern"), insight.get("confidence", 0), insight.get("recommendation"), now_iso()),
        )
        self.conn.commit()

    def _get_openai_key(self) -> Optional[str]:
        row = self.conn.execute("SELECT value FROM config WHERE key = 'openai_key'").fetchone()
        return row["value"] if row else None


class VideoAnalytics:
    def __init__(self, conn):
        self.conn = conn

    def get_cost_summary(self, days: int = 30) -> Dict:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        agg = self.conn.execute(
            "SELECT COUNT(*) as total, COALESCE(SUM(cost_usd),0) as cost, COALESCE(AVG(cost_usd),0) as avg_cost FROM content_video_generations WHERE created_at >= ?",
            (cutoff,),
        ).fetchone()
        providers = self.conn.execute(
            "SELECT provider, COUNT(*) as vids, COALESCE(SUM(cost_usd),0) as cost, AVG(CASE WHEN status='completed' THEN 1 ELSE 0 END) as success_rate FROM content_video_generations WHERE created_at >= ? GROUP BY provider",
            (cutoff,),
        ).fetchall()
        return {"period_days": days, "total_videos": agg["total"], "total_cost_usd": round(agg["cost"], 2), "avg_cost_per_video": round(agg["avg_cost"], 2), "by_provider": {r["provider"]: {"videos": r["vids"], "cost": round(r["cost"], 2), "success_rate": round(r["success_rate"], 2)} for r in providers}}

    def get_performance_metrics(self, days: int = 30) -> Dict:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        try:
            agg = self.conn.execute(
                "SELECT COUNT(*) as total, "
                "SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed, "
                "SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed, "
                "COALESCE(AVG(engagement_rate),0) as avg_eng, "
                "COALESCE(AVG(COALESCE(duration_seconds, duration)),0) as avg_dur "
                "FROM content_video_generations WHERE created_at >= ?",
                (cutoff,),
            ).fetchone()
        except Exception:
            agg = self.conn.execute(
                "SELECT COUNT(*) as total, "
                "SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed, "
                "SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed, "
                "0 as avg_eng, 0 as avg_dur "
                "FROM content_video_generations WHERE created_at >= ?",
                (cutoff,),
            ).fetchone()
        providers = self.conn.execute(
            "SELECT provider, AVG(CASE WHEN status='completed' THEN 1 ELSE 0 END) as success_rate, COALESCE(AVG(cost_usd),0) as avg_cost, COUNT(*) as total, MAX(created_at) as last_used FROM content_video_generations WHERE created_at >= ? GROUP BY provider",
            (cutoff,),
        ).fetchall()
        comp = [{"provider": r["provider"], "success_rate": round(r["success_rate"], 2), "avg_cost": round(r["avg_cost"], 2), "total_videos": r["total"], "last_used": r["last_used"]} for r in providers]
        comp.sort(key=lambda x: x["success_rate"], reverse=True)
        return {"period_days": days, "total_videos": agg["total"], "completed_videos": agg["completed"] or 0, "failed_videos": agg["failed"] or 0, "success_rate": round((agg["completed"] or 0) / agg["total"] * 100, 1) if agg["total"] else 0, "avg_engagement": round(agg["avg_eng"] or 0, 4), "avg_duration": round(agg["avg_dur"] or 0, 1), "provider_comparison": comp}

    def check_budget_alerts(self, daily_limit: float, monthly_limit: float, current_daily: float, current_monthly: float) -> List[Dict]:
        alerts = []
        daily_pct = (current_daily / daily_limit * 100) if daily_limit else 0
        if daily_pct >= 90:
            alerts.append({"type": "critical", "message": f"Daily budget at {daily_pct:.1f}% (${current_daily:.2f}/${daily_limit:.2f})", "timestamp": now_iso()})
        elif daily_pct >= 75:
            alerts.append({"type": "warning", "message": f"Daily budget at {daily_pct:.1f}% (${current_daily:.2f}/${daily_limit:.2f})", "timestamp": now_iso()})
        monthly_pct = (current_monthly / monthly_limit * 100) if monthly_limit else 0
        if monthly_pct >= 90:
            alerts.append({"type": "critical", "message": f"Monthly budget at {monthly_pct:.1f}% (${current_monthly:.2f}/${monthly_limit:.2f})", "timestamp": now_iso()})
        elif monthly_pct >= 75:
            alerts.append({"type": "warning", "message": f"Monthly budget at {monthly_pct:.1f}% (${current_monthly:.2f}/${monthly_limit:.2f})", "timestamp": now_iso()})
        return alerts

    def generate_cost_report(self, days: int = 30) -> str:
        cost = self.get_cost_summary(days)
        perf = self.get_performance_metrics(days)
        recs = self._generate_recommendations(cost, perf)
        report = {"generated_at": now_iso(), "period_days": days, "cost_summary": cost, "performance_metrics": perf, "recommendations": recs}
        path = Path("data/reports/video_analytics")
        path.mkdir(parents=True, exist_ok=True)
        filename = f"video_cost_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = path / filename
        filepath.write_text(json.dumps(report, indent=2))
        return str(filepath)

    def _generate_recommendations(self, cost: Dict, perf: Dict) -> List[str]:
        recs = []
        if cost.get("total_cost_usd", 0) > 150:
            recs.append("Consider using free tier providers (Kling) for non-critical content to reduce costs")
        if perf.get("success_rate", 0) < 80:
            recs.append(f"Success rate is {perf['success_rate']:.1f}%. Review failed generations and adjust prompts/providers")
        best = None
        best_rate = 0
        for p in perf.get("provider_comparison", []):
            if p["success_rate"] > best_rate:
                best_rate = p["success_rate"]
                best = p["provider"]
        if best and best_rate > 90:
            recs.append(f"Provider '{best}' has best success rate ({best_rate:.1f}%). Prioritize for important content")
        if 0 < perf.get("avg_engagement", 0) < 0.03:
            recs.append(f"Average engagement {perf['avg_engagement']:.2%}. Consider A/B testing different video styles")
        return recs

    def get_roi_analysis(self, days: int = 30) -> Dict:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        agg = self.conn.execute(
            "SELECT COALESCE(SUM(cost_usd),0) as cost, COUNT(*) as total FROM content_video_generations WHERE created_at >= ?",
            (cutoff,),
        ).fetchone()
        try:
            videos = self.conn.execute(
                "SELECT COALESCE(views,0) as views, COALESCE(engagement_rate,0) as engagement_rate "
                "FROM content_video_generations WHERE status='completed' AND created_at >= ?",
                (cutoff,),
            ).fetchall()
            total_eng = sum((v["views"] or 0) * (v["engagement_rate"] or 0) for v in videos)
        except Exception:
            total_eng = 0
        value_per_eng = 0.05
        est_value = total_eng * value_per_eng
        roi = ((est_value - agg["cost"]) / agg["cost"] * 100) if agg["cost"] else 0
        return {
            "period_days": days,
            "total_cost": round(agg["cost"], 2),
            "total_videos": agg["total"],
            "total_engagement": int(total_eng),
            "estimated_value": round(est_value, 2),
            "roi_percentage": round(roi, 1),
            "cost_per_engagement": round(agg["cost"] / total_eng, 4) if total_eng else 0,
        }

    def get_trending_video_insights(self, limit: int = 10) -> List[Dict]:
        try:
            videos = self.conn.execute(
                "SELECT * FROM content_video_generations WHERE status='completed' "
                "ORDER BY COALESCE(views,0) * COALESCE(engagement_rate,0) DESC LIMIT ?",
                (limit,),
            ).fetchall()
        except Exception:
            videos = self.conn.execute(
                "SELECT * FROM content_video_generations WHERE status='completed' ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for v in videos:
            keys = v.keys()
            dur = v["duration_seconds"] if "duration_seconds" in keys else None
            if dur is None and "duration" in keys:
                dur = v["duration"]
            views = v["views"] if "views" in keys else 0
            eng = v["engagement_rate"] if "engagement_rate" in keys else 0
            out.append({
                "job_id": v["job_id"],
                "provider": v["provider"],
                "views": views or 0,
                "engagement_rate": eng or 0,
                "engagement_count": int((views or 0) * (eng or 0)),
                "cost": v["cost_usd"],
                "duration": dur,
                "created_at": v["created_at"],
                "prompt_preview": (v["prompt"] or "")[:100],
            })
        return out


class ContentAnalyticsDepartment(BaseAgent):
    name = "content_analytics"
    subject = "Content Analytics Dept"
    district = "Media District"
    color = "#6a1b9a"

    def setup_schema(self):
        self.conn.execute("""CREATE TABLE IF NOT EXISTS viral_content (id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT, content_type TEXT, caption TEXT, engagement_rate REAL, views INTEGER, likes INTEGER, comments INTEGER, shares INTEGER, posted_at TEXT, hashtags TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS trending_hashtags (id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT, hashtag TEXT, usage_count INTEGER, avg_engagement_rate REAL, date TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS viral_stats (id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT, date TEXT, total_posts INTEGER, avg_engagement REAL, top_content_type TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS content_insights (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT, platform TEXT, niche TEXT, pattern TEXT, confidence REAL, recommendation TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS content_video_generations (id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT, job_id TEXT, provider TEXT, prompt TEXT, status TEXT, video_url TEXT, thumbnail_url TEXT, duration_seconds INTEGER, cost_usd REAL, views INTEGER DEFAULT 0, likes INTEGER DEFAULT 0, comments INTEGER DEFAULT 0, shares INTEGER DEFAULT 0, engagement_rate REAL DEFAULT 0, metadata TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, completed_at TEXT)""")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)""")
        # Unify columns if automation created the table first (duration / metadata_json only)
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(content_video_generations)").fetchall()}
        for col, decl in (
            ("duration_seconds", "INTEGER"),
            ("duration", "INTEGER"),
            ("views", "INTEGER DEFAULT 0"),
            ("likes", "INTEGER DEFAULT 0"),
            ("comments", "INTEGER DEFAULT 0"),
            ("shares", "INTEGER DEFAULT 0"),
            ("engagement_rate", "REAL DEFAULT 0"),
            ("metadata", "TEXT"),
            ("metadata_json", "TEXT"),
        ):
            if col not in cols:
                try:
                    self.conn.execute(f"ALTER TABLE content_video_generations ADD COLUMN {col} {decl}")
                except Exception:
                    pass
        self.conn.commit()

    def register_rules(self):
        self.rule(r"^analyze strategy$")(self._analyze_strategy)
        self.rule(r"^optimize strategy$")(self._optimize_strategy)
        self.rule(r"^viral insights$")(self._viral_insights)
        self.rule(r"^video cost summary(?:\s+(?P<days>\d+))?$")(self._video_cost_summary)
        self.rule(r"^video performance(?:\s+(?P<days>\d+))?$")(self._video_performance)
        self.rule(r"^budget alerts?$")(self._budget_alerts)
        self.rule(r"^cost report(?:\s+(?P<days>\d+))?$")(self._cost_report)
        self.rule(r"^roi analysis(?:\s+(?P<days>\d+))?$")(self._roi_analysis)
        self.rule(r"^trending videos?(?:\s+(?P<limit>\d+))?$")(self._trending_videos)
        self.rule(r"^recommendations?(?:\s+(?P<niche>\w+))?(?:\s+(?P<platform>\w+))?$")(self._recommendations)
        self.rule(r"^status$")(self._status)

    def _analyze_strategy(self):
        viral = ViralIntelligence(self.conn)
        strat = self._get_current_strategy()
        result = asyncio.run(viral.analyze_and_optimize(strat))
        return {"optimized_strategy": result["optimized_strategy"], "insights": result["insights"], "patterns": result["patterns"]}

    def _optimize_strategy(self):
        return self._analyze_strategy()

    def _viral_insights(self):
        viral = ViralIntelligence(self.conn)
        data = asyncio.run(viral._gather_viral_data(["instagram", "tiktok", "twitter"]))
        patterns = viral._analyze_patterns(data)
        return {"patterns": patterns, "insights": asyncio.run(viral._generate_ai_insights(patterns, self._get_current_strategy()))}

    def _video_cost_summary(self, days="30"):
        va = VideoAnalytics(self.conn)
        return va.get_cost_summary(int(days))

    def _video_performance(self, days="30"):
        va = VideoAnalytics(self.conn)
        return va.get_performance_metrics(int(days))

    def _budget_alerts(self):
        va = VideoAnalytics(self.conn)
        budget = self._get_budget()
        return va.check_budget_alerts(budget["daily_limit"], budget["monthly_limit"], budget["daily_spent"], budget["monthly_spent"])

    def _cost_report(self, days="30"):
        va = VideoAnalytics(self.conn)
        return {"report_path": va.generate_cost_report(int(days))}

    def _roi_analysis(self, days="30"):
        va = VideoAnalytics(self.conn)
        return va.get_roi_analysis(int(days))

    def _trending_videos(self, limit="10"):
        va = VideoAnalytics(self.conn)
        return {"trending_videos": va.get_trending_video_insights(int(limit))}

    def _recommendations(self, niche="lifestyle", platform="instagram"):
        viral = ViralIntelligence(self.conn)
        return {"recommendations": asyncio.run(viral.get_content_recommendations(niche, platform))}

    def _status(self):
        va = VideoAnalytics(self.conn)
        viral = ViralIntelligence(self.conn)
        cost = va.get_cost_summary(7)
        perf = va.get_performance_metrics(7)
        return {"cost_summary_7d": cost, "performance_7d": perf, "queue": self._queue_status()}

    def _get_current_strategy(self) -> Dict:
        row = self.conn.execute("SELECT value FROM config WHERE key = 'content_strategy'").fetchone()
        if row:
            try:
                return json.loads(row["value"])
            except Exception:
                pass
        return {"niche": "lifestyle", "target_audience": "general", "content_plan": {"themes": ["motivation", "lifestyle", "tips"]}}

    def _get_budget(self) -> Dict:
        row = self.conn.execute("SELECT value FROM config WHERE key = 'video_budget'").fetchone()
        if row:
            try:
                return json.loads(row["value"])
            except Exception:
                pass
        return {"daily_limit": 10.0, "monthly_limit": 200.0, "daily_spent": 0.0, "monthly_spent": 0.0}

    def _queue_status(self) -> Dict:
        rows = self.conn.execute("SELECT status, COUNT(*) as c FROM content_video_generations WHERE created_at >= ? GROUP BY status", ((datetime.now() - timedelta(days=1)).isoformat(),)).fetchall()
        return {r["status"]: r["c"] for r in rows}

    def work(self):
        cost = VideoAnalytics(self.conn).get_cost_summary(1)
        self.log("tick", f"{cost['total_videos']} videos, ${cost['total_cost_usd']:.0f} cost")

    def report(self):
        va = VideoAnalytics(self.conn)
        cost = va.get_cost_summary(30)
        perf = va.get_performance_metrics(30)
        roi = va.get_roi_analysis(30)
        return {"department": self.name, "subject": self.subject, "period_days": 30, "total_videos": cost["total_videos"], "total_cost_usd": cost["total_cost_usd"], "success_rate": perf["success_rate"], "avg_engagement": perf["avg_engagement"], "roi_percentage": roi["roi_percentage"], "top_provider": perf["provider_comparison"][0]["provider"] if perf["provider_comparison"] else "none"}