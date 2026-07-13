"""Cliente de Confluence vía atlassian-python-api.

Único conector cuyos datos sí se indexan en pgvector (ver backend/rag/).
Requiere CONFLUENCE_URL, CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN en el
entorno (ver .env.example) — no hardcodear credenciales (regla dura de
CLAUDE.md, sección "Seguridad").
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterator
from dataclasses import dataclass

from atlassian import Confluence
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_SECONDS = 2.0
_CIRCUIT_FAILURE_THRESHOLD = 5


@dataclass(frozen=True)
class ConfluencePage:
    page_id: str
    title: str
    space_key: str
    url: str
    body_markdown: str


class ConfluenceCircuitOpenError(RuntimeError):
    """Se abrió el circuit breaker tras fallos consecutivos contra Confluence."""


class ConfluenceClient:
    """Wrapper con reintentos y circuit breaker sobre atlassian-python-api."""

    def __init__(self) -> None:
        url = os.environ["CONFLUENCE_URL"]
        self._client = Confluence(
            url=url,
            username=os.environ["CONFLUENCE_USERNAME"],
            password=os.environ["CONFLUENCE_API_TOKEN"],
            cloud=True,
        )
        self._base_url = url.rstrip("/")
        self._consecutive_failures = 0

    def _call_with_retry(self, fn, *args, **kwargs):
        if self._consecutive_failures >= _CIRCUIT_FAILURE_THRESHOLD:
            raise ConfluenceCircuitOpenError(
                f"Circuit breaker abierto tras {self._consecutive_failures} fallos consecutivos "
                "contra Confluence."
            )
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                result = fn(*args, **kwargs)
                self._consecutive_failures = 0
                return result
            except RequestException as exc:
                last_exc = exc
                self._consecutive_failures += 1
                logger.warning("Fallo Confluence (intento %s/%s): %s", attempt, _MAX_RETRIES, exc)
                if attempt < _MAX_RETRIES:
                    time.sleep(_BACKOFF_SECONDS * attempt)
        assert last_exc is not None
        raise last_exc

    def iter_space_pages(self, space_key: str, page_size: int = 25) -> Iterator[ConfluencePage]:
        """Recorre todas las páginas `current` de un espacio, paginando."""
        start = 0
        while True:
            batch = self._call_with_retry(
                self._client.get_all_pages_from_space,
                space_key,
                start=start,
                limit=page_size,
                status="current",
                expand="body.storage",
            )
            if not batch:
                return
            for page in batch:
                yield ConfluencePage(
                    page_id=page["id"],
                    title=page["title"],
                    space_key=space_key,
                    url=f"{self._base_url}/wiki/spaces/{space_key}/pages/{page['id']}",
                    body_markdown=page.get("body", {}).get("storage", {}).get("value", ""),
                )
            start += page_size
