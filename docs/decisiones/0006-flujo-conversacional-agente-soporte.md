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

## Implementación (actualización 2026-07-14)

Un primer intento con **una sola llamada al LLM** haciendo todo (saludar,
confirmar, aclarar, resolver+citar, recolectar datos, escalar) resultó poco
confiable — probado con gpt-4o-mini y gpt-4o: el saludo, la cita de fuentes y
la recolección de datos no ocurrían de forma consistente. Se rearquitectó como
**máquina de estados LangGraph** (`backend/agents/soporte_web/grafo.py`), que
es además lo que manda `CLAUDE.md`:

- El LLM solo hace lo que hace bien: **entender** (`extraer_estado_conversacion`)
  y **redactar/decidir** (`decidir_soporte`). Dos llamadas acotadas.
- Lo estructural es **determinístico**: el saludo del primer turno (plantilla
  con nombre + confirmación del problema), el gating de "no escalar sin
  nombre+correo", y la creación del ticket. Así no dependen de que el modelo
  "haga caso".
- Flujo: `recuperar → analizar → decidir → (aclarar | resolver | escalar)`.
- **Creación de ticket**: al escalar con nombre+correo, crea el ticket en una
  instancia de Odoo de **PRUEBAS** (credenciales `ODOO_*_TEST`, separadas de la
  principal de lectura), gated por `ODOO_TICKET_WRITE_ENABLED`. Verificado
  end-to-end (tickets creados en la instancia de test).
- **Fuentes**: filtrado server-side — solo se muestran documentos públicos de
  Confluence; los tickets internos alimentan la respuesta pero nunca se citan.

## Consecuencias / reconciliación

- **Consola web (`rag_qa.py`)**: implementa este flujo vía el grafo de
  `agents/soporte_web/`.
- **WhatsApp (`agents/soporte/grafo.py`)**: hoy solo tiene resolver/ticket. Debe adoptar el mismo contrato (3 acciones + router + repreguntas de detalle). Se deja como **trabajo de reconciliación pendiente**, coordinando con quien mantiene ese grafo, para no reescribir en paralelo. El objetivo final es que ambas superficies llamen a la misma lógica de decisión.
- Los dos proveedores de LLM (Anthropic en WhatsApp, OpenAI en web) siguen coexistiendo por ahora (ver `0005`); unificar proveedor es una decisión aparte, no la fuerza este ADR.
- El Orquestador/Memoria de `CLAUDE.md` sigue siendo el dueño del estado entre turnos; hoy el historial viaja en cada request (sin estado en servidor), suficiente para Fase 1.
