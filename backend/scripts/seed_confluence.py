"""Bootstrap del RAG: carga páginas de Confluence pre-extraídas (JSON) a pgvector.

Uso normal en Fase 1 (con credenciales reales validadas): el conector
`ConfluenceClient` reemplaza esta carga desde JSON por `iter_space_pages`
en vivo. Este script es el bootstrap de Fase 0 para el primer RAG de
Señalización Digital + Kioscos, construido a partir de contenido ya
auditado y curado manualmente (ver backend/rag/_seed_data/*.json y
backend/rag/ingesta/exclusions.py).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connectors.confluence.client import ConfluencePage  # noqa: E402
from models.rag import Base  # noqa: E402
from rag.indexacion.embeddings import (  # noqa: E402
    HttpEmbeddingsProvider,
    LocalDevFallbackEmbeddingsProvider,
)
from rag.indexacion.indexer import index_pages, reconciliar_espacio  # noqa: E402
from rag.ingesta.exclusions import is_excluded  # noqa: E402

SEED_DIR = Path(__file__).resolve().parents[1] / "rag" / "_seed_data"


def _load_pages(json_path: Path) -> list[ConfluencePage]:
    raw = json.loads(json_path.read_text(encoding="utf-8"))
    pages = []
    skipped = 0
    for item in raw:
        if is_excluded(item["space_key"], item["page_id"], item["title"]):
            skipped += 1
            continue
        pages.append(ConfluencePage(**item))
    print(f"  {json_path.name}: {len(pages)} páginas cargadas, {skipped} excluidas por filtro")
    return pages


def main() -> None:
    database_url = os.environ["DATABASE_URL"].replace("+asyncpg", "")
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)

    if os.environ.get("EMBEDDINGS_SERVICE_URL"):
        embeddings = HttpEmbeddingsProvider()
    else:
        print(
            "AVISO: EMBEDDINGS_SERVICE_URL no configurado — usando "
            "LocalDevFallbackEmbeddingsProvider (solo para dev sin red, sin "
            "calidad semántica real). No usar en producción."
        )
        embeddings = LocalDevFallbackEmbeddingsProvider()

    pages_by_space: dict[str, list[ConfluencePage]] = {}
    for json_path in sorted(SEED_DIR.glob("*.json")):
        for page in _load_pages(json_path):
            pages_by_space.setdefault(page.space_key, []).append(page)

    if not pages_by_space:
        print(f"No se encontraron JSON de seed en {SEED_DIR}")
        return

    with Session(engine) as session:
        nuevas = actualizadas = sin_cambios = eliminadas = chunks_escritos = 0
        for space_key, pages in pages_by_space.items():
            # Cada JSON de seed es un barrido COMPLETO del espacio (no un
            # fetch incremental por fecha) — por eso es válido reconciliar
            # eliminaciones aquí, comparando contra el set de page_ids visto.
            resumen = index_pages(session, pages, embeddings)
            eliminadas_espacio = reconciliar_espacio(session, space_key, {p.page_id for p in pages})
            nuevas += resumen.nuevas
            actualizadas += resumen.actualizadas
            sin_cambios += resumen.sin_cambios
            eliminadas += eliminadas_espacio
            chunks_escritos += resumen.chunks_escritos

    print(
        f"\nListo: {nuevas} páginas nuevas, {actualizadas} actualizadas, "
        f"{sin_cambios} sin cambios (saltadas, cero llamadas a embeddings), "
        f"{eliminadas} eliminadas/reconciliadas -> {chunks_escritos} chunks escritos."
    )


if __name__ == "__main__":
    main()
