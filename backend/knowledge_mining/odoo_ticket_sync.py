"""Sincronización incremental de tickets de Odoo Helpdesk hacia el schema
de staging `knowledge_mining` (minería para autoría de FAQs).

No es parte del RAG de producción — ver
docs/decisiones/0002-staging-mineria-tickets-odoo.md. El agente
conversacional nunca lee de aquí.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from datetime import UTC, datetime

import odoorpc
import psycopg
from psycopg.types.json import Jsonb

logger = logging.getLogger(__name__)

JOB_NAME = "odoo_ticket_mining"
CLOSED_STAGE_IDS = [4, 21, 24]  # Resuelto, Cancelado, Encuesta de satisfacción

TICKET_FIELDS = [
    "id",
    "ticket_ref",
    "name",
    "user_id",
    "x_studio_reportado_por",
    "x_studio_diagnstico",
    "x_studio_complejidad",
    "x_studio_impacto",
    "x_studio_solucin_entregada",
    "x_studio_solicitado_por",
    "partner_id",
    "partner_name",
    "partner_email",
    "partner_phone",
    "create_date",
    "write_date",
    "description",
    "x_studio_tickets_tipo",
    "priority",
    "source_id",
    "tag_ids",
    "team_id",
    "stage_id",
    "message_ids",
    "message_attachment_count",
]


def _retry(fn, *args, attempts: int = 3, delay: float = 3.0, **kwargs):
    last_err: Exception | None = None
    for attempt in range(attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - reintentamos cualquier fallo transitorio de RPC
            last_err = exc
            logger.warning("Reintento %s/%s tras error: %s", attempt + 1, attempts, exc)
            time.sleep(delay)
    assert last_err is not None
    raise last_err


def _connect_odoo() -> odoorpc.ODOO:
    odoo = odoorpc.ODOO(
        os.environ["ODOO_URL"].replace("https://", "").replace("http://", ""),
        protocol="jsonrpc+ssl",
        port=443,
        timeout=60,
    )
    odoo.login(os.environ["ODOO_DB"], os.environ["ODOO_USERNAME"], os.environ["ODOO_PASSWORD"])
    return odoo


def _connect_postgres():
    return psycopg.connect(os.environ["DATABASE_URL"].replace("+asyncpg", ""))


def _get_watermark(conn) -> datetime | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT last_synced_at FROM knowledge_mining.sync_state WHERE job_name = %s",
            (JOB_NAME,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def _set_watermark(conn, ts: datetime) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO knowledge_mining.sync_state (job_name, last_synced_at)
            VALUES (%s, %s)
            ON CONFLICT (job_name) DO UPDATE SET last_synced_at = EXCLUDED.last_synced_at
            """,
            (JOB_NAME, ts),
        )


def _known_attachment_ids(conn) -> set[int]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT odoo_attachment_id FROM knowledge_mining.odoo_ticket_attachment"
        )
        return {row[0] for row in cur.fetchall()}


def sync_open_tickets_incremental() -> dict:
    """Trae tickets abiertos creados/modificados desde la última corrida.

    No vuelve a descargar adjuntos ya vistos (dedup por odoo_attachment_id).
    Retorna un resumen para logging/observabilidad.
    """
    run_started_at = datetime.now(UTC)

    odoo = _connect_odoo()
    Ticket = odoo.env["helpdesk.ticket"]
    Message = odoo.env["mail.message"]
    Attachment = odoo.env["ir.attachment"]
    Tag = odoo.env["helpdesk.tag"]

    conn = _connect_postgres()
    conn.autocommit = False

    try:
        watermark = _get_watermark(conn)

        domain = [("stage_id", "not in", CLOSED_STAGE_IDS)]
        if watermark is not None:
            domain.append(("write_date", ">=", watermark.strftime("%Y-%m-%d %H:%M:%S")))

        ticket_ids = _retry(Ticket.search, domain)
        logger.info(
            "job=%s watermark=%s tickets_candidatos=%d", JOB_NAME, watermark, len(ticket_ids)
        )

        if not ticket_ids:
            _set_watermark(conn, run_started_at)
            conn.commit()
            return {"tickets_sincronizados": 0, "adjuntos_nuevos": 0, "watermark": run_started_at}

        tickets = _retry(Ticket.read, ticket_ids, TICKET_FIELDS)

        all_tag_ids = sorted({tid for t in tickets for tid in t["tag_ids"]})
        tag_names = (
            {t["id"]: t["name"] for t in _retry(Tag.read, all_tag_ids, ["id", "name"])}
            if all_tag_ids
            else {}
        )

        known_attachments = _known_attachment_ids(conn)
        new_attachments_count = 0

        with conn.cursor() as cur:
            for t in tickets:
                msg_ids = t["message_ids"]
                messages = (
                    _retry(
                        Message.read,
                        msg_ids,
                        [
                            "id",
                            "date",
                            "author_id",
                            "email_from",
                            "body",
                            "message_type",
                            "subtype_id",
                        ],
                    )
                    if msg_ids
                    else []
                )

                att_ids = _retry(
                    Attachment.search,
                    [("res_model", "=", "helpdesk.ticket"), ("res_id", "=", t["id"])],
                )
                attachments_meta_out = []
                new_media_attachments = []
                if att_ids:
                    atts_meta = _retry(
                        Attachment.read, att_ids, ["id", "name", "mimetype", "file_size"]
                    )
                    for a in atts_meta:
                        mimetype = a.get("mimetype") or ""
                        is_media = mimetype.startswith("image/") or mimetype.startswith("video/")
                        attachments_meta_out.append(
                            {
                                "id": a["id"],
                                "nombre": a["name"],
                                "mimetype": mimetype,
                                "tamano_bytes": a["file_size"],
                                "es_imagen_o_video": is_media,
                            }
                        )
                        if is_media and a["id"] not in known_attachments:
                            new_media_attachments.append(a)

                ticket_raw = dict(t)
                ticket_raw["tag_names"] = [tag_names.get(tid) for tid in t["tag_ids"]]
                ticket_raw["messages_raw"] = messages
                ticket_raw["attachments_meta"] = attachments_meta_out

                cur.execute(
                    """
                    INSERT INTO knowledge_mining.odoo_ticket_mining_raw
                        (odoo_ticket_id, ticket_ref, source_odoo_config, raw_data)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (odoo_ticket_id, fetched_at) DO NOTHING
                    RETURNING id
                    """,
                    (
                        t["id"],
                        t["ticket_ref"],
                        os.environ.get("DOPPLER_CONFIG", "unknown"),
                        Jsonb(json.loads(json.dumps(ticket_raw, default=str))),
                    ),
                )
                row = cur.fetchone()
                if row is None:
                    continue
                ticket_mining_id = row[0]

                for a_meta in new_media_attachments:
                    full = _retry(Attachment.read, [a_meta["id"]], ["datas"])[0]
                    content = base64.b64decode(full["datas"]) if full["datas"] else None
                    cur.execute(
                        """
                        INSERT INTO knowledge_mining.odoo_ticket_attachment
                            (ticket_mining_id, odoo_attachment_id, nombre, mimetype,
                             tamano_bytes, es_imagen_o_video, contenido)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            ticket_mining_id,
                            a_meta["id"],
                            a_meta["name"],
                            a_meta["mimetype"],
                            a_meta["file_size"],
                            True,
                            content,
                        ),
                    )
                    known_attachments.add(a_meta["id"])
                    new_attachments_count += 1

        _set_watermark(conn, run_started_at)
        conn.commit()

        summary = {
            "tickets_sincronizados": len(tickets),
            "adjuntos_nuevos": new_attachments_count,
            "watermark": run_started_at,
        }
        logger.info("job=%s completado %s", JOB_NAME, summary)
        return summary
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
