"""Endpoint de verificación y recepción de WhatsApp Cloud API (Meta).

- GET: handshake de verificación que Meta hace una sola vez al configurar el
  webhook (compara hub.verify_token contra META_WA_VERIFY_TOKEN). Meta manda
  estos parámetros como query string, no como headers ni body.
- POST: recepción de eventos entrantes. Valida la firma X-Hub-Signature-256
  contra META_WA_APP_SECRET y encola el payload crudo en Redis — el
  procesamiento agéntico (router → soporte/comercial → guardrails →
  orquestador) corre de forma asíncrona, nunca bloqueando esta respuesta
  (ver docs/investigacion-arquitectura.md, sección 2).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os

import redis
from fastapi import APIRouter, Header, HTTPException, Request, Response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/whatsapp", tags=["whatsapp"])

_INBOUND_QUEUE_KEY = "whatsapp:inbound"


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(os.environ["REDIS_URL"])


def _verify_signature(app_secret: str, payload: bytes, signature_header: str | None) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)


@router.get("")
async def verify_webhook(request: Request) -> Response:
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == os.environ["META_WA_VERIFY_TOKEN"]:
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verify token inválido")


@router.post("")
async def receive_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256"),
) -> dict[str, str]:
    raw_body = await request.body()

    if not _verify_signature(os.environ["META_WA_APP_SECRET"], raw_body, x_hub_signature_256):
        logger.warning("Firma inválida en webhook de WhatsApp — payload descartado")
        raise HTTPException(status_code=401, detail="Firma inválida")

    payload = json.loads(raw_body)
    _redis_client().rpush(_INBOUND_QUEUE_KEY, json.dumps(payload))

    return {"status": "queued"}
