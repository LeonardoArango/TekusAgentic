# models/

Esquemas de la base de datos Postgres/pgvector (SQLAlchemy). Separados siempre de los schemas Pydantic de request/response de `api/` — nunca exponer un modelo de este directorio directamente en la API.

Incluye tanto tablas transaccionales de la plataforma (conversaciones, usuarios, configuración) como las tablas de vectores del RAG (chunks de Confluence + embeddings).
