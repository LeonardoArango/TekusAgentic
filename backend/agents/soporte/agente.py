"""Punto de entrada del Agente de Soporte — resuelve un turno de conversación.

La persistencia del estado entre turnos (hoy recibida explícitamente como
`estado_previo`) es responsabilidad del Orquestador/Memoria de conversación
(HU #25, todavía no implementado). Este módulo solo define la lógica de
negocio de un turno, para que integrarlo al Orquestador después sea
enchufar, no reescribir.
"""

from __future__ import annotations

from agents import llm_client
from agents.soporte.grafo import BuscadorHibrido, EstadoSoporte, construir_grafo, resolver_ticket
from connectors.odoo_helpdesk.client import OdooHelpdeskClient


def procesar_mensaje(
    mensaje: str,
    telefono: str,
    buscar: BuscadorHibrido,
    helpdesk: OdooHelpdeskClient,
    estado_previo: EstadoSoporte | None = None,
) -> EstadoSoporte:
    """Procesa un mensaje entrante y devuelve el nuevo estado de la conversación.

    Si el turno anterior quedó esperando que el usuario confirmara un número
    de ticket (`esperando_referencia_ticket=True`), este mensaje se interpreta
    como esa respuesta en vez de como una pregunta nueva.
    """
    if estado_previo and estado_previo.get("esperando_referencia_ticket"):
        extraido = llm_client.extraer_referencia_ticket(mensaje)
        estado: EstadoSoporte = {
            "mensaje": estado_previo["mensaje"],
            "telefono": telefono,
            "esperando_referencia_ticket": True,
            "referencia_ticket_previa": (
                extraido["referencia"] if extraido.get("tiene_ticket") else None
            ),
        }
        return resolver_ticket(estado, helpdesk)

    grafo = construir_grafo(buscar, helpdesk)
    return grafo.invoke({"mensaje": mensaje, "telefono": telefono})
