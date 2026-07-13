"""Tests del conector de Odoo Helpdesk — conexión mockeada, sin llamadas reales."""

from unittest.mock import MagicMock

from connectors.odoo_helpdesk.client import OdooHelpdeskClient

_RECORD = {
    "id": 42,
    "name": "Pantalla no enciende",
    "description": "La pantalla del kiosco no enciende desde ayer",
    "stage_id": (3, "En progreso"),
    "priority": "1",
    "partner_id": (7, "Cliente Demo"),
    "partner_phone": "573000000000",
    "team_id": (1, "Soporte Nivel 1"),
}


def _connection_mock(model_mock: MagicMock) -> MagicMock:
    connection = MagicMock()
    connection.env.env.__getitem__.return_value = model_mock
    connection.call_with_retry.side_effect = lambda fn, *a, **kw: fn(*a, **kw)
    return connection


def test_buscar_por_referencia_encontrado():
    model = MagicMock()
    model.search.return_value = [42]
    model.read.return_value = [_RECORD]
    client = OdooHelpdeskClient(_connection_mock(model))

    ticket = client.buscar_por_referencia("#42")

    model.search.assert_called_once_with([("id", "=", 42)])
    assert ticket is not None
    assert ticket.referencia == "42"
    assert ticket.etapa == "En progreso"
    assert ticket.telefono_contacto == "573000000000"


def test_buscar_por_referencia_formato_tk():
    model = MagicMock()
    model.search.return_value = [42]
    model.read.return_value = [_RECORD]
    client = OdooHelpdeskClient(_connection_mock(model))

    ticket = client.buscar_por_referencia("TK-42")

    model.search.assert_called_once_with([("id", "=", 42)])
    assert ticket is not None


def test_buscar_por_referencia_no_numerica_no_llama_a_odoo():
    model = MagicMock()
    client = OdooHelpdeskClient(_connection_mock(model))

    ticket = client.buscar_por_referencia("no tengo ticket")

    model.search.assert_not_called()
    assert ticket is None


def test_buscar_por_referencia_no_encontrado():
    model = MagicMock()
    model.search.return_value = []
    client = OdooHelpdeskClient(_connection_mock(model))

    assert client.buscar_por_referencia("999") is None
    model.read.assert_not_called()


def test_crear_ticket():
    model = MagicMock()
    model.create.return_value = 55
    model.read.return_value = [{**_RECORD, "id": 55}]
    client = OdooHelpdeskClient(_connection_mock(model))

    ticket = client.crear_ticket(
        asunto="Mi kiosco no prende", descripcion="detalle largo", telefono_contacto="573000000000"
    )

    model.create.assert_called_once_with(
        {
            "name": "Mi kiosco no prende",
            "description": "detalle largo",
            "partner_phone": "573000000000",
        }
    )
    assert ticket.id == 55


def test_ticket_sin_etapa_no_falla():
    model = MagicMock()
    model.search.return_value = [1]
    model.read.return_value = [{**_RECORD, "stage_id": False}]
    client = OdooHelpdeskClient(_connection_mock(model))

    ticket = client.buscar_por_referencia("1")

    assert ticket.etapa == ""
