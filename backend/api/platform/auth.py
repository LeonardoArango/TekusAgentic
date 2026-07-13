"""Validación de tokens de Entra ID (SSO Microsoft 365) para la plataforma web.

Sin login local: todo acceso pasa por SSO M365 (ver CLAUDE.md, sección
Seguridad). El frontend Angular (MSAL) adjunta un Bearer token en cada
request; aquí solo se valida contra las llaves públicas (JWKS) de Entra ID
— nunca se emiten ni se guardan contraseñas.

Single-tenant: solo se aceptan tokens emitidos por el tenant de Tekus
(`ENTRA_TENANT_ID`), no cualquier cuenta M365.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from config import settings

_bearer_scheme = HTTPBearer(auto_error=True)


def _jwks_url() -> str:
    return f"https://login.microsoftonline.com/{settings.entra_tenant_id}" "/discovery/v2.0/keys"


def _issuer() -> str:
    return f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0"


# El cliente JWKS cachea las llaves públicas y las refresca automáticamente
# cuando encuentra un `kid` desconocido — no se reimplementa ese manejo acá.
_jwk_client = PyJWKClient(_jwks_url())


@dataclass
class UsuarioAutenticado:
    """Claims mínimos del usuario autenticado, extraídos del token de Entra ID."""

    oid: str
    nombre: str | None
    correo: str | None


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),  # noqa: B008
) -> UsuarioAutenticado:
    """Dependency de FastAPI: valida el Bearer token y devuelve el usuario.

    Usar en cualquier endpoint de `api/platform/` que toque datos de cliente
    o configuración — nunca dejar un endpoint de la plataforma sin este
    Depends.
    """
    token = credentials.credentials

    try:
        signing_key = _jwk_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.entra_client_id,
            issuer=_issuer(),
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token de Entra ID inválido: {exc}",
        ) from exc

    return UsuarioAutenticado(
        oid=claims["oid"],
        nombre=claims.get("name"),
        correo=claims.get("preferred_username"),
    )
