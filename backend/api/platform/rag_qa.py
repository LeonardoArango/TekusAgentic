"""Endpoint de preguntas al RAG de Confluence para usuarios ya autenticados
por SSO (plataforma web) — reusa el mismo pipeline híbrido del Agente de
Soporte, respondiendo con OpenAI en vez de Anthropic (ver
`agents/llm_client_openai.py` para el porqué de los dos proveedores).
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from agents.llm_client_openai import responder_pregunta_rag
from agents.soporte_web.grafo import construir_grafo, fuentes_publicas
from api.platform.auth import UsuarioAutenticado, get_current_user
from rag.indexacion.provider_factory import get_embeddings_provider
from rag.recuperacion.hybrid_search import hybrid_search

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/platform/rag", tags=["platform", "rag"])

_engine = None
_helpdesk = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", "+psycopg"))
    return _engine


def _ticket_write_enabled() -> bool:
    """La creación real de tickets en Odoo está apagada por defecto. Se
    enciende con ODOO_TICKET_WRITE_ENABLED=1 apuntando a la instancia de
    PRUEBAS (credenciales ODOO_*_TEST en Doppler)."""
    return os.environ.get("ODOO_TICKET_WRITE_ENABLED", "").lower() in ("1", "true", "yes")


def _get_helpdesk():
    """Cliente de Odoo Helpdesk contra la instancia de PRUEBAS (credenciales
    ODOO_*_TEST), perezoso — instanciarlo hace login a Odoo."""
    global _helpdesk
    if _helpdesk is None:
        from connectors.odoo_common import OdooConnection
        from connectors.odoo_helpdesk.client import OdooHelpdeskClient

        _helpdesk = OdooHelpdeskClient(
            OdooConnection(
                url=os.environ["ODOO_URL_TEST"],
                db=os.environ["ODOO_DB_TEST"],
                username=os.environ["ODOO_USERNAME_TEST"],
                password=os.environ["ODOO_API_KEY_TEST"],
            )
        )
    return _helpdesk


class PreguntaRequest(BaseModel):
    pregunta: str


class FuenteResponse(BaseModel):
    page_title: str
    page_url: str
    space_key: str


class PreguntaResponse(BaseModel):
    puede_resolver: bool
    respuesta: str
    fuentes: list[FuenteResponse]


@router.post("/preguntas", response_model=PreguntaResponse)
def preguntar(
    body: PreguntaRequest,
    usuario: UsuarioAutenticado = Depends(get_current_user),  # noqa: B008
) -> PreguntaResponse:
    """Responde una pregunta usando el RAG híbrido sobre Confluence.

    Requiere sesión SSO válida (Depends(get_current_user)) — nunca exponer
    sin autenticación, aunque el contenido fuente (Confluence) no sea
    sensible por sí mismo: es una llamada con costo de LLM por request.
    """
    embeddings = get_embeddings_provider()
    with Session(_get_engine()) as session:
        contexto = hybrid_search(session, body.pregunta, embeddings)

    if not contexto:
        return PreguntaResponse(puede_resolver=False, respuesta="", fuentes=[])

    decision = responder_pregunta_rag(
        pregunta=body.pregunta,
        fragmentos=[c["text"] for c in contexto],
    )

    fuentes = [
        FuenteResponse(
            page_title=contexto[i]["page_title"],
            page_url=contexto[i]["page_url"],
            space_key=contexto[i]["space_key"],
        )
        for i in decision.get("fuentes_usadas", [])
        if 0 <= i < len(contexto)
    ]

    return PreguntaResponse(
        puede_resolver=decision["puede_resolver"],
        respuesta=decision.get("respuesta", ""),
        fuentes=fuentes,
    )


# ---------------------------------------------------------------------------
# Flujo conversacional: el agente puede repreguntar antes de resolver
# ---------------------------------------------------------------------------


class MensajeChat(BaseModel):
    rol: str  # 'user' | 'assistant'
    texto: str


class ChatRequest(BaseModel):
    mensajes: list[MensajeChat]


class ChatResponse(BaseModel):
    tipo: str  # 'pregunta' | 'respuesta' | 'escalar'
    texto: str
    fuentes: list[FuenteResponse]
    intencion: str = "soporte"  # 'soporte' | 'venta' | 'mixto' (venta solo se etiqueta, Fase 1)
    ticket_ref: str | None = None  # nº del ticket recién creado para ESTE cliente (si aplica)


def _crear_ticket(nombre: str, correo: str, resumen: str) -> str | None:
    """CreadorTicket para el grafo. Respeta el gate de escritura a Odoo."""
    if not _ticket_write_enabled():
        logger.info("Escalamiento (escritura de ticket deshabilitada): resumen=%s", resumen[:80])
        return None
    try:
        ticket = _get_helpdesk().crear_ticket(
            asunto=resumen[:120],
            descripcion=resumen,
            nombre_cliente=nombre,
            correo_cliente=correo,
        )
        return ticket.referencia
    except Exception:
        logger.exception("No se pudo crear el ticket en Odoo al escalar")
        return None


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    usuario: UsuarioAutenticado = Depends(get_current_user),  # noqa: B008
) -> ChatResponse:
    """Un turno del flujo conversacional de soporte (grafo LangGraph, ADR 0006).

    Sin estado en el servidor: el historial completo viaja en cada request
    (lo mantiene el frontend). El grafo decide aclarar/resolver/escalar; el
    saludo, el gating de datos y la creación de ticket son determinísticos.
    """
    mensajes = [m.model_dump() for m in body.mensajes]
    if not any(m["rol"] == "user" for m in mensajes):
        return ChatResponse(tipo="pregunta", texto="¿En qué te puedo ayudar?", fuentes=[])

    es_primer_turno = not any(m["rol"] == "assistant" for m in mensajes)
    embeddings = get_embeddings_provider()

    with Session(_get_engine()) as session:

        def buscar(query: str) -> list[dict]:
            return hybrid_search(session, query, embeddings)

        grafo = construir_grafo(buscar, _crear_ticket)
        estado = grafo.invoke({"mensajes": mensajes, "es_primer_turno": es_primer_turno})

    fuentes = [
        FuenteResponse(page_title=c["page_title"], page_url=c["page_url"], space_key=c["space_key"])
        for c in fuentes_publicas(estado)
    ]
    return ChatResponse(
        tipo=estado.get("tipo", "respuesta"),
        texto=estado.get("texto", ""),
        fuentes=fuentes,
        intencion=estado.get("intencion", "soporte"),
        ticket_ref=estado.get("ticket_ref"),
    )
