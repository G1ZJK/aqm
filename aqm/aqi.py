"""US EPA Air Quality Index (AQI) computation.

Implements the piecewise-linear AQI formula using the official breakpoint
tables for PM2.5 and PM10. The overall AQI is the maximum of the per-pollutant
sub-indices (EPA convention).

Reference: US EPA Technical Assistance Document for the Reporting of Daily Air
Quality (AQI). PM2.5 uses the 2024-updated breakpoints.
"""

from __future__ import annotations

# Each tuple: (C_low, C_high, I_low, I_high)
# PM2.5 breakpoints (ug/m3, 24-hr), 2024 revised table.
PM25_BREAKPOINTS: list[tuple[float, float, int, int]] = [
    (0.0, 9.0, 0, 50),
    (9.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150),
    (55.5, 125.4, 151, 200),
    (125.5, 225.4, 201, 300),
    (225.5, 325.4, 301, 500),
]

# PM10 breakpoints (ug/m3, 24-hr).
PM10_BREAKPOINTS: list[tuple[float, float, int, int]] = [
    (0, 54, 0, 50),
    (55, 154, 51, 100),
    (155, 254, 101, 150),
    (255, 354, 151, 200),
    (355, 424, 201, 300),
    (425, 604, 301, 500),
]


def _truncate(value: float, pollutant: str) -> float:
    """Truncate concentration to the precision EPA specifies before lookup."""
    if pollutant == "pm25":
        return int(value * 10) / 10.0  # 0.1 ug/m3
    return float(int(value))  # pm10: integer ug/m3


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


def aqi_from_pm(pm25: float | None, pm10: float | None) -> int | None:
    """Overall US EPA AQI = max of available PM2.5 and PM10 sub-indices."""
    indices: list[int] = []
    if pm25 is not None:
        idx = sub_index(_truncate(pm25, "pm25"), PM25_BREAKPOINTS)
        if idx is not None:
            indices.append(idx)
    if pm10 is not None:
        idx = sub_index(_truncate(pm10, "pm10"), PM10_BREAKPOINTS)
        if idx is not None:
            indices.append(idx)
    if not indices:
        return None
    return max(indices)


def aqi_category(aqi: int | None) -> str:
    """Human-readable EPA category for an AQI value."""
    if aqi is None:
        return "Unknown"
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
