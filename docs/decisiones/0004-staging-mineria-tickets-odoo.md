# ADR 0002 — Staging de minería de tickets Odoo para autoría de FAQs (no es fuente del RAG)

- **Fecha:** 2026-07-14
- **Estado:** Aceptado
- **Contexto de la decisión:** revisión manual de tickets abiertos de Odoo Helpdesk con Leonardo, para empezar a construir la base de conocimiento del agente de soporte.

## Contexto

`CLAUDE.md` establece una regla dura: *"Odoo (CRM y Helpdesk) se consulta en vivo vía API. Nunca se vectoriza ni se duplica en pgvector."* Esa regla protege un caso concreto: el **agente conversacional en producción** nunca debe responder con una copia de Odoo que pudo quedar desactualizada, ni duplicar el control de acceso de un sistema fuente.

Al revisar tickets reales para empezar a redactar FAQs y entender patrones de soporte, surgió una necesidad distinta que `CLAUDE.md` no cubre explícitamente: **un volcado de datos para minería y análisis humano**, no para que el agente responda desde ahí. Este ADR documenta por qué esto no viola el espíritu de la regla original, y cómo se diseñó para que nunca se confunda con el RAG de producción.

## Decisión

1. **Se crea un schema de Postgres separado, `knowledge_mining`**, distinto de cualquier schema que use el RAG de producción (`backend/models/`). Todas sus tablas llevan comentarios SQL (`COMMENT ON SCHEMA/TABLE`) advirtiendo explícitamente que no son fuente del agente conversacional.
2. **El agente en producción nunca consulta este schema.** Sigue consultando Odoo en vivo vía API para cualquier dato operacional (estado de ticket, cliente, etc.), tal como ya establecía `CLAUDE.md`.
3. Este schema es **material crudo para que un humano (o un análisis offline asistido por LLM) redacte FAQs**, que luego se publican en Confluence y se indexan en pgvector siguiendo el pipeline de RAG ya documentado (`CLAUDE.md`, Estrategia de RAG). El camino correcto hacia el agente sigue siendo Confluence, no esta tabla.
4. Diseño de tablas:
   - `knowledge_mining.odoo_ticket_mining_raw`: metadata y mensajes del ticket en JSONB, **sin binarios embebidos** (ver punto 5).
   - `knowledge_mining.odoo_ticket_attachment`: adjuntos de imagen/video en `bytea`, en tabla separada — evita inflar el JSONB con base64 (~33% más pesado que el binario, no indexable, no comprimible dentro de una columna JSON).
   - `knowledge_mining.sync_state`: marca de agua (`last_synced_at`) para la sincronización incremental.
5. **Sincronización incremental diaria**, no un script manual de una sola vez: un job corre dentro del backend (FastAPI, ver `backend/knowledge_mining/`) una vez al día, trae solo tickets abiertos creados o modificados (`write_date`) desde la última corrida, e inserta un nuevo snapshot. Los adjuntos ya vistos (mismo `odoo_attachment_id`) no se vuelven a descargar ni duplicar en `bytea`.

## Alternativas consideradas

- **No crear ninguna tabla, quedarnos solo con exports JSON puntuales**: descartada porque el objetivo explícito es que esto se siga alimentando con el tiempo para construir la base de conocimiento, no un análisis de una sola vez.
- **Embeber las fotos en base64 dentro del mismo JSONB de metadata**: descartada por peso y por no ser indexable/reutilizable — se prefirió una tabla de adjuntos separada en `bytea`.
- **Tratar esta tabla como la fuente que el agente consulta en vez de llamar a Odoo por API**: descartada explícitamente — cambiaría la arquitectura de RAG de `CLAUDE.md` y no es lo que se pidió; de quererse en el futuro, requeriría un ADR nuevo que reemplace esta decisión y la regla correspondiente en `CLAUDE.md`.

## Consecuencias

- Existe ahora un schema de Postgres (`knowledge_mining`) que técnicamente contiene una copia de datos de Odoo — cualquier futura sesión de desarrollo debe leer este ADR antes de asumir que esto contradice la regla de "Odoo siempre en vivo" de `CLAUDE.md`. No la contradice: están resolviendo problemas distintos (respuesta en producción vs. minería offline para autoría de contenido).
- El pipeline incremental corre dentro del backend (ver `backend/knowledge_mining/`), reutilizando las credenciales de Odoo ya declaradas en `.env`/Doppler.
- Queda pendiente definir la retención de este schema (¿por cuánto tiempo se acumulan snapshots históricos?) — no se fijó límite en esta decisión, revisar cuando el volumen de datos lo amerite.
