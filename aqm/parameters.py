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
    description: str = ""


# Ten measured parameters plus one computed (AQI).
PARAMETERS: tuple[ParameterSpec, ...] = (
    ParameterSpec(
        "co2",
        "CO\u2082",
        "ppm",
        "Carbon dioxide. Indoors it tracks ventilation; above ~1000 ppm air "
        "feels stuffy and concentration drops, above ~2000 ppm it is poorly "
        "ventilated.",
    ),
    ParameterSpec(
        "co",
        "CO",
        "ppm",
        "Carbon monoxide, a toxic gas from incomplete combustion. Prolonged "
        "exposure above ~9 ppm is a concern; ~35 ppm and up is dangerous.",
    ),
    ParameterSpec(
        "tvoc",
        "TVOC",
        "mg/m\u00b3",
        "Total volatile organic compounds from paints, cleaners and furnishings. "
        "Lower is better; sustained high levels can cause irritation and headaches.",
    ),
    ParameterSpec(
        "hcho",
        "Formaldehyde",
        "mg/m\u00b3",
        "Formaldehyde (CH\u2082O), a VOC off-gassed by new furniture and finishes. "
        "A known irritant and carcinogen; keep below ~0.1 mg/m\u00b3.",
    ),
    ParameterSpec(
        "pm03",
        "PM0.3",
        "pcs/L",
        "Count of ultrafine particles \u22650.3\u00b5m per litre of air. A raw "
        "particle-count indicator of filtration quality.",
    ),
    ParameterSpec(
        "pm1",
        "PM1",
        "\u00b5g/m\u00b3",
        "Fine particulate matter \u22641\u00b5m. These deep-lung particles come "
        "from combustion and cooking.",
    ),
    ParameterSpec(
        "pm25",
        "PM2.5",
        "\u00b5g/m\u00b3",
        "Fine particulate matter \u22642.5\u00b5m \u2014 the key health metric. "
        "The US EPA flags 24h averages above 35\u00b5g/m\u00b3 as unhealthy for "
        "sensitive groups.",
    ),
    ParameterSpec(
        "pm10",
        "PM10",
        "\u00b5g/m\u00b3",
        "Coarse particulate matter \u226410\u00b5m (dust, pollen, mold). Elevated "
        "levels aggravate asthma and allergies.",
    ),
    ParameterSpec(
        "temperature",
        "Temperature",
        "\u00b0C",
        "Ambient air temperature. Comfort range is roughly 18\u201324\u00b0C.",
    ),
    ParameterSpec(
        "humidity",
        "Humidity",
        "%RH",
        "Relative humidity. 30\u201360%RH is comfortable; too low dries airways, "
        "too high encourages mold and dust mites.",
    ),
    ParameterSpec(
        "aqi",
        "AQI",
        "index",
        "US EPA Air Quality Index computed from PM2.5/PM10. 0\u201350 Good, "
        "51\u2013100 Moderate, 101\u2013150 Unhealthy for sensitive groups, 150+ "
        "Unhealthy.",
    ),
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
