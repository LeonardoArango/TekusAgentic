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


# Contrato del flujo conversacional.
# Ver docs/decisiones/0006-flujo-conversacional-agente-soporte.md
_CONVERSAR_TOOL = {
    "type": "function",
    "function": {
        "name": "decidir_turno",
        "description": (
            "Decide la acción del agente para este turno: preguntar un detalle, resolver, "
            "o escalar a un agente humano."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "accion": {
                    "type": "string",
                    "enum": ["preguntar", "responder", "escalar"],
                    "description": (
                        "'preguntar' si la consulta es ambigua o falta un dato clave. "
                        "'responder' si el contexto alcanza para dar la solución. "
                        "'escalar' si NO hay respuesta en el contexto, si ya repreguntaste y "
                        "el cliente no aporta el dato (no converge), o si el cliente pide "
                        "explícitamente un humano."
                    ),
                },
                "intencion": {
                    "type": "string",
                    "enum": ["soporte", "venta", "mixto"],
                    "description": "Intención del mensaje. En esta fase 'venta' solo se etiqueta.",
                },
                "pregunta_aclaratoria": {
                    "type": "string",
                    "description": (
                        "Si accion='preguntar': UNA pregunta concreta y corta, en español, "
                        "tono de tú. Vacía en otro caso."
                    ),
                },
                "respuesta": {
                    "type": "string",
                    "description": (
                        "Si accion='responder': solución paso a paso, en español, tono "
                        "cercano. Si accion='escalar': mensaje cálido avisando que se pasa a "
                        "un agente humano. Vacía si accion='preguntar'."
                    ),
                },
                "fuentes_usadas": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": (
                        "Si accion='responder': índices (0-based) de los fragmentos usados."
                    ),
                },
                "motivo_escalamiento": {
                    "type": "string",
                    "description": (
                        "Si accion='escalar': sin_respuesta | no_converge | cliente_pide_humano."
                    ),
                },
            },
            "required": ["accion", "intencion"],
        },
    },
}


def conversar_rag(mensajes: list[dict], fragmentos: list[str]) -> dict:
    """Flujo conversacional de 3 acciones (ver ADR 0006).

    `mensajes` es el historial [{rol: 'user'|'assistant', texto: str}, ...].
    Devuelve {accion, intencion, pregunta_aclaratoria, respuesta, fuentes_usadas,
    motivo_escalamiento}.
    """
    contexto_numerado = "\n\n".join(f"[{i}] {frag}" for i, frag in enumerate(fragmentos))

    system = (
        "Eres el asistente de soporte de Tekus. Respondes usando EXCLUSIVAMENTE el "
        "contexto entregado (wiki de Confluence y tickets de soporte resueltos).\n"
        "Elige la acción del turno:\n"
        "- preguntar: si la consulta es ambigua o falta un dato clave (modelo/tipo de "
        "equipo, síntoma exacto, en qué punto ocurre, qué ya intentó). Haz UNA pregunta "
        "concreta. No interrogues de más.\n"
        "- responder: en cuanto tengas lo suficiente, da la solución paso a paso citando "
        "las fuentes usadas.\n"
        "- escalar: si el contexto no tiene la respuesta, si ya preguntaste y el cliente no "
        "puede darte el dato (no converge), o si pide hablar con un humano. Al escalar, "
        "dile con calidez que lo pasas a un agente humano.\n"
        "Clasifica también la intención (soporte/venta/mixto); en esta fase la venta solo "
        "se etiqueta, no actúes como vendedor.\n"
        "Tono cercano, de tú, en español. Sin emojis. Nunca inventes lo que no está en el "
        "contexto."
    )

    chat_msgs = [{"role": "system", "content": system}]
    for m in mensajes:
        rol = "assistant" if m.get("rol") == "assistant" else "user"
        chat_msgs.append({"role": rol, "content": m.get("texto", "")})
    chat_msgs.append(
        {
            "role": "system",
            "content": f"Contexto recuperado para el último mensaje:\n{contexto_numerado}",
        }
    )

    response = _get_client().chat.completions.create(
        model=_model(),
        messages=chat_msgs,
        tools=[_CONVERSAR_TOOL],
        tool_choice={"type": "function", "function": {"name": "decidir_turno"}},
    )
    tool_call = response.choices[0].message.tool_calls[0]
    return json.loads(tool_call.function.arguments)


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
