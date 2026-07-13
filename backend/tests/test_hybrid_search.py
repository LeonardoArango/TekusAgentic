"""Tests de recuperación híbrida — contra Postgres+pgvector real (ver conftest).

Cierra la deuda de HU #18 (no había tests automatizados de este módulo).
"""

from connectors.confluence.client import ConfluencePage
from rag.indexacion.embeddings import LocalDevFallbackEmbeddingsProvider
from rag.indexacion.indexer import index_pages
from rag.recuperacion import hybrid_search as hs
from tests.conftest import requiere_postgres


@requiere_postgres
def test_hybrid_search_encuentra_por_texto_exacto(db_session):
    embeddings = LocalDevFallbackEmbeddingsProvider()
    paginas = [
        ConfluencePage(
            page_id="1",
            title="Errores conocidos",
            space_key="TEST",
            url="https://wiki/x/1",
            body_markdown=(
                "## Pantalla negra\n\nSi la pantalla queda negra, reinicia el player "
                "manteniendo presionado el botón de encendido 5 segundos."
            ),
        ),
        ConfluencePage(
            page_id="2",
            title="Licenciamiento",
            space_key="TEST",
            url="https://wiki/x/2",
            body_markdown=(
                "## Tipos de licencia\n\nExisten licencias demo, laboratorio, gratuita "
                "y comercial."
            ),
        ),
    ]
    index_pages(db_session, paginas, embeddings)
    db_session.flush()

    resultados = hs.hybrid_search(db_session, "la pantalla queda negra", embeddings)

    assert len(resultados) > 0
    assert resultados[0]["page_url"] == "https://wiki/x/1"
    assert all("page_url" in r and "text" in r for r in resultados)


@requiere_postgres
def test_hybrid_search_sin_resultados_no_falla(db_session):
    resultados = hs.hybrid_search(
        db_session,
        "pregunta sin ningún contenido relacionado en la base",
        LocalDevFallbackEmbeddingsProvider(),
    )
    assert resultados == []


def test_rrf_respeta_tope_y_unicidad():
    ranked_a = [(str(i), i) for i in range(25)]
    ranked_b = [(str(i), i) for i in range(20, 45)]

    fusionados = hs._reciprocal_rank_fusion([ranked_a, ranked_b], top_k=30)

    assert len(fusionados) <= 30
    assert len(fusionados) == len(set(fusionados))


def test_rrf_prioriza_coincidencias_en_ambas_listas():
    # "en_ambas" aparece en las dos listas (aunque no en el primer puesto);
    # "solo_en_a"/"solo_en_b" están en el primer puesto pero solo en una
    # lista cada uno. RRF debe premiar la coincidencia en ambas por encima
    # de estar arriba en una sola.
    ranked_a = [("solo_en_a", 0), ("en_ambas", 5)]
    ranked_b = [("en_ambas", 0), ("solo_en_b", 5)]

    fusionados = hs._reciprocal_rank_fusion([ranked_a, ranked_b], top_k=3)

    assert fusionados[0] == "en_ambas"
