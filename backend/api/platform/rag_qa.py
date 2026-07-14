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

from agents.llm_client_openai import conversar_rag, responder_pregunta_rag
from api.platform.auth import UsuarioAutenticado, get_current_user
from rag.indexacion.provider_factory import get_embeddings_provider
from rag.recuperacion.hybrid_search import hybrid_search

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/platform/rag", tags=["platform", "rag"])

# Fuentes internas que NUNCA se muestran al usuario (solo alimentan la
# respuesta). Los tickets de Odoo son conocimiento interno; solo se citan
# documentos públicos de Confluence. Ver feedback de Leonardo (2026-07-14).
_SPACES_INTERNOS = {"ODOO_HELPDESK"}

_engine = None
_helpdesk = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", "+psycopg"))
    return _engine


def _ticket_write_enabled() -> bool:
    """La creación real de tickets en Odoo está apagada por defecto hasta que
    se configuren credenciales de una instancia de PRUEBAS (no producción).
    Encender con ODOO_TICKET_WRITE_ENABLED=1."""
    return os.environ.get("ODOO_TICKET_WRITE_ENABLED", "").lower() in ("1", "true", "yes")


def _get_helpdesk():
    """Cliente de Odoo Helpdesk (perezoso). Solo se instancia si la escritura
    está habilitada — instanciarlo hace login a Odoo."""
    global _helpdesk
    if _helpdesk is None:
        from connectors.odoo_common import OdooConnection
        from connectors.odoo_helpdesk.client import OdooHelpdeskClient

        _helpdesk = OdooHelpdeskClient(OdooConnection())
    return _helpdesk


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", "+psycopg"))
    return _engine


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


def _query_de_conversacion(mensajes: list[MensajeChat]) -> str:
    """Construye la query de recuperación con los turnos del usuario (los que
    aportan el problema real), no las repreguntas del agente."""
    return " ".join(m.texto for m in mensajes if m.rol == "user").strip()


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    usuario: UsuarioAutenticado = Depends(get_current_user),  # noqa: B008
) -> ChatResponse:
    """Turno de conversación: recupera contexto con todo lo que el cliente ha
    dicho hasta ahora y deja que el agente decida repreguntar o resolver.

    Sin estado en el servidor: el historial completo viaja en cada request
    (lo mantiene el frontend) — simple y suficiente para esta fase.
    """
    query = _query_de_conversacion(body.mensajes)
    if not query:
        return ChatResponse(tipo="pregunta", texto="¿En qué te puedo ayudar?", fuentes=[])

    embeddings = get_embeddings_provider()
    with Session(_get_engine()) as session:
        contexto = hybrid_search(session, query, embeddings)

    decision = conversar_rag(
        mensajes=[m.model_dump() for m in body.mensajes],
        fragmentos=[c["text"] for c in contexto],
    )
    intencion = decision.get("intencion", "soporte")
    accion = decision.get("accion", "responder")

    if accion == "preguntar":
        return ChatResponse(
            tipo="pregunta",
            texto=decision.get("pregunta_aclaratoria", ""),
            fuentes=[],
            intencion=intencion,
        )

    if accion == "escalar":
        texto = decision.get("respuesta") or (
            "No encontré una respuesta certera para esto. Lo escalo a un agente humano "
            "de Tekus para que te ayude."
        )
        ticket_ref = _crear_ticket_si_procede(decision)
        if ticket_ref:
            texto = f"{texto} Tu ticket es el #{ticket_ref}."
        return ChatResponse(
            tipo="escalar", texto=texto, fuentes=[], intencion=intencion, ticket_ref=ticket_ref
        )

    return ChatResponse(
        tipo="respuesta",
        texto=decision.get("respuesta", ""),
        fuentes=_fuentes_publicas(decision, contexto),
        intencion=intencion,
    )


def _fuentes_publicas(decision: dict, contexto: list[dict]) -> list[FuenteResponse]:
    """Solo documentos públicos de Confluence — nunca tickets internos de Odoo."""
    fuentes = []
    for i in decision.get("fuentes_usadas", []):
        if not (0 <= i < len(contexto)):
            continue
        if contexto[i]["space_key"] in _SPACES_INTERNOS:
            continue
        fuentes.append(
            FuenteResponse(
                page_title=contexto[i]["page_title"],
                page_url=contexto[i]["page_url"],
                space_key=contexto[i]["space_key"],
            )
        )
    return fuentes


def _crear_ticket_si_procede(decision: dict) -> str | None:
    """Crea el ticket en Odoo con los datos reunidos, si la escritura está
    habilitada. Devuelve la referencia del ticket o None."""
    datos = decision.get("datos_cliente") or {}
    resumen = decision.get("resumen_problema") or "Consulta de soporte por WhatsApp/consola"

    if not _ticket_write_enabled():
        logger.info(
            "Escalamiento (escritura de ticket deshabilitada): datos=%s resumen=%s",
            {k: bool(v) for k, v in datos.items()},
            resumen[:80],
        )
        return None

    try:
        ticket = _get_helpdesk().crear_ticket(
            asunto=resumen[:120],
            descripcion=resumen,
            nombre_cliente=datos.get("nombre"),
            correo_cliente=datos.get("correo"),
        )
        return ticket.referencia
    except Exception:
        logger.exception("No se pudo crear el ticket en Odoo al escalar")
        return None
