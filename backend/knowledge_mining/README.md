# knowledge_mining/

Staging de minería de tickets de Odoo Helpdesk para autoría humana de FAQs — **no es parte del RAG de producción**. Ver `docs/decisiones/0002-staging-mineria-tickets-odoo.md` para la decisión completa.

- Escribe en el schema de Postgres `knowledge_mining` (separado de `backend/models/`, que sí es consultado por el agente/RAG).
- El agente conversacional en producción **nunca** lee de aquí — sigue consultando Odoo en vivo vía `backend/connectors/odoo_helpdesk/`, tal como exige `CLAUDE.md`.
- El camino hacia el agente sigue siendo: un humano (o análisis offline) lee estos datos, redacta una FAQ, esa FAQ se publica en Confluence, y de ahí sí se indexa en pgvector por el pipeline normal de `backend/rag/`.

## Job incremental

`odoo_ticket_sync.py` corre una vez al día (ver registro del scheduler en `backend/main.py`). Trae solo tickets abiertos creados o modificados desde la última corrida (`knowledge_mining.sync_state`), y no vuelve a descargar adjuntos ya vistos.
