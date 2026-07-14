"""Grafo LangGraph del motor conversacional de soporte (ADR 0006).

Máquina de estados de diálogo orientada a tareas. Reparte el trabajo para que
sea confiable y humano:

- NLU (`entender`): clasifica el acto del último mensaje y extrae lo aportado.
- `actualizar`: funde lo entendido en el estado (determinístico).
- `recuperar`: RAG solo si el turno es del problema.
- Política (aristas condicionales): enruta a la acción — meta / objeción /
  social / problema / contacto / escalar / cerrar. El ramo del problema usa
  `decidir_problema` (LLM) para resolver/aclarar/escalar.
- NLG: cada acción redacta en lenguaje natural, acusando recibo y SIN repetir
  (recibe lo ya dicho/preguntado).

El estado se carga/guarda en Redis por conversation_id fuera del grafo (ver
`memoria.py` y el endpoint) — el grafo opera sobre un DialogueState ya cargado.
"""

from __future__ import annotations

from typing import Protocol, TypedDict

from langgraph.graph import END, StateGraph

from agents.soporte_web import nlg, nlu, politica
from agents.soporte_web.estado import DialogueState, Fase


class BuscadorHibrido(Protocol):
    def __call__(self, query: str) -> list[dict]: ...


class CreadorTicket(Protocol):
    def __call__(self, nombre: str, correo: str, resumen: str, sede: str) -> str | None: ...


_SPACES_INTERNOS = {"ODOO_HELPDESK"}


class GS(TypedDict, total=False):
    estado: DialogueState
    nlu: dict
    contexto: list[dict]
    accion: str
    borrador: str
    sugerencia: str
    fuentes_idx: list[int]
    # salida
    tipo: str  # pregunta | respuesta | escalar
    texto: str


# --- nodos ------------------------------------------------------------------


def _entender(estado_gs: GS) -> GS:
    return {"nlu": nlu.entender(estado_gs["estado"])}


def _actualizar(estado_gs: GS) -> GS:
    est = estado_gs["estado"]
    n = estado_gs["nlu"]
    est.intencion = n.get("intencion", est.intencion)
    est.sentimiento = n.get("sentimiento", est.sentimiento)
    if n.get("problema"):
        est.problema = n["problema"]
    for s in n.get("sintomas_nuevos", []):
        if s and s not in est.sintomas:
            est.sintomas.append(s)
    for p in n.get("pasos_intentados_nuevos", []):
        if p and p not in est.pasos_intentados:
            est.pasos_intentados.append(p)
    d = n.get("datos") or {}
    for campo in ("nombre", "correo", "cuenta", "telefono", "sede"):
        val = (d.get(campo) or "").strip()
        if val and not getattr(est.slots, campo):
            setattr(est.slots, campo, val)
    return {}


def _nodo_recuperar(buscar: BuscadorHibrido):
    def nodo(estado_gs: GS) -> GS:
        n = estado_gs["nlu"]
        if n.get("acto") not in politica.ACTOS_PROBLEMA:
            return {"contexto": []}
        est = estado_gs["estado"]
        query = f"{est.problema} {est.turnos[-1].texto}".strip() if est.turnos else est.problema
        return {"contexto": buscar(query)}

    return nodo


def _ruta(estado_gs: GS) -> str:
    return politica.ruta_principal(estado_gs["nlu"].get("acto", "otro"))


def _decidir_problema(estado_gs: GS) -> GS:
    est = estado_gs["estado"]
    contexto = estado_gs.get("contexto", [])
    d = nlu.decidir_problema(est, [c["text"] for c in contexto])
    return {
        "accion": d.get("accion", "escalar"),
        "borrador": d.get("borrador_respuesta", ""),
        "sugerencia": d.get("sugerencia_pregunta", ""),
        "fuentes_idx": d.get("fuentes_usadas", []),
    }


def _ruta_problema(estado_gs: GS) -> str:
    return estado_gs.get("accion", "escalar")


# generación


def _n_meta(gs: GS) -> GS:
    return {"tipo": "pregunta", "texto": nlg.responder_meta(gs["estado"])}


def _n_objecion(gs: GS) -> GS:
    return {"tipo": "pregunta", "texto": nlg.atender_objecion(gs["estado"])}


def _n_social(gs: GS) -> GS:
    return {"tipo": "pregunta", "texto": nlg.responder_social(gs["estado"])}


def _n_aclarar(gs: GS) -> GS:
    est = gs["estado"]
    texto = nlg.aclarar(est, gs.get("sugerencia", ""))
    est.preguntas_hechas.append(gs.get("sugerencia") or texto[:80])
    est.fase = Fase.DIAGNOSTICO
    return {"tipo": "pregunta", "texto": texto}


def _n_resolver(gs: GS) -> GS:
    est = gs["estado"]
    contexto = gs.get("contexto", [])
    texto = nlg.resolver(est, gs.get("borrador", ""), [c["text"] for c in contexto])
    if gs.get("borrador"):
        est.pasos_sugeridos.append(gs["borrador"][:80])
    est.fase = Fase.DIAGNOSTICO
    return {"tipo": "respuesta", "texto": texto, "fuentes_idx": gs.get("fuentes_idx", [])}


def _nodo_escalar(crear_ticket: CreadorTicket):
    def nodo(gs: GS) -> GS:
        est = gs["estado"]
        faltan = politica.datos_faltantes(est)

        # Gating con tope de intentos: si faltan datos y aún no agotamos los
        # intentos, los pedimos (variando) en vez de crear el ticket a ciegas.
        if faltan and not politica.agotamos_intentos(est, faltan):
            for d in faltan:
                est.registrar_intento(d)
            etiquetas = [politica.etiqueta_dato(d) for d in faltan]
            en_ultimo = any(est.intentos(d) >= politica.MAX_INTENTOS_POR_DATO for d in faltan)
            texto = (
                nlg.recolectar_dato_ultimo_intento(est, etiquetas)
                if en_ultimo
                else nlg.recolectar_dato(est, etiquetas)
            )
            est.fase = Fase.RECOLECCION_DATOS
            est.preguntas_hechas.append("pedir_datos:" + ",".join(faltan))
            return {"tipo": "pregunta", "texto": texto}

        # Datos suficientes (o agotamos intentos): creamos el caso igual.
        resumen = est.problema or "Consulta de soporte"
        ref = crear_ticket(est.slots.nombre, est.slots.correo, resumen, est.slots.sede)
        est.ticket_ref = ref
        est.fase = Fase.ESCALADO
        return {"tipo": "escalar", "texto": nlg.escalar(est, ref)}

    return nodo


def _n_cerrar(gs: GS) -> GS:
    gs["estado"].fase = Fase.CERRADO
    return {"tipo": "respuesta", "texto": nlg.cerrar(gs["estado"])}


def construir_grafo(buscar: BuscadorHibrido, crear_ticket: CreadorTicket):
    g = StateGraph(GS)
    g.add_node("entender", _entender)
    g.add_node("actualizar", _actualizar)
    g.add_node("recuperar", _nodo_recuperar(buscar))
    g.add_node("decidir_problema", _decidir_problema)
    g.add_node("meta", _n_meta)
    g.add_node("objecion", _n_objecion)
    g.add_node("social", _n_social)
    g.add_node("aclarar", _n_aclarar)
    g.add_node("resolver", _n_resolver)
    g.add_node("escalar", _nodo_escalar(crear_ticket))
    g.add_node("cerrar", _n_cerrar)

    g.set_entry_point("entender")
    g.add_edge("entender", "actualizar")
    g.add_edge("actualizar", "recuperar")
    g.add_conditional_edges(
        "recuperar",
        _ruta,
        {
            "meta": "meta",
            "objecion": "objecion",
            "social": "social",
            "problema": "decidir_problema",
            "contacto": "escalar",
            "escalar": "escalar",
            "cerrar": "cerrar",
        },
    )
    g.add_conditional_edges(
        "decidir_problema",
        _ruta_problema,
        {"resolver": "resolver", "aclarar": "aclarar", "escalar": "escalar"},
    )
    for terminal in ("meta", "objecion", "social", "aclarar", "resolver", "escalar", "cerrar"):
        g.add_edge(terminal, END)
    return g.compile()


def fuentes_publicas(gs: GS) -> list[dict]:
    """Solo documentos públicos de Confluence — nunca tickets internos."""
    contexto = gs.get("contexto", [])
    return [
        contexto[i]
        for i in gs.get("fuentes_idx", [])
        if 0 <= i < len(contexto) and contexto[i]["space_key"] not in _SPACES_INTERNOS
    ]
