"""Grafo LangGraph del Agente de Soporte.

recuperar_contexto -> decidir_respuesta -> (fin | resolver_ticket) -> fin

`construir_grafo(...)` recibe las dependencias externas (búsqueda híbrida ya
resuelta a una sesión/proveedor de embeddings concretos, cliente de Odoo
Helpdesk) y devuelve un grafo compilado — así se puede mockear todo en tests
sin tocar la lógica de negocio.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, TypedDict

from langgraph.graph import END, StateGraph

from agents import llm_client
from connectors.odoo_helpdesk.client import OdooHelpdeskClient, Ticket


class EstadoSoporte(TypedDict, total=False):
    mensaje: str
    telefono: str
    contexto: list[dict]
    puede_resolver: bool
    respuesta: str
    fuentes: list[str]
    esperando_referencia_ticket: bool
    referencia_ticket_previa: str | None
    ticket: Ticket | None
    ticket_creado: bool


class BuscadorHibrido(Protocol):
    def __call__(self, query: str) -> list[dict]: ...


def _nodo_recuperar_contexto(buscar: BuscadorHibrido) -> Callable[[EstadoSoporte], EstadoSoporte]:
    def nodo(estado: EstadoSoporte) -> EstadoSoporte:
        return {"contexto": buscar(estado["mensaje"])}

    return nodo


def _nodo_decidir_respuesta(estado: EstadoSoporte) -> EstadoSoporte:
    contexto = estado.get("contexto", [])
    if not contexto:
        return {"puede_resolver": False, "respuesta": "", "fuentes": []}

    decision = llm_client.decidir_respuesta_soporte(
        pregunta=estado["mensaje"],
        fragmentos=[c["text"] for c in contexto],
    )
    fuentes = [
        contexto[i]["page_url"]
        for i in decision.get("fuentes_usadas", [])
        if 0 <= i < len(contexto)
    ]
    return {
        "puede_resolver": decision["puede_resolver"],
        "respuesta": decision.get("respuesta", ""),
        "fuentes": fuentes,
    }


def _siguiente_tras_decision(estado: EstadoSoporte) -> str:
    return END if estado.get("puede_resolver") else "resolver_ticket"


def _crear_ticket(
    estado: EstadoSoporte,
    helpdesk: OdooHelpdeskClient,
    referencia_no_encontrada: str | None = None,
) -> EstadoSoporte:
    ticket = helpdesk.crear_ticket(
        asunto=estado["mensaje"][:120],
        descripcion=estado["mensaje"],
        telefono_contacto=estado["telefono"],
    )
    aviso_previo = (
        f" (no encontré el ticket #{referencia_no_encontrada} que mencionaste, así que abrí "
        "uno nuevo)"
        if referencia_no_encontrada
        else ""
    )
    return {
        "ticket": ticket,
        "ticket_creado": True,
        "esperando_referencia_ticket": False,
        "respuesta": (
            f"No pude resolverlo automáticamente{aviso_previo}. Creé el ticket "
            f"#{ticket.referencia} y un agente humano te va a contactar pronto."
        ),
        "fuentes": [],
    }


def resolver_ticket(estado: EstadoSoporte, helpdesk: OdooHelpdeskClient) -> EstadoSoporte:
    """Lógica de negocio de la etapa de ticket — un único lugar, reusado por el
    nodo del grafo y por el flujo de "retomo tras preguntar por el ticket" en
    `agente.procesar_mensaje` (ver ese módulo para el porqué)."""
    referencia_previa = estado.get("referencia_ticket_previa")

    if referencia_previa:
        ticket = helpdesk.buscar_por_referencia(referencia_previa)
        if ticket:
            return {
                "ticket": ticket,
                "esperando_referencia_ticket": False,
                "respuesta": (
                    f'Encontré tu ticket #{ticket.referencia} ("{ticket.asunto}"), actualmente '
                    f'en estado "{ticket.etapa}". Un agente humano lo está revisando.'
                ),
                "fuentes": [],
            }
        return _crear_ticket(estado, helpdesk, referencia_no_encontrada=referencia_previa)

    if not estado.get("esperando_referencia_ticket"):
        return {
            "esperando_referencia_ticket": True,
            "respuesta": (
                "No encontré una respuesta certera en nuestra base de conocimiento. "
                "¿Ya tienes un número de ticket abierto para este problema? Si es así, "
                "compártemelo; si no, te creo uno nuevo ahora mismo."
            ),
            "fuentes": [],
        }

    return _crear_ticket(estado, helpdesk)


def construir_grafo(buscar: BuscadorHibrido, helpdesk: OdooHelpdeskClient):
    grafo = StateGraph(EstadoSoporte)
    grafo.add_node("recuperar_contexto", _nodo_recuperar_contexto(buscar))
    grafo.add_node("decidir_respuesta", _nodo_decidir_respuesta)
    grafo.add_node("resolver_ticket", lambda estado: resolver_ticket(estado, helpdesk))

    grafo.set_entry_point("recuperar_contexto")
    grafo.add_edge("recuperar_contexto", "decidir_respuesta")
    grafo.add_conditional_edges(
        "decidir_respuesta",
        _siguiente_tras_decision,
        {END: END, "resolver_ticket": "resolver_ticket"},
    )
    grafo.add_edge("resolver_ticket", END)

    return grafo.compile()
