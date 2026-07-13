"""Tests del indexador incremental — contra Postgres+pgvector real (ver conftest).

Lo que más importa validar aquí para costo/escalabilidad: contenido sin
cambios se salta por completo, cero llamadas a embeddings.
"""

from unittest.mock import MagicMock

from connectors.confluence.client import ConfluencePage
from models.rag import ConfluenceChunk, ConfluencePageState
from rag.indexacion.embeddings import LocalDevFallbackEmbeddingsProvider
from rag.indexacion.indexer import index_pages, reconciliar_espacio
from tests.conftest import requiere_postgres


def _page(page_id="1", body="## Título\n\nContenido de prueba.", space_key="TEST"):
    return ConfluencePage(
        page_id=page_id,
        title="Página de prueba",
        space_key=space_key,
        url=f"https://wiki/x/{page_id}",
        body_markdown=body,
    )


@requiere_postgres
def test_pagina_nueva_se_indexa(db_session):
    resumen = index_pages(db_session, [_page()], LocalDevFallbackEmbeddingsProvider())

    assert resumen.nuevas == 1
    assert resumen.chunks_escritos > 0
    chunks_guardados = db_session.query(ConfluenceChunk).filter_by(page_id="1").count()
    assert chunks_guardados == resumen.chunks_escritos
    assert db_session.query(ConfluencePageState).filter_by(page_id="1").count() == 1


@requiere_postgres
def test_contenido_sin_cambios_no_reembebe(db_session):
    embeddings = LocalDevFallbackEmbeddingsProvider()
    index_pages(db_session, [_page()], embeddings)

    embed_espiado = MagicMock(wraps=embeddings.embed)
    embeddings.embed = embed_espiado

    resumen = index_pages(db_session, [_page()], embeddings)

    assert resumen.sin_cambios == 1
    assert resumen.nuevas == 0
    assert resumen.actualizadas == 0
    embed_espiado.assert_not_called()


@requiere_postgres
def test_contenido_modificado_se_reembebe(db_session):
    embeddings = LocalDevFallbackEmbeddingsProvider()
    index_pages(db_session, [_page(body="## Original\n\nTexto viejo.")], embeddings)

    resumen = index_pages(
        db_session,
        [_page(body="## Nuevo\n\nTexto completamente distinto y más largo.")],
        embeddings,
    )

    assert resumen.actualizadas == 1
    assert resumen.nuevas == 0
    assert resumen.sin_cambios == 0


@requiere_postgres
def test_reconciliar_elimina_paginas_ausentes(db_session):
    embeddings = LocalDevFallbackEmbeddingsProvider()
    index_pages(db_session, [_page(page_id="1"), _page(page_id="2")], embeddings)

    eliminadas = reconciliar_espacio(db_session, "TEST", {"1"})

    assert eliminadas == 1
    assert db_session.query(ConfluenceChunk).filter_by(page_id="2").count() == 0
    assert db_session.query(ConfluencePageState).filter_by(page_id="2").count() == 0
    assert db_session.query(ConfluenceChunk).filter_by(page_id="1").count() > 0


@requiere_postgres
def test_reconciliar_no_borra_paginas_vistas(db_session):
    embeddings = LocalDevFallbackEmbeddingsProvider()
    index_pages(db_session, [_page(page_id="1")], embeddings)

    eliminadas = reconciliar_espacio(db_session, "TEST", {"1"})

    assert eliminadas == 0
    assert db_session.query(ConfluenceChunk).filter_by(page_id="1").count() > 0
