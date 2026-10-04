"""Lifetime energy sensors built from the session energy."""
from __future__ import annotations

from modbus_connection import ModbusExceptionError
from pytest_homeassistant_custom_component.common import mock_restore_cache_with_extra_data

from homeassistant.core import State

from custom_components.compleo_wallbox.const import DOMAIN

LP1_METER = "sensor.box_point_1_meter_reading_lifetime"
STATION_METER = "sensor.box_energy_lifetime_station"


async def _refresh(hass, entry) -> None:
    await hass.data[DOMAIN][entry.entry_id].async_refresh()
    await hass.async_block_till_done()


def _session(unit, base: int, kwh: float) -> None:
    unit.input[base + 0x08] = round(kwh * 10)


async def test_meter_counts_sessions(hass, mock_unit, config_entry) -> None:
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    await _refresh(hass, config_entry)
    assert float(hass.states.get(LP1_METER).state) == 3.0

    _session(mock_unit, 0x0100, 4.0)
    await _refresh(hass, config_entry)
    assert float(hass.states.get(LP1_METER).state) == 4.0

    # New session starts at 0.5 kWh
    _session(mock_unit, 0x0100, 0.5)
    await _refresh(hass, config_entry)
    assert float(hass.states.get(LP1_METER).state) == 4.5


async def test_missing_reading_is_not_counted_twice(hass, mock_unit, config_entry) -> None:
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    await _refresh(hass, config_entry)

    # The block with the session energy is rejected once
    mock_unit.fail_read(0x0101, ModbusExceptionError("busy"), register_type="input")
    await _refresh(hass, config_entry)
    mock_unit.fail_read(0x0101, None, register_type="input")
    await _refresh(hass, config_entry)

    assert float(hass.states.get(LP1_METER).state) == 3.0


async def test_station_total_per_point(hass, mock_unit, config_entry) -> None:
    _session(mock_unit, 0x0200, 2.0)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    await _refresh(hass, config_entry)
    assert float(hass.states.get(STATION_METER).state) == 5.0

    # Point 1 goes on, point 2 starts a new session
    _session(mock_unit, 0x0100, 4.0)
    _session(mock_unit, 0x0200, 0.1)
    await _refresh(hass, config_entry)
    assert round(float(hass.states.get(STATION_METER).state), 3) == 6.1


async def test_meter_restored_from_extra_data(hass, mock_unit, config_entry) -> None:
    mock_restore_cache_with_extra_data(hass, [
        (State(LP1_METER, "unavailable"), {"total": 50.0, "last_sessions": {"1": 1.0}}),
    ])
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    await _refresh(hass, config_entry)

    assert float(hass.states.get(LP1_METER).state) == 52.0
