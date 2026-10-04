"""Fixtures for the Compleo Wallbox tests."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from modbus_connection.mock import MockModbusConnection, MockModbusUnit
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.compleo_wallbox.const import DOMAIN

HOST = "192.0.2.10"
PORT = 502
ENTRY_ID = "compleo_test"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from custom_components."""
    yield


@pytest.fixture
def mock_connection() -> MockModbusConnection:
    """One in-memory Modbus connection, handed out by the Modbus integration."""
    connection = MockModbusConnection()
    with patch(
        "homeassistant.components.modbus.connection.ModbusConnection",
        return_value=connection,
    ):
        yield connection


def _load_point(unit: MockModbusUnit, base: int, energy: float, power: int) -> None:
    # Single addresses: a write must not wipe neighbouring registers in the mock
    unit.holding.update({base + i: 0 for i in range(10)})
    unit.holding[base] = 110          # max power 11 kW
    unit.holding[base + 9] = 1        # phase mode automatic
    unit.input.update({
        base + 0x01: 0,               # status word
        base + 0x02: power // 100,    # power
        base + 0x03: 160,             # 16.0 A
        base + 0x08: round(energy * 10),
        base + 0x0B: 0,               # no error
        base + 0x0C: 2,               # charging
        base + 0x0D: 230,
        base + 0x1A: 0,
    })


@pytest.fixture
def mock_unit(mock_connection: MockModbusConnection) -> MockModbusUnit:
    """A Compleo Duo answering on unit 1."""
    unit = mock_connection.for_unit(1)
    unit.input[0x0008] = 2                           # two charging points
    unit.input[0x0006] = [0x0100, 0x0203]            # firmware 2.3.1
    unit.input[0x0009] = [110, 160, 160, 160, 0]
    # Strings end at the first NUL, real wallboxes leave garbage behind it
    unit.input[0x0020] = [0x4142, 0x4300, 0x3700]    # article "ABC" + "\0" + "7"
    unit.input[0x0030] = [0x3132, 0x3334]            # serial "1234"
    _load_point(unit, 0x0100, energy=3.0, power=11000)
    _load_point(unit, 0x0200, energy=0.0, power=0)
    return unit


@pytest.fixture
def config_entry(hass) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id=ENTRY_ID,
        unique_id=f"{HOST}_{PORT}",
        title="Box",
        data={"host": HOST, "port": PORT, "name": "Box"},
    )
    entry.add_to_hass(hass)
    return entry


def writes(unit: MockModbusUnit) -> list[tuple[int, int]]:
    """Collect (address, value) of every holding register write."""
    events: list[tuple[int, int]] = []
    unit.on_write(lambda e: events.append((e.address, e.values[0])))
    return events
