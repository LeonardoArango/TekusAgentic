"""Indexa tickets de Odoo (staging `knowledge_mining`) al RAG para que el
Agente de Soporte pueda recuperar problemas y soluciones de casos pasados.

Decisión de Leonardo (2026-07-14) que REVIERTE la regla previa de "Odoo nunca
se vectoriza" (ver docs/decisiones/0005-indexar-tickets-odoo-y-embeddings-openai.md):
- Solo se vectoriza el conocimiento HISTÓRICO de tickets (asunto, diagnóstico,
  solución, notas), no datos operativos en vivo (estado actual, cuenta, mora),
  que siguen consultándose por API en vivo.
- Cada ticket se representa como un "documento" reusando el mismo pipeline de
  indexación de Confluence (ConfluencePage), con space_key='ODOO_HELPDESK' y
  URL trazable al ticket en Odoo.
"""

from __future__ import annotations

import html
import os
import re

import psycopg
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from connectors.confluence.client import ConfluencePage
from models.rag import Base
from rag.indexacion.indexer import index_pages
from rag.indexacion.provider_factory import get_embeddings_provider

SPACE_KEY = "ODOO_HELPDESK"


def _strip_html(texto: str | None) -> str:
    if not texto:
        return ""
    sin_tags = re.sub(r"<[^>]+>", " ", texto)
    return html.unescape(re.sub(r"\s+", " ", sin_tags)).strip()


def _ticket_a_documento(raw: dict) -> str:
    """Compone un documento de texto legible a partir del JSON crudo del ticket.

    Incluye los campos con valor semántico para troubleshooting; omite los
    vacíos para no meter ruido.
    """
    partes: list[str] = []
    partes.append(f"Asunto: {raw.get('name', '')}")
    if raw.get("x_studio_tickets_tipo"):
        partes.append(f"Tipo: {raw['x_studio_tickets_tipo']}")
    if raw.get("x_studio_diagnstico"):
        partes.append(f"Diagnóstico: {raw['x_studio_diagnstico']}")
    if raw.get("x_studio_solucin_entregada"):
        partes.append(f"Solución entregada: {raw['x_studio_solucin_entregada']}")
    if raw.get("x_studio_procedimiento_para_la_solucin"):
        partes.append(f"Procedimiento: {raw['x_studio_procedimiento_para_la_solucin']}")
    if raw.get("description"):
        desc = _strip_html(raw["description"])
        if desc:
            partes.append(f"Descripción del cliente: {desc}")

    # Notas relevantes (comentarios humanos), no notificaciones automáticas
    notas = []
    for msg in raw.get("messages_raw", []):
        if msg.get("message_type") == "comment":
            cuerpo = _strip_html(msg.get("body"))
            if cuerpo and "o_mail_notification" not in (msg.get("body") or ""):
                notas.append(cuerpo)
    if notas:
        partes.append("Notas de seguimiento:\n" + "\n".join(f"- {n}" for n in notas))

    return "\n\n".join(partes)


def _ticket_url(raw: dict) -> str:
    base = os.environ.get("ODOO_URL", "").rstrip("/")
    return f"{base}/odoo/helpdesk/{raw.get('odoo_ticket_id') or raw.get('id')}"


def index_tickets_to_rag() -> dict:
    engine = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", "+psycopg"))
    Base.metadata.create_all(engine)
    embeddings = get_embeddings_provider()

    # Un snapshot por ticket (el más reciente por odoo_ticket_id).
    conn = psycopg.connect(os.environ["DATABASE_URL"].replace("+asyncpg", ""))
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (odoo_ticket_id) odoo_ticket_id, ticket_ref, raw_data
            FROM knowledge_mining.odoo_ticket_mining_raw
            ORDER BY odoo_ticket_id, fetched_at DESC
        """
        )
        filas = cur.fetchall()
    conn.close()

    pages: list[ConfluencePage] = []
    for odoo_ticket_id, ticket_ref, raw in filas:
        raw = dict(raw)
        raw["odoo_ticket_id"] = odoo_ticket_id
        cuerpo = _ticket_a_documento(raw)
        if not cuerpo.strip():
            continue
        titulo = f"Ticket #{ticket_ref}: {raw.get('name', '')}".strip()
        pages.append(
            ConfluencePage(
                page_id=f"odoo-ticket-{odoo_ticket_id}",
                title=titulo[:512],
                space_key=SPACE_KEY,
                url=_ticket_url(raw),
                body_markdown=cuerpo,
            )
        )

    with Session(engine) as session:
        resumen = index_pages(session, pages, embeddings)

    return {
        "tickets_indexados": len(pages),
        "nuevos": resumen.nuevas,
        "actualizados": resumen.actualizadas,
        "sin_cambios": resumen.sin_cambios,
        "chunks_escritos": resumen.chunks_escritos,
    }


if __name__ == "__main__":
    print(index_tickets_to_rag())
