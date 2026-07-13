from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración vía variables de entorno. Ver `.env.example` en la raíz."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    entra_tenant_id: str = ""
    entra_client_id: str = ""
    entra_client_secret: str = ""


settings = Settings()
