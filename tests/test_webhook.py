# LINE の Webhook（署名検証）
import base64
import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.line_api import verify_signature
from app.main import create_app


def sign(secret, body):
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


def test_署名の確認():
    body = b'{"events":[]}'
    assert verify_signature("s", body, sign("s", body))
    assert not verify_signature("s", body, sign("other", body))
    assert not verify_signature("s", body, "")
    assert not verify_signature("", body, sign("", body))


def make_client(svc):
    return TestClient(create_app(settings=svc.s, service=svc, background=False))


def test_正しい署名なら処理する(svc):
    body = json.dumps({"events": [{"type": "follow", "source": {"type": "user", "userId": "U1"},
                                   "replyToken": "rt"}]}).encode()
    with make_client(svc) as c:
        r = c.post("/callback", content=body, headers={"X-Line-Signature": sign("test-secret", body)})
    assert r.status_code == 200
    assert svc.line.sent and svc.line.sent[0][0] == "reply"


def test_なりすましは拒否(svc):
    body = b'{"events":[]}'
    with make_client(svc) as c:
        r = c.post("/callback", content=body, headers={"X-Line-Signature": sign("wrong", body)})
    assert r.status_code == 400


def test_静的ページ(svc):
    with make_client(svc) as c:
        assert c.get("/healthz").json()["ok"]
        assert "もしもカード" in c.get("/card/").text
