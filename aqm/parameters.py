"""Canonical air-quality parameter definitions.

These 11 parameters are the stable internal vocabulary of the application. The
mapping from device DPS ids to these names lives in config (``device.dps_map``)
because it varies by firmware and must be discovered live from the device.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParameterSpec:
    """Metadata for a single air-quality parameter."""

    key: str
    label: str
    unit: str


# Ten measured parameters plus one computed (AQI).
PARAMETERS: tuple[ParameterSpec, ...] = (
    ParameterSpec("co2", "CO\u2082", "ppm"),
    ParameterSpec("co", "CO", "ppm"),
    ParameterSpec("tvoc", "TVOC", "mg/m\u00b3"),
    ParameterSpec("hcho", "Formaldehyde", "mg/m\u00b3"),
    ParameterSpec("pm03", "PM0.3", "pcs/L"),
    ParameterSpec("pm1", "PM1", "\u00b5g/m\u00b3"),
    ParameterSpec("pm25", "PM2.5", "\u00b5g/m\u00b3"),
    ParameterSpec("pm10", "PM10", "\u00b5g/m\u00b3"),
    ParameterSpec("temperature", "Temperature", "\u00b0C"),
    ParameterSpec("humidity", "Humidity", "%RH"),
    ParameterSpec("aqi", "AQI", "index"),
)

# Keys that are physically measured by the device (everything except computed AQI).
MEASURED_KEYS: tuple[str, ...] = tuple(p.key for p in PARAMETERS if p.key != "aqi")

# All parameter keys, including computed.
ALL_KEYS: tuple[str, ...] = tuple(p.key for p in PARAMETERS)

PARAMETERS_BY_KEY: dict[str, ParameterSpec] = {p.key: p for p in PARAMETERS}


def unit_for(key: str) -> str:
    """Return the unit string for a parameter key, or empty string if unknown."""
    spec = PARAMETERS_BY_KEY.get(key)
    return spec.unit if spec else ""
