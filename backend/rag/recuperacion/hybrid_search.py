"""Recuperación híbrida: BM25 (top 20) + vector pgvector (top 20) → RRF (top 30
únicos) → reranker (top 5-8). Ver docs/investigacion-arquitectura.md sección 4.

El reranker (`bge-reranker-v2-m3`, autohospedado) es un servicio externo
configurable — si RERANKER_SERVICE_URL no está definido, se degrada a
devolver el orden de RRF sin reranking (mejor un resultado sin reranking que
un error duro, pero se loggea explícitamente para que no pase desapercibido).
"""

from __future__ import annotations

import logging
import os

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from rag.indexacion.embeddings import EmbeddingsProvider

logger = logging.getLogger(__name__)

_BM25_TOP_K = 20
_VECTOR_TOP_K = 20
_RRF_TOP_K = 30
_FINAL_TOP_K = 6
_RRF_K = 60  # constante estándar de RRF (Cormack et al.)


def _bm25_candidates(session: Session, query: str, top_k: int) -> list[tuple[str, int]]:
    """BM25-ish vía full-text search nativo de Postgres (ts_rank_cd)."""
    rows = session.execute(
        text("""
            SELECT id,
                   ts_rank_cd(to_tsvector('spanish', text), plainto_tsquery('spanish', :query))
                       AS rank
            FROM confluence_chunks
            WHERE to_tsvector('spanish', text) @@ plainto_tsquery('spanish', :query)
            ORDER BY rank DESC
            LIMIT :top_k
            """),
        {"query": query, "top_k": top_k},
    ).all()
    return [(str(row.id), i) for i, row in enumerate(rows)]


def _vector_candidates(
    session: Session, query_vector: list[float], top_k: int
) -> list[tuple[str, int]]:
    rows = session.execute(
        text("""
            SELECT id
            FROM confluence_chunks
            ORDER BY embedding <=> (:query_vector)::vector
            LIMIT :top_k
            """),
        {"query_vector": str(query_vector), "top_k": top_k},
    ).all()
    return [(str(row.id), i) for i, row in enumerate(rows)]


def _reciprocal_rank_fusion(ranked_lists: list[list[tuple[str, int]]], top_k: int) -> list[str]:
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for chunk_id, rank in ranked:
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (_RRF_K + rank + 1)
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [chunk_id for chunk_id, _ in ordered[:top_k]]


def _rerank(query: str, candidates: list[dict]) -> list[dict]:
    base_url = os.environ.get("RERANKER_SERVICE_URL")
    if not base_url:
        logger.warning(
            "RERANKER_SERVICE_URL no configurado — devolviendo orden de RRF sin reranking. "
            "No usar así en producción (ver docs/investigacion-arquitectura.md sección 4)."
        )
        return candidates[:_FINAL_TOP_K]

    response = httpx.post(
        f"{base_url.rstrip('/')}/rerank",
        json={"query": query, "documents": [c["text"] for c in candidates]},
        timeout=10.0,
    )
    response.raise_for_status()
    order = response.json()["order"]  # lista de índices, más relevante primero
    return [candidates[i] for i in order[:_FINAL_TOP_K]]


def hybrid_search(session: Session, query: str, embeddings: EmbeddingsProvider) -> list[dict]:
    """Devuelve hasta _FINAL_TOP_K chunks, cada uno trazable a su página origen."""
    (query_vector,) = embeddings.embed([query])

    bm25_ranked = _bm25_candidates(session, query, _BM25_TOP_K)
    vector_ranked = _vector_candidates(session, query_vector, _VECTOR_TOP_K)
    fused_ids = _reciprocal_rank_fusion([bm25_ranked, vector_ranked], _RRF_TOP_K)
    if not fused_ids:
        return []

    rows = session.execute(
        text("""
            SELECT id, page_title, page_url, space_key, text
            FROM confluence_chunks
            WHERE id = ANY(:ids)
            """),
        {"ids": fused_ids},
    ).all()
    by_id = {str(row.id): row for row in rows}
    candidates = [
        {
            "chunk_id": chunk_id,
            "text": by_id[chunk_id].text,
            "page_title": by_id[chunk_id].page_title,
            "page_url": by_id[chunk_id].page_url,
            "space_key": by_id[chunk_id].space_key,
        }
        for chunk_id in fused_ids
        if chunk_id in by_id
    ]
    return _rerank(query, candidates)
