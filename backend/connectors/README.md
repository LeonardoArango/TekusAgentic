# connectors/

Clientes a sistemas externos. Todo lo que aquí exista en Fase 0/1 son **stubs** — no hay llamadas reales hasta que los accesos estén validados y Leonardo lo confirme (ver `CLAUDE.md`, punto 5 de reglas de arranque).

- `odoo_crm/` — OdooRPC, cuentas y oportunidades. Lectura y escritura vía API, siempre en vivo. Nunca vectorizar estos datos.
- `odoo_helpdesk/` — OdooRPC, histórico y creación de tickets. Igual que CRM: en vivo, nunca vectorizado.
- `confluence/` — atlassian-python-api. Único conector cuyos datos sí se indexan en pgvector (vía `rag/`).
- `whatsapp/` — PyWa, cliente de WhatsApp Cloud API (Meta) y servidor de webhooks. Conexión directa, sin BSP intermediario.

Toda integración real (cuando se implemente) debe tener manejo de reintentos y circuit breaker.
