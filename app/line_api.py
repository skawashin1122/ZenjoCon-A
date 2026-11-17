"""LINE Messaging API とのやりとり。

- 署名検証（X-Line-Signature）
- 応答メッセージ（reply：無料プランの通数に数えない）
- プッシュメッセージ（push：通数に数える。異常時だけ使う）
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import sqlite3
from datetime import datetime
from typing import Protocol

import httpx

from .config import JST

log = logging.getLogger("mamorinet.line")
API = "https://api.line.me/v2/bot"


def verify_signature(channel_secret: str, body: bytes, signature: str) -> bool:
    if not channel_secret or not signature:
        return False
    digest = hmac.new(channel_secret.encode(), body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature)


class Messenger(Protocol):
    async def reply(self, reply_token: str, messages: list[dict]) -> None: ...
    async def push(self, to: str, messages: list[dict]) -> None: ...
    async def display_name(self, user_id: str) -> str: ...


class LineClient:
    """本物の LINE に送る。"""

    def __init__(self, access_token: str):
        self._http = httpx.AsyncClient(
            base_url=API, timeout=10.0,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    async def reply(self, reply_token: str, messages: list[dict]) -> None:
        r = await self._http.post("/message/reply", json={"replyToken": reply_token, "messages": messages[:5]})
        if r.status_code >= 400:
            log.error("reply failed %s %s", r.status_code, r.text)
            r.raise_for_status()

    async def push(self, to: str, messages: list[dict]) -> None:
        r = await self._http.post("/message/push", json={"to": to, "messages": messages[:5]})
        if r.status_code >= 400:
            log.error("push failed %s %s", r.status_code, r.text)
            r.raise_for_status()

    async def display_name(self, user_id: str) -> str:
        try:
            r = await self._http.get(f"/profile/{user_id}")
            if r.status_code == 200:
                return r.json().get("displayName", "")
        except httpx.HTTPError:
            log.exception("profile failed")
        return ""

    async def aclose(self) -> None:
        await self._http.aclose()


class DryRunClient:
    """LINE の鍵がないとき用。送ったつもりの内容を outbox テーブルとログに残す。"""

    def __init__(self, conn: sqlite3.Connection | None = None):
        self.conn = conn
        self.sent: list[tuple[str, str, list[dict]]] = []  # (kind, to, messages) テスト用

    def _record(self, kind: str, to: str, messages: list[dict]) -> None:
        self.sent.append((kind, to, messages))
        body = json.dumps(messages, ensure_ascii=False)
        log.info("[DRY-RUN %s → %s] %s", kind, to, body[:300])
        if self.conn is not None:
            self.conn.execute(
                "INSERT INTO outbox(at, kind, to_line, body) VALUES (?,?,?,?)",
                (datetime.now(JST).isoformat(timespec="seconds"), kind, to, body),
            )

    async def reply(self, reply_token: str, messages: list[dict]) -> None:
        self._record("reply", reply_token, messages)

    async def push(self, to: str, messages: list[dict]) -> None:
        self._record("push", to, messages)

    async def display_name(self, user_id: str) -> str:
        return ""

    async def aclose(self) -> None:
        pass

    # --- テスト用の便利関数 ---
    def texts(self, kind: str | None = None, to: str | None = None) -> list[str]:
        """送ったメッセージの文字（text / altText）だけを取り出す。"""
        out = []
        for k, t, msgs in self.sent:
            if (kind and k != kind) or (to and t != to):
                continue
            for m in msgs:
                out.append(m.get("text") or m.get("altText") or "")
        return out
