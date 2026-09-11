"""
config.py - Configuracion centralizada via Pydantic Settings.
Lee .env automaticamente. Nunca hardcodear credenciales.
"""
import os
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # PrestaShop MySQL
    ps_mysql_host: str = "localhost"
    ps_mysql_port: int = 3306
    ps_mysql_user: str = ""
    ps_mysql_password: str = ""
    ps_mysql_db: str = "prestashop_example"
    ps_mysql_pool_size: int = 5
    ps_mysql_is_test: bool = True

    # Ambar SQL Server
    ambar_sqlserver_host: str = "localhost"
    ambar_sqlserver_instance: str | None = None
    ambar_sqlserver_port: str | None = "1433"
    ambar_sqlserver_user: str = ""
    ambar_sqlserver_password: str = ""
    ambar_sqlserver_db: str = "erp_example"
    ambar_driver: str = "ODBC Driver 17 for SQL Server"
    ambar_is_test: bool = True

    # AppB2B MySQL
    b2b_mysql_host: str = "localhost"
    b2b_mysql_port: int = 3306
    b2b_mysql_user: str = ""
    b2b_mysql_password: str = ""
    b2b_mysql_db: str = "b2b_example"
    b2b_mysql_pool_size: int = 3

    # App
    app_secret_key: str = ""
    app_debug: bool = False
    app_port: int = 8000
    app_read_only: bool = True

    # Negocio
    ps_admin_url: str = ""
    ps_public_url: str = "https://shop.example.invalid"
    ps_admin_token: str = ""
    ps_state_bridge_url: str = ""
    ps_state_bridge_token: str = ""
    ps_state_bridge_timeout_sec: int = 8

    # SMTP correo cliente pedido
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    email_logo_url: str = ""
    email_company_name: str = "Empresa de ejemplo"
    email_site_url: str = "https://shop.example.invalid"
    email_support_email: str = "support@example.invalid"

    @field_validator("ambar_sqlserver_port", mode="before")
    @classmethod
    def _normalizar_port_sqlserver(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("ambar_sqlserver_instance", mode="before")
    @classmethod
    def _normalizar_instancia_sqlserver(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @property
    def ambar_server_target(self) -> str:
        host = self.ambar_sqlserver_host.strip()
        if self.ambar_sqlserver_instance:
            host = f"{host}\\{self.ambar_sqlserver_instance}"
        if self.ambar_sqlserver_port:
            return f"{host},{self.ambar_sqlserver_port}"
        return host

    @property
    def ambar_connection_string(self) -> str:
        base = (
            f"DRIVER={{{self.ambar_driver}}};"
            f"SERVER={self.ambar_server_target};"
            f"DATABASE={self.ambar_sqlserver_db};"
            f"UID={self.ambar_sqlserver_user};"
            f"PWD={self.ambar_sqlserver_password};"
        )
        # Algunos drivers legacy (ej: "SQL Server") no soportan Encrypt/TrustServerCertificate.
        if "odbc driver" in self.ambar_driver.lower():
            return base + "Encrypt=no;TrustServerCertificate=yes;"
        return base

    @property
    def env_file_active(self) -> str:
        return os.getenv("APP_ENV_FILE", ".env")

    @property
    def env_profile_from_file(self) -> str | None:
        base = os.path.basename(self.env_file_active).lower()
        if base == ".env.test":
            return "test"
        if base == ".env.prod":
            return "produccion"
        return None

    @property
    def prestashop_env_label(self) -> str:
        # Prioridad 1: perfil explicito por archivo de entorno.
        profile = self.env_profile_from_file
        if profile:
            return profile
        # Prioridad 2: flag especifico de PrestaShop.
        return "test" if self.ps_mysql_is_test else "produccion"

    @property
    def ambar_env_label(self) -> str:
        # Prioridad 1: perfil explicito por archivo de entorno.
        profile = self.env_profile_from_file
        if profile:
            return profile
        # Prioridad 2: flag especifico de Ambar.
        return "test" if self.ambar_is_test else "produccion"

    @property
    def is_any_production(self) -> bool:
        return (not self.ps_mysql_is_test) or (not self.ambar_is_test)

    @property
    def environment_context(self) -> dict:
        env_file = self.env_file_active
        profile = self.env_profile_from_file
        return {
            "prestashop": {
                "env": self.prestashop_env_label,
                "host": self.ps_mysql_host,
                "db": self.ps_mysql_db,
            },
            "ambar": {
                "env": self.ambar_env_label,
                "server": self.ambar_server_target,
                "db": self.ambar_sqlserver_db,
            },
            "read_only": self.app_read_only,
            "is_any_production": self.is_any_production,
            "config_source": {
                "app_env_file_var": env_file,
                "resolved_path": os.path.basename(env_file),
                "profile_from_file": profile or "none",
                "classification_rule": (
                    "env_file_profile"
                    if profile
                    else "per_system_flags"
                ),
            },
        }


@lru_cache
def get_settings() -> Settings:
    """Singleton de configuracion (se cachea tras la primera llamada)."""
    env_file = os.getenv("APP_ENV_FILE", ".env")
    return Settings(_env_file=env_file)
