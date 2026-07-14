"""Persistencia del estado de diálogo en Redis, por conversation_id.

Es el "Orquestador/Memoria" que pide CLAUDE.md (HU #25): el estado no viaja
en cada request ni se reconstruye — vive en Redis con TTL. Así el motor puede
sostener conversaciones largas sin reenviar todo el historial ni reventar el
contexto del LLM.
"""

from __future__ import annotations

import json
import os

import redis

from agents.soporte_web.estado import DialogueState, Fase

# TTL alineado con la ventana de 24h de WhatsApp; una conversación inactiva
# más de eso se considera cerrada.
_TTL_SEGUNDOS = 24 * 60 * 60
_PREFIJO = "conv:"

_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    return _client


def cargar(conversation_id: str, canal: str = "web") -> DialogueState:
    """Devuelve el estado guardado o uno nuevo si la conversación no existe."""
    raw = _get_client().get(_PREFIJO + conversation_id)
    if raw:
        return DialogueState.from_dict(json.loads(raw))
    return DialogueState(conversation_id=conversation_id, canal=canal, fase=Fase.SALUDO)


def guardar(estado: DialogueState) -> None:
    _get_client().set(
        _PREFIJO + estado.conversation_id,
        json.dumps(estado.to_dict(), ensure_ascii=False),
        ex=_TTL_SEGUNDOS,
    )


# A partir de cuántos turnos crudos empezamos a resumir los más viejos, para
# no crecer el contexto del LLM sin límite en conversaciones largas.
_UMBRAL_TURNOS = 16
_CONSERVAR_RECIENTES = 8


def resumir_si_necesario(estado: DialogueState) -> None:
    """Comprime los turnos viejos en `estado.resumen` cuando el historial crece.

    Mantiene los últimos turnos crudos y funde el resto (más el resumen previo)
    en un resumen breve. Usa el modelo barato — es una tarea trivial.
    """
    if len(estado.turnos) <= _UMBRAL_TURNOS:
        return

    from agents import llm_client_openai as llm

    viejos = estado.turnos[:-_CONSERVAR_RECIENTES]
    recientes = estado.turnos[-_CONSERVAR_RECIENTES:]
    transcripcion = "\n".join(f"{t.rol}: {t.texto}" for t in viejos)
    system = (
        "Resume en pocas frases, en español, esta parte de una conversación de soporte "
        "(problema del cliente, qué se intentó, datos entregados, estado). Sé factual y breve."
    )
    entrada = (f"Resumen previo:\n{estado.resumen}\n\n" if estado.resumen else "") + (
        f"Conversación a resumir:\n{transcripcion}"
    )
    estado.resumen = llm.completar_texto(
        system, [{"role": "user", "content": entrada}], model=llm.modelo_simple(), temperatura=0.2
    )
    estado.turnos = recientes
