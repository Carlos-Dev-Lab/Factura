"""Configuración centralizada, leída de variables de entorno."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Factura"
    environment: str = Field("production", pattern="^(development|production|test)$")

    database_url: str = "postgresql+psycopg://factura:factura@db:5432/factura"

    secret_key: str = Field(min_length=32)
    access_token_minutes: int = 60 * 12
    cookie_secure: bool = True

    allow_registration: bool = False
    login_max_attempts: int = 5
    login_window_seconds: int = 300

    storage_dir: Path = Path("/data/uploads")
    max_upload_mb: int = 15
    ocr_languages: str = "spa+eng"

    # Avisos. Sin token, Telegram queda desactivado; las notificaciones push funcionan solas.
    telegram_bot_token: str = ""
    # Dirección pública de la app (https://...), para los enlaces de las notificaciones.
    public_url: str = ""
    # Respaldos automáticos (los genera el contenedor "db" con backup/backup.sh; el backend solo los lista).
    backups_dir: Path = Path("/backups")
    trash_days: int = 30
    # Nombres con los que se puede entrar a la app, separados por coma (ej. "mi-pc.tu-red.ts.net").
    # Vacío = cualquiera. Con valor, un pedido con otro nombre se rechaza: así una página maliciosa
    # no puede hablarle a tu servidor haciéndose pasar por otro dominio (DNS rebinding).
    allowed_hosts: str = ""

    # Ingreso con Google (OAuth). Sin ID o sin secreto, el botón no aparece.
    google_client_id: str = ""
    google_client_secret: str = ""

    # Avisos por email: una cuenta del servidor (por ejemplo Gmail con contraseña de aplicación).
    # Sin usuario o sin contraseña, el canal de email queda desactivado.
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)

    @property
    def allowed_host_list(self) -> list[str]:
        hosts = [h.strip().lower() for h in self.allowed_hosts.split(",") if h.strip()]
        # El chequeo de salud de Docker y nginx entran por estos nombres.
        return [*hosts, "localhost", "127.0.0.1", "backend"] if hosts else []

    @field_validator("secret_key")
    @classmethod
    def _reject_placeholder(cls, v: str) -> str:
        if v.lower().startswith("cambiar"):
            raise ValueError("SECRET_KEY no fue configurada: generá una clave aleatoria")
        return v

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
