# ADR 0002 — Odoo (CRM + Helpdesk) se consulta en vivo vía API, nunca se vectoriza

- **Fecha:** 2026-07-13
- **Estado:** Aceptado
- **Contexto de la decisión:** `docs/Plan Producto Agente WhatsApp Tekus.docx`, secciones 4 y 4.1 (aprobado 2026-07-12); confirmado en `CLAUDE.md`, sección "Estrategia de RAG".

## Contexto

El agente necesita dos tipos de fuente muy distintos:

1. **Datos transaccionales de Odoo** (CRM: cuentas, oportunidades; Helpdesk: histórico y estado de tickets) — cambian constantemente durante el día (un ticket se cierra, una oportunidad avanza de etapa, una cuenta entra en mora) y son la base para decisiones sensibles: si el Agente de Políticas puede autorizar una intervención comercial, si un cliente tiene un incidente crítico abierto, si su plan está por vencer.
2. **Conocimiento de Confluence** — relativamente estable (políticas, procedimientos, FAQ, documentación de producto), apto para indexación periódica.

El plan de producto (sección 4.1, "Pipeline de conocimiento propuesto") ya fija esta distinción: *"conector directo a Odoo (...) para CRM y Helpdesk, sin duplicar datos transaccionales — se consulta en vivo, no se vectoriza el CRM"*.

## Decisión

1. **Odoo CRM y Odoo Helpdesk se consultan siempre en vivo vía API** (OdooRPC, ver `docs/investigacion-arquitectura.md`), tanto para lectura como para escritura (crear/actualizar tickets, avanzar oportunidades). Nunca se copian ni se vectorizan en pgvector.
2. **Confluence sí se indexa** en pgvector (chunking semántico + embeddings + metadatos de espacio/permiso), porque su tasa de cambio es compatible con re-sincronización periódica (incremental vía webhook, o polling cada 15-30 min si no hay webhook disponible) sin arriesgar respuestas basadas en datos obsoletos.
3. El clasificador de consulta (Agentic RAG, ver `docs/investigacion-arquitectura.md`) enruta cada pregunta a: (a) lookup directo a Odoo cuando la pregunta depende de estado transaccional, (b) recuperación híbrida sobre Confluence cuando depende de conocimiento/documentación, o (c) ambas cuando la pregunta las combina (ej. "¿por qué este cliente tiene 3 incidentes abiertos y su plan vence en 10 días?").
4. Cada respuesta debe poder trazarse a su origen exacto: página de Confluence o registro de Odoo. Una respuesta que no puede citar su fuente es un bug (ver `CLAUDE.md`, sección "Estrategia de RAG").

## Alternativas consideradas

- **Vectorizar/replicar Odoo en pgvector** (para simplificar la recuperación a un único pipeline): descartada. Introduce una copia que se desactualiza en cuanto cambia el registro origen — inaceptable para decisiones de guardrail (mora, incidente crítico abierto) y para SLA de soporte, donde una respuesta basada en un estado viejo tiene costo reputacional y potencialmente contractual directo.
- **RAG puramente vectorial también para Confluence**: descartada a favor de recuperación híbrida (BM25 + vector + reranker) — ver `docs/investigacion-arquitectura.md` para el detalle, no es objeto de este ADR.

## Consecuencias

- El pipeline de RAG (`backend/rag/`) solo indexa contenido de Confluence; los conectores de Odoo (`backend/connectors/odoo_crm/`, `backend/connectors/odoo_helpdesk/`) exponen únicamente llamadas en vivo, sin capa de sincronización a Postgres para esos datos.
- Cualquier propuesta futura de cachear o pre-computar datos de Odoo para performance debe pasar explícitamente por esta decisión (ver `CLAUDE.md`, sección "Qué NO hacer sin confirmar con Leonardo": *"Migrar o vectorizar datos de Odoo hacia Postgres"*) — no es un ajuste técnico menor, requiere aprobación explícita.
