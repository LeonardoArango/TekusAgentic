# rag/

Recuperación híbrida sobre Confluence. **Nunca sobre Odoo** (Odoo se consulta en vivo vía `connectors/`, ver `docs/decisiones/` para el ADR correspondiente).

- `ingesta/` — extracción de páginas de Confluence vía `atlassian-python-api`.
- `indexacion/` — chunking semántico + generación de embeddings + escritura en pgvector con metadatos de espacio/permiso.
- `recuperacion/` — pipeline híbrido: BM25 (top 20) + vector pgvector (top 20) → fusión RRF (top 30 únicos) → reranker `bge-reranker-v2-m3` (top 5-8) → contexto al LLM. Ver `docs/investigacion-arquitectura.md` sección 4.

Toda respuesta generada a partir de este pipeline debe poder trazarse a la página de Confluence que la originó.
