"""Normalized air-quality reading model and the raw->Reading pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from .aqi import aqi_from_pm
from .device import map_dps_to_parameters
from .parameters import ALL_KEYS


class Reading(BaseModel):
    """A single normalized reading: timestamp plus per-parameter values.

    Values are stored in a ``values`` dict keyed by canonical parameter key.
    Missing parameters are simply absent (not zero).
    """

    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    values: dict[str, float] = Field(default_factory=dict)

    def to_storage_doc(self, device_id: str) -> dict[str, Any]:
        """Shape for MongoDB time-series insertion."""
        return {"ts": self.ts, "meta": {"device": device_id}, "values": self.values}


def apply_scaling(values: dict[str, float], scaling: dict[str, float]) -> dict[str, float]:
    """Return a new dict with per-parameter multipliers applied."""
    out = dict(values)
    for key, factor in scaling.items():
        if key in out:
            out[key] = out[key] * factor
    return out


def normalize(
    raw_dps: dict[str, Any],
    dps_map: dict[str, str],
    scaling: dict[str, float] | None = None,
    *,
    ts: datetime | None = None,
    compute_aqi: bool = True,
    aqi_method: str = "us_epa",
) -> Reading:
    """Convert a raw DPS payload into a normalized :class:`Reading`.

    Steps: map DPS ids -> parameters, apply scaling, then (optionally) compute
    the AQI from PM2.5/PM10 and add it as the ``aqi`` parameter. ``aqi_method``
    selects the AQI standard (``us_epa`` or ``china_mee``).
    """
    mapped = map_dps_to_parameters(raw_dps, dps_map)
    scaled = apply_scaling(mapped, scaling or {})

    if compute_aqi:
        aqi = aqi_from_pm(scaled.get("pm25"), scaled.get("pm10"), aqi_method)
        if aqi is not None:
            scaled["aqi"] = float(aqi)

    # Keep only canonical keys (defensive; map already restricts measured keys).
    clean = {k: v for k, v in scaled.items() if k in ALL_KEYS}
    return Reading(ts=ts or datetime.now(UTC), values=clean)
