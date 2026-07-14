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


def test_chat_sin_token_devuelve_401():
    response = client.post(
        "/api/platform/rag/chat", json={"mensajes": [{"rol": "user", "texto": "hola"}]}
    )
    assert response.status_code == 401


_ESTADO_VACIO = {
    "nombre": "",
    "correo": "",
    "cuenta": "",
    "resumen_problema": "la pantalla no muestra imagen",
    "intencion": "soporte",
    "pide_humano": False,
}


def _chat(mensajes, contexto, estado, decision):
    """Invoca /chat mockeando los nodos LLM del grafo y la recuperación."""
    with (
        patch("api.platform.rag_qa._get_engine"),
        patch("api.platform.rag_qa.Session"),
        patch("api.platform.rag_qa.hybrid_search", return_value=contexto),
        patch("agents.soporte_web.grafo.llm.extraer_estado_conversacion", return_value=estado),
        patch("agents.soporte_web.grafo.llm.decidir_soporte", return_value=decision),
    ):
        return client.post("/api/platform/rag/chat", json={"mensajes": mensajes})


def test_chat_agente_pide_aclaracion():
    app.dependency_overrides[get_current_user] = _override_usuario
    try:
        r = _chat(
            [{"rol": "user", "texto": "tengo un problema con la pantalla"}],
            contexto=[{"text": "algo", "page_title": "x", "page_url": "u", "space_key": "AL"}],
            estado=_ESTADO_VACIO,
            decision={"accion": "aclarar", "pregunta": "¿Está totalmente negra o con rayas?"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["tipo"] == "pregunta"
        assert "negra" in body["texto"].lower()
        assert body["fuentes"] == []
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_chat_agente_resuelve_con_fuentes():
    app.dependency_overrides[get_current_user] = _override_usuario
    contexto = [
        {
            "text": "Reinicia el player manteniendo el botón 5 segundos.",
            "page_title": "Errores conocidos",
            "page_url": "https://wiki/x/9",
            "space_key": "AL",
        }
    ]
    try:
        r = _chat(
            [
                {"rol": "user", "texto": "la pantalla se ve negra"},
                {"rol": "assistant", "texto": "¿totalmente negra?"},
                {"rol": "user", "texto": "sí, totalmente"},
            ],
            contexto=contexto,
            estado=_ESTADO_VACIO,
            decision={
                "accion": "resolver",
                "respuesta": "Mantén presionado el botón 5 segundos.",
                "fuentes_usadas": [0],
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["tipo"] == "respuesta"
        assert body["fuentes"][0]["space_key"] == "AL"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_chat_escala_pide_datos_si_faltan():
    """Si el cliente pide humano pero no hay nombre/correo, el agente los pide
    (no crea ticket todavía)."""
    app.dependency_overrides[get_current_user] = _override_usuario
    try:
        r = _chat(
            [{"rol": "user", "texto": "quiero hablar con una persona"}],
            contexto=[],
            estado={**_ESTADO_VACIO, "pide_humano": True},
            decision={"accion": "escalar"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["tipo"] == "pregunta"
        assert "correo" in body["texto"].lower() or "nombre" in body["texto"].lower()
        assert body["ticket_ref"] is None
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_chat_escala_crea_ticket_con_datos():
    """Con nombre+correo y escritura habilitada, escala creando el ticket."""
    app.dependency_overrides[get_current_user] = _override_usuario
    estado = {
        **_ESTADO_VACIO,
        "nombre": "Leonardo",
        "correo": "leo@tienda.com",
        "pide_humano": True,
    }
    try:
        with patch("api.platform.rag_qa._crear_ticket", return_value="9001") as mock_crear:
            r = _chat(
                [
                    {
                        "rol": "user",
                        "texto": "quiero que me contacte alguien, soy Leonardo, leo@tienda.com",
                    }
                ],
                contexto=[],
                estado=estado,
                decision={"accion": "escalar"},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["tipo"] == "escalar"
        assert body["ticket_ref"] == "9001"
        assert "9001" in body["texto"]
        mock_crear.assert_called_once()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_chat_no_expone_fuentes_internas_de_odoo():
    """Las fuentes de tickets de Odoo (internas) NUNCA se muestran al usuario."""
    app.dependency_overrides[get_current_user] = _override_usuario
    contexto = [
        {
            "text": "Ticket resuelto: se cambió la fuente.",
            "page_title": "Ticket #4398",
            "page_url": "https://erp.tekus.co/odoo/helpdesk/4385",
            "space_key": "ODOO_HELPDESK",
        },
        {
            "text": "Reinicia el player 5 segundos.",
            "page_title": "Errores conocidos",
            "page_url": "https://wiki/x/9",
            "space_key": "AL",
        },
    ]
    try:
        r = _chat(
            [{"rol": "user", "texto": "pantalla sin imagen"}],
            contexto=contexto,
            estado=_ESTADO_VACIO,
            decision={
                "accion": "resolver",
                "respuesta": "Reinícialo 5 segundos.",
                "fuentes_usadas": [0, 1],  # usó ambos, pero solo se muestra el público
            },
        )
        assert r.status_code == 200
        fuentes = r.json()["fuentes"]
        assert len(fuentes) == 1
        assert fuentes[0]["space_key"] == "AL"
        assert all("helpdesk" not in f["page_url"] for f in fuentes)
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
