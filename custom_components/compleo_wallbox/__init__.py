"""The Compleo Wallbox integration."""
from __future__ import annotations

import time
from datetime import timedelta
import logging

from modbus_connection import (
    ModbusConnectionError,
    ModbusError,
    ModbusExceptionError,
    ModbusTcpParams,
    ModbusTimeoutError,
    ModbusUnit,
)

from homeassistant.components.modbus import async_get_unit
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_HOST, CONF_PORT, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    DOMAIN, DEFAULT_SCAN_INTERVAL, DEFAULT_UNIT_ID,
    # Registers
    REG_SYS_POWER_LIMIT, REG_SYS_MAX_SCHIEFLAST, REG_SYS_FALLBACK_POWER,
    REG_SYS_FW_PATCH, REG_SYS_NUM_POINTS, REG_SYS_ARTICLE_NUM, REG_SYS_SERIAL_NUM,
    LEN_STRING_REGISTERS, REG_SYS_TOTAL_POWER_READ,
    ADDR_LP1_BASE, ADDR_LP2_BASE,
    OFFSET_MAX_POWER, OFFSET_STATUS_WORD, OFFSET_PHASE_SWITCHES,
    OFFSET_PHASE_MODE, OFFSET_RFID_TAG, OFFSET_DERATING_STATUS,
    # Logic Constants
    MODE_FAST, MODE_LIMITED, MODE_SOLAR, MODE_DISABLED, MODE_EXTERNAL, CHARGING_MODES,
    DEFAULT_FAST_POWER, DEFAULT_LIMITED_POWER, DEFAULT_SOLAR_BUFFER,
    DEFAULT_ZOE_MIN_CURRENT, TIME_HOLD_RISING, TIME_HOLD_FALLING, TIME_HOLD_PHASE,
    THRESHOLD_DROP_PERCENT, PERSISTED_INPUTS, STORAGE_VERSION
)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.SELECT, Platform.SWITCH]

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    name = entry.data.get(CONF_NAME, "Compleo Wallbox")
    try:
        # The connection is owned by the Modbus integration: shared with other
        # integrations on the same device and closed when the entry unloads.
        unit = async_get_unit(hass, entry, ModbusTcpParams(host=host, port=port), DEFAULT_UNIT_ID)
    except HomeAssistantError as err:
        raise ConfigEntryError(str(err)) from err
    coordinator = CompleoDataUpdateCoordinator(hass, unit, host, name, entry.entry_id)
    # Restore charging mode etc. before the first refresh, otherwise the first
    # logic run would apply the defaults (fast = 11 kW) after every restart.
    await coordinator.logic.async_load()
    # Raises ConfigEntryNotReady if the wallbox does not answer: HA retries the
    # setup instead of creating the entities with a wrong number of points.
    await coordinator.async_config_entry_first_refresh()
    # Create the station first: the charging point devices link to it by id
    station = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **coordinator.system_device_info()
    )
    coordinator.station_device_id = station.id
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.logic.async_save()
    return unload_ok

async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()

class CompleoSmartChargingController:
    """Handles the logic for Solar, Manual, and ALT modes per point."""
    def __init__(self, coordinator, hass: HomeAssistant, entry_id: str):
        self.coordinator = coordinator
        self.points_state = {}
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}")

    def init_point(self, index):
        if index not in self.points_state:
            self.points_state[index] = {
                "mode": MODE_FAST,
                "manual_limit": DEFAULT_LIMITED_POWER,
                "solar_excess": 0,
                "zoe_mode": False,
                "zoe_min_current": DEFAULT_ZOE_MIN_CURRENT,
                "last_change_ts": 0,
                "stable_target": 0,
                "phase": None,
                "phase_change_ts": 0,
            }

    async def async_load(self):
        """Load the persisted user inputs (mode, limits, ALT settings)."""
        data = await self._store.async_load() or {}
        for idx_str, values in data.get("points", {}).items():
            try:
                index = int(idx_str)
            except ValueError:
                continue
            self.init_point(index)
            for key in PERSISTED_INPUTS:
                if key not in values:
                    continue
                if key == "mode" and values[key] not in CHARGING_MODES:
                    continue
                self.points_state[index][key] = values[key]

    def _data_to_save(self):
        return {
            "points": {
                str(index): {key: state[key] for key in PERSISTED_INPUTS}
                for index, state in self.points_state.items()
            }
        }

    async def async_save(self):
        await self._store.async_save(self._data_to_save())

    def update_input(self, index, key, value):
        self.init_point(index)
        self.points_state[index][key] = value
        if key == "zoe_mode" and not value:
            # Phase is handed back to the wallbox (automatic), forget our decision
            self.points_state[index]["phase"] = None
        if key in PERSISTED_INPUTS:
            self._store.async_delay_save(self._data_to_save, 1)

    def get_input(self, index, key):
        self.init_point(index)
        return self.points_state[index].get(key)

    def _smooth_solar(self, state, target_power, now):
        """Hysteresis for solar mode: hold the target for a while before following."""
        last_target = state["stable_target"]
        last_ts = state["last_change_ts"]

        is_significant_drop = False
        if last_target > 0:
            drop_pct = (last_target - target_power) / last_target * 100
            if drop_pct > THRESHOLD_DROP_PERCENT:
                is_significant_drop = True

        minutes_since_change = (now - last_ts) / 60

        if is_significant_drop:
            state["stable_target"] = target_power
            state["last_change_ts"] = now
        elif target_power > last_target:
            if minutes_since_change >= TIME_HOLD_RISING:
                state["stable_target"] = target_power
                state["last_change_ts"] = now
            else:
                target_power = last_target
        elif target_power < last_target:
            if minutes_since_change >= TIME_HOLD_FALLING:
                state["stable_target"] = target_power
                state["last_change_ts"] = now
            else:
                target_power = last_target

        if last_target == 0 and target_power > 0:
            state["stable_target"] = target_power
            state["last_change_ts"] = now

        return target_power

    def _alt_phase(self, state, target_power, now):
        """ALT mode: choose 1-/3-phase from the (smoothed) target, with a minimum hold time."""
        min_amp = state["zoe_min_current"]
        threshold_3ph = min_amp * 230 * 3
        min_power_1ph = min_amp * 230
        max_power_1ph = 32 * 230

        wanted_phase = 3 if target_power >= threshold_3ph else 2
        current_phase = state["phase"]
        if current_phase is not None and wanted_phase != current_phase:
            minutes_since_switch = (now - state["phase_change_ts"]) / 60
            if minutes_since_switch < TIME_HOLD_PHASE:
                # Keep the phase to avoid switching back and forth with every cloud
                wanted_phase = current_phase
        if wanted_phase != current_phase:
            state["phase"] = wanted_phase
            state["phase_change_ts"] = now

        if wanted_phase == 2 and target_power > max_power_1ph:
            target_power = max_power_1ph
        if target_power < min_power_1ph:
            target_power = 0

        return target_power, wanted_phase

    async def run_logic(self, index):
        self.init_point(index)
        state = self.points_state[index]
        mode = state["mode"]
        if mode == MODE_EXTERNAL:
            # Setpoints are controlled manually or by another system
            return

        now = time.time()
        target_power = 0
        target_phase_mode = None

        if mode == MODE_FAST:
            target_power = DEFAULT_FAST_POWER
        elif mode == MODE_LIMITED:
            target_power = state["manual_limit"]
        elif mode == MODE_SOLAR:
            raw_solar = max(state["solar_excess"] - DEFAULT_SOLAR_BUFFER, 0)
            target_power = self._smooth_solar(state, raw_solar, now)
        elif mode == MODE_DISABLED:
            target_power = 0

        # Phase decision on the smoothed value, so phase and power stay consistent
        if state["zoe_mode"]:
            target_power, target_phase_mode = self._alt_phase(state, target_power, now)

        base_addr = ADDR_LP1_BASE if index == 1 else ADDR_LP2_BASE

        # Written every cycle on purpose: acts as keep-alive towards the wallbox
        val_to_write = int(target_power / 100)
        try:
            await self.coordinator.async_write_register(base_addr + OFFSET_MAX_POWER, val_to_write)
            if target_phase_mode is not None:
                await self.coordinator.async_write_register(base_addr + OFFSET_PHASE_MODE, target_phase_mode)
        except HomeAssistantError as err:
            # Readings stay valid; the next cycle writes again
            _LOGGER.warning("Charging point %s: could not write setpoint: %s", index, err)


class CompleoDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching and controlling Compleo Wallbox data."""

    def __init__(self, hass: HomeAssistant, unit: ModbusUnit, host: str, name: str, entry_id: str) -> None:
        self.unit = unit
        self.host = host
        self.device_name = name
        # Registry id of the station device, parent of the charging point devices
        self.station_device_id: str | None = None

        self.logic = CompleoSmartChargingController(self, hass, entry_id)

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{host}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

        self.data = {
            "system": {"num_points": 1},
            "points": {}
        }

    def system_device_info(self) -> DeviceInfo:
        """Device of the station; every platform must hand out the same info."""
        system_data = self.data.get("system", {}) if self.data else {}
        return DeviceInfo(
            identifiers={(DOMAIN, self.host)},
            name=self.device_name,
            manufacturer="Compleo",
            model=system_data.get("article_number", "Compleo Wallbox"),
            sw_version=system_data.get("firmware_version"),
            serial_number=system_data.get("serial_number"),
        )

    def point_device_info(self, index: int) -> DeviceInfo:
        """Device of one charging point, linked to the station."""
        info = DeviceInfo(
            identifiers={(DOMAIN, f"{self.host}_lp{index}")},
            name=f"{self.device_name} Point {index}",
            manufacturer="Compleo",
            model="Charging Point",
        )
        if self.station_device_id is not None:
            info["via_device_id"] = self.station_device_id
        return info

    async def _async_update_data(self):
        try:
            new_data = await self._fetch_wallbox_data()
        except (ModbusConnectionError, ModbusTimeoutError) as err:
            raise UpdateFailed(f"Wallbox {self.host} not reachable: {err}") from err
        except ModbusError as err:
            raise UpdateFailed(f"Communication error: {err}") from err

        num_points = new_data["system"].get("num_points", 1)
        for i in range(1, num_points + 1):
            await self.logic.run_logic(i)
        return new_data

    async def _read(self, kind: str, address: int, count: int) -> list[int] | None:
        """Read registers; None if the wallbox rejects the address (exception response).

        Connection errors and timeouts are raised and fail the whole update.
        """
        func = self.unit.read_input_registers if kind == "input" else self.unit.read_holding_registers
        try:
            regs = await func(address, count)
        except ModbusExceptionError as err:
            _LOGGER.debug("Register 0x%04X (%s, %d) not readable: %s", address, kind, count, err)
            return None
        if len(regs) < count:
            return None
        return regs

    async def _fetch_wallbox_data(self):
        new_data = {"system": {}, "points": {}}

        num_points = 1
        regs = await self._read("input", REG_SYS_NUM_POINTS, 1)
        if regs and regs[0] in (1, 2):
            num_points = regs[0]
        new_data["system"]["num_points"] = num_points

        if regs := await self._read("holding", REG_SYS_POWER_LIMIT, 1):
            new_data["system"]["power_setpoint_abs"] = regs[0]
        if regs := await self._read("holding", REG_SYS_MAX_SCHIEFLAST, 1):
            new_data["system"]["max_schieflast"] = regs[0]
        if regs := await self._read("holding", REG_SYS_FALLBACK_POWER, 1):
            new_data["system"]["fallback_power"] = regs[0]

        if regs := await self._read("input", REG_SYS_FW_PATCH, 2):
            new_data["system"]["firmware_version"] = f"{regs[1]>>8}.{regs[1]&0xFF}.{regs[0]>>8}"

        if regs := await self._read("input", REG_SYS_TOTAL_POWER_READ, 5):
            new_data["system"]["total_power"] = regs[0] * 100
            new_data["system"]["total_current_l1"] = regs[1] * 0.1
            new_data["system"]["total_current_l2"] = regs[2] * 0.1
            new_data["system"]["total_current_l3"] = regs[3] * 0.1
            new_data["system"]["unused_power"] = regs[4] * 100

        # Article and serial number never change: read them once
        for key, address in (("article_number", REG_SYS_ARTICLE_NUM), ("serial_number", REG_SYS_SERIAL_NUM)):
            value = (self.data or {}).get("system", {}).get(key)
            if value is None:
                value = await self._read_string(address, LEN_STRING_REGISTERS)
            if value:
                new_data["system"][key] = value

        sum_sess = 0.0
        for i in range(1, num_points + 1):
            pd = await self._read_charging_point_data(i)
            new_data["points"][i] = pd
            sum_sess += pd.get("energy_session", 0)

        new_data["system"]["total_energy_session"] = sum_sess
        return new_data

    async def async_write_register(self, address: int, value: int) -> None:
        """Write one holding register; raises HomeAssistantError on failure."""
        try:
            await self.unit.write_register(address, value)
        except ModbusError as err:
            raise HomeAssistantError(f"Writing register 0x{address:04X} failed: {err}") from err

    @staticmethod
    def _decode_registers_to_string(regs: list[int] | None) -> str | None:
        if not regs:
            return None
        raw = b"".join(reg.to_bytes(2, "big") for reg in regs)
        return raw.decode("ascii", errors="ignore").rstrip("\x00").strip() or None

    async def _read_string(self, address: int, count: int) -> str | None:
        val = self._decode_registers_to_string(await self._read("input", address, count))
        if val:
            return val
        return self._decode_registers_to_string(await self._read("holding", address, count))

    async def _read_charging_point_data(self, index: int) -> dict:
        base = ADDR_LP1_BASE if index == 1 else ADDR_LP2_BASE
        data = {}

        if regs := await self._read("holding", base + OFFSET_MAX_POWER, 10):
            data["max_power_limit"] = regs[0]
            data["phase_mode"] = regs[9]

        if regs := await self._read("input", base + OFFSET_STATUS_WORD, 8):
            data["status_word"] = regs[0]
            data["current_power"] = regs[1] * 100
            data["current_l1"] = regs[2] * 0.1
            data["current_l2"] = regs[3] * 0.1
            data["current_l3"] = regs[4] * 0.1
            data["charging_time"] = regs[5] + (regs[6] << 16)
            data["energy_session"] = regs[7] * 0.1

        if regs := await self._read("input", base + OFFSET_PHASE_SWITCHES, 6):
            data["phase_switch_count"] = regs[0]
            data["error_code"] = regs[1]
            data["status_code"] = regs[2]
            data["voltage_l1"] = regs[3]
            data["voltage_l2"] = regs[4]
            data["voltage_l3"] = regs[5]

        if rfid := await self._read_string(base + OFFSET_RFID_TAG, 10):
            data["rfid_tag"] = rfid

        if regs := await self._read("input", base + OFFSET_DERATING_STATUS, 1):
            data["derating_status"] = regs[0]

        return data
