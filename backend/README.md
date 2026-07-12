# Backend — Agente WhatsApp Tekus

API REST + webhooks de WhatsApp + orquestador de agentes (FastAPI). Ver `/CLAUDE.md` en la raíz del repo para stack, arquitectura y reglas antes de tocar este código.

## Desarrollo local

```bash
cd backend
uv sync --extra dev
uv run uvicorn main:app --reload
uv run pytest
```

## Estructura

- `agents/` — nodos del grafo LangGraph (router, soporte, comercial, políticas, orquestador).
- `connectors/` — clientes a Odoo (CRM/Helpdesk), Confluence y WhatsApp. Stubs hasta que los accesos de Fase 0 estén validados.
- `api/` — routers de FastAPI (webhooks de Meta, endpoints de la plataforma web).
- `rag/` — ingesta, indexación y recuperación híbrida sobre Confluence (nunca sobre Odoo).
- `models/` — esquemas Postgres/pgvector.
