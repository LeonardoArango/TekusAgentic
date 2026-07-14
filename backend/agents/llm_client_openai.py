"""Cliente OpenAI — usado únicamente por el endpoint de preguntas al RAG de
la plataforma web (`api/platform/rag_qa.py`), no por el Agente de Soporte de
WhatsApp (ese sigue en `agents/llm_client.py`, Anthropic).

Dos proveedores de LLM conviven a propósito en este repo: decisión explícita
de Leonardo para esta feature — no unificar sin confirmarlo de nuevo.
"""

from __future__ import annotations

import json
import os

from openai import OpenAI

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def _model() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


_RESPONDER_TOOL = {
    "type": "function",
    "function": {
        "name": "responder_pregunta",
        "description": (
            "Registra si el contexto entregado alcanza para responder la pregunta con "
            "confianza, y la respuesta en caso de que sí."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "puede_resolver": {
                    "type": "boolean",
                    "description": (
                        "true solo si el contexto contiene información suficiente para "
                        "responder sin inventar nada. Ante la duda, false."
                    ),
                },
                "respuesta": {
                    "type": "string",
                    "description": (
                        "Respuesta en español, profesional y concreta. Vacía si "
                        "puede_resolver es false."
                    ),
                },
                "fuentes_usadas": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": (
                        "Índices (0-based) de los fragmentos de contexto realmente usados."
                    ),
                },
            },
            "required": ["puede_resolver", "respuesta", "fuentes_usadas"],
        },
    },
}


def responder_pregunta_rag(pregunta: str, fragmentos: list[str]) -> dict:
    """Responde `pregunta` usando únicamente `fragmentos` como contexto.

    Fuerza la salida vía tool-calling (no parsea texto libre) — mismo criterio
    que `agents/llm_client.decidir_respuesta_soporte`, para poder testear con
    mocks y no depender de que el modelo devuelva JSON bien formado por su cuenta.
    """
    contexto_numerado = "\n\n".join(f"[{i}] {frag}" for i, frag in enumerate(fragmentos))

    response = _get_client().chat.completions.create(
        model=_model(),
        messages=[
            {
                "role": "system",
                "content": (
                    "Respondes preguntas del equipo interno de Tekus usando exclusivamente "
                    "el contexto entregado (fragmentos de la wiki de Confluence). Si el "
                    "contexto no alcanza para responder con confianza, dilo explícitamente "
                    "en vez de inventar."
                ),
            },
            {
                "role": "user",
                "content": f"Contexto:\n{contexto_numerado}\n\nPregunta: {pregunta}",
            },
        ],
        tools=[_RESPONDER_TOOL],
        tool_choice={"type": "function", "function": {"name": "responder_pregunta"}},
    )

    tool_call = response.choices[0].message.tool_calls[0]
    return json.loads(tool_call.function.arguments)
