"""Selección del proveedor de embeddings según el entorno.

Prioridad: servicio autohospedado (EMBEDDINGS_SERVICE_URL) > OpenAI
(OPENAI_API_KEY) > fallback local sin red (solo dev, sin calidad real).
Un único lugar para esta decisión, reutilizado por la ingesta y por el
endpoint de preguntas — así no divergen.
"""

from __future__ import annotations

import logging
import os

from rag.indexacion.embeddings import (
    EmbeddingsProvider,
    HttpEmbeddingsProvider,
    LocalDevFallbackEmbeddingsProvider,
    OpenAIEmbeddingsProvider,
)

logger = logging.getLogger(__name__)


def get_embeddings_provider() -> EmbeddingsProvider:
    if os.environ.get("EMBEDDINGS_SERVICE_URL"):
        return HttpEmbeddingsProvider()
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAIEmbeddingsProvider()
    logger.warning(
        "Sin EMBEDDINGS_SERVICE_URL ni OPENAI_API_KEY — usando fallback local "
        "sin calidad semántica real. No usar en producción."
    )
    return LocalDevFallbackEmbeddingsProvider()
