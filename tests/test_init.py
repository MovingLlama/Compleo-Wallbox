"""Setup, polling and control through the Modbus integration's units."""
from __future__ import annotations

from modbus_connection import IllegalDataAddressError, ModbusConnectionError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.compleo_wallbox.const import DOMAIN

from .conftest import ENTRY_ID, HOST, writes


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_duo(hass, mock_unit, config_entry) -> None:
    await _setup(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.box_total_power_station").state == "11000"
    assert hass.states.get("sensor.box_point_1_power").state == "11000"
    assert hass.states.get("sensor.box_point_1_status").state == "2"
    # Second charging point detected from register 0x0008
    assert hass.states.get("select.box_point_2_charging_mode") is not None

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, HOST)})
    assert device.sw_version == "2.3.1"
    assert device.model == "ABC"


async def test_unreachable_retries_setup(hass, mock_unit, config_entry) -> None:
    mock_unit.fail_requests(ModbusConnectionError("no route to host"))
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_default_mode_is_fast(hass, mock_unit, config_entry) -> None:
    events = writes(mock_unit)
    await _setup(hass, config_entry)

    assert (0x0100, 110) in events
    assert (0x0200, 110) in events


async def test_stored_modes_survive_restart(hass, hass_storage, mock_unit, config_entry) -> None:
    hass_storage[f"{DOMAIN}.{ENTRY_ID}"] = {
        "version": 1,
        "key": f"{DOMAIN}.{ENTRY_ID}",
        "data": {"points": {
            "1": {"mode": "disabled", "manual_limit": 3600, "zoe_mode": False, "zoe_min_current": 8},
            "2": {"mode": "external", "manual_limit": 3600, "zoe_mode": False, "zoe_min_current": 8},
        }},
    }
    events = writes(mock_unit)
    await _setup(hass, config_entry)

    # Never 11 kW: point 1 is disabled, point 2 is left alone
    assert events and set(events) == {(0x0100, 0)}
    assert hass.states.get("select.box_point_1_charging_mode").state == "disabled"
    assert hass.states.get("select.box_point_2_charging_mode").state == "external"


async def test_selected_mode_is_stored(hass, hass_storage, mock_unit, config_entry) -> None:
    await _setup(hass, config_entry)
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": "select.box_point_1_charging_mode", "option": "solar"},
        blocking=True,
    )
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    stored = hass_storage[f"{DOMAIN}.{ENTRY_ID}"]["data"]["points"]
    assert stored["1"]["mode"] == "solar"
    assert "solar_excess" not in stored["1"]


async def test_external_mode_allows_manual_limit(hass, mock_unit, config_entry) -> None:
    await _setup(hass, config_entry)
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": "select.box_point_1_charging_mode", "option": "external"},
        blocking=True,
    )
    events = writes(mock_unit)
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": "number.box_point_1_max_power_hardware", "value": 5000},
        blocking=True,
    )
    await hass.async_block_till_done()

    # Only the manual write for point 1, the logic does not overwrite it
    assert [e for e in events if e[0] == 0x0100] == [(0x0100, 50)]
    assert mock_unit.holding[0x0100] == 50


async def test_write_failure_does_not_fail_update(hass, mock_unit, config_entry) -> None:
    mock_unit.fail_write(0x0100, ModbusConnectionError("write lost"))
    await _setup(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.box_point_1_power").state == "11000"


async def test_rejected_register_is_skipped(hass, mock_unit, config_entry) -> None:
    mock_unit.fail_read(0x011A, IllegalDataAddressError("no derating"), register_type="input")
    await _setup(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.box_point_1_temp_derating").state == "unknown"
    assert hass.states.get("sensor.box_point_1_power").state == "11000"


async def test_lost_connection_marks_unavailable(hass, mock_unit, config_entry) -> None:
    await _setup(hass, config_entry)
    mock_unit.fail_requests(ModbusConnectionError("gone"))
    await hass.data[DOMAIN][config_entry.entry_id].async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("sensor.box_point_1_power").state == "unavailable"


async def test_unload_closes_connection(hass, mock_connection, mock_unit, config_entry) -> None:
    await _setup(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_connection._closed
