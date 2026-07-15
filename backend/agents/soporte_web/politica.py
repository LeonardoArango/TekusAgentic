"""Política de diálogo — la "siguiente mejor acción".

Router determinístico y auditable (como piden los guardrails de CLAUDE.md):
mapea el acto del último mensaje + la fase + los contadores a la acción del
agente. La decisión resolver/aclarar/escalar del ramo "problema" la toma el
LLM acotado (`nlu.decidir_problema`); aquí va el resto de reglas.
"""

from __future__ import annotations

from agents.soporte_web.estado import DialogueState

ACTOS_PROBLEMA = {"reportar_problema", "dar_detalle", "responder_pregunta"}

# El cliente pide algo que se atiende SIEMPRE de inmediato, sin importar la
# fase (para no ignorarlo ni sonar a robot).
ACTOS_INMEDIATOS = {
    "meta_pregunta": "meta",
    "objecion_frustracion": "objecion",
    "pedir_humano": "escalar",
    "despedida": "cerrar",
}

# Playbook de Leonardo: identificar al cliente ANTES de diagnosticar.
# Mínimo para continuar: persona, empresa, sede, correo y el problema.
DATOS_IDENTIFICACION = ["nombre", "cuenta", "sede", "correo"]  # + problema (no es slot)
DATOS_REQUERIDOS = ["nombre", "correo"]  # mínimo duro para crear el ticket
MAX_INTENTOS_POR_DATO = 2


def datos_identificacion_faltantes(estado) -> list[str]:
    """Qué falta para dar por identificado al cliente (playbook, paso 3)."""
    faltan = []
    etiquetas = {
        "nombre": "tu nombre",
        "cuenta": "la empresa",
        "sede": "la sede o punto",
        "correo": "tu correo",
    }
    for campo in DATOS_IDENTIFICACION:
        if not getattr(estado.slots, campo).strip():
            faltan.append(etiquetas[campo])
    if not estado.problema.strip():
        faltan.append("qué problema presenta el equipo")
    return faltan


def ruta(estado, acto: str) -> str:
    """Ruta de alto nivel: atiende lo inmediato; si no, sigue el playbook por
    fase (identificar → revisar ticket → diagnosticar)."""
    if acto in ACTOS_INMEDIATOS:
        return ACTOS_INMEDIATOS[acto]

    # Identificar primero.
    if datos_identificacion_faltantes(estado):
        return "identificar"

    # ¿Ya revisamos si tenía ticket previo? (se pregunta una vez)
    if not estado.reporto_antes:
        return "ticket_check"

    if acto in ACTOS_PROBLEMA or acto == "dar_datos_contacto":
        return "problema"
    return "social"


def datos_faltantes(estado: DialogueState) -> list[str]:
    faltan = []
    if not estado.slots.nombre.strip():
        faltan.append("nombre")
    if not estado.slots.correo.strip():
        faltan.append("correo")
    return faltan


def agotamos_intentos(estado: DialogueState, faltan: list[str]) -> bool:
    """True si ya insistimos el máximo por los datos faltantes — hay que dejar
    de preguntar y crear el caso igual, en vez de caer en un bucle."""
    return all(estado.intentos(d) >= MAX_INTENTOS_POR_DATO for d in faltan) if faltan else False


def etiqueta_dato(dato: str) -> str:
    return {"nombre": "tu nombre", "correo": "tu correo", "sede": "la sede o punto"}.get(dato, dato)
