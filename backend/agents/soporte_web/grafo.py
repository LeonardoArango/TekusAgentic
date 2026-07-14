"""Grafo LangGraph del flujo conversacional de soporte (consola web).

Implementa el flujo del ADR 0006 como máquina de estados, en vez de una sola
llamada al LLM. Reparte responsabilidades para que el comportamiento sea
confiable:

- El LLM SOLO entiende y redacta (nodos `analizar` y `decidir`).
- Lo estructural es determinístico (saludo del primer turno, exigir
  nombre+correo antes de escalar, crear el ticket): así el saludo, la
  recolección de datos y la trazabilidad no dependen de que el modelo
  "haga caso".

recuperar → analizar → decidir → (aclarar | resolver | escalar)
El nodo `escalar` primero exige datos del cliente (si faltan, pide) y solo
entonces crea el ticket.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, TypedDict

from langgraph.graph import END, StateGraph

from agents import llm_client_openai as llm


class BuscadorHibrido(Protocol):
    def __call__(self, query: str) -> list[dict]: ...


class CreadorTicket(Protocol):
    def __call__(self, nombre: str, correo: str, resumen: str) -> str | None:
        """Crea el ticket y devuelve su referencia, o None si no se pudo/está deshabilitado."""


class EstadoChat(TypedDict, total=False):
    mensajes: list[dict]  # [{rol, texto}]
    es_primer_turno: bool
    contexto: list[dict]
    datos: dict  # {nombre, correo, cuenta, resumen_problema, intencion, pide_humano}
    accion: str  # aclarar | resolver | escalar
    _pregunta: str  # borrador de pregunta del nodo decidir
    _respuesta: str  # borrador de respuesta del nodo decidir
    # salida
    tipo: str  # pregunta | respuesta | escalar
    texto: str
    fuentes_idx: list[int]
    intencion: str
    ticket_ref: str | None


_SPACES_INTERNOS = {"ODOO_HELPDESK"}


def _saludo(datos: dict) -> str:
    nombre = (datos.get("nombre") or "").strip()
    hola = f"Hola {nombre}, " if nombre else "Hola, "
    resumen = (datos.get("resumen_problema") or "").strip()
    if resumen:
        return f"{hola}entiendo que {resumen[0].lower()}{resumen[1:]}. "
    return hola


def _query(mensajes: list[dict]) -> str:
    return " ".join(m["texto"] for m in mensajes if m.get("rol") == "user").strip()


def _nodo_recuperar(buscar: BuscadorHibrido) -> Callable[[EstadoChat], EstadoChat]:
    def nodo(estado: EstadoChat) -> EstadoChat:
        return {"contexto": buscar(_query(estado["mensajes"]))}

    return nodo


def _nodo_analizar(estado: EstadoChat) -> EstadoChat:
    datos = llm.extraer_estado_conversacion(estado["mensajes"])
    return {"datos": datos, "intencion": datos.get("intencion", "soporte")}


def _nodo_decidir(estado: EstadoChat) -> EstadoChat:
    # Si el cliente pidió humano explícitamente, escala sin más.
    if estado["datos"].get("pide_humano"):
        return {"accion": "escalar"}
    contexto = estado.get("contexto", [])
    decision = llm.decidir_soporte(estado["mensajes"], [c["text"] for c in contexto])
    return {
        "accion": decision.get("accion", "escalar"),
        "_pregunta": decision.get("pregunta", ""),
        "_respuesta": decision.get("respuesta", ""),
        "fuentes_idx": decision.get("fuentes_usadas", []),
    }


def _prefijo(estado: EstadoChat) -> str:
    return _saludo(estado["datos"]) if estado.get("es_primer_turno") else ""


def _nodo_aclarar(estado: EstadoChat) -> EstadoChat:
    pregunta = estado.get("_pregunta") or "¿Me das un poco más de detalle del problema?"
    return {"tipo": "pregunta", "texto": _prefijo(estado) + pregunta, "fuentes_idx": []}


def _nodo_resolver(estado: EstadoChat) -> EstadoChat:
    return {
        "tipo": "respuesta",
        "texto": _prefijo(estado) + (estado.get("_respuesta") or ""),
        "fuentes_idx": estado.get("fuentes_idx", []),
    }


def _nodo_escalar(crear_ticket: CreadorTicket) -> Callable[[EstadoChat], EstadoChat]:
    def nodo(estado: EstadoChat) -> EstadoChat:
        datos = estado["datos"]
        nombre = (datos.get("nombre") or "").strip()
        correo = (datos.get("correo") or "").strip()

        # Gating determinístico: sin nombre+correo no se crea ticket, se piden.
        if not nombre or not correo:
            faltan = (
                "tu nombre y correo"
                if (not nombre and not correo)
                else ("tu nombre" if not nombre else "tu correo")
            )
            texto = _prefijo(estado) + (
                f"Para crear tu caso y que un agente de Tekus te contacte, ¿me compartes {faltan}?"
            )
            return {"tipo": "pregunta", "texto": texto, "fuentes_idx": []}

        resumen = (datos.get("resumen_problema") or "Consulta de soporte").strip()
        ref = crear_ticket(nombre, correo, resumen)
        base = (
            _prefijo(estado)
            + "No pude resolverlo por aquí, así que lo escalo a un agente humano de Tekus."
        )
        if ref:
            base += f" Creé tu caso #{ref} y te contactarán pronto."
        else:
            base += " Un agente te contactará pronto."
        return {"tipo": "escalar", "texto": base, "fuentes_idx": [], "ticket_ref": ref}

    return nodo


def construir_grafo(buscar: BuscadorHibrido, crear_ticket: CreadorTicket):
    g = StateGraph(EstadoChat)
    g.add_node("recuperar", _nodo_recuperar(buscar))
    g.add_node("analizar", _nodo_analizar)
    g.add_node("decidir", _nodo_decidir)
    g.add_node("aclarar", _nodo_aclarar)
    g.add_node("resolver", _nodo_resolver)
    g.add_node("escalar", _nodo_escalar(crear_ticket))

    g.set_entry_point("recuperar")
    g.add_edge("recuperar", "analizar")
    g.add_edge("analizar", "decidir")
    g.add_conditional_edges(
        "decidir",
        lambda e: e["accion"],
        {"aclarar": "aclarar", "resolver": "resolver", "escalar": "escalar"},
    )
    g.add_edge("aclarar", END)
    g.add_edge("resolver", END)
    g.add_edge("escalar", END)
    return g.compile()


def fuentes_publicas(estado: EstadoChat) -> list[dict]:
    """Solo documentos públicos de Confluence — nunca tickets internos."""
    contexto = estado.get("contexto", [])
    out = []
    for i in estado.get("fuentes_idx", []):
        if 0 <= i < len(contexto) and contexto[i]["space_key"] not in _SPACES_INTERNOS:
            out.append(contexto[i])
    return out
