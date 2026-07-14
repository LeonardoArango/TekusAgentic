"""Tests del cliente LLM — llamada a Anthropic mockeada, sin red ni tokens reales."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agents import llm_client


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    llm_client._client = None
    yield
    llm_client._client = None


def _fake_message(tool_input: dict) -> SimpleNamespace:
    tool_use_block = SimpleNamespace(type="tool_use", input=tool_input)
    return SimpleNamespace(content=[tool_use_block])


def test_decidir_respuesta_soporte_pasa_tool_choice_correcto(monkeypatch):
    mock_create = MagicMock(
        return_value=_fake_message(
            {"puede_resolver": True, "respuesta": "Prueba esto...", "fuentes_usadas": [0]}
        )
    )
    monkeypatch.setattr(
        llm_client,
        "_get_client",
        lambda: SimpleNamespace(messages=SimpleNamespace(create=mock_create)),
    )

    resultado = llm_client.decidir_respuesta_soporte("¿cómo reinicio?", ["fragmento de ayuda"])

    assert resultado["puede_resolver"] is True
    kwargs = mock_create.call_args.kwargs
    assert kwargs["tool_choice"] == {"type": "tool", "name": "responder_soporte"}
    assert "fragmento de ayuda" in kwargs["messages"][0]["content"]


def test_extraer_referencia_ticket(monkeypatch):
    mock_create = MagicMock(
        return_value=_fake_message({"tiene_ticket": True, "referencia": "TK-42"})
    )
    monkeypatch.setattr(
        llm_client,
        "_get_client",
        lambda: SimpleNamespace(messages=SimpleNamespace(create=mock_create)),
    )

    resultado = llm_client.extraer_referencia_ticket("sí, es el TK-42")

    assert resultado == {"tiene_ticket": True, "referencia": "TK-42"}


def test_model_usa_env_var(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-4-8")
    assert llm_client._model() == "claude-opus-4-8"


def test_model_default_sin_env_var(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    assert llm_client._model() == "claude-sonnet-5"
