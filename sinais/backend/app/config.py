"""Typed environment-based application settings."""

import os
from dataclasses import dataclass


def _positive_int(name: str, default: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    grafana_db_user: str
    grafana_db_password: str
    db_pool_min_size: int
    db_pool_max_size: int
    alert_poll_seconds: int
    spo2_alert_seconds: int
    heart_rate_alert_seconds: int
    hypotension_alert_seconds: int
    alert_webhook_url: str | None
    randomuser_enabled: bool
    randomuser_api_url: str
    simulator_interval_seconds: float
    api_url: str

    @classmethod
    def from_env(cls) -> "Settings":
        webhook = os.getenv("ALERT_WEBHOOK_URL", "").strip()
        return cls(
            db_host=os.getenv("DB_HOST", "timescaledb"),
            db_port=_positive_int("DB_PORT", 5432),
            db_name=os.getenv("POSTGRES_DB", "vitals"),
            db_user=os.getenv("POSTGRES_USER", "vitals"),
            db_password=os.getenv("POSTGRES_PASSWORD", "local-development-only"),
            grafana_db_user=os.getenv("GRAFANA_DB_USER", "grafana_reader"),
            grafana_db_password=os.getenv(
                "GRAFANA_DB_PASSWORD", "local-development-only"
            ),
            db_pool_min_size=_positive_int("DB_POOL_MIN_SIZE", 2),
            db_pool_max_size=_positive_int("DB_POOL_MAX_SIZE", 20),
            alert_poll_seconds=_positive_int("ALERT_POLL_SECONDS", 10),
            spo2_alert_seconds=_positive_int("SPO2_ALERT_SECONDS", 30),
            heart_rate_alert_seconds=_positive_int("HEART_RATE_ALERT_SECONDS", 60),
            hypotension_alert_seconds=_positive_int("HYPOTENSION_ALERT_SECONDS", 60),
            alert_webhook_url=webhook or None,
            randomuser_enabled=os.getenv("RANDOMUSER_ENABLED", "false").lower()
            in {"1", "true", "yes", "on"},
            randomuser_api_url=os.getenv(
                "RANDOMUSER_API_URL", "https://randomuser.me/api/"
            ),
            simulator_interval_seconds=float(
                os.getenv("SIMULATOR_INTERVAL_SECONDS", "1")
            ),
            api_url=os.getenv("API_URL", "http://api:8000"),
        )

    def __post_init__(self) -> None:
        if self.db_pool_min_size > self.db_pool_max_size:
            raise ValueError("DB_POOL_MIN_SIZE cannot exceed DB_POOL_MAX_SIZE")
        if self.db_user == self.grafana_db_user:
            raise ValueError("Grafana must use a separate read-only database user")
        if self.simulator_interval_seconds <= 0:
            raise ValueError("SIMULATOR_INTERVAL_SECONDS must be positive")

    @property
    def database_kwargs(self) -> dict[str, int | str]:
        return {
            "host": self.db_host,
            "port": self.db_port,
            "database": self.db_name,
            "user": self.db_user,
            "password": self.db_password,
            "min_size": self.db_pool_min_size,
            "max_size": self.db_pool_max_size,
        }
