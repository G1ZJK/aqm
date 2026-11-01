"""Tests for AQI computation and reading normalization (Task 4)."""

from __future__ import annotations

from datetime import UTC, datetime

from aqm.aqi import PM25_BREAKPOINTS, aqi_category, aqi_from_pm, sub_index
from aqm.reading import apply_scaling, normalize

# --- AQI --------------------------------------------------------------------

def test_aqi_pm25_boundary_values():
    # Lower edge of each band maps to the band's I_low.
    assert aqi_from_pm(0.0, None) == 0
    assert aqi_from_pm(9.0, None) == 50
    assert aqi_from_pm(9.1, None) == 51
    assert aqi_from_pm(35.5, None) == 101
    assert aqi_from_pm(55.5, None) == 151


def test_aqi_pm25_midrange_known_value():
    # PM2.5 = 22.0 is within 9.1-35.4 -> 51..100 band.
    # aqi = (100-51)/(35.4-9.1)*(22.0-9.1)+51 = 49/26.3*12.9+51 ~= 75
    assert aqi_from_pm(22.0, None) == 75


def test_aqi_takes_max_of_pollutants():
    # PM2.5=10 (~53), PM10=200 (~123). Overall = max = 123.
    result = aqi_from_pm(10.0, 200.0)
    assert result == max(aqi_from_pm(10.0, None), aqi_from_pm(None, 200.0))
    assert result == 123


def test_aqi_above_range_caps():
    assert aqi_from_pm(10000.0, None) == 500


def test_aqi_none_when_no_input():
    assert aqi_from_pm(None, None) is None


def test_sub_index_negative_is_none():
    assert sub_index(-1, PM25_BREAKPOINTS) is None


def test_aqi_category():
    assert aqi_category(25) == "Good"
    assert aqi_category(75) == "Moderate"
    assert aqi_category(125) == "Unhealthy for Sensitive Groups"
    assert aqi_category(175) == "Unhealthy"
    assert aqi_category(250) == "Very Unhealthy"
    assert aqi_category(400) == "Hazardous"
    assert aqi_category(None) == "Unknown"


# --- Normalization ----------------------------------------------------------

DPS_MAP = {
    "2": "pm25",
    "18": "pm10",
    "21": "co2",
    "25": "temperature",
    "26": "humidity",
}


def test_apply_scaling():
    out = apply_scaling({"temperature": 231.0, "co2": 650.0}, {"temperature": 0.1})
    assert out["temperature"] == 23.1
    assert out["co2"] == 650.0


def test_normalize_full_pipeline_with_aqi():
    raw = {"2": 12.0, "18": 20.0, "21": 650, "25": 231, "26": 45}
    reading = normalize(raw, DPS_MAP, {"temperature": 0.1})
    assert reading.values["pm25"] == 12.0
    assert reading.values["temperature"] == 23.1
    assert reading.values["co2"] == 650.0
    # AQI computed from pm25=12 / pm10=20.
    assert "aqi" in reading.values
    assert reading.values["aqi"] == float(aqi_from_pm(12.0, 20.0))


def test_normalize_missing_datapoints():
    raw = {"21": 650}  # only CO2 present
    reading = normalize(raw, DPS_MAP, {})
    assert reading.values == {"co2": 650.0}
    assert "aqi" not in reading.values  # no PM -> no AQI


def test_normalize_can_skip_aqi():
    raw = {"2": 12.0}
    reading = normalize(raw, DPS_MAP, {}, compute_aqi=False)
    assert "aqi" not in reading.values


def test_reading_storage_doc():
    reading = normalize({"2": 12.0}, DPS_MAP, {}, ts=datetime(2026, 1, 1, tzinfo=UTC))
    doc = reading.to_storage_doc("devX")
    assert doc["meta"]["device"] == "devX"
    assert doc["values"]["pm25"] == 12.0
    assert doc["ts"] == datetime(2026, 1, 1, tzinfo=UTC)
