"""Backfill de conocimiento: indexa al RAG TODOS los tickets resueltos de
Odoo Helpdesk — la verdadera fuente de problemas y soluciones pasadas.

A diferencia de `odoo_ticket_sync.py` (que minaba tickets ABIERTOS con sus
binarios, para curación humana), este backfill:
- Trae tickets RESUELTOS (stage_id = 4).
- Es SOLO TEXTO (asunto/diagnóstico/solución/notas) — no descarga adjuntos
  binarios: para el RAG solo importa el texto, y 4100 tickets de fotos serían
  gigabytes inútiles.
- Va directo de Odoo al RAG (no pasa por la tabla de staging), reusando la
  composición de documento y el pipeline de indexación de Confluence.

Ver docs/decisiones/0005-indexar-tickets-odoo-y-embeddings-openai.md.
"""

from __future__ import annotations

import logging
import os
import time

import odoorpc
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from connectors.confluence.client import ConfluencePage
from knowledge_mining.index_tickets_to_rag import SPACE_KEY, _ticket_a_documento, _ticket_url
from models.rag import Base
from rag.indexacion.indexer import index_pages
from rag.indexacion.provider_factory import get_embeddings_provider

logger = logging.getLogger(__name__)

RESUELTO_STAGE_ID = 4
_READ_BATCH = 200
_MSG_READ_BATCH = 500
_INDEX_BATCH = 200  # tickets por corrida de index_pages (acota memoria/embeddings)

_TICKET_FIELDS = [
    "id",
    "ticket_ref",
    "name",
    "x_studio_tickets_tipo",
    "x_studio_diagnstico",
    "x_studio_solucin_entregada",
    "x_studio_procedimiento_para_la_solucin",
    "description",
    "message_ids",
]


def _retry(fn, *args, attempts: int = 3, delay: float = 3.0, **kwargs):
    last = None
    for i in range(attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last = exc
            logger.warning("reintento %s/%s: %s", i + 1, attempts, exc)
            time.sleep(delay)
    raise last


def _connect_odoo() -> odoorpc.ODOO:
    odoo = odoorpc.ODOO(
        os.environ["ODOO_URL"].replace("https://", "").replace("http://", ""),
        protocol="jsonrpc+ssl",
        port=443,
        timeout=180,
    )
    odoo.login(os.environ["ODOO_DB"], os.environ["ODOO_USERNAME"], os.environ["ODOO_PASSWORD"])
    return odoo


def backfill_resolved_tickets() -> dict:
    odoo = _connect_odoo()
    Ticket = odoo.env["helpdesk.ticket"]
    Message = odoo.env["mail.message"]

    engine = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", "+psycopg"))
    Base.metadata.create_all(engine)
    embeddings = get_embeddings_provider()

    ids = _retry(Ticket.search, [("stage_id", "=", RESUELTO_STAGE_ID)])
    logger.info("Tickets resueltos a procesar: %d", len(ids))
    print(f"Tickets resueltos a procesar: {len(ids)}")

    totales = {"indexados": 0, "chunks": 0, "sin_texto": 0}

    # Se procesa en bloques: leer metadata del bloque, leer sus mensajes en
    # lote, componer documentos e indexar. Así no se cargan 4100 tickets +
    # todos sus mensajes en memoria a la vez.
    for inicio in range(0, len(ids), _INDEX_BATCH):
        bloque_ids = ids[inicio : inicio + _INDEX_BATCH]
        tickets = _retry(Ticket.read, bloque_ids, _TICKET_FIELDS)

        # Junta todos los message_ids del bloque y léelos de una vez.
        todos_msg_ids = [mid for t in tickets for mid in t.get("message_ids", [])]
        mensajes_por_id: dict[int, dict] = {}
        for m_ini in range(0, len(todos_msg_ids), _MSG_READ_BATCH):
            lote = todos_msg_ids[m_ini : m_ini + _MSG_READ_BATCH]
            for m in _retry(Message.read, lote, ["id", "body", "message_type"]):
                mensajes_por_id[m["id"]] = m

        pages: list[ConfluencePage] = []
        for t in tickets:
            raw = dict(t)
            raw["odoo_ticket_id"] = t["id"]
            raw["messages_raw"] = [
                mensajes_por_id[mid] for mid in t.get("message_ids", []) if mid in mensajes_por_id
            ]
            cuerpo = _ticket_a_documento(raw)
            # Un ticket sin diagnóstico/solución/descripción no aporta
            # conocimiento — solo tendría el asunto. Se omite.
            if len(cuerpo.strip()) <= len(f"Asunto: {raw.get('name', '')}") + 5:
                totales["sin_texto"] += 1
                continue
            titulo = f"Ticket #{t.get('ticket_ref')}: {t.get('name', '')}".strip()
            pages.append(
                ConfluencePage(
                    page_id=f"odoo-ticket-{t['id']}",
                    title=titulo[:512],
                    space_key=SPACE_KEY,
                    url=_ticket_url(raw),
                    body_markdown=cuerpo,
                )
            )

        if pages:
            with Session(engine) as session:
                resumen = index_pages(session, pages, embeddings)
            totales["indexados"] += len(pages)
            totales["chunks"] += resumen.chunks_escritos

        print(
            f"  bloque {inicio // _INDEX_BATCH + 1}: "
            f"{totales['indexados']} indexados, {totales['sin_texto']} sin texto útil"
        )

    print(f"LISTO: {totales}")
    return totales


if __name__ == "__main__":
    print(backfill_resolved_tickets())
