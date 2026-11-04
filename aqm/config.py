"""Typed, validated application configuration.

Configuration is loaded from a YAML file (default: ``config.yaml`` in the
current working directory, override with the ``AQM_CONFIG`` environment
variable). Secrets such as the device local key live only in this file, which
is git-ignored. ``config.example.yaml`` documents every field.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from .parameters import ALL_KEYS, MEASURED_KEYS

DEFAULT_CONFIG_PATH = "config.yaml"
CONFIG_ENV_VAR = "AQM_CONFIG"
MONGO_URI_ENV_VAR = "AQM_MONGO_URI"
MONGO_DB_ENV_VAR = "AQM_MONGO_DATABASE"

VALID_BUCKETS = ("minute", "hourly", "daily", "weekly", "monthly")


class DeviceConfig(BaseModel):
    """ZN-MT29 Tuya device connection settings (read over the LAN)."""

    device_id: str = Field(..., min_length=1, description="Tuya device id")
    local_key: str = Field(..., min_length=1, description="Tuya local key (secret)")
    ip: str = Field(..., min_length=1, description="Device LAN IP address")
    version: float = Field(3.3, description="Tuya protocol version, e.g. 3.3 / 3.4 / 3.5")
    poll_interval_seconds: float = Field(
        30.0, gt=0, description="Seconds between device polls"
    )
    connection_timeout_seconds: float = Field(
        5.0, gt=0, description="Per-request socket timeout"
    )
    use_monitor_fallback: bool = Field(
        True, description="Fall back to tinytuya push/monitor mode if polling returns no data"
    )
    # Maps device DPS id (as string) -> canonical parameter key.
    # Discovered live via the DPS discovery utility (Task 3).
    dps_map: dict[str, str] = Field(default_factory=dict)
    # Optional per-parameter multiplier applied to raw values (e.g. temp 0.1).
    scaling: dict[str, float] = Field(default_factory=dict)

    @field_validator("dps_map")
    @classmethod
    def _validate_dps_targets(cls, value: dict[str, str]) -> dict[str, str]:
        for dps_id, param in value.items():
            if param not in MEASURED_KEYS:
                raise ValueError(
                    f"dps_map[{dps_id!r}] = {param!r} is not a measured parameter; "
                    f"valid keys: {', '.join(MEASURED_KEYS)}"
                )
        return value

    @field_validator("scaling")
    @classmethod
    def _validate_scaling_targets(cls, value: dict[str, float]) -> dict[str, float]:
        for param in value:
            if param not in MEASURED_KEYS:
                raise ValueError(
                    f"scaling[{param!r}] is not a measured parameter; "
                    f"valid keys: {', '.join(MEASURED_KEYS)}"
                )
        return value


class MongoConfig(BaseModel):
    """MongoDB connection and collection settings."""

    uri: str = Field("mongodb://localhost:27017", min_length=1)
    database: str = Field("air_quality", min_length=1)
    raw_collection: str = Field("readings", min_length=1)
    rollup_daily_collection: str = Field("rollup_daily", min_length=1)
    rollup_weekly_collection: str = Field("rollup_weekly", min_length=1)
    rollup_monthly_collection: str = Field("rollup_monthly", min_length=1)
    alerts_collection: str = Field("alerts", min_length=1)
    # Raw time-series retention in seconds (TTL). Default 30 days.
    raw_retention_seconds: int = Field(30 * 24 * 3600, gt=0)
    server_selection_timeout_ms: int = Field(5000, gt=0)


class RollupConfig(BaseModel):
    """Scheduled rollup job settings."""

    enabled: bool = True
    # Cron-like interval expressed as minutes between rollup runs.
    interval_minutes: int = Field(60, gt=0)
    # On startup, backfill this many days of rollups if missing.
    backfill_days: int = Field(7, ge=0)


class ThresholdLevel(BaseModel):
    """A warn/critical threshold pair for one parameter.

    A bound of ``None`` disables that direction. ``clear_margin`` implements
    hysteresis: once active, the alert only clears after the value moves back
    past the threshold by this margin.
    """

    warn_high: float | None = None
    critical_high: float | None = None
    warn_low: float | None = None
    critical_low: float | None = None
    clear_margin: float = Field(0.0, ge=0)

    @model_validator(mode="after")
    def _check_ordering(self) -> ThresholdLevel:
        if (
            self.warn_high is not None
            and self.critical_high is not None
            and self.critical_high < self.warn_high
        ):
            raise ValueError("critical_high must be >= warn_high")
        if (
            self.warn_low is not None
            and self.critical_low is not None
            and self.critical_low > self.warn_low
        ):
            raise ValueError("critical_low must be <= warn_low")
        return self


class AlertsConfig(BaseModel):
    """Alerts engine settings: per-parameter thresholds."""

    enabled: bool = True
    thresholds: dict[str, ThresholdLevel] = Field(default_factory=dict)

    @field_validator("thresholds")
    @classmethod
    def _validate_threshold_targets(
        cls, value: dict[str, ThresholdLevel]
    ) -> dict[str, ThresholdLevel]:
        for param in value:
            if param not in ALL_KEYS:
                raise ValueError(
                    f"thresholds[{param!r}] is not a known parameter; "
                    f"valid keys: {', '.join(ALL_KEYS)}"
                )
        return value


class WebConfig(BaseModel):
    """FastAPI web server settings."""

    host: str = Field("0.0.0.0", min_length=1)
    port: int = Field(8000, gt=0, lt=65536)
    title: str = "Air Quality Monitor"


class AQIConfig(BaseModel):
    """AQI computation settings."""

    method: str = Field("us_epa", description="AQI calculation method")

    @field_validator("method")
    @classmethod
    def _validate_method(cls, value: str) -> str:
        valid = ("us_epa", "china_mee")
        if value not in valid:
            raise ValueError(
                f"unsupported AQI method {value!r}; valid: {', '.join(valid)}"
            )
        return value


class AppConfig(BaseModel):
    """Root application configuration."""

    device: DeviceConfig
    mongo: MongoConfig = Field(default_factory=MongoConfig)
    rollup: RollupConfig = Field(default_factory=RollupConfig)
    alerts: AlertsConfig = Field(default_factory=AlertsConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    aqi: AQIConfig = Field(default_factory=AQIConfig)

    def redacted(self) -> dict[str, Any]:
        """Return a dict of the config with secrets masked, safe for logging."""
        data = self.model_dump()
        if data.get("device", {}).get("local_key"):
            data["device"]["local_key"] = "***REDACTED***"
        if data.get("device", {}).get("device_id"):
            did = data["device"]["device_id"]
            data["device"]["device_id"] = (
                did[:4] + "..." + did[-4:] if len(did) > 8 else "***"
            )
        # Mask any credentials embedded in a Mongo URI.
        uri = data.get("mongo", {}).get("uri", "")
        if "@" in uri and "://" in uri:
            scheme, rest = uri.split("://", 1)
            if "@" in rest:
                _creds, host = rest.split("@", 1)
                data["mongo"]["uri"] = f"{scheme}://***:***@{host}"
        return data


def resolve_config_path(path: str | os.PathLike[str] | None = None) -> Path:
    """Resolve which config file to load, honoring the ``AQM_CONFIG`` env var."""
    if path is not None:
        return Path(path)
    env = os.environ.get(CONFIG_ENV_VAR)
    if env:
        return Path(env)
    return Path(DEFAULT_CONFIG_PATH)


def load_config(path: str | os.PathLike[str] | None = None) -> AppConfig:
    """Load and validate configuration from YAML.

    Raises ``FileNotFoundError`` if the file is missing and ``ValueError`` with
    a readable message if validation fails.
    """
    config_path = resolve_config_path(path)
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Config file not found: {config_path}. "
            f"Copy config.example.yaml to {DEFAULT_CONFIG_PATH} and fill it in."
        )
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Config file {config_path} must contain a YAML mapping at the top level")
    _apply_env_overrides(raw)
    return AppConfig.model_validate(raw)


def _apply_env_overrides(raw: dict) -> None:
    """Override selected config values from environment variables (in place).

    This lets the same ``config.yaml`` work bare-metal and in Docker: compose
    sets ``AQM_MONGO_URI`` to point at the ``mongo`` service without editing the
    file. Environment values take precedence over the file.
    """
    uri = os.environ.get(MONGO_URI_ENV_VAR)
    database = os.environ.get(MONGO_DB_ENV_VAR)
    if uri or database:
        mongo = raw.setdefault("mongo", {})
        if not isinstance(mongo, dict):
            raise ValueError("'mongo' section must be a mapping to apply env overrides")
        if uri:
            mongo["uri"] = uri
        if database:
            mongo["database"] = database
