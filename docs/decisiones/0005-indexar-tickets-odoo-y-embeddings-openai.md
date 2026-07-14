# ADR 0005 — Indexar tickets de Odoo al RAG + embeddings de OpenAI

- **Fecha:** 2026-07-14
- **Estado:** Aceptado
- **Decisor:** Leonardo Arango (explícito, en sesión de pruebas del RAG).
- **Reemplaza parcialmente:** ADR 0002 (Odoo en vivo, nunca vectorizado) y la regla correspondiente de `CLAUDE.md`; ajusta la decisión de embeddings autohospedados de `docs/investigacion-arquitectura.md` §4.

## Contexto

Al probar el endpoint de preguntas al RAG, una consulta de soporte típica ("mi pantalla se ve en negro") devolvía "no encontré información". El diagnóstico (verificado, no supuesto) encontró dos causas:

1. **Los tickets de Odoo no alimentaban el RAG.** Por el ADR 0002, Odoo se consultaba solo en vivo y nunca se vectorizaba; los tickets minados vivían en el schema `knowledge_mining` como material para que un humano redactara FAQs. Resultado: el conocimiento de troubleshooting de casos pasados era invisible para el agente.
2. **Los embeddings locales eran un placeholder sin calidad semántica** (`LocalDevFallbackEmbeddingsProvider`, un hash), porque el sandbox no tiene el servicio autohospedado. La recuperación vectorial era esencialmente aleatoria.

## Decisión

1. **Se vectorizan los tickets de Odoo Helpdesk al RAG** (`knowledge_mining/index_tickets_to_rag.py`), representando cada ticket como un documento (asunto + diagnóstico + solución + notas) reusando el mismo pipeline de indexación de Confluence, con `space_key='ODOO_HELPDESK'` y URL trazable al ticket.

   **Matiz que preserva el espíritu del ADR 0002:** solo se vectoriza **conocimiento histórico de troubleshooting** (qué pasó, qué se hizo). Los **datos operativos en vivo** (estado actual de un ticket, cuenta, mora, oportunidad) se siguen consultando por API en vivo vía `connectors/odoo_*`, NUNCA desde el vector — ahí la regla del ADR 0002 sigue vigente. Lo que cambia es exclusivamente: usar el texto de tickets pasados como fuente de conocimiento recuperable.

2. **Embeddings vía OpenAI** (`text-embedding-3-small`, 1536 dims) en vez del servicio autohospedado que planteaba la investigación — desbloquea calidad real sin operar infra de modelos. El servicio autohospedado (`EMBEDDINGS_SERVICE_URL`) sigue teniendo prioridad si se configura (ver `rag/indexacion/provider_factory.py`); OpenAI es el default cuando hay `OPENAI_API_KEY`.

## Consecuencias

- La dimensión del vector cambió de 384 a 1536 — se recreó `confluence_chunks` y se re-indexó todo el corpus.
- El corpus del RAG ahora mezcla dos fuentes en la misma tabla, distinguibles por `space_key` (`kiosk`/`AK`/`AL` = Confluence, `ODOO_HELPDESK` = tickets). El nombre de tabla `confluence_chunks` quedó como misnomer histórico.
- **Riesgo asumido:** un ticket con un diagnóstico incorrecto o una solución mala se convierte en fuente citable por el agente. Mitigación pendiente: preferir indexar tickets **resueltos** (con solución validada) sobre los abiertos, y/o un paso de curación. Hoy se indexa lo que haya en `knowledge_mining` (mayormente tickets abiertos), suficiente para pruebas pero a endurecer antes de producción.
- Costo: embeddings de OpenAI por chunk indexado y por pregunta (barato con `-3-small`, pero deja de ser "cero costo marginal" como el autohospedado).
- **Pendiente:** el reranker (`bge-reranker-v2-m3`) sigue sin conectar (`RERANKER_SERVICE_URL` vacío) — la recuperación degrada al orden de RRF. No bloquea, pero es el siguiente eslabón de calidad.
