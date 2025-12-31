"""The Compleo Wallbox integration."""
from __future__ import annotations

import asyncio
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
    DOMAIN, 
    DEFAULT_SCAN_INTERVAL,
    REG_SYS_POWER_LIMIT,
    REG_SYS_MAX_SCHIEFLAST,
    REG_SYS_FALLBACK_POWER,
    REG_SYS_FW_PATCH,
    REG_SYS_NUM_POINTS,
    REG_SYS_ARTICLE_NUM,
    REG_SYS_SERIAL_NUM,
    LEN_STRING_REGISTERS,
    REG_SYS_TOTAL_POWER_READ,
    REG_SYS_TOTAL_CURRENT_L1,
    REG_SYS_TOTAL_CURRENT_L2,
    REG_SYS_TOTAL_CURRENT_L3,
    REG_SYS_UNUSED_POWER,
    ADDR_LP1_BASE,
    ADDR_LP2_BASE,
    OFFSET_MAX_POWER,
    OFFSET_STATUS_WORD,
    OFFSET_POWER,
    OFFSET_CURRENT_L1,
    OFFSET_CURRENT_L2,
    OFFSET_CURRENT_L3,
    OFFSET_CHARGING_TIME,
    OFFSET_ENERGY,
    OFFSET_PHASE_SWITCHES,
    OFFSET_ERROR_CODE,
    OFFSET_STATUS_CODE,
    OFFSET_VOLTAGE_L1,
    OFFSET_VOLTAGE_L2,
    OFFSET_VOLTAGE_L3,
    OFFSET_PHASE_MODE,
    OFFSET_RFID_TAG,
    OFFSET_METER_READING,
    OFFSET_DERATING_STATUS
)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.SELECT]

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Compleo Wallbox from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    name = entry.data.get(CONF_NAME, "Compleo Wallbox")

    coordinator = CompleoDataUpdateCoordinator(hass, host, port, name)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as e:
        _LOGGER.warning("Initial data fetch failed for %s (%s). Will retry in background.", host, e)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        if coordinator.client.connected:
            coordinator.client.close()
    return unload_ok

class CompleoDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Compleo Wallbox data."""

    def __init__(self, hass: HomeAssistant, host: str, port: int, name: str) -> None:
        self.host = host
        self.client = AsyncModbusTcpClient(host, port=port, timeout=5)
        self.device_name = name
        self.device_info_map = {} 
        self._strategy_name = None
        
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{host}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        
        self.data = {
            "system": {
                "num_points": 1 # Default
            },
            "points": {}
        }

    async def _read_registers_safe(self, func_name, address, count, slave_id=1):
        """Helper to call Modbus read functions trying multiple signatures."""
        if not self.client.connected:
            await self.client.connect()
            await asyncio.sleep(0.2)

        func = getattr(self.client, func_name)
        
        strategies = []
        # Group A: Positional
        strategies.append(("slave_pos_cnt", [address, count], {"slave": slave_id}))
        strategies.append(("unit_pos_cnt", [address, count], {"unit": slave_id}))
        strategies.append(("no_unit_pos_cnt", [address, count], {}))
        # Group B: Keyword Count
        strategies.append(("slave_kw_cnt", [address], {"count": count, "slave": slave_id}))
        strategies.append(("unit_kw_cnt", [address], {"count": count, "unit": slave_id}))
        strategies.append(("no_unit_kw_cnt", [address], {"count": count}))
        
        if self._strategy_name:
             for i, (name, _, _) in enumerate(strategies):
                 if name == self._strategy_name:
                     strategies.insert(0, strategies.pop(i))
                     break

        last_error = None
        for name, args, kwargs in strategies:
            try:
                result = await func(*args, **kwargs)
                if result is None or (hasattr(result, 'isError') and result.isError()):
                    return result

                if hasattr(result, 'registers') and len(result.registers) < count:
                    continue

                self._strategy_name = name
                return result

            except TypeError:
                continue
            except Exception as e:
                last_error = e
                continue

        return None

    async def async_write_register(self, address, value, slave_id=1):
        """Public helper to write a register."""
        if not self.client.connected:
            await self.client.connect()
            await asyncio.sleep(0.1)

        async def attempt(kwargs_dict):
            return await self.client.write_register(address, value, **kwargs_dict)

        attempts = [
            {"slave": slave_id}, 
            {"unit": slave_id}, 
            {} 
        ]

        last_error = None
        for kwargs in attempts:
            try:
                result = await attempt(kwargs)
                if result and not (hasattr(result, 'isError') and result.isError()):
                    return result 
                if result and hasattr(result, 'isError') and result.isError():
                     _LOGGER.warning("Write rejected by device (params: %s): %s", kwargs, result)
                     return result 
            except TypeError as te:
                last_error = te
                continue
            except Exception as e:
                last_error = e
                continue

        _LOGGER.error("Failed to write to 0x%04x. All variants failed. Last error: %s", address, last_error)
        return None

    def _decode_registers_to_string(self, rr, count) -> str | None:
        if rr and not (hasattr(rr, 'isError') and rr.isError()) and hasattr(rr, 'registers'):
            try:
                s = b""
                for reg in rr.registers:
                    s += reg.to_bytes(2, 'big')
                val = s.decode('ascii', errors='ignore').rstrip('\x00').strip()
                if val and len(val) > 0:
                    return val
            except Exception:
                pass
        return None

    async def _read_string(self, address, count, name_debug="Unknown") -> str | None:
        """Helper to read a string from registers (tries Input then Holding)."""
        rr = await self._read_registers_safe("read_input_registers", address, count)
        val = self._decode_registers_to_string(rr, count)
        if val:
            return val
            
        rr_hold = await self._read_registers_safe("read_holding_registers", address, count)
        val_hold = self._decode_registers_to_string(rr_hold, count)
        if val_hold:
            return val_hold
        return None

    async def _read_charging_point_data(self, index: int) -> dict | None:
        """Read data for a specific charging point."""
        
        base_address = None
        if index == 1:
            base_address = ADDR_LP1_BASE
        elif index == 2:
            base_address = ADDR_LP2_BASE
        
        if base_address is None:
            return None
        
        data = {}

        # 1. HOLDING: Max Power (0x0) + Phase Mode (0x9)
        addr_hold_0 = base_address + OFFSET_MAX_POWER
        rr_hold = await self._read_registers_safe("read_holding_registers", addr_hold_0, 10)
        if rr_hold and not (hasattr(rr_hold, 'isError') and rr_hold.isError()) and len(rr_hold.registers) >= 10:
             data["max_power_limit"] = rr_hold.registers[0]
             data["phase_mode"] = rr_hold.registers[9]

        # 2. INPUT Block 1: Status, Power, Currents, Time, Energy Session (0x1 .. 0x8)
        start_addr_1 = base_address + OFFSET_STATUS_WORD
        rr_block1 = await self._read_registers_safe("read_input_registers", start_addr_1, 8)
        
        if rr_block1 and not (hasattr(rr_block1, 'isError') and rr_block1.isError()):
            regs = rr_block1.registers
            if len(regs) >= 8:
                data["status_word"] = regs[0]
                data["current_power"] = regs[1] * 100 
                data["current_l1"] = regs[2] * 0.1    
                data["current_l2"] = regs[3] * 0.1
                data["current_l3"] = regs[4] * 0.1
                data["charging_time"] = regs[5]
                data["energy_session"] = regs[7] * 0.1 

        # 3. INPUT Block 2: Phase Switches, Error, Status, Voltages (0xA .. 0xF)
        start_addr_2 = base_address + OFFSET_PHASE_SWITCHES
        rr_block2 = await self._read_registers_safe("read_input_registers", start_addr_2, 6)
        
        data.update({"status_code": 0, "error_code": 0, "voltage_l1": 0, "voltage_l2": 0, "voltage_l3": 0})
        
        if rr_block2 and not (hasattr(rr_block2, 'isError') and rr_block2.isError()):
            regs = rr_block2.registers
            if len(regs) >= 6:
                data["phase_switch_count"] = regs[0]
                data["error_code"] = regs[1]
                data["status_code"] = regs[2]
                data["voltage_l1"] = regs[3]
                data["voltage_l2"] = regs[4]
                data["voltage_l3"] = regs[5]

        # 4. RFID (0x10)
        addr_rfid = base_address + OFFSET_RFID_TAG
        rfid_val = await self._read_string(addr_rfid, 10, f"LP{index} RFID")
        if rfid_val:
            data["rfid_tag"] = rfid_val

        # 5. Meter Reading (Lifetime) (0x18)
        addr_meter = base_address + OFFSET_METER_READING
        rr_meter = await self._read_registers_safe("read_input_registers", addr_meter, 1)
        if rr_meter and not (hasattr(rr_meter, 'isError') and rr_meter.isError()) and len(rr_meter.registers) > 0:
             data["meter_reading"] = rr_meter.registers[0] * 0.1

        # 6. Derating (0x1A)
        addr_derating = base_address + OFFSET_DERATING_STATUS
        rr_derating = await self._read_registers_safe("read_input_registers", addr_derating, 1)
        if rr_derating and not (hasattr(rr_derating, 'isError') and rr_derating.isError()) and len(rr_derating.registers) > 0:
            data["derating_status"] = rr_derating.registers[0]

        return data

    async def _async_update_data(self):
        """Fetch data from the wallbox."""
        try:
            new_data = {"system": {}, "points": {}}
            
            # --- DETECT NUMBER OF POINTS ---
            # Try to read 0x0008 (Global Input). If fail, default to 1.
            num_points = 1
            rr_points = await self._read_registers_safe("read_input_registers", REG_SYS_NUM_POINTS, 1)
            if rr_points and not (hasattr(rr_points, 'isError') and rr_points.isError()) and len(rr_points.registers) > 0:
                val = rr_points.registers[0]
                if val in [1, 2]:
                    num_points = val
                    _LOGGER.debug("Detected %d charging points from register 0x0008", num_points)
                else:
                    _LOGGER.warning("Register 0x0008 returned %d points. Defaulting to 1.", val)
            
            new_data["system"]["num_points"] = num_points

            # 1. Global Holdings
            rr = await self._read_registers_safe("read_holding_registers", REG_SYS_POWER_LIMIT, 1)
            if rr and not (hasattr(rr, 'isError') and rr.isError()) and len(rr.registers) > 0:
                new_data["system"]["power_setpoint_abs"] = rr.registers[0]
            
            rr = await self._read_registers_safe("read_holding_registers", REG_SYS_MAX_SCHIEFLAST, 1)
            if rr and not (hasattr(rr, 'isError') and rr.isError()) and len(rr.registers) > 0:
                new_data["system"]["max_schieflast"] = rr.registers[0]

            rr = await self._read_registers_safe("read_holding_registers", REG_SYS_FALLBACK_POWER, 1)
            if rr and not (hasattr(rr, 'isError') and rr.isError()) and len(rr.registers) > 0:
                new_data["system"]["fallback_power"] = rr.registers[0]

            # 2. System Info / Inputs
            rr_sys = await self._read_registers_safe("read_input_registers", REG_SYS_FW_PATCH, 2)
            if rr_sys and not (hasattr(rr_sys, 'isError') and rr_sys.isError()) and len(rr_sys.registers) >= 2:
                patch = rr_sys.registers[0] >> 8 
                major = rr_sys.registers[1] >> 8
                minor = rr_sys.registers[1] & 0xFF
                new_data["system"]["firmware_version"] = f"{major}.{minor}.{patch}"

            rr_ins = await self._read_registers_safe("read_input_registers", REG_SYS_TOTAL_POWER_READ, 5)
            if rr_ins and not (hasattr(rr_ins, 'isError') and rr_ins.isError()) and len(rr_ins.registers) >= 5:
                new_data["system"]["total_power"] = rr_ins.registers[0] * 100 
                new_data["system"]["total_current_l1"] = rr_ins.registers[1] * 0.1 
                new_data["system"]["total_current_l2"] = rr_ins.registers[2] * 0.1
                new_data["system"]["total_current_l3"] = rr_ins.registers[3] * 0.1
                new_data["system"]["unused_power"] = rr_ins.registers[4] * 100 

            # 3. Strings
            art_num = await self._read_string(REG_SYS_ARTICLE_NUM, LEN_STRING_REGISTERS, "Article Num")
            if art_num: new_data["system"]["article_number"] = art_num
            
            ser_num = await self._read_string(REG_SYS_SERIAL_NUM, LEN_STRING_REGISTERS, "Serial Num")
            if ser_num: new_data["system"]["serial_number"] = ser_num

            # 4. Points (Dynamic Loop)
            for i in range(1, num_points + 1):
                lp_data = await self._read_charging_point_data(i)
                if lp_data:
                    new_data["points"][i] = lp_data

            # 5. Calculate System Totals
            sum_energy_session = 0.0
            sum_energy_total = 0.0
            points_found = False
            
            for p in new_data["points"].values():
                val_session = p.get("energy_session")
                if val_session is not None:
                    sum_energy_session += val_session
                    points_found = True
                
                val_total = p.get("meter_reading")
                if val_total is not None:
                    sum_energy_total += val_total
            
            new_data["system"]["total_energy_session"] = sum_energy_session
            new_data["system"]["total_energy_total"] = sum_energy_total

            if not points_found and not new_data["system"]:
                 raise UpdateFailed("No data received from Wallbox")

            return new_data

        except Exception as err:
            _LOGGER.error("Error updating Compleo data: %s", err)
            raise UpdateFailed(f"Communication error: {err}")