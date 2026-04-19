"""
Centralized configuration. All thresholds and constants from the original app.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ── Database (PostgreSQL) ─────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql://dbinfra:dbinfra@localhost:5432/db_infra_ops",
        description="PostgreSQL connection string (overridden via DATABASE_URL env var)",
    )
    db_pool_size: int = Field(default=5, description="SQLAlchemy connection pool size")
    db_pool_max_overflow: int = Field(default=10, description="Max overflow connections")
    db_pool_recycle: int = Field(default=300, description="Recycle connections after N seconds")

    # ── Zabbix defaults (overridden at runtime via API) ───────────────────
    zabbix_url: str = ""
    zabbix_token: str = ""
    zabbix_group: str = "PAASDB"
    zabbix_verify_tls: bool = Field(
        default=False,
        description="Verify TLS certificates for Zabbix API calls",
    )
    days_back: int = 30

    # ── API timeouts (per-request, not total — retries multiply this) ────
    api_timeout_short: int = 30
    api_timeout_medium: int = 60
    api_timeout_long: int = 120

    # ── Fetch reliability ─────────────────────────────────────────────────
    # Max time a fetch can sit in 'running' before stale detection expires it.
    # Must exceed the realistic worst-case fetch duration (~25 min with reduced timeouts).
    fetch_stale_timeout_seconds: int = 3600

    # Per-stage ceiling in the parallel ThreadPoolExecutor (fetch_all).
    # If a single stage exceeds this, it's killed and the fetch continues with partial data.
    fetch_stage_timeout_seconds: int = 600

    # ── Processing limits ─────────────────────────────────────────────────
    trend_chunk_size: int = 200

    # ── Scheduler ─────────────────────────────────────────────────────────
    fetch_interval_hours: int = 24

    # ── CORS ──────────────────────────────────────────────────────────────
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:8090",
        description="Comma-separated list of allowed CORS origins",
    )

    # ── Risk thresholds (from original app, centralized here) ─────────────
    system_drive_critical_pct: float = 95.0
    system_drive_warning_pct: float = 90.0
    system_drive_low_free_gb: float = 2.0
    db_drive_critical_pct: float = 95.0
    db_drive_warning_pct: float = 90.0
    cpu_runway_critical_days: int = 30
    db_growth_warning_gb: float = 5.0
    alert_storm_threshold: int = 10
    underutil_load_pct: float = 10.0
    silent_fail_load_pct: float = 75.0
    overload_pct: float = 75.0
    zombie_load_pct: float = 15.0
    zombie_min_vcpu: int = 8
    forecast_target_pct: float = 95.0


settings = Settings()
