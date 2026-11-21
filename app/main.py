"""FastAPI アプリ本体。

起動：uvicorn app.main:app --host 127.0.0.1 --port 8000
（本番は Nginx が HTTPS を受け、/callback だけをここへ転送する。設計書 4-1）
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import BASE_DIR, Settings
from .db import connect
from .line_api import DryRunClient, LineClient, verify_signature
from .scheduler import start_background
from .service import Service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("mamorinet")


def create_app(settings: Settings | None = None, service: Service | None = None,
               background: bool = True) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if service is None:
            conn = connect(settings.db_path)
            line = DryRunClient(conn) if settings.dry_run else LineClient(settings.channel_access_token)
            app.state.svc = Service(conn, line, settings)
        else:
            app.state.svc = service
        if settings.dry_run:
            log.warning("LINE_CHANNEL_ACCESS_TOKEN が未設定：ドライラン（送信せず outbox に記録）で動きます")
        tasks = start_background(app.state.svc, settings) if background else []
        yield
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if hasattr(app.state.svc.line, "aclose"):
            await app.state.svc.line.aclose()

    app = FastAPI(title="にちなん・まもりネット", lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.post("/callback")
    async def callback(request: Request):
        body = await request.body()
        if not verify_signature(settings.channel_secret, body, request.headers.get("X-Line-Signature", "")):
            raise HTTPException(status_code=400, detail="invalid signature")
        try:
            payload = json.loads(body or b"{}")
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="invalid JSON") from None
        if not isinstance(payload, dict) or not isinstance(payload.get("events", []), list):
            raise HTTPException(status_code=400, detail="invalid webhook payload")
        svc: Service = request.app.state.svc
        for ev in payload.get("events", []):
            try:
                await svc.handle_event(ev)
            except Exception:
                log.exception("イベント処理に失敗")
        return JSONResponse({"ok": True})

    @app.get("/healthz")
    async def healthz():
        return {"ok": True, "dry_run": settings.dry_run}

    # 開発用：静的ページ（本番では Nginx が配信する）
    app.mount("/", StaticFiles(directory=BASE_DIR / "static", html=True), name="static")
    return app


app = create_app()
