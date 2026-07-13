"""Cliente de WhatsApp Cloud API (Meta) vía PyWa.

Conexión directa a la Graph API oficial, sin BSP intermediario (ver
CLAUDE.md, "Qué NO hacer sin confirmar con Leonardo"). Requiere
META_WA_TOKEN, META_WA_PHONE_NUMBER_ID, META_WA_BUSINESS_ACCOUNT_ID,
META_WA_APP_SECRET en el entorno (ver .env.example) — el token es un
System User token sin expiración: tratarlo como una contraseña de
producción, nunca en el frontend ni en el repo.
"""

from __future__ import annotations

import logging
import os
import time

from pywa import WhatsApp
from pywa.errors import WhatsAppError

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_SECONDS = 2.0
_CIRCUIT_FAILURE_THRESHOLD = 5


class WhatsAppCircuitOpenError(RuntimeError):
    """Se abrió el circuit breaker tras fallos consecutivos contra la Cloud API."""


class WhatsAppClient:
    """Wrapper con reintentos y circuit breaker sobre PyWa, solo para envío.

    La recepción de mensajes (webhooks) vive en backend/api/webhooks/whatsapp.py,
    no aquí — este cliente no registra rutas de servidor, solo envía.
    """

    def __init__(self) -> None:
        self._wa = WhatsApp(
            phone_id=os.environ["META_WA_PHONE_NUMBER_ID"],
            token=os.environ["META_WA_TOKEN"],
            business_account_id=os.environ.get("META_WA_BUSINESS_ACCOUNT_ID"),
        )
        self._consecutive_failures = 0

    def _call_with_retry(self, fn, *args, **kwargs):
        if self._consecutive_failures >= _CIRCUIT_FAILURE_THRESHOLD:
            raise WhatsAppCircuitOpenError(
                f"Circuit breaker abierto tras {self._consecutive_failures} fallos "
                "consecutivos contra la Cloud API de WhatsApp."
            )
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                result = fn(*args, **kwargs)
                self._consecutive_failures = 0
                return result
            except WhatsAppError as exc:
                last_exc = exc
                self._consecutive_failures += 1
                logger.warning(
                    "Fallo WhatsApp Cloud API (intento %s/%s): %s", attempt, _MAX_RETRIES, exc
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(_BACKOFF_SECONDS * attempt)
        assert last_exc is not None
        raise last_exc

    def send_text(self, to: str, text: str) -> str:
        """Envía un mensaje de texto libre (solo válido dentro de la ventana de 24h)."""
        message_id = self._call_with_retry(self._wa.send_message, to=to, text=text)
        return message_id

    def send_template(self, to: str, template_name: str, language: str = "es", **params) -> str:
        """Envía una plantilla aprobada por Meta (válido fuera de la ventana de 24h)."""
        message_id = self._call_with_retry(
            self._wa.send_template,
            to=to,
            name=template_name,
            language=language,
            **params,
        )
        return message_id
