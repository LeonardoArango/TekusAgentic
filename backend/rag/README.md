# rag/

Recuperación híbrida sobre Confluence. **Nunca sobre Odoo** (Odoo se consulta en vivo vía `connectors/`, ver `docs/decisiones/` para el ADR correspondiente).

- `ingesta/` — extracción de páginas de Confluence vía `atlassian-python-api` y registro de exclusiones (`exclusions.py`).
- `indexacion/` — chunking semántico + generación de embeddings + escritura **incremental** en pgvector.
- `recuperacion/` — pipeline híbrido: BM25 (top 20) + vector pgvector (top 20) → fusión RRF (top 30 únicos) → reranker `bge-reranker-v2-m3` (top 5-8) → contexto al LLM. Ver `docs/investigacion-arquitectura.md` sección 4.

Toda respuesta generada a partir de este pipeline debe poder trazarse a la página de Confluence que la originó.

## Diseño para escala (no reprocesar, no botar tokens)

- **Incremental por hash de contenido**: `ConfluencePageState` (`models/rag.py`) guarda un hash SHA-256 del cuerpo de cada página ya indexada. `index_pages()` se salta por completo (cero chunking, cero llamadas a embeddings, cero escrituras) cualquier página cuyo hash no cambió desde la última corrida — más robusto que comparar por fecha de modificación.
- **Reconciliación de eliminaciones**: `reconciliar_espacio()` borra chunks + estado de páginas que desaparecieron de un espacio (archivadas/eliminadas/fuera de alcance) — solo válido llamarlo tras un barrido *completo* del espacio, no tras un fetch incremental por fecha.
- **Fetch incremental desde Confluence**: `connectors/confluence/client.py` expone `iter_space_pages_modified_since()` (vía CQL) para sincronizaciones periódicas que no necesitan re-descargar el espacio entero.
- **Embeddings en lotes**: `_embeber_en_lotes()` acota el tamaño de cada llamada al proveedor de embeddings (default 64 chunks), para no mandar de una vez cientos de fragmentos de una página gigante.
- **Índices para que la recuperación escale**: `embedding` tiene un índice HNSW (`vector_cosine_ops`) y `tsv` (columna generada y persistida por Postgres, no calculada al vuelo) tiene un índice GIN. Con pocas filas, Postgres puede preferir un sequential scan (correcto, es más barato a esa escala) — el índice empieza a usarse automáticamente según el corpus crece, sin cambios de código.

## Tests que requieren Postgres real

`tests/test_indexer_incremental.py` y `tests/test_hybrid_search.py` corren contra una base de datos de test dedicada (`DATABASE_URL` + sufijo `_test`, nunca la misma base de desarrollo/seed) — necesario para columnas generadas, índices HNSW/GIN y operadores de pgvector, que no se pueden mockear con un ORM en memoria. Se saltan automáticamente si no hay Postgres alcanzable. Para CI, hace falta un servicio de Postgres+pgvector (ver `docker-compose.yml`) cuando se configure GitHub Actions.
