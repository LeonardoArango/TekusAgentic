# Prompt de arranque — Claude Code

Copia y pega este mensaje como primer prompt en Claude Code, dentro de la carpeta vacía (o recién inicializada con git) donde vivirá el repo. Antes de pegarlo, coloca en esa carpeta el archivo `CLAUDE.md` (ya generado), `docs/investigacion-arquitectura.md` y el documento `plan-producto-whatsapp-tekus.docx` dentro de `docs/`.

---

Estás iniciando el desarrollo de un producto nuevo de Tekus: un agente conversacional de WhatsApp orquestado por IA (soporte técnico + ventas en el mismo hilo) más una plataforma web de gestión/dashboards. Ya existe un `CLAUDE.md` en la raíz de este repo — léelo por completo antes de escribir una sola línea de código; contiene el stack obligatorio, las librerías concretas a usar, la arquitectura de agentes, la estrategia de RAG y las reglas de seguridad no negociables. También existen `docs/plan-producto-whatsapp-tekus.docx` (plan de negocio: visión, roadmap, unit economics, riesgos) y `docs/investigacion-arquitectura.md` (justificación técnica de cada librería elegida y alternativas evaluadas) — consúltalos si necesitas contexto que no esté en CLAUDE.md.

Aplica desde ya el model routing y la disciplina de skills/subagentes descrita en la sección "Cómo trabajar en este repo con Claude Code" de `CLAUDE.md`: no uses un modelo más costoso del necesario para tareas mecánicas, y no cargues skills o MCPs que esta sesión no vaya a usar.

Estamos en **Fase 0 (Discovery)**, así que el objetivo de esta sesión no es construir el producto completo, sino dejar el repo listo para empezar Fase 1 (MVP de Soporte). Concretamente, quiero que:

1. Propongas y confirmes conmigo la estructura de carpetas exacta antes de crear archivos (usa como base la de CLAUDE.md, pero dime si algo no tiene sentido).
2. Inicialices el monorepo con:
   - `backend/`: proyecto Python con FastAPI, `pydantic`, `black`/`ruff` configurados, y estructura de carpetas para agentes (con `langgraph` como dependencia, aunque el grafo real se construya en Fase 1), conectores (`odoorpc`, `atlassian-python-api`, `pywa` como dependencias declaradas, sin uso real todavía), API y RAG (vacíos con un `README.md` cada uno explicando su responsabilidad, sin lógica de negocio todavía).
   - `frontend/`: proyecto Angular (standalone components, signals, TypeScript strict) con el layout base responsive, sin implementar pantallas todavía. No agregues Nx a menos que ya exista o vayas a crear una segunda app real.
   - `docker/`: `docker-compose.yml` para desarrollo local con al menos Postgres (con `pgvector`), Redis, backend y frontend, todo parametrizado por variables de entorno.
   - `.env.example` con todas las variables que ya sabemos que se van a necesitar (token de Meta WhatsApp Cloud API, credenciales Odoo, credenciales Confluence, credenciales Entra ID/MSAL, conexión Postgres), sin valores reales.
3. Configures un pipeline mínimo de calidad: `pre-commit` (black, ruff, detección de secretos), linting, formateo y un test "hello world" por cada servicio (backend y frontend) que corra localmente (no configures GitHub Actions todavía, solo scripts locales — cuando pasemos a Fase 1 sí lo haremos con matrix strategy y pipeline objetivo bajo 10 minutos).
4. Documentes en `docs/decisiones/` un primer ADR (Architecture Decision Record) explicando por qué Odoo se consulta en vivo y nunca se vectoriza, y por qué se descartó el enfoque "second brain"/Obsidian — cópialo de la lógica ya definida en CLAUDE.md y el plan de producto, no la reinventes.
5. Antes de generar código de conectores reales a Odoo/Confluence/Meta, avísame — esos accesos aún no están validados (es tarea de Fase 0) y no quiero que se escriban credenciales o llamadas reales todavía. Trabaja con conectores "stub"/mockeados hasta que yo confirme que los accesos están listos.

No implementes todavía el Agente de Políticas (guardrails) con reglas reales de venta cruzada — solo deja el esqueleto del componente en `backend/agents/` con la interfaz definida, documentando en el docstring que las reglas de negocio se definirán junto con Jaime y Santiago antes de Fase 2.

Antes de empezar a escribir código, dame un resumen breve de tu plan (estructura de carpetas + orden de pasos) para que lo confirme.
