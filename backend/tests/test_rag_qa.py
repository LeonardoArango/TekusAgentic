"""Tests del endpoint de preguntas al RAG (plataforma web) — mockea
hybrid_search y el cliente OpenAI, no requiere Postgres real ni llamadas
salientes (ver CLAUDE.md: mockear Odoo/Confluence/WhatsApp desde el día uno,
mismo criterio aplica a servicios LLM externos)."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from api.platform.auth import UsuarioAutenticado, get_current_user
from main import app

client = TestClient(app)


def _override_usuario():
    return UsuarioAutenticado(oid="test-oid", nombre="Test User", correo="test@tekus.co")


def test_preguntas_sin_token_devuelve_401():
    response = client.post("/api/platform/rag/preguntas", json={"pregunta": "hola"})
    assert response.status_code == 401


def test_preguntas_sin_contexto_no_llama_al_llm():
    app.dependency_overrides[get_current_user] = _override_usuario
    try:
        with (
            patch("api.platform.rag_qa._get_engine"),
            patch("api.platform.rag_qa.Session"),
            patch("api.platform.rag_qa.hybrid_search", return_value=[]) as mock_search,
            patch("api.platform.rag_qa.responder_pregunta_rag") as mock_llm,
        ):
            response = client.post(
                "/api/platform/rag/preguntas", json={"pregunta": "¿algo sin contexto?"}
            )
        assert response.status_code == 200
        assert response.json() == {"puede_resolver": False, "respuesta": "", "fuentes": []}
        mock_search.assert_called_once()
        mock_llm.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_preguntas_con_contexto_devuelve_respuesta_y_fuentes():
    app.dependency_overrides[get_current_user] = _override_usuario
    contexto = [
        {
            "chunk_id": "1",
            "text": "Para reiniciar el kiosco, mantén presionado el botón 5 segundos.",
            "page_title": "Manual de kioscos",
            "page_url": "https://wiki/x/1",
            "space_key": "kiosk",
        }
    ]
    try:
        with (
            patch("api.platform.rag_qa._get_engine"),
            patch("api.platform.rag_qa.Session"),
            patch("api.platform.rag_qa.hybrid_search", return_value=contexto),
            patch(
                "api.platform.rag_qa.responder_pregunta_rag",
                return_value={
                    "puede_resolver": True,
                    "respuesta": "Mantén presionado el botón 5 segundos.",
                    "fuentes_usadas": [0],
                },
            ),
        ):
            response = client.post(
                "/api/platform/rag/preguntas", json={"pregunta": "¿cómo reinicio el kiosco?"}
            )
        assert response.status_code == 200
        body = response.json()
        assert body["puede_resolver"] is True
        assert body["fuentes"] == [
            {
                "page_title": "Manual de kioscos",
                "page_url": "https://wiki/x/1",
                "space_key": "kiosk",
            }
        ]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
