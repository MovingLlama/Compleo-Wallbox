"""The Compleo Wallbox integration."""
from __future__ import annotations

import asyncio
import time
from datetime import timedelta
import logging

from pymodbus.client import AsyncModbusTcpClient
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_HOST, CONF_PORT, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    DOMAIN, DEFAULT_SCAN_INTERVAL,
    # Registers
    REG_SYS_POWER_LIMIT, REG_SYS_MAX_SCHIEFLAST, REG_SYS_FALLBACK_POWER,
    REG_SYS_FW_PATCH, REG_SYS_NUM_POINTS, REG_SYS_ARTICLE_NUM, REG_SYS_SERIAL_NUM,
    LEN_STRING_REGISTERS, REG_SYS_TOTAL_POWER_READ, REG_SYS_TOTAL_CURRENT_L1,
    REG_SYS_TOTAL_CURRENT_L2, REG_SYS_TOTAL_CURRENT_L3, REG_SYS_UNUSED_POWER,
    ADDR_LP1_BASE, ADDR_LP2_BASE,
    OFFSET_MAX_POWER, OFFSET_STATUS_WORD, OFFSET_POWER, OFFSET_CURRENT_L1,
    OFFSET_CURRENT_L2, OFFSET_CURRENT_L3, OFFSET_CHARGING_TIME, OFFSET_ENERGY,
    OFFSET_PHASE_SWITCHES, OFFSET_ERROR_CODE, OFFSET_STATUS_CODE,
    OFFSET_VOLTAGE_L1, OFFSET_VOLTAGE_L2, OFFSET_VOLTAGE_L3,
    OFFSET_PHASE_MODE, OFFSET_RFID_TAG, OFFSET_METER_READING, OFFSET_DERATING_STATUS,
    # Logic Constants
    MODE_FAST, MODE_LIMITED, MODE_SOLAR,
    DEFAULT_FAST_POWER, DEFAULT_LIMITED_POWER, DEFAULT_SOLAR_BUFFER,
    DEFAULT_ZOE_MIN_CURRENT, TIME_HOLD_RISING, TIME_HOLD_FALLING, THRESHOLD_DROP_PERCENT
)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.SELECT, Platform.SWITCH]

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    name = entry.data.get(CONF_NAME, "Compleo Wallbox")
    coordinator = CompleoDataUpdateCoordinator(hass, host, port, name)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as e:
        _LOGGER.warning("Initial fetch failed: %s", e)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        if coordinator.client.connected:
            coordinator.client.close()
    return unload_ok

class CompleoSmartChargingController:
    """Handles the logic for Solar, Manual, and Zoe modes per point."""
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.points_state = {} # Stores virtual state per point

    def init_point(self, index):
        if index not in self.points_state:
            self.points_state[index] = {
                "mode": MODE_FAST,          # Default Mode
                "manual_limit": DEFAULT_LIMITED_POWER,
                "solar_excess": 0,          # Input from HA
                "zoe_mode": False,
                "zoe_min_current": DEFAULT_ZOE_MIN_CURRENT,
                # Hysteresis State
                "last_power_target": 0,
                "last_change_ts": 0,
                "stable_target": 0
            }

    def update_input(self, index, key, value):
        self.init_point(index)
        self.points_state[index][key] = value

    def get_input(self, index, key):
        self.init_point(index)
        return self.points_state[index].get(key)

    async def run_logic(self, index):
        """Calculates target power and phase mode, then writes to wallbox."""
        self.init_point(index)
        state = self.points_state[index]
        
        mode = state["mode"]
        target_power = 0
        target_phase_mode = None # None means don't change by default

        # --- 1. Determine Raw Target Power ---
        if mode == MODE_FAST:
            target_power = DEFAULT_FAST_POWER
        elif mode == MODE_LIMITED:
            target_power = state["manual_limit"]
        elif mode == MODE_SOLAR:
            # Solar Logic: Excess - Buffer
            raw_solar = state["solar_excess"] - DEFAULT_SOLAR_BUFFER
            if raw_solar < 0: raw_solar = 0
            target_power = raw_solar

        # --- 2. Zoe / Phase Logic (Forced Phase Switching) ---
        if mode == MODE_SOLAR and state["zoe_mode"]:
            min_amp = state["zoe_min_current"]
            # Power needed for 3-phase min current: A * 230V * 3
            threshold_3ph = min_amp * 230 * 3
            
            # Power needed for 1-phase min current: A * 230V
            min_power_1ph = min_amp * 230
            
            # Limit for 1-Phase charging (max 32A -> ~7.4kW)
            max_power_1ph = 32 * 230

            if target_power < min_power_1ph:
                # Not enough for 1-Phase Minimum -> Stop Charging
                target_power = 0
                # We stay in 1-Phase mode usually to be ready
                target_phase_mode = 2 
            elif target_power < threshold_3ph:
                # Active 1-Phase Mode
                target_phase_mode = 2 # Force 1-Phase
                
                # Cap power if calculation exceeds physical 1-phase limit
                if target_power > max_power_1ph:
                    target_power = max_power_1ph
            else:
                # Active 3-Phase Mode
                target_phase_mode = 3 # Force 3-Phase
        
        # --- 3. Hysteresis (Only in Solar Mode) ---
        if mode == MODE_SOLAR:
            now = time.time()
            last_target = state["stable_target"]
            last_ts = state["last_change_ts"]
            
            # Check drop percentage
            is_significant_drop = False
            if last_target > 0:
                drop_pct = (last_target - target_power) / last_target * 100
                if drop_pct > THRESHOLD_DROP_PERCENT:
                    is_significant_drop = True

            minutes_since_change = (now - last_ts) / 60
            
            if is_significant_drop:
                # Immediate adjustment down
                state["stable_target"] = target_power
                state["last_change_ts"] = now
            elif target_power > last_target:
                # Rising: Hold for TIME_HOLD_RISING
                if minutes_since_change >= TIME_HOLD_RISING:
                    state["stable_target"] = target_power
                    state["last_change_ts"] = now
                else:
                    # Keep old target
                    target_power = last_target
            elif target_power < last_target:
                # Falling (small drop): Hold for TIME_HOLD_FALLING
                if minutes_since_change >= TIME_HOLD_FALLING:
                    state["stable_target"] = target_power
                    state["last_change_ts"] = now
                else:
                    target_power = last_target
            
            # If starting (last_target 0), take immediate
            if last_target == 0 and target_power > 0:
                 state["stable_target"] = target_power
                 state["last_change_ts"] = now
        
        # --- 4. Write to Wallbox ---
        base_addr = ADDR_LP1_BASE if index == 1 else ADDR_LP2_BASE
        if base_addr is None: return

        # Write Power (Offset 0x0)
        val_to_write = int(target_power / 100)
        await self.coordinator.async_write_register(base_addr + OFFSET_MAX_POWER, val_to_write)
        
        # Write Phase Mode if calculated (especially in Zoe Mode)
        if target_phase_mode is not None:
             await self.coordinator.async_write_register(base_addr + OFFSET_PHASE_MODE, target_phase_mode)


class CompleoDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching and controlling Compleo Wallbox data."""

    def __init__(self, hass: HomeAssistant, host: str, port: int, name: str) -> None:
        self.host = host
        self.client = AsyncModbusTcpClient(host, port=port, timeout=5)
        self.device_name = name
        self.device_info_map = {} 
        self._strategy_name = None
        
        # Init Logic Controller
        self.logic = CompleoSmartChargingController(self)
        
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

    async def _async_update_data(self):
        """Fetch data AND run logic."""
        try:
            # 1. Fetch Data
            new_data = await self._fetch_wallbox_data()
            
            # 2. Run Logic per Point
            num_points = new_data["system"].get("num_points", 1)
            for i in range(1, num_points + 1):
                self.logic.init_point(i)
                await self.logic.run_logic(i)
            
            return new_data

        except Exception as err:
            _LOGGER.error("Error updating/controlling Compleo: %s", err)
            raise UpdateFailed(f"Communication error: {err}")

    async def _fetch_wallbox_data(self):
        new_data = {"system": {}, "points": {}}
        
        # Detect Points
        num_points = 1
        rr = await self._read_registers_safe("read_input_registers", REG_SYS_NUM_POINTS, 1)
        if rr and not (hasattr(rr, 'isError') and rr.isError()) and len(rr.registers) > 0:
            val = rr.registers[0]
            if val in [1, 2]: num_points = val
        new_data["system"]["num_points"] = num_points

        # System Reads
        rr = await self._read_registers_safe("read_holding_registers", REG_SYS_POWER_LIMIT, 1)
        if rr and hasattr(rr, 'registers') and len(rr.registers)>0: new_data["system"]["power_setpoint_abs"] = rr.registers[0]
        
        rr = await self._read_registers_safe("read_holding_registers", REG_SYS_MAX_SCHIEFLAST, 1)
        if rr and hasattr(rr, 'registers') and len(rr.registers)>0: new_data["system"]["max_schieflast"] = rr.registers[0]
        
        rr = await self._read_registers_safe("read_holding_registers", REG_SYS_FALLBACK_POWER, 1)
        if rr and hasattr(rr, 'registers') and len(rr.registers)>0: new_data["system"]["fallback_power"] = rr.registers[0]

        rr = await self._read_registers_safe("read_input_registers", REG_SYS_FW_PATCH, 2)
        if rr and hasattr(rr, 'registers') and len(rr.registers)>=2:
            new_data["system"]["firmware_version"] = f"{rr.registers[1]>>8}.{rr.registers[1]&0xFF}.{rr.registers[0]>>8}"

        rr = await self._read_registers_safe("read_input_registers", REG_SYS_TOTAL_POWER_READ, 5)
        if rr and hasattr(rr, 'registers') and len(rr.registers)>=5:
            new_data["system"]["total_power"] = rr.registers[0] * 100
            new_data["system"]["total_current_l1"] = rr.registers[1] * 0.1
            new_data["system"]["total_current_l2"] = rr.registers[2] * 0.1
            new_data["system"]["total_current_l3"] = rr.registers[3] * 0.1
            new_data["system"]["unused_power"] = rr.registers[4] * 100

        art = await self._read_string(REG_SYS_ARTICLE_NUM, LEN_STRING_REGISTERS)
        if art: new_data["system"]["article_number"] = art
        ser = await self._read_string(REG_SYS_SERIAL_NUM, LEN_STRING_REGISTERS)
        if ser: new_data["system"]["serial_number"] = ser

        # Point Reads
        sum_sess = 0.0
        sum_tot = 0.0
        found = False
        for i in range(1, num_points + 1):
            pd = await self._read_charging_point_data(i)
            if pd:
                new_data["points"][i] = pd
                sum_sess += pd.get("energy_session", 0)
                sum_tot += pd.get("meter_reading", 0)
                found = True
        
        new_data["system"]["total_energy_session"] = sum_sess
        new_data["system"]["total_energy_total"] = sum_tot
        
        if not found and not new_data["system"]: raise UpdateFailed("No data")
        return new_data

    async def _read_registers_safe(self, func_name, address, count, slave_id=1):
        if not self.client.connected:
            await self.client.connect()
            await asyncio.sleep(0.2)
        func = getattr(self.client, func_name)
        strategies = [
            ("slave_pos_cnt", [address, count], {"slave": slave_id}),
            ("unit_pos_cnt", [address, count], {"unit": slave_id}),
            ("no_unit_pos_cnt", [address, count], {}),
            ("slave_kw_cnt", [address], {"count": count, "slave": slave_id}),
            ("unit_kw_cnt", [address], {"count": count, "unit": slave_id}),
            ("no_unit_kw_cnt", [address], {"count": count})
        ]
        if self._strategy_name:
             for i, (name, _, _) in enumerate(strategies):
                 if name == self._strategy_name:
                     strategies.insert(0, strategies.pop(i))
                     break
        for name, args, kwargs in strategies:
            try:
                result = await func(*args, **kwargs)
                if result is None or (hasattr(result, 'isError') and result.isError()):
                    return result
                if hasattr(result, 'registers') and len(result.registers) < count:
                    continue
                self._strategy_name = name
                return result
            except TypeError: continue
            except Exception: continue
        return None

    async def async_write_register(self, address, value, slave_id=1):
        if not self.client.connected:
            await self.client.connect()
            await asyncio.sleep(0.1)
        async def attempt(kwargs_dict): return await self.client.write_register(address, value, **kwargs_dict)
        attempts = [{"slave": slave_id}, {"unit": slave_id}, {}]
        for kwargs in attempts:
            try:
                res = await attempt(kwargs)
                if res and not (hasattr(res, 'isError') and res.isError()): return res
            except TypeError: continue
            except Exception: continue
        return None

    def _decode_registers_to_string(self, rr, count) -> str | None:
        if rr and hasattr(rr, 'registers'):
            try:
                s = b""
                for reg in rr.registers: s += reg.to_bytes(2, 'big')
                val = s.decode('ascii', errors='ignore').rstrip('\x00').strip()
                if val: return val
            except: pass
        return None

    async def _read_string(self, address, count, name_debug="Unknown") -> str | None:
        rr = await self._read_registers_safe("read_input_registers", address, count)
        val = self._decode_registers_to_string(rr, count)
        if val: return val
        rr_hold = await self._read_registers_safe("read_holding_registers", address, count)
        return self._decode_registers_to_string(rr_hold, count)

    async def _read_charging_point_data(self, index: int) -> dict | None:
        base = ADDR_LP1_BASE if index == 1 else ADDR_LP2_BASE
        if base is None: return None
        data = {}
        
        # Readings
        rr = await self._read_registers_safe("read_holding_registers", base + OFFSET_MAX_POWER, 10)
        if rr and len(rr.registers)>=10:
             data["max_power_limit"] = rr.registers[0]
             data["phase_mode"] = rr.registers[9]

        # Status Block (Offsets 0x001 to 0x008)
        # Register Map:
        # [0] 0x001: Status
        # [1] 0x002: Power
        # [2] 0x003: L1
        # [3] 0x004: L2
        # [4] 0x005: L3
        # [5] 0x006: Time Low Word (detected by user)
        # [6] 0x007: Time High Word
        # [7] 0x008: Energy Session
        rr = await self._read_registers_safe("read_input_registers", base + OFFSET_STATUS_WORD, 8)
        if rr and len(rr.registers)>=8:
             data["status_word"] = rr.registers[0]
             data["current_power"] = rr.registers[1] * 100
             data["current_l1"] = rr.registers[2] * 0.1
             data["current_l2"] = rr.registers[3] * 0.1
             data["current_l3"] = rr.registers[4] * 0.1
             
             # Combined 32-bit Time: Low + (High << 16)
             data["charging_time"] = rr.registers[5] + (rr.registers[6] << 16)
             
             data["energy_session"] = rr.registers[7] * 0.1

        rr = await self._read_registers_safe("read_input_registers", base + OFFSET_PHASE_SWITCHES, 6)
        if rr and len(rr.registers)>=6:
             data["phase_switch_count"] = rr.registers[0]
             data["error_code"] = rr.registers[1]
             data["status_code"] = rr.registers[2]
             data["voltage_l1"] = rr.registers[3]
             data["voltage_l2"] = rr.registers[4]
             data["voltage_l3"] = rr.registers[5]
        
        rfid = await self._read_string(base + OFFSET_RFID_TAG, 10)
        if rfid: data["rfid_tag"] = rfid
        
        rr = await self._read_registers_safe("read_input_registers", base + OFFSET_METER_READING, 1)
        if rr and len(rr.registers)>0: data["meter_reading"] = rr.registers[0] * 0.1
        
        rr = await self._read_registers_safe("read_input_registers", base + OFFSET_DERATING_STATUS, 1)
        if rr and len(rr.registers)>0: data["derating_status"] = rr.registers[0]

        return data