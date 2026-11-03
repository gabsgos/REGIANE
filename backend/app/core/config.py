from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ABEL_",
        extra="ignore",
    )

    environment: str = "development"
    app_name: str = "ABEL Clinica"
    app_version: str = "1.0.0+build.60"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    business_timezone: str = "America/Sao_Paulo"
    database_url: str | None = None
    session_hours: int = 8
    cookie_secure: bool = False
    login_max_attempts: int = 5
    login_window_seconds: int = 300
    document_storage_path: str = "data/documents"
    document_max_bytes: int = 10 * 1024 * 1024
    log_path: str = "data/logs/abel.jsonl"
    log_max_bytes: int = 5 * 1024 * 1024
    log_backup_count: int = 5
    mysql_bin_path: str = "C:/Program Files/MySQL/MySQL Server 8.4/bin"
    backup_directory: str = "backups/system"
    backup_retention_count: int = 14
    authorization_mode: str = "COMPAT"
    authorization_admin_mode: str | None = None
    authorization_finance_mode: str | None = None
    authorization_clinical_mode: str | None = None
    authorization_documents_mode: str | None = None
    authorization_reports_mode: str | None = None
    step_up_minutes: int = 15


@lru_cache
def get_settings() -> Settings:
    return Settings()
