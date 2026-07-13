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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.connectors.confluence.client import ConfluencePage  # noqa: E402
from backend.models.rag import Base  # noqa: E402
from backend.rag.indexacion.embeddings import (  # noqa: E402
    HttpEmbeddingsProvider,
    LocalDevFallbackEmbeddingsProvider,
)
from backend.rag.indexacion.indexer import index_pages  # noqa: E402
from backend.rag.ingesta.exclusions import is_excluded  # noqa: E402

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

    all_pages: list[ConfluencePage] = []
    for json_path in sorted(SEED_DIR.glob("*.json")):
        all_pages.extend(_load_pages(json_path))

    if not all_pages:
        print(f"No se encontraron JSON de seed en {SEED_DIR}")
        return

    with Session(engine) as session:
        total_chunks = index_pages(session, all_pages, embeddings)

    print(f"\nListo: {len(all_pages)} páginas -> {total_chunks} chunks indexados.")


if __name__ == "__main__":
    main()
