"""Modelos Postgres/pgvector para el RAG de Confluence.

Solo Confluence se vectoriza aquí (ver docs/decisiones/0002-odoo-en-vivo-no-vectorizado.md).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ConfluenceChunk(Base):
    """Un fragmento indexable de una página de Confluence, con su embedding.

    `space_key` y `page_id` permiten excluir un espacio o página completa del
    RAG (ver EXCLUDED_PAGE_IDS en rag/ingesta) sin tener que limpiar embeddings
    sueltos. `page_url` es lo que se cita como fuente en cada respuesta del
    agente (ver CLAUDE.md, sección "Estrategia de RAG": toda respuesta debe
    poder trazarse a su origen).
    """

    __tablename__ = "confluence_chunks"
    __table_args__ = (UniqueConstraint("page_id", "chunk_index", name="uq_page_chunk"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_key: Mapped[str] = mapped_column(String(32), index=True)
    page_id: Mapped[str] = mapped_column(String(64), index=True)
    page_title: Mapped[str] = mapped_column(String(512))
    page_url: Mapped[str] = mapped_column(String(1024))
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(384))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
