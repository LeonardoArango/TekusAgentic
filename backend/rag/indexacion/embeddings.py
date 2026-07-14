"""Proveedor de embeddings — interfaz intercambiable.

`HttpEmbeddingsProvider` es la implementación de producción: llama a un
servicio de embeddings autohospedado (ver docs/investigacion-arquitectura.md,
sección 4 — mismo criterio que el reranker `bge-reranker-v2-m3`, se opera
propio en vez de depender de un proveedor externo). Se configura con
EMBEDDINGS_SERVICE_URL.

`LocalDevFallbackEmbeddingsProvider` NO es apta para producción: es un hash
determinístico de baja calidad semántica, usado únicamente para poder correr
el pipeline de ingesta/recuperación en un entorno sin salida a internet (p.
ej. este sandbox de desarrollo, que no tiene acceso a Hugging Face). Debe
reemplazarse por HttpEmbeddingsProvider antes de cualquier ambiente real.
"""

from __future__ import annotations

import hashlib
import os
import struct
from typing import Protocol

import httpx

# 1536 = dimensión nativa de text-embedding-3-small (OpenAI). El servicio
# autohospedado (bge-m3) también puede producir 1536 con proyección; si se
# cambia de modelo con otra dimensión hay que recrear la columna Vector y
# re-indexar (ver models/rag.py).
EMBEDDING_DIM = 1536


class EmbeddingsProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbeddingsProvider:
    """Embeddings vía OpenAI (text-embedding-3-small).

    Decisión de Leonardo (2026-07-14): usar OpenAI para embeddings además de
    para generar respuestas, en vez del servicio autohospedado que planteaba
    la investigación — desbloquea calidad real sin operar infra de modelos.
    Ver docs/decisiones/0005-indexar-tickets-odoo-y-embeddings-openai.md.
    """

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        from openai import OpenAI

        self._model = model or os.environ.get("OPENAI_EMBEDDINGS_MODEL", "text-embedding-3-small")
        self._client = OpenAI(api_key=api_key or os.environ["OPENAI_API_KEY"])

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # OpenAI acepta lotes; se acota a 128 por llamada para no exceder el
        # límite de tokens por request con textos largos.
        out: list[list[float]] = []
        for i in range(0, len(texts), 128):
            lote = texts[i : i + 128]
            resp = self._client.embeddings.create(model=self._model, input=lote)
            out.extend(item.embedding for item in resp.data)
        return out


class HttpEmbeddingsProvider:
    """Llama a un servicio de embeddings autohospedado (producción)."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or os.environ["EMBEDDINGS_SERVICE_URL"]).rstrip("/")

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = httpx.post(f"{self._base_url}/embed", json={"inputs": texts}, timeout=30.0)
        response.raise_for_status()
        return response.json()["embeddings"]


class LocalDevFallbackEmbeddingsProvider:
    """Embedding determinístico basado en hashing — SOLO para desarrollo local
    sin red. No tiene calidad semántica real; sirve para ejercitar el pipeline
    de indexación/recuperación de punta a punta, no para evaluar precisión.
    """

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    @staticmethod
    def _embed_one(text: str) -> list[float]:
        tokens = text.lower().split()
        vector = [0.0] * EMBEDDING_DIM
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            (bucket,) = struct.unpack_from(">I", digest, 0)
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket % EMBEDDING_DIM] += sign
        norm = sum(v * v for v in vector) ** 0.5
        if norm == 0:
            return vector
        return [v / norm for v in vector]
