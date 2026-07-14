# ADR 0006 — Flujo conversacional del Agente de Soporte

- **Fecha:** 2026-07-14
- **Estado:** Aceptado
- **Decisor:** Leonardo Arango (sesión de definición del flujo).

## Contexto

Existían **dos implementaciones divergentes** del agente y **ninguna definición escrita** del flujo:

1. Agente de Soporte de WhatsApp (LangGraph, Anthropic) — `backend/agents/soporte/`. Flujo: `recuperar_contexto → decidir_respuesta → (resolver | pedir nº de ticket → crear ticket)`. Solo una repregunta (el número de ticket); no repregunta por detalles del problema.
2. Chat de la consola web (OpenAI) — `backend/api/platform/rag_qa.py`. Repreguntas de aclaración, pero sin router de intención, sin guardrails, sin escalamiento.

Este ADR define **un único flujo conversacional** que ambas superficies deben seguir.

## Decisión — el flujo

**Un solo motor de agente, dos superficies (WhatsApp y consola web).** El canal es solo entrada/salida; la lógica de conversación es la misma. (Coherente con la arquitectura de `CLAUDE.md`: Router → Soporte/Comercial → Guardrails → Orquestador.)

Secuencia por turno:

1. **Router de intención** — clasifica el mensaje en `soporte` / `venta` / `mixto` y estima urgencia. En Fase 1 solo actúa la rama de soporte; **si detecta intención de venta la etiqueta pero no actúa** (el Agente Comercial y los Guardrails son Fase 2, ver `0001-canal-voz-fase2.md` y `CLAUDE.md`).
2. **Recuperar contexto (RAG híbrido)** — sobre Confluence + tickets resueltos de Odoo (ver `0005`).
3. **Decisión del agente — 3 acciones posibles** (una sola llamada al LLM, salida estructurada):
   - **Repreguntar**: la consulta es ambigua o falta un dato clave (modelo/tipo de equipo, síntoma exacto, en qué punto ocurre, qué ya intentó). Hace **una** pregunta concreta y vuelve a recuperar con la nueva información.
   - **Resolver**: hay contexto suficiente → da la solución paso a paso **citando la fuente** (regla de trazabilidad de `CLAUDE.md`).
   - **Escalar**: ver disparadores abajo.
4. **Cierre / confirmación** tras resolver.

**Sin tope numérico de repreguntas.** El agente juzga cuándo no está convergiendo (el cliente no aporta el dato, da vueltas) y en ese caso escala, en vez de un contador fijo. Se prioriza no interrogar de más.

### Disparadores de escalamiento (a ticket Odoo + humano)

El agente escala cuando ocurre **cualquiera** de:
- No hay respuesta en la base de conocimiento (contexto insuficiente tras recuperar).
- Ya repreguntó y **no converge** (el cliente no puede/no da el dato necesario).
- El cliente **pide explícitamente** un humano ("quiero hablar con alguien", "esto no me sirve").

Al escalar: buscar ticket existente por referencia si el cliente la tiene; si no, **crear ticket estructurado** en Odoo Helpdesk y hacer handoff a un agente humano. (Reusa la lógica ya existente en `agents/soporte/grafo.py:resolver_ticket`.)

> Nota: la urgencia/criticidad alta **no** se definió como disparador automático de escalamiento en esta decisión — el Router la estima para priorización/reportes, pero no salta el flujo por sí sola. Revisar si el piloto muestra que hace falta.

## Estado del contrato de decisión

La función de decisión del agente devuelve una de tres acciones + la intención detectada:

```
accion: "preguntar" | "responder" | "escalar"
intencion: "soporte" | "venta" | "mixto"     # venta solo se etiqueta en Fase 1
pregunta_aclaratoria: str    # si accion == preguntar
respuesta: str               # si accion == responder
fuentes_usadas: [int]        # si accion == responder
motivo_escalamiento: str     # si accion == escalar
```

## Consecuencias / reconciliación

- **Consola web (`rag_qa.py`)**: se implementa este flujo de 3 acciones + etiqueta de intención en este mismo cambio (superficie activa hoy).
- **WhatsApp (`agents/soporte/grafo.py`)**: hoy solo tiene resolver/ticket. Debe adoptar el mismo contrato (3 acciones + router + repreguntas de detalle). Se deja como **trabajo de reconciliación pendiente**, coordinando con quien mantiene ese grafo, para no reescribir en paralelo. El objetivo final es que ambas superficies llamen a la misma lógica de decisión.
- Los dos proveedores de LLM (Anthropic en WhatsApp, OpenAI en web) siguen coexistiendo por ahora (ver `0005`); unificar proveedor es una decisión aparte, no la fuerza este ADR.
- El Orquestador/Memoria de `CLAUDE.md` sigue siendo el dueño del estado entre turnos; hoy el historial viaja en cada request (sin estado en servidor), suficiente para Fase 1.
