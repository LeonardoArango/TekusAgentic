"""Conector real a Odoo Helpdesk — lectura y creación de tickets, en vivo.

Nunca se vectoriza ni se duplica esta información en pgvector (ver
docs/decisiones/0002-odoo-en-vivo-no-vectorizado.md).

**Asunción sin confirmar (HU #14):** se asume el modelo estándar
`helpdesk.ticket` (Odoo Enterprise / módulo `helpdesk_mgmt` de la OCA) y sus
campos habituales. Si la instancia real de Tekus usa otro módulo o nombres de
campo distintos, este es el ÚNICO archivo que hay que ajustar — los nombres
de modelo/campo están centralizados en `_MODEL`/`_FIELDS` a propósito. En
particular, `partner_phone` como campo de búsqueda por teléfono es la parte
menos segura de esta asunción: confirmarlo contra la instancia real antes de
confiar en `buscar_por_telefono`.
"""

from __future__ import annotations

from dataclasses import dataclass

from connectors.odoo_common import OdooConnection

_MODEL = "helpdesk.ticket"
_FIELDS = [
    "id",
    "name",
    "description",
    "stage_id",
    "priority",
    "partner_id",
    "partner_phone",
    "team_id",
]


@dataclass(frozen=True)
class Ticket:
    id: int
    referencia: str
    asunto: str
    descripcion: str
    etapa: str
    prioridad: str
    telefono_contacto: str | None


def _many2one_display(value) -> str:
    """Los campos many2one vienen de `read()` como (id, "display_name") o False."""
    return value[1] if value else ""


def _to_ticket(record: dict) -> Ticket:
    return Ticket(
        id=record["id"],
        referencia=str(record["id"]),
        asunto=record.get("name") or "",
        descripcion=record.get("description") or "",
        etapa=_many2one_display(record.get("stage_id")),
        prioridad=record.get("priority") or "",
        telefono_contacto=record.get("partner_phone") or None,
    )


def _limpiar_referencia(referencia: str) -> str | None:
    """Normaliza formatos comunes ("#123", "TK-123", "123") a un id numérico."""
    limpia = referencia.strip().lstrip("#").upper().removeprefix("TK-").strip()
    return limpia if limpia.isdigit() else None


class OdooHelpdeskClient:
    def __init__(self, connection: OdooConnection) -> None:
        self._connection = connection

    def buscar_por_referencia(self, referencia: str) -> Ticket | None:
        """Busca un ticket por su referencia. Hoy, el `id` numérico de Odoo."""
        referencia_numerica = _limpiar_referencia(referencia)
        if referencia_numerica is None:
            return None

        model = self._connection.env.env[_MODEL]
        record_ids = self._connection.call_with_retry(
            model.search, [("id", "=", int(referencia_numerica))]
        )
        if not record_ids:
            return None
        records = self._connection.call_with_retry(model.read, record_ids, _FIELDS)
        return _to_ticket(records[0])

    def buscar_por_telefono(self, telefono: str, limite: int = 5) -> list[Ticket]:
        """Busca tickets recientes asociados a un teléfono de contacto."""
        model = self._connection.env.env[_MODEL]
        record_ids = self._connection.call_with_retry(
            model.search,
            [("partner_phone", "=", telefono)],
            0,
            limite,
            "create_date desc",
        )
        if not record_ids:
            return []
        records = self._connection.call_with_retry(model.read, record_ids, _FIELDS)
        return [_to_ticket(r) for r in records]

    def crear_ticket(self, asunto: str, descripcion: str, telefono_contacto: str) -> Ticket:
        model = self._connection.env.env[_MODEL]
        ticket_id = self._connection.call_with_retry(
            model.create,
            {
                "name": asunto,
                "description": descripcion,
                "partner_phone": telefono_contacto,
            },
        )
        records = self._connection.call_with_retry(model.read, [ticket_id], _FIELDS)
        return _to_ticket(records[0])
