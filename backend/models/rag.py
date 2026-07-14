"""Modelos Postgres/pgvector para el RAG de Confluence.

Solo Confluence se vectoriza aquí (ver docs/decisiones/0002-odoo-en-vivo-no-vectorizado.md).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def ahora_utc() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class ConfluenceChunk(Base):
    """Un fragmento indexable de una página de Confluence, con su embedding.

    `space_key` y `page_id` permiten excluir un espacio o página completa del
    RAG (ver EXCLUDED_PAGE_IDS en rag/ingesta) sin tener que limpiar embeddings
    sueltos. `page_url` es lo que se cita como fuente en cada respuesta del
    agente (ver CLAUDE.md, sección "Estrategia de RAG": toda respuesta debe
    poder trazarse a su origen).

    `tsv` es una columna generada y persistida por Postgres (no se escribe
    desde Python) — permite indexar el full-text con GIN en vez de calcular
    `to_tsvector(...)` al vuelo en cada búsqueda, que no escala.
    """

    __tablename__ = "confluence_chunks"
    __table_args__ = (
        UniqueConstraint("page_id", "chunk_index", name="uq_page_chunk"),
        Index(
            "ix_confluence_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_confluence_chunks_tsv_gin", "tsv", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_key: Mapped[str] = mapped_column(String(32), index=True)
    page_id: Mapped[str] = mapped_column(String(64), index=True)
    page_title: Mapped[str] = mapped_column(String(512))
    page_url: Mapped[str] = mapped_column(String(1024))
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(384))
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('spanish', text)", persisted=True)
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)


class ConfluencePageState(Base):
    """Estado de indexación de cada página — la fuente de verdad de qué ya se
    procesó y con qué contenido exacto, para poder saltarnos páginas sin
    cambios (incremental) y detectar páginas eliminadas (reconciliación).
    """

    __tablename__ = "confluence_page_state"

    page_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    space_key: Mapped[str] = mapped_column(String(32), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    chunk_count: Mapped[int] = mapped_column(Integer)
    last_indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora_utc)
