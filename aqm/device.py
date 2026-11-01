"""Device connection and DPS discovery.

The ZN-MT29 is a Tuya WiFi device read over the LAN with ``tinytuya``. This
module wraps connection setup, a raw status dump for discovering the DPS
(datapoint) ids, and the pure function that maps a raw DPS payload to canonical
parameter keys using ``device.dps_map`` from config.

Obtaining device_id + local_key (one-time):
    1. Create a free Tuya IoT project at https://iot.tuya.com and link your
       Smart Life / Tuya app account to it.
    2. Run ``python -m tinytuya wizard`` which writes ``devices.json`` with the
       device id and local key for each device.
    3. Find the device IP with ``python -m tinytuya scan`` or your router.
"""

from __future__ import annotations

import logging
from typing import Any

from .config import DeviceConfig

logger = logging.getLogger("aqm.device")


def map_dps_to_parameters(
    raw_dps: dict[str, Any], dps_map: dict[str, str]
) -> dict[str, float]:
    """Map a raw DPS payload to canonical parameter values.

    ``raw_dps`` is the ``dps`` dict returned by tinytuya ``status()``, keyed by
    DPS id (as string or int). ``dps_map`` maps DPS id (string) to a canonical
    parameter key. Only numeric values for mapped ids are returned; unmapped or
    non-numeric datapoints are ignored.
    """
    result: dict[str, float] = {}
    for dps_id, value in raw_dps.items():
        key = dps_map.get(str(dps_id))
        if key is None:
            continue
        if isinstance(value, bool):
            # bools are ints in Python; skip to avoid treating on/off as 0/1 data
            continue
        if isinstance(value, (int, float)):
            result[key] = float(value)
        else:
            # Some firmwares send numeric strings.
            try:
                result[key] = float(value)
            except (TypeError, ValueError):
                logger.debug("Skipping non-numeric DPS %s=%r", dps_id, value)
    return result


def build_device(cfg: DeviceConfig):  # pragma: no cover - thin tinytuya wrapper
    """Construct a tinytuya device object from config.

    Imported lazily so unit tests and non-device code paths don't require the
    tinytuya runtime/network.
    """
    import tinytuya

    device = tinytuya.Device(
        dev_id=cfg.device_id,
        address=cfg.ip,
        local_key=cfg.local_key,
        version=cfg.version,
    )
    device.set_socketTimeout(cfg.connection_timeout_seconds)
    device.set_socketPersistent(True)
    return device


def fetch_status(cfg: DeviceConfig) -> dict[str, Any]:  # pragma: no cover - needs device
    """Poll the device once and return the raw status dict (incl. 'dps')."""
    device = build_device(cfg)
    status = device.status()
    return status or {}
