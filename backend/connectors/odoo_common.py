"""Conexión base a Odoo vía OdooRPC — compartida por odoo_crm/ y odoo_helpdesk/.

Todo lo que se lee/escribe aquí es en vivo, nunca vectorizado (ver
docs/decisiones/0002-odoo-en-vivo-no-vectorizado.md). Requiere ODOO_URL,
ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD en el entorno — ODOO_PASSWORD puede
ser una API Key de Odoo (recomendado) en vez de una contraseña real.

Los métodos de negocio específicos (leer/crear ticket, leer/avanzar
oportunidad) viven en odoo_crm/client.py y odoo_helpdesk/client.py — dependen
de los nombres exactos de modelo y campo de la instancia de Tekus, que aún
no están confirmados (ver conversación de Fase 0 con Leonardo).
"""

from __future__ import annotations

import logging
import os
import time

import odoorpc
from odoorpc.error import RPCError

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_SECONDS = 2.0
_CIRCUIT_FAILURE_THRESHOLD = 5


class OdooCircuitOpenError(RuntimeError):
    """Se abrió el circuit breaker tras fallos consecutivos contra Odoo."""


class OdooConnection:
    """Conexión autenticada a Odoo con reintentos y circuit breaker.

    No expone métodos de negocio — es la base sobre la que se construyen
    los clientes de CRM y Helpdesk (composición, no herencia, para que cada
    uno declare explícitamente qué modelos toca).
    """

    def __init__(self) -> None:
        url = os.environ["ODOO_URL"]
        scheme, _, host_port = url.partition("://")
        host, _, port = host_port.partition(":")

        self._odoo = odoorpc.ODOO(
            host,
            protocol="jsonrpc+ssl" if scheme == "https" else "jsonrpc",
            port=int(port) if port else (443 if scheme == "https" else 8069),
        )
        self._odoo.login(
            os.environ["ODOO_DB"],
            os.environ["ODOO_USERNAME"],
            os.environ["ODOO_PASSWORD"],
        )
        self._consecutive_failures = 0

    @property
    def env(self) -> odoorpc.ODOO:
        return self._odoo

    def call_with_retry(self, fn, *args, **kwargs):
        if self._consecutive_failures >= _CIRCUIT_FAILURE_THRESHOLD:
            raise OdooCircuitOpenError(
                f"Circuit breaker abierto tras {self._consecutive_failures} fallos "
                "consecutivos contra Odoo."
            )
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                result = fn(*args, **kwargs)
                self._consecutive_failures = 0
                return result
            except RPCError as exc:
                last_exc = exc
                self._consecutive_failures += 1
                logger.warning("Fallo Odoo (intento %s/%s): %s", attempt, _MAX_RETRIES, exc)
                if attempt < _MAX_RETRIES:
                    time.sleep(_BACKOFF_SECONDS * attempt)
        assert last_exc is not None
        raise last_exc
