# ADR 0001 — Canal de voz (llamadas telefónicas) como adición al roadmap, entra en Fase 2

- **Fecha:** 2026-07-12
- **Estado:** Aceptado
- **Contexto de la decisión:** conversación de arranque de Fase 0 con Leonardo Arango.

## Contexto

`docs/Plan Producto Agente WhatsApp Tekus.docx` (aprobado el 2026-07-12) no menciona voz ni telefonía en ningún punto. La única mención a expansión de canales aparece en la Fase 3 ("evaluación de expansión a otros canales: Teams, web chat, eventual productización white-label"), sin STT/TTS ni llamadas en tiempo real.

Al iniciar el desarrollo, Leonardo confirmó que sí quiere un asistente de voz — específicamente **llamadas telefónicas en tiempo real** (STT + LLM + TTS con expectativa de latencia conversacional, no un canal asíncrono como WhatsApp) — y que es un compromiso de roadmap, no una idea suelta. Esto no estaba escrito en el plan de producto, así que se registra aquí como decisión formal en vez de reescribir el `.docx` ya aprobado.

Voz en tiempo real es un salto técnico distinto al resto del plan: el pipeline RAG híbrido definido en `docs/investigacion-arquitectura.md` (BM25 + vector + reranker, ~200-400ms añadidos) es aceptable para WhatsApp asíncrono pero no está pensado para un turno de conversación hablada con expectativa de respuesta en 1-2 segundos.

## Decisión

1. **Voz entra en Fase 2**, en paralelo al Agente Comercial. **Fase 1 (MVP de Soporte) no cambia de alcance**: sigue siendo exclusivamente WhatsApp texto, sin ningún trabajo de voz.
2. Cuando se construya, voz se implementa como **un grafo LangGraph separado y optimizado para latencia** (menos o ningún RAG pesado, respuestas más cortas), no como el mismo grafo de texto con un adaptador de canal encima. Se acepta cierta duplicación de lógica de conversación a cambio de no comprometer la latencia del canal de voz con el diseño pensado para WhatsApp.
3. Lo que **sí se comparte** entre el grafo de texto y el grafo de voz:
   - Conectores a Odoo (CRM + Helpdesk) y Confluence — se consultan igual, en vivo, sin duplicar por canal.
   - El **Agente de Políticas (Guardrails)** — las mismas reglas de cuándo se puede vender o se debe escalar a humano aplican sin importar el canal.
4. **Proveedor de telefonía y STT/TTS: sin decidir.** Se investiga y evalúa cuando arranque el trabajo de voz en Fase 2 (candidatos típicos a evaluar entonces: Twilio, Vonage, Deepgram, ElevenLabs, ASR/TTS de los propios proveedores de LLM — ninguno preseleccionado hoy).
5. **Implicación para Fase 0/1 (para no bloquear esto después):** la estructura de `backend/agents/` debe dejar espacio para que en Fase 2 aparezca un segundo grafo (p. ej. `agents/voz/`) sin forzar que el Router o el Orquestador de Fase 1 asuman "un solo canal" de forma rígida. Esto es una nota de diseño, no implica construir nada de voz en Fase 0/1.

## Alternativas consideradas

- **Un solo cerebro LangGraph multicanal** (WhatsApp y voz comparten el mismo grafo, el canal es solo adaptador de entrada/salida): descartada por ahora — obligaría a diseñar el RAG y el grafo de texto pensando en restricciones de latencia de voz desde Fase 1, antes de tener claridad de requisitos reales de voz.
- **No decidir nada hasta Fase 2**: descartada — dejar esto totalmente abierto arriesga que el diseño de agentes de Fase 1 asuma implícitamente un solo canal y haya que refactorizar el orquestador cuando llegue voz.

## Consecuencias

- El plan de producto (`docs/Plan Producto Agente WhatsApp Tekus.docx`) queda desactualizado en su mención de canales futuros (dice "Teams, web chat" y no incluye voz); este ADR es la fuente de verdad hasta que el documento se revise formalmente.
- Volumen esperado de llamadas de voz y proveedor de telefonía quedan como incógnitas abiertas — no bloquean Fase 0/1, se resuelven al arrancar Fase 2.
- Ver también `docs/decisiones/0002-odoo-en-vivo-no-vectorizado.md` y `docs/decisiones/0003-descartar-second-brain-obsidian.md` (pendientes, mencionados en el prompt de arranque de Claude Code) para el resto de decisiones de arquitectura de Fase 0.
