# api/

Routers de FastAPI. `main.py` en la raíz de `backend/` solo registra routers y middlewares — la lógica vive en cada dominio (`agents/`, `connectors/`, `rag/`), no aquí.

- `webhooks/` — endpoint de verificación y recepción de mensajes de WhatsApp Cloud API (Meta). Encola el procesamiento agéntico, nunca lo bloquea.
- `platform/` — endpoints de la plataforma web (dashboards, configuración, reportes) consumidos por el frontend Angular. Protegidos por SSO Microsoft 365 / Entra ID.
