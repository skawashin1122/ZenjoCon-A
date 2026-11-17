"""定期的に動く処理：見守り判定（5分ごと）と地震監視（1分ごと）。"""
from __future__ import annotations

import asyncio
import logging

import httpx

from .config import JMA_FEED_URL, Settings
from .quake import parse_feed, parse_report
from .service import Service, jst_now

log = logging.getLogger("mamorinet.scheduler")


class QuakeWatcher:
    """気象庁の Atom フィードを確認し、新しい「震源・震度に関する情報」を処理する。"""

    def __init__(self, svc: Service, settings: Settings, http: httpx.AsyncClient | None = None):
        self.svc = svc
        self.s = settings
        self.http = http or httpx.AsyncClient(timeout=15.0, headers={"User-Agent": "nichinan-mamorinet/1.0"})
        self.last_modified: str | None = None

    async def poll_once(self) -> int:
        headers = {"If-Modified-Since": self.last_modified} if self.last_modified else {}
        r = await self.http.get(JMA_FEED_URL, headers=headers)
        if r.status_code == 304:
            return 0
        r.raise_for_status()
        self.last_modified = r.headers.get("Last-Modified", self.last_modified)
        sent = 0
        # フィードは新しい順。古いものから処理する
        for entry in reversed(parse_feed(r.content)):
            if self.svc.seen(entry.id):
                continue
            try:
                doc = await self.http.get(entry.url)
                doc.raise_for_status()
                report = parse_report(doc.content, self.s.city_code)
                sent += await self.svc.handle_quake_report(report)
            except Exception:
                log.exception("電文の処理に失敗: %s", entry.url)
                continue  # 既読にしない → 次回もう一度
            self.svc.mark_seen(entry.id, jst_now())
        return sent


async def _loop(name: str, interval: int, fn) -> None:
    while True:
        try:
            await fn()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("%s でエラー", name)
        await asyncio.sleep(interval)


def start_background(svc: Service, settings: Settings) -> list[asyncio.Task]:
    tasks = [asyncio.create_task(_loop("見守り判定", settings.watch_interval, svc.watch_tick))]
    if settings.quake_enabled:
        qw = QuakeWatcher(svc, settings)

        async def quake_all():
            await qw.poll_once()
            await svc.quake_followup()

        tasks.append(asyncio.create_task(_loop("地震監視", settings.quake_interval, quake_all)))
    return tasks
