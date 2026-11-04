"""Air Quality Index (AQI) computation.

Supports two standards, selectable via config (``aqi.method``):

* ``us_epa`` — US EPA AQI using the official breakpoint tables (PM2.5 2024
  revision). The dashboard value tends to run high because EPA crosses AQI 50
  at just 9 ug/m3 of PM2.5.
* ``china_mee`` — China MEE (GB 3095-2012 / HJ 633-2012) AQI. Its first PM2.5
  band is 0-35 ug/m3 -> 0-50, so it reports a lower number for the same air.
  This matches the on-device display of the ZN-MT29.

Both compute the overall AQI as the maximum of the available per-pollutant
sub-indices (the shared IAQI convention).
"""

from __future__ import annotations

# Each tuple: (C_low, C_high, I_low, I_high)
# PM2.5 breakpoints (ug/m3, 24-hr), US EPA 2024 revised table.
PM25_BREAKPOINTS: list[tuple[float, float, int, int]] = [
    (0.0, 9.0, 0, 50),
    (9.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150),
    (55.5, 125.4, 151, 200),
    (125.5, 225.4, 201, 300),
    (225.5, 325.4, 301, 500),
]

# PM10 breakpoints (ug/m3, 24-hr), US EPA.
PM10_BREAKPOINTS: list[tuple[float, float, int, int]] = [
    (0, 54, 0, 50),
    (55, 154, 51, 100),
    (155, 254, 101, 150),
    (255, 354, 151, 200),
    (355, 424, 201, 300),
    (425, 604, 301, 500),
]

# China MEE (HJ 633-2012) PM2.5 breakpoints (ug/m3, 24-hr).
PM25_BREAKPOINTS_CHINA: list[tuple[float, float, int, int]] = [
    (0, 35, 0, 50),
    (35, 75, 50, 100),
    (75, 115, 100, 150),
    (115, 150, 150, 200),
    (150, 250, 200, 300),
    (250, 350, 300, 400),
    (350, 500, 400, 500),
]

# China MEE (HJ 633-2012) PM10 breakpoints (ug/m3, 24-hr).
PM10_BREAKPOINTS_CHINA: list[tuple[float, float, int, int]] = [
    (0, 50, 0, 50),
    (50, 150, 50, 100),
    (150, 250, 100, 150),
    (250, 350, 150, 200),
    (350, 420, 200, 300),
    (420, 500, 300, 400),
    (500, 600, 400, 500),
]

US_EPA = "us_epa"
CHINA_MEE = "china_mee"

# Per-method breakpoint tables.
_BREAKPOINTS: dict[str, dict[str, list[tuple[float, float, int, int]]]] = {
    US_EPA: {"pm25": PM25_BREAKPOINTS, "pm10": PM10_BREAKPOINTS},
    CHINA_MEE: {"pm25": PM25_BREAKPOINTS_CHINA, "pm10": PM10_BREAKPOINTS_CHINA},
}


def _truncate(value: float, pollutant: str, method: str) -> float:
    """Truncate concentration to the precision the standard specifies.

    EPA truncates PM2.5 to 0.1 ug/m3 and PM10 to integer. China MEE rounds to
    integer ug/m3 for both.
    """
    if method == US_EPA and pollutant == "pm25":
        return int(value * 10) / 10.0  # 0.1 ug/m3
    return float(int(value))  # integer ug/m3


def sub_index(concentration: float, breakpoints: list[tuple[float, float, int, int]]) -> int | None:
    """Compute the AQI sub-index for one pollutant, or None if out of range."""
    if concentration < 0:
        return None
    for c_low, c_high, i_low, i_high in breakpoints:
        if c_low <= concentration <= c_high:
            aqi = (i_high - i_low) / (c_high - c_low) * (concentration - c_low) + i_low
            return round(aqi)
    # Above the top breakpoint -> cap at the maximum index.
    return breakpoints[-1][3]


def aqi_from_pm(
    pm25: float | None, pm10: float | None, method: str = US_EPA
) -> int | None:
    """Overall AQI = max of available PM2.5 and PM10 sub-indices.

    ``method`` selects the breakpoint standard: ``us_epa`` or ``china_mee``.
    """
    tables = _BREAKPOINTS.get(method)
    if tables is None:
        raise ValueError(f"unknown AQI method: {method!r}")
    indices: list[int] = []
    if pm25 is not None:
        idx = sub_index(_truncate(pm25, "pm25", method), tables["pm25"])
        if idx is not None:
            indices.append(idx)
    if pm10 is not None:
        idx = sub_index(_truncate(pm10, "pm10", method), tables["pm10"])
        if idx is not None:
            indices.append(idx)
    if not indices:
        return None
    return max(indices)


def aqi_category(aqi: int | None, method: str = US_EPA) -> str:
    """Human-readable category for an AQI value, per the selected standard."""
    if aqi is None:
        return "Unknown"
    if method == CHINA_MEE:
        # China MEE six-level scale.
        if aqi <= 50:
            return "Excellent"
        if aqi <= 100:
            return "Good"
        if aqi <= 150:
            return "Lightly Polluted"
        if aqi <= 200:
            return "Moderately Polluted"
        if aqi <= 300:
            return "Heavily Polluted"
        return "Severely Polluted"
    # US EPA scale.
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Moderate"
    if aqi <= 150:
        return "Unhealthy for Sensitive Groups"
    if aqi <= 200:
        return "Unhealthy"
    if aqi <= 300:
        return "Very Unhealthy"
    return "Hazardous"
