# agents/

Nodos del grafo LangGraph (canal WhatsApp/texto, Fase 1). Ver `CLAUDE.md` sección "Arquitectura de agentes" y "Canal de voz".

- `router/` — clasifica intención del mensaje (soporte / venta / mixta) y urgencia.
- `soporte/` — RAG sobre Confluence + lectura de tickets en Odoo Helpdesk.
- `comercial/` — RAG sobre catálogo + datos de cuenta en Odoo CRM. No implementar antes de Fase 2.
- `politicas/` — Guardrails: decide cuándo el agente comercial puede intervenir y cuándo escalar a humano. Solo esqueleto/interfaz en Fase 0-1 — las reglas de negocio se definen con Jaime y Santiago antes de Fase 2.
- `orquestador/` — mantiene el estado de la conversación y decide el siguiente paso.

El grafo de voz (Fase 2, ver `docs/decisiones/0001-canal-voz-fase2.md`) vivirá en un módulo separado (p. ej. `agents/voz/`), no aquí.
