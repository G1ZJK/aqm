"""Tests for the configuration loader (Task 1)."""

from __future__ import annotations

import textwrap

import pytest

from aqm.config import CONFIG_ENV_VAR, load_config, resolve_config_path
from tests.conftest import MINIMAL_VALID_CONFIG


def test_valid_config_parses(write_config):
    path = write_config(MINIMAL_VALID_CONFIG)
    cfg = load_config(path)
    assert cfg.device.device_id == "bf1234567890abcdef"
    assert cfg.device.ip == "192.168.1.50"
    assert cfg.device.version == 3.3
    assert cfg.device.dps_map["2"] == "pm25"
    assert cfg.device.scaling["temperature"] == 0.1
    assert cfg.mongo.database == "air_quality_test"
    # Defaults applied when sections omitted.
    assert cfg.web.port == 8000
    assert cfg.rollup.interval_minutes == 60
    assert cfg.aqi.method == "us_epa"


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "does-not-exist.yaml")


def test_missing_required_device_field_errors(write_config):
    content = textwrap.dedent(
        """
        device:
          device_id: "abc"
          ip: "192.168.1.50"
        """
    )  # local_key missing
    path = write_config(content)
    with pytest.raises(ValueError) as excinfo:
        load_config(path)
    assert "local_key" in str(excinfo.value)


def test_invalid_dps_target_errors(write_config):
    content = textwrap.dedent(
        """
        device:
          device_id: "abc"
          local_key: "key"
          ip: "192.168.1.50"
          dps_map:
            "2": "not_a_parameter"
        """
    )
    path = write_config(content)
    with pytest.raises(ValueError) as excinfo:
        load_config(path)
    assert "not_a_parameter" in str(excinfo.value)


def test_invalid_threshold_target_errors(write_config):
    content = textwrap.dedent(
        """
        device:
          device_id: "abc"
          local_key: "key"
          ip: "192.168.1.50"
        alerts:
          thresholds:
            bogus_param:
              warn_high: 1
        """
    )
    path = write_config(content)
    with pytest.raises(ValueError) as excinfo:
        load_config(path)
    assert "bogus_param" in str(excinfo.value)


def test_threshold_ordering_validation(write_config):
    content = textwrap.dedent(
        """
        device:
          device_id: "abc"
          local_key: "key"
          ip: "192.168.1.50"
        alerts:
          thresholds:
            pm25:
              warn_high: 50
              critical_high: 10
        """
    )
    path = write_config(content)
    with pytest.raises(ValueError) as excinfo:
        load_config(path)
    assert "critical_high" in str(excinfo.value)


def test_invalid_port_errors(write_config):
    content = textwrap.dedent(
        """
        device:
          device_id: "abc"
          local_key: "key"
          ip: "192.168.1.50"
        web:
          port: 99999
        """
    )
    path = write_config(content)
    with pytest.raises(ValueError):
        load_config(path)


def test_redacted_masks_secrets(write_config):
    path = write_config(MINIMAL_VALID_CONFIG)
    cfg = load_config(path)
    red = cfg.redacted()
    assert red["device"]["local_key"] == "***REDACTED***"
    assert "secretkey" not in str(red)
    assert red["device"]["device_id"].startswith("bf12")
    assert red["device"]["device_id"].endswith("cdef")
    # Mongo credentials masked.
    assert "user:pass" not in red["mongo"]["uri"]
    assert "***:***" in red["mongo"]["uri"]


def test_resolve_config_path_env(monkeypatch, tmp_path):
    target = tmp_path / "custom.yaml"
    monkeypatch.setenv(CONFIG_ENV_VAR, str(target))
    assert resolve_config_path() == target
    # Explicit arg overrides env.
    other = tmp_path / "explicit.yaml"
    assert resolve_config_path(other) == other


def test_top_level_must_be_mapping(write_config):
    path = write_config("- just\n- a\n- list\n")
    with pytest.raises(ValueError):
        load_config(path)


def test_mongo_uri_env_override(write_config, monkeypatch):
    from aqm.config import MONGO_DB_ENV_VAR, MONGO_URI_ENV_VAR

    path = write_config(MINIMAL_VALID_CONFIG)
    monkeypatch.setenv(MONGO_URI_ENV_VAR, "mongodb://mongo:27017")
    monkeypatch.setenv(MONGO_DB_ENV_VAR, "overridden_db")
    cfg = load_config(path)
    assert cfg.mongo.uri == "mongodb://mongo:27017"
    assert cfg.mongo.database == "overridden_db"


def test_mongo_env_override_absent_uses_file(write_config, monkeypatch):
    from aqm.config import MONGO_DB_ENV_VAR, MONGO_URI_ENV_VAR

    monkeypatch.delenv(MONGO_URI_ENV_VAR, raising=False)
    monkeypatch.delenv(MONGO_DB_ENV_VAR, raising=False)
    path = write_config(MINIMAL_VALID_CONFIG)
    cfg = load_config(path)
    # Falls back to the file's values.
    assert cfg.mongo.database == "air_quality_test"
