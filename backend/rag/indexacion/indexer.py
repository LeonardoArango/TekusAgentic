"""Indexación: toma páginas de Confluence, las chunkea y las guarda en pgvector."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.connectors.confluence.client import ConfluencePage
from backend.models.rag import ConfluenceChunk
from backend.rag.indexacion.chunking import chunk_markdown
from backend.rag.indexacion.embeddings import EmbeddingsProvider


def index_pages(
    session: Session,
    pages: list[ConfluencePage],
    embeddings: EmbeddingsProvider,
) -> int:
    """Chunkea e indexa `pages`. Devuelve la cantidad de chunks escritos.

    Reemplaza (delete + insert) los chunks existentes de cada page_id, para
    que reindexar una página no deje fragmentos huérfanos de una versión vieja.
    """
    total = 0
    for page in pages:
        session.query(ConfluenceChunk).filter(ConfluenceChunk.page_id == page.page_id).delete()

        chunks = chunk_markdown(page.body_markdown)
        if not chunks:
            continue

        vectors = embeddings.embed([c.text for c in chunks])
        for chunk, vector in zip(chunks, vectors, strict=True):
            session.add(
                ConfluenceChunk(
                    space_key=page.space_key,
                    page_id=page.page_id,
                    page_title=page.title,
                    page_url=page.url,
                    chunk_index=chunk.index,
                    text=chunk.text,
                    embedding=vector,
                )
            )
            total += 1

    session.commit()
    return total
