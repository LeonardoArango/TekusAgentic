# CLAUDE.md — Agente WhatsApp Tekus (Comercial + Soporte)

Este archivo orienta a Claude Code (y a cualquier agente que trabaje en este repo) sobre el propósito, la arquitectura y las convenciones del proyecto. Léelo por completo antes de generar o modificar código.

Referencia completa de negocio: `docs/plan-producto-whatsapp-tekus.docx` (documento de arquitectura, estrategia y roadmap aprobado el 2026-07-12). Ante cualquier duda de alcance o prioridad, ese documento es la fuente de verdad de negocio; este archivo es la fuente de verdad técnica de implementación.

Referencia de librerías y mejores prácticas: `docs/investigacion-arquitectura.md` (investigación de estado del arte, 2026-07-12). Las decisiones de librerías concretas de este archivo (LangGraph, PyWa, OdooRPC, atlassian-python-api, reranker) vienen de ahí — consúltalo si necesitas la justificación completa o alternativas evaluadas.

Decisiones de arquitectura registradas como ADR (más recientes que el plan de producto original, prevalecen sobre él en caso de conflicto): `docs/decisiones/`. Ver en particular `0001-canal-voz-fase2.md` — el plan de producto no menciona voz, pero es un compromiso de roadmap confirmado el 2026-07-12.

## Qué es este proyecto

Primer producto de transformación digital de Tekus: un agente conversacional de WhatsApp orquestado por IA que atiende **soporte técnico** y **ventas** en el mismo hilo, respaldado por una plataforma web de gestión, configuración, dashboards y reportes. Es un proyecto interno de Innovación y Nuevos Negocios (equipo "skunkworks" separado de la operación core de Tekus).

Fuentes de datos del agente:
- **Odoo CRM** — cuentas, oportunidades (lectura y escritura vía API, en vivo, nunca vectorizado).
- **Odoo Servicio al Cliente / Helpdesk** — histórico y creación de tickets (lectura y escritura vía API, en vivo).
- **Confluence (wiki.tekus.co)** — base de conocimiento, indexada en pgvector para RAG híbrido.

## Arquitectura y stack (no negociable salvo decisión explícita de Leonardo o Jaime)

| Capa | Tecnología | Notas |
|---|---|---|
| Backend | Python (FastAPI) | API REST + webhooks de WhatsApp + orquestador de agentes |
| Orquestación de agentes | **LangGraph** | Grafo dirigido; cada agente de la sección siguiente es un nodo, el Guardrail es una arista condicional explícita (auditable), no un `if` escondido en el código |
| Frontend | Angular (standalone components + signals) | Responsive mobile-first, usa el Design System de Tekus (no inventar componentes visuales nuevos sin verificarlo). Nx solo si aparece una segunda app real — no añadirlo de entrada |
| Base de datos | Postgres + extensión `pgvector` | Única base de datos: datos transaccionales de la plataforma + vectores del RAG |
| Contenedores | Docker / docker-compose | Todo el stack corre dockerizado, incluso en desarrollo local |
| Secretos | `.env` (dev) / **Doppler o SOPS** (prod) | Vault de HashiCorp solo si más adelante se necesita rotación automática o auditoría fina — no lo introduzcas para el MVP, es complejidad innecesaria |
| Canal de mensajería | WhatsApp Cloud API (Meta), vía **PyWa** | No usar BSP intermediario. On-Premises API está descontinuado — no es una opción |
| Conector Odoo | **OdooRPC** (paquete mantenido por la OCA) | Cliente RPC de referencia de la comunidad Odoo |
| Conector Confluence | **atlassian-python-api** | Cubre paginación y rate-limit ya resueltos |
| Autenticación (plataforma web) | SSO Microsoft 365 / Entra ID (OAuth2/OIDC, MSAL) | Sin usuarios/contraseñas locales |
| Cola de mensajes | Redis o RabbitMQ | Desacopla ingesta de WhatsApp del procesamiento agéntico |
| Observabilidad | OpenTelemetry con convenciones semánticas OTel-GenAI | Spans tipo `LLM`, `RETRIEVER`, `TOOL`, `AGENT`, `GUARDRAIL` desde el día uno — evita re-instrumentar todo después |

## Arquitectura de agentes (comportamiento dual soporte/venta)

El sistema no es un árbol de decisión ni un único prompt monolítico. Se implementa como agentes especializados coordinados:

1. **Router / Clasificador de intención** — determina si el mensaje es soporte, venta, o intención mixta, y la urgencia.
2. **Agente de Soporte** — RAG sobre Confluence + lectura de tickets en Odoo Helpdesk; resuelve o abre ticket estructurado.
3. **Agente Comercial** — RAG sobre catálogo/propuesta de valor + datos de cuenta en Odoo CRM; califica, informa, avanza oportunidad.
4. **Agente de Políticas (Guardrails)** — decide cuándo el agente comercial puede intervenir en una conversación de soporte (reglas: cuenta activa, sin incidente crítico abierto, no en mora, propensión de compra > umbral) y cuándo escalar a humano. Este agente es el que **impide** que el bot venda de forma agresiva o inoportuna — cualquier cambio a sus reglas requiere aprobación explícita, no solo un ajuste de prompt silencioso.
5. **Orquestador/Memoria** — mantiene el estado de la conversación y decide el siguiente mejor paso.

Esta arquitectura (Router → Soporte/Comercial → Guardrails → Orquestador) es la del **canal WhatsApp (texto)**, que es todo lo que se construye en Fase 1. Ver sección "Canal de voz" más abajo para lo que cambia en Fase 2.

## Canal de voz (Fase 2 — no construir todavía)

Confirmado como compromiso de roadmap (ver `docs/decisiones/0001-canal-voz-fase2.md`), aunque el plan de producto original no lo menciona. Reglas para cuando se construya:

- Es **llamadas telefónicas en tiempo real** (STT + LLM + TTS), no notas de voz de WhatsApp ni un asistente interno tipo Alexa.
- Entra en **Fase 2**, junto con el Agente Comercial. **No cambia el alcance de Fase 1** (Fase 1 sigue siendo 100% WhatsApp texto).
- Se implementa como **un grafo LangGraph separado y optimizado para latencia** — no el mismo grafo de texto con un adaptador de canal encima. El RAG híbrido con reranker (~200-400ms) está pensado para WhatsApp asíncrono, no para un turno de voz con expectativa de respuesta en 1-2 segundos.
- Lo único que se comparte entre el grafo de texto y el de voz: los conectores a Odoo/Confluence y el **Agente de Políticas (Guardrails)** — las mismas reglas de venta/escalamiento aplican sin importar el canal.
- Proveedor de telefonía/STT/TTS: sin decidir — se evalúa al arrancar el trabajo de voz en Fase 2, no antes.
- Implicación para Fase 0/1: dejar espacio en `backend/agents/` para que en Fase 2 quepa un segundo grafo (p. ej. `agents/voz/`) sin que el Router/Orquestador de Fase 1 asuman "un solo canal" de forma rígida. Esto es solo una nota de diseño — no implica construir nada de voz ahora.

## Estrategia de RAG

- **Odoo (CRM y Helpdesk) se consulta en vivo vía API. Nunca se vectoriza ni se duplica en pgvector.** Es el error más costoso de introducir por accidente (datos desactualizados, riesgo de exponer información que ya cambió en Odoo).
- **Confluence sí se indexa**: chunking semántico + embeddings en pgvector + metadatos de espacio/permiso.
- Recuperación **híbrida**: `BM25 (top 20) + vector pgvector (top 20) → fusión RRF (top 30 únicos) → reranker (top 5-8) → contexto al LLM`. No usar recuperación vectorial pura — la ganancia de precisión del reranker (3-7% nDCG) importa en un producto donde una respuesta mala tiene costo reputacional.
- Reranker por defecto: `bge-reranker-v2-m3` (BAAI/FlagEmbedding), autohospedado, multilingüe. Para la fusión RRF, partir de los ejemplos oficiales de `pgvector-python` (`examples/hybrid_search/`) en vez de reimplementarla desde cero.
- Cada respuesta del agente debe poder trazarse a la página de Confluence o registro de Odoo que la originó. Si una respuesta no puede citar su fuente, es un bug, no un detalle menor.
- No se usa Obsidian ni ningún esquema de "second brain" — fue evaluado y descartado por falta de control de acceso y trazabilidad (ver plan de producto, sección 4).

## Estructura de carpetas esperada

```
/backend
  /agents          # router, soporte, comercial, políticas, orquestador
  /connectors       # odoo_crm, odoo_helpdesk, confluence, whatsapp
  /api              # FastAPI: webhooks, endpoints de plataforma
  /rag              # ingesta, indexación, recuperación híbrida
  /models           # esquemas Postgres/pgvector
/frontend           # Angular (dashboards, configuración, reportes)
/docker             # Dockerfiles, docker-compose.yml, compose por entorno
/docs               # plan de producto, decisiones de arquitectura (ADRs)
.env.example        # variables requeridas, sin valores reales
```

Si el código existente no coincide con esta estructura, no la fuerces de golpe — señala la discrepancia antes de refactorizar masivamente.

## Convenciones de código

- Python: `black` + `ruff`, tipado con `pydantic` para todos los modelos de datos y payloads de API.
- Angular: standalone components, `strict` mode de TypeScript activado.
- Toda integración externa (Odoo, Confluence, Meta) debe tener manejo de reintentos y circuit breaker — no llamadas directas sin manejo de fallos.
- Todo endpoint y agente que toque datos de cliente debe loggear de forma estructurada (para auditoría, ver sección de seguridad del plan de producto).
- Commits en español o inglés consistente con el resto del repo (verificar historial antes de mezclar idiomas).

## Seguridad — reglas duras

- Nunca hardcodear tokens de Meta, credenciales de Odoo/Confluence o secretos de Entra ID en código, tests o fixtures.
- El token de WhatsApp Cloud API es un **System User token sin expiración** — tratarlo como una contraseña de producción, nunca en el frontend ni en el repo.
- Todo acceso a la plataforma web pasa por SSO Microsoft 365. No implementar login local "temporal" ni siquiera para desarrollo, salvo un modo explícito de mock claramente aislado.

## Pipeline de calidad y CI/CD

- Trunk-based development: commits directos a `main` o ramas de vida muy corta (1-2 días). El pipeline corre en cada push.
- `pre-commit` con `black`, `ruff` y detección de secretos antes de cada commit — más barato que descubrirlo en CI.
- GitHub Actions como estándar; objetivo de pipeline completo bajo 10 minutos. Usar matrix strategy para paralelizar backend/frontend.
- Cualquier Action de terceros se fija por SHA completo, nunca por tag mutable. Permisos mínimos por job. OIDC en vez de credenciales estáticas para despliegues.
- Tests: `pytest` + `TestClient` de FastAPI con dependency overrides para mockear Odoo/Confluence/WhatsApp desde el día uno (ya exigido en el kickoff del proyecto). Angular: test runner nativo del CLI; Playwright para e2e a partir de Fase 1.

## Cómo trabajar en este repo con Claude Code (control de créditos y calidad)

- **Model routing**: usa Haiku para lookups y ediciones simples (renombrar, mover archivos, ajustes de formato), Sonnet para implementación estándar y debugging, y reserva Opus solo para decisiones de arquitectura o refactors complejos que toquen varios módulos a la vez.
- **Skills antes que exploración libre**: si existe una skill para el stack (FastAPI, Angular, testing, revisión de código), invócala en vez de dejar que Claude explore la solución desde cero — reduce tokens y evita desviarse de las convenciones de este archivo.
- **Subagentes solo cuando el ahorro de contexto lo justifica**: úsalos para tareas que leen muchos archivos o generan mucho output intermedio (ej. auditar todo el contenido exportado de Confluence, analizar logs largos). Para ediciones puntuales o un `git commit`, resuélvelo directamente — el overhead de un subagente no se justifica.
- No cargues skills o MCPs "por reflejo" al inicio de la sesión; carga solo lo que la tarea concreta requiere.
- Detalle completo de esta investigación (frameworks evaluados, librerías alternativas, fuentes): `docs/investigacion-arquitectura.md`.

## Qué NO hacer sin confirmar con Leonardo

- Cambiar el stack definido arriba (backend, frontend, base de datos, canal de mensajería, SSO).
- Migrar o vectorizar datos de Odoo hacia Postgres.
- Introducir un BSP de WhatsApp de terceros en lugar de la conexión directa a Meta.
- Relajar las reglas del Agente de Políticas (guardrails) que limitan cuándo el bot puede vender.

## Estado del proyecto

Fase actual: **Fase 0 — Discovery** (validación de accesos a Odoo/Confluence/Meta Business Manager, definición de alcance del MVP). Ver roadmap completo en `docs/plan-producto-whatsapp-tekus.docx`, sección 8, con la adición de voz en Fase 2 registrada en `docs/decisiones/0001-canal-voz-fase2.md`.
