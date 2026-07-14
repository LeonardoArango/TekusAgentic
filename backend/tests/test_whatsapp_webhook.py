import hashlib
import hmac
import json

import fakeredis
import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

_APP_SECRET = "test-app-secret"
_VERIFY_TOKEN = "test-verify-token"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("META_WA_APP_SECRET", _APP_SECRET)
    monkeypatch.setenv("META_WA_VERIFY_TOKEN", _VERIFY_TOKEN)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch):
    fake = fakeredis.FakeRedis()
    monkeypatch.setattr("api.webhooks.whatsapp.redis.Redis.from_url", lambda *_a, **_k: fake)
    return fake


def _sign(payload: bytes) -> str:
    digest = hmac.new(_APP_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_verify_webhook_success():
    response = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": _VERIFY_TOKEN,
            "hub.challenge": "12345",
        },
    )
    assert response.status_code == 200
    assert response.text == "12345"


def test_verify_webhook_wrong_token():
    response = client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "x"},
    )
    assert response.status_code == 403


def test_receive_webhook_valid_signature_queues_payload(_fake_redis):
    payload = {"entry": [{"changes": [{"value": {"messages": [{"from": "573000000000"}]}}]}]}
    body = json.dumps(payload).encode()

    response = client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={"X-Hub-Signature-256": _sign(body), "Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "queued"}
    assert _fake_redis.llen("whatsapp:inbound") == 1
    assert json.loads(_fake_redis.lindex("whatsapp:inbound", 0)) == payload


def test_receive_webhook_invalid_signature_rejected():
    body = json.dumps({"entry": []}).encode()

    response = client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={"X-Hub-Signature-256": "sha256=deadbeef", "Content-Type": "application/json"},
    )

    assert response.status_code == 401
