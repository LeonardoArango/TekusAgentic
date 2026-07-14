"""Cliente LLM compartido (Anthropic Claude) para los nodos del grafo de agentes.

Todas las decisiones estructuradas (¿puedo resolver esto?, ¿el usuario dio un
número de ticket?) se fuerzan vía tool-use en vez de parsear texto libre —
más confiable y más fácil de testear con mocks.
"""

from __future__ import annotations

import os

import anthropic

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def _model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")


_RESPONDER_TOOL = {
    "name": "responder_soporte",
    "description": (
        "Registra si el contexto entregado alcanza para responder la pregunta del cliente "
        "con confianza, y la respuesta en caso de que sí."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "puede_resolver": {
                "type": "boolean",
                "description": (
                    "true solo si el contexto contiene información suficiente para responder "
                    "sin inventar nada. Ante la duda, false."
                ),
            },
            "respuesta": {
                "type": "string",
                "description": (
                    "Respuesta para el cliente en español, profesional y cercana. Vacía si "
                    "puede_resolver es false."
                ),
            },
            "fuentes_usadas": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Índices (0-based) de los fragmentos de contexto realmente usados.",
            },
        },
        "required": ["puede_resolver", "respuesta", "fuentes_usadas"],
    },
}

_EXTRAER_TICKET_TOOL = {
    "name": "extraer_referencia_ticket",
    "description": (
        "Extrae si el usuario mencionó un número/referencia de ticket de soporte existente."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tiene_ticket": {"type": "boolean"},
            "referencia": {
                "type": "string",
                "description": (
                    "El número o referencia tal cual la escribió el usuario. Vacío si "
                    "tiene_ticket es false."
                ),
            },
        },
        "required": ["tiene_ticket", "referencia"],
    },
}


def _tool_input(message: anthropic.types.Message) -> dict:
    tool_use = next(block for block in message.content if block.type == "tool_use")
    return tool_use.input


def decidir_respuesta_soporte(pregunta: str, fragmentos: list[str]) -> dict:
    """Decide si `fragmentos` (contexto recuperado del RAG) alcanza para responder `pregunta`."""
    contexto = "\n\n".join(f"[{i}] {frag}" for i, frag in enumerate(fragmentos))
    message = _get_client().messages.create(
        model=_model(),
        max_tokens=1024,
        system=(
            "Eres el Agente de Soporte de Tekus por WhatsApp. Respondes SOLO con base en el "
            "contexto entregado (extraído de la wiki interna de Tekus). Nunca inventes "
            "información que no esté en el contexto. Es preferible escalar a un ticket humano "
            "que dar una respuesta incorrecta o inventada."
        ),
        tools=[_RESPONDER_TOOL],
        tool_choice={"type": "tool", "name": "responder_soporte"},
        messages=[
            {
                "role": "user",
                "content": f"Pregunta del cliente:\n{pregunta}\n\nContexto disponible:\n{contexto}",
            }
        ],
    )
    return _tool_input(message)


def extraer_referencia_ticket(respuesta_usuario: str) -> dict:
    """Interpreta la respuesta del usuario a "¿tienes ya un número de ticket?"."""
    message = _get_client().messages.create(
        model=_model(),
        max_tokens=256,
        system=(
            "Extraes si el usuario mencionó un número de ticket de soporte existente. Los "
            'usuarios lo escriben de muchas formas ("sí, es el 4521", "no tengo", "TK-00123").'
        ),
        tools=[_EXTRAER_TICKET_TOOL],
        tool_choice={"type": "tool", "name": "extraer_referencia_ticket"},
        messages=[{"role": "user", "content": respuesta_usuario}],
    )
    return _tool_input(message)
