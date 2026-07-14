"""Endpoint de preguntas al RAG de Confluence para usuarios ya autenticados
por SSO (plataforma web) — reusa el mismo pipeline híbrido del Agente de
Soporte, respondiendo con OpenAI en vez de Anthropic (ver
`agents/llm_client_openai.py` para el porqué de los dos proveedores).
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from agents.llm_client_openai import responder_pregunta_rag
from api.platform.auth import UsuarioAutenticado, get_current_user
from rag.indexacion.provider_factory import get_embeddings_provider
from rag.recuperacion.hybrid_search import hybrid_search

router = APIRouter(prefix="/api/platform/rag", tags=["platform", "rag"])

_engine = None


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
