"""Fixtures compartidos.

`db_session`: sesión contra un Postgres+pgvector real, pero en una base de
datos DEDICADA de test (el nombre de `DATABASE_URL` + sufijo `_test`) —
nunca la misma base que usa `docker-compose`/`scripts/seed_confluence.py`,
para no contaminar los tests con datos reales de seed ya existentes.
Necesario para lo que no se puede mockear con un ORM en memoria: columnas
generadas (`tsv`), índices HNSW/GIN, operadores de pgvector. Cada test corre
dentro de un savepoint que se revierte al terminar.

Si no hay Postgres alcanzable, estos tests se saltan en vez de fallar (no
todo entorno de desarrollo lo tiene corriendo).
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from models.rag import Base


def _url_base_de_test(url: str) -> str:
    partes = urlsplit(url)
    return urlunsplit(partes._replace(path=partes.path + "_test"))


_DATABASE_URL = os.environ.get("DATABASE_URL", "").replace("+asyncpg", "+psycopg")
_TEST_DATABASE_URL = _url_base_de_test(_DATABASE_URL) if _DATABASE_URL else ""


def _postgres_disponible() -> bool:
    if not _TEST_DATABASE_URL:
        return False
    try:
        engine = create_engine(_TEST_DATABASE_URL)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


requiere_postgres = pytest.mark.skipif(
    not _postgres_disponible(),
    reason=(
        "Requiere una base de datos de test dedicada "
        "(DATABASE_URL + '_test') con pgvector alcanzable"
    ),
)


@pytest.fixture
def db_session():
    engine = create_engine(_TEST_DATABASE_URL)
    Base.metadata.create_all(engine)
    connection = engine.connect()
    outer_tx = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    yield session

    session.close()
    outer_tx.rollback()
    connection.close()
    engine.dispose()
