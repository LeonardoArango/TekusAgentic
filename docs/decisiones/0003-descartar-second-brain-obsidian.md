# ADR 0003 — Descartar el enfoque "second brain" / Obsidian para la base de conocimiento

- **Fecha:** 2026-07-13
- **Estado:** Aceptado
- **Contexto de la decisión:** `docs/Plan Producto Agente WhatsApp Tekus.docx`, resumen ejecutivo y sección 4 (aprobado 2026-07-12); confirmado en `CLAUDE.md`, sección "Estrategia de RAG".

## Contexto

Durante la evaluación de arquitectura de conocimiento se consideró un enfoque tipo "second brain" (herramientas de notas enlazadas al estilo Obsidian/Zettelkasten) como base de conocimiento del agente, en lugar de indexar directamente Confluence en pgvector.

El plan de producto es explícito en el resumen ejecutivo: el agente debe operar mediante *"una arquitectura de Agentic RAG (no un enfoque tipo 'second brain'/Obsidian, que carece de gobierno, control de acceso y trazabilidad para un entorno B2B de misión crítica)"*.

Este proyecto opera en un entorno B2B de misión crítica: las respuestas del agente pueden involucrar SLA, políticas comerciales, e información de cuenta de clientes reales. Cualquier fuente de conocimiento necesita, como requisito no negociable:

- **Control de acceso** a nivel de fuente (quién puede ver qué página/espacio).
- **Trazabilidad**: cada respuesta debe poder citar el registro exacto que la originó (página de Confluence, o registro de Odoo — ver ADR 0002).
- **Gobierno**: un dueño claro de cada pieza de contenido, con proceso de actualización y revisión.

Un esquema tipo "second brain"/Obsidian —pensado originalmente para notas personales interconectadas— no ofrece nativamente ninguna de las tres garantías anteriores: no tiene modelo de permisos por documento, no mantiene metadatos de origen/versión compatibles con auditoría, y su fortaleza (enlaces libres entre notas) es orientada a exploración individual, no a servir de fuente de verdad auditable para un agente que responde a clientes externos.

## Decisión

1. Se descarta cualquier esquema tipo "second brain"/Obsidian como base de conocimiento del agente.
2. La base de conocimiento indexada es **exclusivamente Confluence** (`wiki.tekus.co`), que ya es la wiki corporativa existente, con su propio modelo de espacios/permisos que se preserva como metadato en la indexación (ver ADR 0002 y `backend/rag/README.md`).
3. La arquitectura de recuperación es **Agentic RAG**: un clasificador enruta cada consulta entre lookup directo a Odoo, recuperación híbrida sobre Confluence, o ambas — no un grafo de notas de conocimiento personal ni una base de conocimiento paralela mantenida a mano.

## Alternativas consideradas

- **Second brain/Obsidian como base de conocimiento**: descartada por falta de control de acceso, trazabilidad y gobierno (ver Contexto). Además introduciría una fuente de conocimiento paralela a Confluence que ya es la wiki corporativa oficial, duplicando mantenimiento sin necesidad.
- **Migrar el contenido de Confluence a un formato tipo second brain antes de indexarlo**: descartada — no aporta ninguna ventaja sobre indexar Confluence directamente, y rompe la trazabilidad al origen (la respuesta ya no citaría la página de Confluence real, sino una nota derivada).

## Consecuencias

- No se introduce ninguna herramienta de notas personales (Obsidian u otra) en el stack de este proyecto, ni como servicio ni como formato intermedio de contenido.
- Toda evolución futura de la base de conocimiento (nuevas fuentes, taxonomías, etc.) se evalúa dentro del modelo Confluence + pgvector + metadatos de permiso ya decidido, no como un esquema de notas enlazadas alternativo.
