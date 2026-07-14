from fastapi import APIRouter, Depends

from api.platform.auth import UsuarioAutenticado, get_current_user

router = APIRouter(prefix="/api/platform", tags=["platform"])


@router.get("/me")
def me(
    usuario: UsuarioAutenticado = Depends(get_current_user),  # noqa: B008
) -> dict[str, str | None]:
    """Endpoint de ejemplo protegido por SSO — confirma que el token es válido."""
    return {"oid": usuario.oid, "nombre": usuario.nombre, "correo": usuario.correo}
