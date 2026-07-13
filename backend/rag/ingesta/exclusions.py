"""Registro de páginas de Confluence excluidas explícitamente del RAG.

No es un filtro automático de calidad — cada entrada aquí viene de la
auditoría manual de contenido de Fase 0 (2026-07-13) y debe tener una razón
explícita. "Sin razón documentada" no es una exclusión válida.
"""

from __future__ import annotations

# space_key -> {page_id: razón}
EXCLUDED_PAGES: dict[str, dict[str, str]] = {
    # Kioscos (oficial): credenciales reales en texto plano — ver ADR pendiente
    # de rotación con el equipo. Nunca indexar estas páginas.
    "kiosk": {
        # IDs a confirmar/completar por quien tenga acceso de escritura al
        # espacio para rotarlas; mientras tanto se excluyen por título en
        # rag/ingesta/confluence_ingest.py como salvaguarda adicional.
    },
    "AL": {
        # Artículo de ayuda de otra empresa (Driversnote) copiado verbatim,
        # sin relación con Tekus — no es documentación de soporte válida.
    },
}

# Salvaguarda por título (además de por ID) para espacios donde el ID exacto
# de la página con credenciales/contenido no válido no se ha confirmado aún.
EXCLUDED_TITLE_SUBSTRINGS: dict[str, list[str]] = {
    "kiosk": ["Loggro", "Kokoriko"],
    "AL": ["Configuración de consumo y optimización de batería"],
}


def is_excluded(space_key: str, page_id: str, title: str) -> bool:
    if page_id in EXCLUDED_PAGES.get(space_key, {}):
        return True
    return any(
        substring.lower() in title.lower()
        for substring in EXCLUDED_TITLE_SUBSTRINGS.get(space_key, [])
    )
