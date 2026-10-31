"""Configuración de despliegue (12-factor, secretos fuera del código)."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SCHEMA_DIR = (
    Path(__file__).resolve().parents[3] / "schemas" / "witsml" / "1.4.1.1"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SENTINEL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    database_url: str = (
        "postgresql+asyncpg://sentinel:sentinel_dev@localhost:5432/sentinel"
    )
    admin_origin: str = "http://localhost:3000"
    public_base_url: str = "http://localhost:8000"

    # TLS: el adaptador WMLS rechaza HTTP cuando require_https es true.
    require_https: bool = True
    trust_forwarded_proto: bool = True
    cookie_secure: bool = True
    session_cookie_name: str = "sentinel_session"
    csrf_cookie_name: str = "sentinel_csrf"

    schema_dir: Path | None = Field(default=None)

    smtp_host: str = "smtp.zoho.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@example.com"
    smtp_starttls: bool = True
    smtp_timeout_seconds: int = 20

    wpctt_dir: Path | None = None
    log_level: str = "INFO"
    mail_worker_interval_seconds: int = 5

    @property
    def resolved_schema_dir(self) -> Path | None:
        return self.schema_dir or (DEFAULT_SCHEMA_DIR if DEFAULT_SCHEMA_DIR.is_dir() else None)

    @property
    def is_development(self) -> bool:
        return self.env.lower() in ("development", "dev", "test")
