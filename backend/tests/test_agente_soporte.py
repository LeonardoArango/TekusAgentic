"""Tests del Agente de Soporte end-to-end, con RAG/Odoo/LLM mockeados."""

from unittest.mock import MagicMock

import pytest

from agents.soporte import agente, grafo
from connectors.odoo_helpdesk.client import Ticket


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")


def _ticket(id_=42, etapa="Nuevo") -> Ticket:
    return Ticket(
        id=id_,
        referencia=str(id_),
        asunto="Pantalla no enciende",
        descripcion="La pantalla del kiosco no enciende desde ayer",
        etapa=etapa,
        prioridad="1",
        telefono_contacto="573000000000",
    )


def test_resuelve_con_contexto_suficiente(monkeypatch):
    buscar = MagicMock(
        return_value=[
            {"text": "Para reiniciar el player, mantén presionado...", "page_url": "https://wiki/x"}
        ]
    )
    helpdesk = MagicMock()
    monkeypatch.setattr(
        "agents.llm_client.decidir_respuesta_soporte",
        lambda pregunta, fragmentos: {
            "puede_resolver": True,
            "respuesta": "Para reiniciar el player, manten presionado el botón 5 segundos.",
            "fuentes_usadas": [0],
        },
    )

    resultado = agente.procesar_mensaje(
        "¿cómo reinicio el player?", "573000000000", buscar, helpdesk
    )

    assert resultado["puede_resolver"] is True
    assert resultado["fuentes"] == ["https://wiki/x"]
    helpdesk.crear_ticket.assert_not_called()


def test_sin_contexto_pregunta_por_ticket_existente(monkeypatch):
    buscar = MagicMock(return_value=[])
    helpdesk = MagicMock()

    resultado = agente.procesar_mensaje("mi kiosco no prende", "573000000000", buscar, helpdesk)

    assert resultado["puede_resolver"] is False
    assert resultado["esperando_referencia_ticket"] is True
    assert "número de ticket" in resultado["respuesta"]
    helpdesk.crear_ticket.assert_not_called()
    helpdesk.buscar_por_referencia.assert_not_called()


def test_usuario_confirma_ticket_existente(monkeypatch):
    helpdesk = MagicMock()
    helpdesk.buscar_por_referencia.return_value = _ticket(id_=99, etapa="En progreso")
    monkeypatch.setattr(
        "agents.llm_client.extraer_referencia_ticket",
        lambda respuesta: {"tiene_ticket": True, "referencia": "99"},
    )

    estado_previo = {
        "mensaje": "mi kiosco no prende",
        "esperando_referencia_ticket": True,
    }
    resultado = agente.procesar_mensaje(
        "sí, es el 99",
        "573000000000",
        buscar=MagicMock(),
        helpdesk=helpdesk,
        estado_previo=estado_previo,
    )

    assert resultado["ticket"].referencia == "99"
    assert "En progreso" in resultado["respuesta"]
    helpdesk.crear_ticket.assert_not_called()


def test_usuario_sin_ticket_se_crea_uno_nuevo(monkeypatch):
    helpdesk = MagicMock()
    helpdesk.crear_ticket.return_value = _ticket(id_=101)
    monkeypatch.setattr(
        "agents.llm_client.extraer_referencia_ticket",
        lambda respuesta: {"tiene_ticket": False, "referencia": ""},
    )

    estado_previo = {
        "mensaje": "mi kiosco no prende",
        "esperando_referencia_ticket": True,
    }
    resultado = agente.procesar_mensaje(
        "no tengo ninguno",
        "573000000000",
        buscar=MagicMock(),
        helpdesk=helpdesk,
        estado_previo=estado_previo,
    )

    helpdesk.crear_ticket.assert_called_once()
    assert resultado["ticket_creado"] is True
    assert "101" in resultado["respuesta"]


def test_referencia_mencionada_pero_no_existe_crea_ticket_nuevo(monkeypatch):
    helpdesk = MagicMock()
    helpdesk.buscar_por_referencia.return_value = None
    helpdesk.crear_ticket.return_value = _ticket(id_=202)
    monkeypatch.setattr(
        "agents.llm_client.extraer_referencia_ticket",
        lambda respuesta: {"tiene_ticket": True, "referencia": "12345"},
    )

    estado_previo = {"mensaje": "mi kiosco no prende", "esperando_referencia_ticket": True}
    resultado = agente.procesar_mensaje(
        "el 12345",
        "573000000000",
        buscar=MagicMock(),
        helpdesk=helpdesk,
        estado_previo=estado_previo,
    )

    helpdesk.crear_ticket.assert_called_once()
    assert "12345" in resultado["respuesta"]
    assert resultado["ticket"].referencia == "202"


def test_grafo_se_construye_y_compila():
    compilado = grafo.construir_grafo(buscar=MagicMock(return_value=[]), helpdesk=MagicMock())
    assert compilado is not None
