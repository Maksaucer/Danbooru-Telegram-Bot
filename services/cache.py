import asyncio
import time
import random
import logging
from collections import deque, OrderedDict
from datetime import datetime, timedelta
from typing import Deque, Dict, List, Tuple

from config import (
    CACHE_REFILL_SIZE,
    CACHE_TTL,
    CACHE_MAX_KEYS,
    CACHE_MAX_PAGES,
    GELBOORU_USER_ID,
    GELBOORU_API_KEY,
)
from parsers.gelbooru import fetch_by_tags
from services.filters import is_post_allowed

HARD_BAN_TAGS = {"gore", "feces", "urine"}

def _period_threshold(period: str) -> datetime:
    now = datetime.now()
    if period == "day": return now - timedelta(days=1)
    if period == "week": return now - timedelta(days=7)
    if period == "month": return now - timedelta(days=30)
    return now - timedelta(days=3650)

def _parse_created_at(s: str | None) -> datetime | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%a %b %d %H:%M:%S %z %Y"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt if dt.tzinfo is None else dt.astimezone(tz=None).replace(tzinfo=None)
        except Exception:
            continue
    return None

def build_query_tags(user_filters: List[str], random_order: bool) -> List[str]:
    tags: List[str] = []
    tags += [f"-{t}" for t in sorted({"gore","feces","urine"})]
    fset = {f.lower() for f in user_filters}

    # ТОЛЬКО пользовательский фильтр управляет SFW
    if "nsfw" in fset:
        tags.append("rating:safe")

    if "gay" in fset:
        tags += ["-1boy", "1girl"]

    tags.append("sort:random" if random_order else "sort:score")
    return tags

class Buffer:
    def __init__(self, refill_size: int, ttl_sec: int):
        self.refill_size = refill_size
        self.ttl_sec = ttl_sec
        self.items: Deque[dict] = deque()
        self.expires_at: float = 0.0
        self.lock = asyncio.Lock()

    def expired(self) -> bool:
        return time.time() > self.expires_at

    def put_all(self, posts: List[dict]) -> None:
        random.shuffle(posts)
        self.items = deque(posts)
        self.expires_at = time.time() + self.ttl_sec

    def pop(self) -> dict | None:
        return self.items.pop() if self.items else None

class Cache:
    def __init__(self, refill_size: int, ttl_sec: int, max_keys: int):
        self.refill_size = refill_size
        self.ttl_sec = ttl_sec
        self.max_keys = max_keys
        self.buffers: OrderedDict[Tuple[str, str], Buffer] = OrderedDict()
        self._rate_lock = asyncio.Lock()
        self._last_req_at = 0.0

    def _key(self, period_key: str, filters_key: str) -> Tuple[str, str]:
        return (period_key, filters_key)

    async def _rate_limit(self):
        async with self._rate_lock:
            delta = time.time() - self._last_req_at
            if delta < 1.0:
                await asyncio.sleep(1.0 - delta)
            self._last_req_at = time.time()

    def _get_or_create(self, key: Tuple[str, str]) -> Buffer:
        buf = self.buffers.get(key)
        if buf is None:
            if len(self.buffers) >= self.max_keys:
                self.buffers.popitem(last=False)
            buf = Buffer(self.refill_size, self.ttl_sec)
            self.buffers[key] = buf
        self.buffers.move_to_end(key, last=True)
        return buf

    async def _refill(self, buf: Buffer, user_filters: List[str], period: str, random_order: bool) -> None:
        tags = build_query_tags(user_filters, random_order=random_order)

        # RANDOM: одной страницы обычно хватает
        if random_order:
            await self._rate_limit()
            raw = await fetch_by_tags(tags, limit=self.refill_size)
            filtered = [p for p in raw if is_post_allowed(p, user_filters)]
            logging.info(
                "cache refill: got=%d, after_filter=%d, random=%s, period=%s, tags=%s",
                len(raw), len(filtered), random_order, period, " ".join(tags)
            )
            buf.put_all(filtered)
            return

        # TOP BY PERIOD: постранично собираем свежие посты
        thr = _period_threshold(period)
        collected: List[dict] = []
        pid = 0
        page_limit = max(1, CACHE_MAX_PAGES)

        while len(collected) < self.refill_size and pid < page_limit:
            await self._rate_limit()
            raw = await fetch_by_tags(tags, limit=min(self.refill_size, 100), pid=pid)
            if not raw:
                break

            for p in raw:
                if not is_post_allowed(p, user_filters):
                    continue
                dt = _parse_created_at(p.get("created_at"))
                # если дата не распарсилась — пропускаем (чтобы «день/неделя» были честными)
                if not dt or dt < thr:
                    continue
                collected.append(p)
                if len(collected) >= self.refill_size:
                    break

            pid += 1

        logging.info(
            "cache refill (TOP): pages=%d, collected=%d/%d, period=%s, tags=%s",
            pid, len(collected), self.refill_size, period, " ".join(tags)
        )
        buf.put_all(collected)

    async def get_post(self, user_filters: List[str], period: str = "week", random_order: bool = True) -> dict | None:
        filters_key = ",".join(sorted(map(str.lower, user_filters)))
        key = self._key("random" if random_order else period, filters_key)
        buf = self._get_or_create(key)
        async with buf.lock:
            if buf.expired() or not buf.items:
                await self._refill(buf, user_filters, period, random_order)
                if not buf.items:
                    return None
            post = buf.pop()
            if len(buf.items) < self.refill_size // 3:
                asyncio.create_task(self._refill(buf, user_filters, period, random_order))
            return post
        
    # На всякий случай
    def clear(self):
        self.buffers.clear()

cache = Cache(refill_size=CACHE_REFILL_SIZE, ttl_sec=CACHE_TTL, max_keys=CACHE_MAX_KEYS)