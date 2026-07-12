"""Agente de Políticas (Guardrails).

Esqueleto de interfaz únicamente — NO implementar reglas de negocio reales
todavía. Las reglas de cuándo el agente comercial puede intervenir en una
conversación de soporte (cuenta activa, sin incidente crítico abierto, no en
mora, propensión de compra > umbral) y cuándo escalar a humano se definirán
junto con Jaime y Santiago antes de Fase 2 (ver CLAUDE.md, sección
"Arquitectura de agentes" y "Qué NO hacer sin confirmar con Leonardo").

Este nodo se expone como una arista condicional explícita en el grafo de
LangGraph, no como un `if` escondido en el código de negocio de otro agente
— debe quedar auditable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DecisionPolitica(str, Enum):
    """Resultado posible de una evaluación del Agente de Políticas."""

    PERMITIR_COMERCIAL = "permitir_comercial"
    BLOQUEAR_COMERCIAL = "bloquear_comercial"
    ESCALAR_HUMANO = "escalar_humano"


@dataclass
class ContextoConversacion:
    """Placeholder del contexto que el guardrail necesitará evaluar.

    Los campos reales (estado de cuenta, incidentes abiertos, mora,
    propensión de compra, etc.) se definen junto con Jaime y Santiago.
    """


def evaluar(contexto: ContextoConversacion) -> DecisionPolitica:
    """Punto de entrada del Agente de Políticas.

    No implementado — placeholder de interfaz para Fase 0/1. Ver docstring
    del módulo.
    """
    raise NotImplementedError(
        "Reglas de negocio del Agente de Políticas pendientes de definir "
        "con Jaime y Santiago antes de Fase 2."
    )
