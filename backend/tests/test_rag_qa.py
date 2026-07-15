"""Tests del endpoint conversacional /chat (motor LangGraph) y /preguntas.

Mockea NLU/NLG (agents.soporte_web.grafo.{nlu,nlg}), la recuperación y la
memoria Redis — no requiere Postgres, Redis ni llamadas a OpenAI.
"""

from contextlib import contextmanager
from unittest.mock import patch

from fastapi.testclient import TestClient

from agents.soporte_web.estado import DialogueState
from api.platform.auth import UsuarioAutenticado, get_current_user
from main import app

client = TestClient(app)


def _override_usuario():
    return UsuarioAutenticado(oid="test-oid", nombre="Test User", correo="test@tekus.co")


@contextmanager
def _memoria_en_memoria():
    """Reemplaza la memoria Redis por un dict en proceso."""
    store: dict[str, DialogueState] = {}

    def cargar(cid, canal="web"):
        return store.get(cid) or DialogueState(conversation_id=cid, canal=canal)

    def guardar(est):
        store[est.conversation_id] = est

    with (
        patch("api.platform.rag_qa.memoria.cargar", side_effect=cargar),
        patch("api.platform.rag_qa.memoria.guardar", side_effect=guardar),
        patch("api.platform.rag_qa.memoria.resumir_si_necesario"),
        patch("api.platform.rag_qa._get_engine"),
        patch("api.platform.rag_qa.Session"),
    ):
        yield store


def _post(texto, cid=None):
    return client.post("/api/platform/rag/chat", json={"texto": texto, "conversation_id": cid})


# --- auth -------------------------------------------------------------------


def test_chat_sin_token_devuelve_401():
    assert _post("hola").status_code == 401


# --- regresión del screenshot: meta-pregunta NO se ignora ni se repite ------


def test_meta_pregunta_se_responde_no_se_repite():
    app.dependency_overrides[get_current_user] = _override_usuario
    try:
        with (
            _memoria_en_memoria(),
            patch("api.platform.rag_qa.hybrid_search", return_value=[]),
            patch(
                "agents.soporte_web.grafo.nlu.entender",
                return_value={
                    "acto": "meta_pregunta",
                    "sentimiento": "neutral",
                    "intencion": "soporte",
                },
            ),
            patch(
                "agents.soporte_web.grafo.nlg.responder_meta",
                return_value="Soy Kai, un asistente virtual de Tekus.",
            ) as meta,
        ):
            r = _post("¿eres humano?")
        assert r.status_code == 200
        body = r.json()
        assert body["tipo"] == "pregunta"
        assert "virtual" in body["texto"].lower()
        assert "correo" not in body["texto"].lower()  # NO cae en el gate de datos
        meta.assert_called_once()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# --- resolver: solo fuentes públicas de Confluence --------------------------


def test_resolver_filtra_fuentes_internas():
    app.dependency_overrides[get_current_user] = _override_usuario
    contexto = [
        {
            "text": "ticket interno",
            "page_title": "Ticket #x",
            "page_url": "https://erp/helpdesk/1",
            "space_key": "ODOO_HELPDESK",
        },
        {"text": "doc", "page_title": "Errores", "page_url": "https://wiki/9", "space_key": "AL"},
    ]
    try:
        with (
            _memoria_en_memoria(),
            patch("api.platform.rag_qa.hybrid_search", return_value=contexto),
            patch(
                "agents.soporte_web.grafo.nlu.entender",
                return_value={
                    "acto": "reportar_problema",
                    "sentimiento": "neutral",
                    "intencion": "soporte",
                    "problema": "la pantalla no muestra imagen",
                    "reporto_antes": "no",
                    # cliente ya identificado en un turno (para llegar al ramo problema)
                    "datos": {
                        "nombre": "Leo",
                        "cuenta": "Tienda X",
                        "sede": "CC Cacique",
                        "correo": "leo@x.com",
                    },
                },
            ),
            patch(
                "agents.soporte_web.grafo.nlu.decidir_problema",
                return_value={
                    "accion": "resolver",
                    "borrador_respuesta": "reinicia",
                    "fuentes_usadas": [0, 1],
                },
            ),
            patch("agents.soporte_web.grafo.nlg.resolver", return_value="Reinícialo."),
        ):
            r = _post("la pantalla no muestra imagen")
        assert r.status_code == 200
        fuentes = r.json()["fuentes"]
        assert len(fuentes) == 1 and fuentes[0]["space_key"] == "AL"
        assert all("helpdesk" not in f["page_url"] for f in fuentes)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# --- escalamiento: pide datos si faltan; crea ticket si están ---------------


def test_pedir_humano_sin_datos_pide_datos_no_crea_ticket():
    app.dependency_overrides[get_current_user] = _override_usuario
    try:
        with (
            _memoria_en_memoria(),
            patch("api.platform.rag_qa.hybrid_search", return_value=[]),
            patch(
                "agents.soporte_web.grafo.nlu.entender",
                return_value={
                    "acto": "pedir_humano",
                    "sentimiento": "neutral",
                    "intencion": "soporte",
                },
            ),
            patch(
                "agents.soporte_web.grafo.nlg.recolectar_dato",
                return_value="¿Me compartes tu nombre y correo?",
            ),
            patch("api.platform.rag_qa._crear_ticket", return_value=None) as crear,
        ):
            r = _post("quiero hablar con una persona")
        assert r.status_code == 200
        assert r.json()["tipo"] == "pregunta"
        assert r.json()["ticket_ref"] is None
        crear.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_pedir_humano_con_datos_crea_ticket():
    app.dependency_overrides[get_current_user] = _override_usuario
    try:
        with (
            _memoria_en_memoria(),
            patch("api.platform.rag_qa.hybrid_search", return_value=[]),
            patch(
                "agents.soporte_web.grafo.nlu.entender",
                return_value={
                    "acto": "pedir_humano",
                    "sentimiento": "neutral",
                    "intencion": "soporte",
                    "datos": {
                        "nombre": "Leonardo",
                        "correo": "leo@tienda.com",
                        "sede": "CC Cacique",
                    },
                },
            ),
            patch(
                "agents.soporte_web.grafo.nlg.escalar", return_value="Listo, dejé tu caso #9001."
            ),
            patch("api.platform.rag_qa._crear_ticket", return_value="9001") as crear,
        ):
            r = _post("soy Leonardo, leo@tienda.com, en CC Cacique; que me contacte alguien")
        assert r.status_code == 200
        body = r.json()
        assert body["tipo"] == "escalar" and body["ticket_ref"] == "9001"
        crear.assert_called_once()
        # la sede se pasa al creador de ticket
        assert (
            crear.call_args.args[3] == "CC Cacique"
            or crear.call_args.kwargs.get("sede") == "CC Cacique"
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# --- /preguntas (QA one-shot, sin conversación) -----------------------------


def test_preguntas_sin_token_devuelve_401():
    assert client.post("/api/platform/rag/preguntas", json={"pregunta": "hola"}).status_code == 401
