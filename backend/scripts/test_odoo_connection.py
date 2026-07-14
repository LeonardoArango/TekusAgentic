"""Prueba de conexión a Odoo — solo lectura, no crea ni modifica nada.

Uso (con Doppler, sin escribir secretos a disco):
    doppler run -- uv run python scripts/test_odoo_connection.py

No imprime ningún valor de ODOO_URL/ODOO_USERNAME/ODOO_PASSWORD — solo
confirma si la autenticación funcionó y con qué versión de Odoo se conectó.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connectors.odoo_common import OdooConnection  # noqa: E402


def main() -> None:
    try:
        connection = OdooConnection()
    except KeyError as exc:
        print(
            f"FALTA variable de entorno: {exc} — revisa que Doppler tenga las 4 (ODOO_URL, "
            "ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD) en el config que estás usando."
        )
        raise SystemExit(1) from exc
    except Exception as exc:  # noqa: BLE001
        print(f"FALLÓ la conexión/login: {type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

    version = connection.env.version
    uid = connection.env.env.uid
    print(f"OK — autenticado contra Odoo {version} como uid={uid}")

    try:
        partner_model = connection.env.env["res.partner"]
        count = connection.call_with_retry(partner_model.search_count, [])
        print(f"OK — acceso de lectura a res.partner confirmado ({count} registros visibles).")
    except Exception as exc:  # noqa: BLE001
        print(
            f"Conexión OK, pero sin acceso de lectura a res.partner: {type(exc).__name__}: {exc}. "
            "Puede ser normal si el usuario de integración no tiene ese permiso — no es un error "
            "de conexión."
        )


if __name__ == "__main__":
    main()
