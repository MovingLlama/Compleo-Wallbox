"""Smart charging logic: modes, ALT phase hold, solar smoothing."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components import compleo_wallbox as cw
from custom_components.compleo_wallbox.const import (
    MODE_EXTERNAL, MODE_FAST, MODE_LIMITED, MODE_SOLAR,
)


@pytest.fixture
def ctrl(hass):
    coordinator = MagicMock()
    coordinator.async_write_register = AsyncMock()
    return cw.CompleoSmartChargingController(coordinator, hass, "logic_test")


@pytest.fixture
def clock():
    now = [1_000_000.0]
    with patch.object(cw.time, "time", lambda: now[0]):
        yield now


def written(ctrl) -> list[tuple[int, int]]:
    return [c.args for c in ctrl.coordinator.async_write_register.call_args_list]


async def test_persisted_inputs_roundtrip(hass, ctrl) -> None:
    ctrl.update_input(1, "mode", MODE_SOLAR)
    ctrl.update_input(1, "zoe_mode", True)
    ctrl.update_input(1, "solar_excess", 4000)
    await ctrl.async_save()

    other = cw.CompleoSmartChargingController(MagicMock(), hass, "logic_test")
    await other.async_load()
    assert other.get_input(1, "mode") == MODE_SOLAR
    assert other.get_input(1, "zoe_mode") is True
    assert other.get_input(1, "solar_excess") == 0


async def test_unknown_stored_mode_is_ignored(hass, hass_storage) -> None:
    hass_storage["compleo_wallbox.bad"] = {
        "version": 1, "key": "compleo_wallbox.bad",
        "data": {"points": {"1": {"mode": "bogus"}}},
    }
    ctrl = cw.CompleoSmartChargingController(MagicMock(), hass, "bad")
    await ctrl.async_load()
    assert ctrl.get_input(1, "mode") == MODE_FAST


async def test_external_mode_writes_nothing(ctrl) -> None:
    ctrl.update_input(1, "mode", MODE_EXTERNAL)
    await ctrl.run_logic(1)
    assert written(ctrl) == []

    ctrl.update_input(1, "mode", MODE_FAST)
    await ctrl.run_logic(1)
    assert written(ctrl) == [(0x0100, 110)]


async def test_alt_phase_is_held(ctrl, clock) -> None:
    ctrl.update_input(2, "mode", MODE_LIMITED)
    ctrl.update_input(2, "zoe_mode", True)

    ctrl.update_input(2, "manual_limit", 6000)
    await ctrl.run_logic(2)
    assert written(ctrl)[-2:] == [(0x0200, 60), (0x0209, 3)]

    # Below the 3-phase threshold (5520 W at 8 A), but within the hold time
    clock[0] += 60
    ctrl.update_input(2, "manual_limit", 5000)
    await ctrl.run_logic(2)
    assert written(ctrl)[-1] == (0x0209, 3)

    clock[0] += 8 * 60 + 59
    await ctrl.run_logic(2)
    assert written(ctrl)[-1] == (0x0209, 3)

    clock[0] += 2
    await ctrl.run_logic(2)
    assert written(ctrl)[-2:] == [(0x0200, 50), (0x0209, 2)]

    # Below the 1-phase minimum (1840 W) -> stop
    ctrl.update_input(2, "manual_limit", 1000)
    await ctrl.run_logic(2)
    assert written(ctrl)[-2] == (0x0200, 0)

    ctrl.update_input(2, "zoe_mode", False)
    assert ctrl.get_input(2, "phase") is None


async def test_solar_smoothing_feeds_phase(ctrl, clock) -> None:
    ctrl.update_input(1, "mode", MODE_SOLAR)
    ctrl.update_input(1, "zoe_mode", True)

    ctrl.update_input(1, "solar_excess", 7000)  # 6500 W after the buffer
    await ctrl.run_logic(1)
    assert written(ctrl)[-2:] == [(0x0100, 65), (0x0109, 3)]

    # 5500 W is a drop of > 10 %: follow at once, phase still held
    clock[0] += 30
    ctrl.update_input(1, "solar_excess", 6000)
    await ctrl.run_logic(1)
    assert written(ctrl)[-2:] == [(0x0100, 55), (0x0109, 3)]

    # Small rise: held for 20 min
    clock[0] += 30
    ctrl.update_input(1, "solar_excess", 6100)
    await ctrl.run_logic(1)
    assert written(ctrl)[-2] == (0x0100, 55)
