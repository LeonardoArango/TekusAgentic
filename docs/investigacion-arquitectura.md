# Investigación de Arquitectura y Mejores Prácticas — Agente WhatsApp Tekus

Fecha: 2026-07-12 · Complementa `CLAUDE.md` y `docs/plan-producto-whatsapp-tekus.docx`.

## BLUF

El stack definido (Python/FastAPI, Angular, Postgres, Docker, Meta Cloud API, SSO M365) es correcto y sigue siendo el estándar de facto en 2026. La investigación no cambia ninguna decisión de arquitectura de alto nivel; **concreta las librerías, patrones y herramientas de segundo nivel** que hoy son el estado del arte, y añade una capa que el plan original no cubría: cómo trabajar con Claude Code de forma que el desarrollo sea rápido, barato en créditos y de calidad profesional. Recomendación central: adoptar **LangGraph** para orquestación de agentes, **PyWa** para el canal de WhatsApp, **OdooRPC (OCA)** y **atlassian-python-api** como conectores, **búsqueda híbrida + reranker** sobre pgvector (no vector puro), y una disciplina de **model-routing + skills + subagentes** en Claude Code para controlar el consumo de créditos.

---

## 1. Orquestación de agentes (el corazón del producto)

| Framework | GitHub / adopción | Cuándo usarlo | Veredicto para Tekus |
|---|---|---|---|
| **LangGraph** | Superó a CrewAI en estrellas en 2026; ~34.5M descargas/mes | Workflows con estado, control explícito, alta exigencia de producción | **Recomendado.** El modelo de grafo dirigido encaja exactamente con la arquitectura de agentes ya definida (Router → Soporte/Comercial → Guardrails → Orquestador) descrita en el plan de producto. |
| CrewAI | ~5.2M descargas/mes, curva de entrada más rápida | Prototipos multi-agente rápidos | Útil solo para el prototipo de Fase 0 si se necesita algo desechable en días; no para el MVP. |
| OpenAI Agents SDK | Sucesor de Swarm, patrón de "handoff" explícito | Equipos ya atados al ecosistema OpenAI | Válido como alternativa, pero acopla la arquitectura a un único proveedor de modelo. |
| Pydantic AI | ~16k estrellas, tipado fuerte | Equipos que ya construyen su backend con `pydantic` (como el nuestro) | Fuerte candidato secundario: si el equipo prioriza seguridad de tipos sobre control de flujo explícito, es intercambiable con LangGraph sin romper el resto del stack. |

**Decisión adoptada:** LangGraph como orquestador principal, con los agentes de la sección "Arquitectura de agentes" de `CLAUDE.md` implementados como nodos del grafo y el Agente de Políticas como una arista condicional explícita (no un simple `if` dentro del código de negocio — debe ser visible en el grafo para auditoría).

## 2. Backend — Python / FastAPI

Patrón de referencia 2026 (`zhanymkanov/fastapi-best-practices`, ampliamente citado como referencia de la industria):

- Estructura **por dominio/feature**, no solo por capa técnica: cada carpeta de dominio (`agents/`, `connectors/`, `rag/`) contiene su propio `router.py`, `schemas.py`, `service.py`, `exceptions.py` — evita que `backend/api` se convierta en un basurero de 200 endpoints sin relación.
- Separar siempre **schema de request/response** (Pydantic) del **modelo de base de datos** (ORM) — nunca exponer el modelo de Postgres directamente en la API.
- `main.py` debe quedar mínimo: solo registra routers y middlewares.
- Tareas largas (ingesta de Confluence, llamadas a Odoo que puedan tardar) van a una cola (Redis/RQ o Celery), nunca bloqueando el request-response del webhook de WhatsApp.
- Dependencias de FastAPI (`Depends`) para inyectar sesión de DB, cliente de Odoo, cliente de Confluence — permite mockear todo en tests sin tocar la lógica de negocio.

## 3. Frontend — Angular

- Angular 19+ con **standalone components** y **signals** para estado local — ya no se recomienda NgModules ni RxJS para estado simple de UI.
- Si el proyecto crece a varias apps (portal de gestión, futura app de agente/QA interno), considerar **Nx** como herramienta de monorepo: cachea builds, visualiza el grafo de dependencias y evita recompilar todo el frontend en cada cambio. Para el alcance actual (una sola SPA), Nx es opcional — no añadirlo prematuramente si no hay una segunda app real todavía.
- Diseño por dominio (carpetas `conversaciones/`, `configuracion/`, `reportes/`) en vez de por tipo de archivo (`components/`, `services/` planos).

## 4. RAG — recuperación híbrida y reranking (ajuste importante al plan original)

El plan de producto ya definía "recuperación híbrida + reranker" en términos generales; la investigación concreta el pipeline exacto que es hoy el estándar de producción:

```
Query → BM25 (top 20) + Vector pgvector (top 20) → Fusión RRF (top 30 únicos) → Reranker (top 5-8) → Contexto al LLM
```

- Latencia añadida por hybrid + reranking: ~200-400ms — aceptable para un canal conversacional asíncrono como WhatsApp.
- Reranker recomendado para arrancar: **`bge-reranker-v2-m3`** (BAAI/FlagEmbedding) — multilingüe (clave porque Confluence y las conversaciones son en español), autohospedable, sin costo marginal por consulta. Alternativa gestionada si se prefiere no operar el modelo: Cohere Rerank 3.
- Librería recomendada para la fusión BM25+vector+reranker en Postgres: los ejemplos oficiales de `pgvector/pgvector-python` (`hybrid_search/rrf.py` y `hybrid_search/cross_encoder.py`) — evita reinventar la fusión RRF desde cero.
- No usar vector puro sin reranker: la ganancia de nDCG (3-7%) justifica el costo en un producto donde una respuesta incorrecta de soporte tiene costo reputacional.

## 5. Conectores — librerías de mayor calidad en GitHub

| Integración | Librería recomendada | Por qué |
|---|---|---|
| WhatsApp Cloud API | **PyWa** (~558★, la más estrellada del ecosistema Python para Cloud API) | Soporta mensajes, plantillas, WhatsApp Flows y servidor de webhooks out-of-the-box; evita escribir el manejo de webhooks a mano. |
| Odoo (CRM + Helpdesk) | **OdooRPC** (mantenida por la OCA — Odoo Community Association, sucesora oficial del proyecto original) | Es el cliente RPC de referencia de la comunidad Odoo, probado contra múltiples versiones de Odoo. Alternativa moderna a vigilar: **Zenoo RPC** (async/await nativo, más joven, evaluar en Fase 1 si el volumen de conversaciones exige I/O asíncrono real). |
| Confluence | **atlassian-python-api** (~1.7k★, mantenida activamente) | Cubre Confluence, Jira y Bitbucket con una sola librería; bien documentada, con paginación y manejo de rate-limit ya resueltos. |

## 6. Pipeline de calidad, CI/CD y testing

- **Trunk-based development**: commits directos a `main` o ramas de vida muy corta (1-2 días), pipeline corriendo en cada push. Encaja con un equipo "skunkworks" pequeño como el de Innovación.
- **Pre-commit hooks** (`pre-commit` framework): `black`, `ruff`, detección de secretos (patrón tipo `git-secrets`) antes de cada commit — más barato que descubrir el problema en CI.
- GitHub Actions como estándar de facto; pipeline objetivo **bajo 10 minutos** (ideal bajo 5). Usar matrix strategy para paralelizar tests de backend/frontend.
- Seguridad de supply chain: fijar Actions de terceros por SHA completo (no por tag mutable), usar OIDC en vez de credenciales estáticas para cualquier despliegue a la nube, permisos mínimos por job.
- Testing: `pytest` con fixtures de FastAPI (`TestClient` + dependency overrides para mockear Odoo/Confluence/WhatsApp desde el día uno, tal como ya exige el prompt de arranque). En Angular, tests unitarios con el runner nativo del CLI; para e2e del flujo completo (WhatsApp simulado → dashboard), evaluar Playwright en Fase 1.

## 7. Observabilidad de agentes

- 2026 estandarizó las **convenciones semánticas OTel-GenAI** + spans tipo OpenInference (`LLM`, `RETRIEVER`, `TOOL`, `AGENT`, `GUARDRAIL`) — usar estos nombres de span desde el inicio evita re-instrumentar todo más adelante.
- Cada paso del grafo de LangGraph debe emitir un span: permite responder "¿por qué el agente decidió vender en este ticket de soporte?" con una traza concreta — no solo con logs de texto.
- Exportación de spans en batch/async para no añadir latencia perceptible al flujo de WhatsApp.

## 8. Gestión de secretos

- `.env` es válido solo en desarrollo local (ya está en `CLAUDE.md`). Para cualquier entorno compartido (staging/prod), evaluar entre:
  - **Doppler** — más simple de operar, buena relación esfuerzo/beneficio para un equipo pequeño.
  - **SOPS (Mozilla)** — si se prefiere mantener los secretos versionados y cifrados dentro del propio repo (integra bien con GitOps).
  - **HashiCorp Vault** — solo si más adelante se necesita rotación automática de credenciales o auditoría fina; es la opción de mayor complejidad operativa, no justificada para el MVP.
- Regla dura sin excepción: nunca variables de entorno planas para el token de Meta o credenciales de Odoo en ningún entorno compartido — solo en local.

## 9. Claude Code — cómo desarrollar esto gastando pocos créditos y con calidad

Esta es la pregunta que más impacto tiene en el día a día del desarrollo, y la investigación (documentación oficial de Claude Code + reportes de la comunidad 2026) converge en un mismo conjunto de prácticas:

- **Model routing en `CLAUDE.md`**: declarar explícitamente qué modelo usar según el tipo de tarea — Haiku para lookups/ediciones simples, Sonnet para implementación estándar y debugging, Opus solo para arquitectura y refactors complejos. Ya se puede añadir esta directriz al `CLAUDE.md` del proyecto.
- **Skills bien escritas ahorran 30-50% de tokens** en tareas rutinarias, porque le dan a Claude el enfoque correcto a la primera en vez de que explore varias soluciones. Para este proyecto conviene tener (o crear con `skill-creator`) skills específicas de:
  - Revisión de código / linting para este stack (evita ciclos caros de debugging).
  - Testing (reduce ciclos de escribir-reescribir).
  - Arquitectura del stack específico (previene que Claude Code construya algo que no sigue `CLAUDE.md`).
- **`effort: low` en el frontmatter de una skill** para tareas mecánicas (formateo, linting, revisiones simples) — reduce tokens sin pérdida perceptible de calidad.
- **Subagentes solo cuando valen la pena**: útiles para tareas que leen muchos archivos o generan mucho output intermedio (por ejemplo, explorar toda la wiki de Confluence exportada, o correr un análisis largo de logs) — el resultado vuelve resumido y no ensucia el contexto principal. Para tareas pequeñas (un `git commit`, una edición puntual) el overhead de arrancar un subagente no se justifica.
- **No cargar skills/MCPs "por reflejo" al inicio de sesión** — cargar solo lo que la tarea concreta necesita. Diseñar el flujo de trabajo para que Claude Code vea solo lo que genuinamente necesita en cada paso.
- Repositorios de referencia para robar configuraciones ya probadas (no para instalar a ciegas, sino para inspirarse en su estructura de `CLAUDE.md` y comandos): `rohitg00/awesome-claude-code-toolkit` (incluye configs específicos por stack, incluido FastAPI) y `hesreallyhim/awesome-claude-code` (colección curada de skills, agentes y plugins).

**Aplicación concreta a este repo:** se añade a `CLAUDE.md` una sección de "Model routing" y una nota de qué tareas delegar a subagente vs. resolver en el hilo principal (ver archivo actualizado).

## 10. Tabla resumen de decisiones adoptadas

| Área | Decisión | Cambia el plan original? |
|---|---|---|
| Orquestación de agentes | LangGraph | No, lo concreta (el plan solo decía "framework tipo grafo de agentes") |
| WhatsApp | PyWa | No estaba especificado, se concreta |
| Odoo | OdooRPC (OCA) | No estaba especificado, se concreta |
| Confluence | atlassian-python-api | No estaba especificado, se concreta |
| RAG | Híbrido BM25+vector+reranker (`bge-reranker-v2-m3`) | Concreta el reranker, ya estaba previsto en el plan |
| Monorepo frontend | Nx (opcional, solo si aparece 2ª app) | Nuevo, no rompe nada |
| CI/CD | Trunk-based + pre-commit + GitHub Actions <10min | Nuevo, complementa "pipeline mínimo de calidad" ya pedido |
| Observabilidad | OTel-GenAI semantic conventions | Nuevo, no estaba en el plan original — se recomienda incluirlo desde el MVP |
| Secretos (prod) | Doppler o SOPS (Vault solo si se justifica) | Concreta ".env / vault" ya mencionado en CLAUDE.md |
| Uso de Claude Code | Model routing + skills + subagentes selectivos | Nuevo, directamente solicitado por Leonardo |

## Fuentes consultadas

- [FastAPI Best Practices (zhanymkanov)](https://github.com/zhanymkanov/fastapi-best-practices)
- [The best AI agent frameworks in 2026 (LangChain)](https://www.langchain.com/resources/ai-agent-frameworks)
- [Best AI Agent Frameworks 2026: 7 Compared](https://alicelabs.ai/en/insights/best-ai-agent-frameworks-2026)
- [pgvector-python — ejemplos de hybrid search](https://github.com/pgvector/pgvector-python/blob/master/examples/hybrid_search/rrf.py)
- [FlagOpen/FlagEmbedding (BGE reranker)](https://github.com/flagopen/flagembedding)
- [AnswerDotAI/rerankers](https://github.com/AnswerDotAI/rerankers)
- [PyWa / WhatsApp Cloud API topics en GitHub](https://github.com/topics/whatsapp-cloud-api)
- [OCA/odoorpc](https://github.com/OCA/odoorpc)
- [atlassian-api/atlassian-python-api](https://github.com/atlassian-api/atlassian-python-api)
- [Nx Angular Architecture Guide](https://nx.dev/blog/architecting-angular-applications)
- [awesome-copilot: GitHub Actions CI/CD best practices](https://github.com/github/awesome-copilot/blob/main/instructions/github-actions-ci-cd-best-practices.instructions.md)
- [OpenTelemetry: AI Agent Observability — Evolving Standards](https://opentelemetry.io/blog/2025/ai-agent-observability/)
- [Secrets management in Docker Compose: .env, SOPS, Bitwarden](https://blog.stackademic.com/secrets-management-in-docker-compose-env-sops-bitwarden-and-the-good-enough-threat-model-2bbc6d8e1064)
- [Claude Code Docs — Manage costs effectively](https://code.claude.com/docs/en/costs)
- [How to Reduce Claude Code Costs with Skills](https://www.agensi.io/learn/reduce-claude-code-costs-skills)
- [rohitg00/awesome-claude-code-toolkit](https://github.com/rohitg00/awesome-claude-code-toolkit)
- [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code)
