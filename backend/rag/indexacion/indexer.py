"""Indexación incremental: toma páginas de Confluence, salta por completo
(cero llamadas a embeddings) las que no cambiaron desde la última corrida, y
solo chunkea/embebe/guarda lo nuevo o modificado.

La detección de cambio es por hash de contenido (`ConfluencePageState`), no
por fecha — más robusto ante relojes desincronizados o reprocesos manuales
del mismo contenido.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import delete
from sqlalchemy.orm import Session

from connectors.confluence.client import ConfluencePage
from models.rag import ConfluenceChunk, ConfluencePageState, ahora_utc
from rag.indexacion.chunking import chunk_markdown
from rag.indexacion.embeddings import EmbeddingsProvider

_EMBED_BATCH_SIZE = 64


@dataclass
class ResumenIndexacion:
    nuevas: int = 0
    actualizadas: int = 0
    sin_cambios: int = 0
    eliminadas: int = 0
    chunks_escritos: int = 0

    @property
    def paginas_procesadas(self) -> int:
        return self.nuevas + self.actualizadas + self.sin_cambios


def _hash_contenido(body_markdown: str) -> str:
    return hashlib.sha256(body_markdown.encode("utf-8")).hexdigest()


def _embeber_en_lotes(embeddings: EmbeddingsProvider, textos: list[str]) -> list[list[float]]:
    """Llama a `embeddings.embed` en lotes acotados — evita mandar de una sola
    vez cientos de chunks de una página gigante a un servicio con límites de
    tamaño de request."""
    vectores: list[list[float]] = []
    for inicio in range(0, len(textos), _EMBED_BATCH_SIZE):
        lote = textos[inicio : inicio + _EMBED_BATCH_SIZE]
        vectores.extend(embeddings.embed(lote))
    return vectores


def index_pages(
    session: Session,
    pages: list[ConfluencePage],
    embeddings: EmbeddingsProvider,
) -> ResumenIndexacion:
    """Indexa `pages` de forma incremental.

    No reconcilia eliminaciones — para eso ver `reconciliar_espacio`, que se
    corre aparte con el set COMPLETO de page_ids vistos en un barrido total
    del espacio (si `pages` es un fetch incremental por fecha de
    modificación, no reconciliar con ese subconjunto borraría contenido
    válido que simplemente no cambió recientemente).
    """
    resumen = ResumenIndexacion()
    if not pages:
        return resumen

    estados_existentes = {
        estado.page_id: estado
        for estado in session.query(ConfluencePageState)
        .filter(ConfluencePageState.page_id.in_([p.page_id for p in pages]))
        .all()
    }

    for page in pages:
        content_hash = _hash_contenido(page.body_markdown)
        estado_previo = estados_existentes.get(page.page_id)

        if estado_previo and estado_previo.content_hash == content_hash:
            resumen.sin_cambios += 1
            continue

        session.execute(delete(ConfluenceChunk).where(ConfluenceChunk.page_id == page.page_id))

        chunks = chunk_markdown(page.body_markdown)
        vectores = _embeber_en_lotes(embeddings, [c.text for c in chunks]) if chunks else []

        for chunk, vector in zip(chunks, vectores, strict=True):
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

        if estado_previo:
            estado_previo.content_hash = content_hash
            estado_previo.chunk_count = len(chunks)
            estado_previo.last_indexed_at = ahora_utc()
            resumen.actualizadas += 1
        else:
            session.add(
                ConfluencePageState(
                    page_id=page.page_id,
                    space_key=page.space_key,
                    content_hash=content_hash,
                    chunk_count=len(chunks),
                )
            )
            resumen.nuevas += 1

        resumen.chunks_escritos += len(chunks)

    session.commit()
    return resumen


def reconciliar_espacio(session: Session, space_key: str, page_ids_vistos: set[str]) -> int:
    """Borra chunks + estado de páginas de `space_key` que ya no aparecieron
    en un barrido COMPLETO del espacio (eliminadas, archivadas, o sacadas de
    alcance). Devuelve cuántas páginas se limpiaron."""
    estados_espacio = (
        session.query(ConfluencePageState).filter(ConfluencePageState.space_key == space_key).all()
    )
    huerfanos = [e.page_id for e in estados_espacio if e.page_id not in page_ids_vistos]
    if not huerfanos:
        return 0

    session.execute(delete(ConfluenceChunk).where(ConfluenceChunk.page_id.in_(huerfanos)))
    session.execute(delete(ConfluencePageState).where(ConfluencePageState.page_id.in_(huerfanos)))
    session.commit()
    return len(huerfanos)
