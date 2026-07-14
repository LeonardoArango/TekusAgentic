"""Política de diálogo — la "siguiente mejor acción".

Router determinístico y auditable (como piden los guardrails de CLAUDE.md):
mapea el acto del último mensaje + la fase + los contadores a la acción del
agente. La decisión resolver/aclarar/escalar del ramo "problema" la toma el
LLM acotado (`nlu.decidir_problema`); aquí va el resto de reglas.
"""

from __future__ import annotations

from agents.soporte_web.estado import DialogueState

ACTOS_PROBLEMA = {"reportar_problema", "dar_detalle", "responder_pregunta"}

# Datos mínimos para crear el caso; la sede es muy deseable (visita en sitio)
# pero no bloquea la creación del ticket.
DATOS_REQUERIDOS = ["nombre", "correo"]
MAX_INTENTOS_POR_DATO = 2


def ruta_principal(acto: str) -> str:
    """Ruta de alto nivel según el acto del último mensaje."""
    return {
        "meta_pregunta": "meta",
        "objecion_frustracion": "objecion",
        "smalltalk_saludo": "social",
        "pedir_humano": "escalar",
        "dar_datos_contacto": "contacto",
        "despedida": "cerrar",
        "fuera_de_tema": "social",
    }.get(acto, "problema" if acto in ACTOS_PROBLEMA else "social")


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
