"""Shared pytest fixtures."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

MINIMAL_VALID_CONFIG = textwrap.dedent(
    """
    device:
      device_id: "bf1234567890abcdef"
      local_key: "secretkey1234567"
      ip: "192.168.1.50"
      version: 3.3
      dps_map:
        "2": "pm25"
        "18": "pm10"
      scaling:
        temperature: 0.1
    mongo:
      uri: "mongodb://user:pass@localhost:27017"
      database: "air_quality_test"
    alerts:
      thresholds:
        pm25:
          warn_high: 35.5
          critical_high: 55.5
          clear_margin: 2.0
    """
)


@pytest.fixture()
def write_config(tmp_path: Path):
    """Return a helper that writes YAML to a temp file and returns its path."""

    def _write(content: str, name: str = "config.yaml") -> Path:
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        return path

    return _write
