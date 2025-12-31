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
    REG_SYS_ARTICLE_NUM,
    REG_SYS_SERIAL_NUM,
    LEN_STRING_REGISTERS,
    REG_SYS_TOTAL_POWER_READ,
    REG_SYS_TOTAL_CURRENT_L1,
    REG_SYS_TOTAL_CURRENT_L2,
    REG_SYS_TOTAL_CURRENT_L3,
    REG_SYS_UNUSED_POWER,
    REG_SYS_RFID_TAG,
    ADDR_LP1_BASE,
    ADDR_LP2_BASE,
    OFFSET_STATUS_WORD,
    OFFSET_POWER,
    OFFSET_CURRENT_L1,
    OFFSET_CURRENT_L2,
    OFFSET_CURRENT_L3,
    OFFSET_ENERGY,
    OFFSET_PHASE_SWITCHES,
    OFFSET_STATUS_CODE,
    OFFSET_VOLTAGE_L1,
    OFFSET_VOLTAGE_L2,
    OFFSET_VOLTAGE_L3,
    OFFSET_PHASE_MODE
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
            "system": {},
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
        """Public helper to write a register using the discovered strategy."""
        if not self.client.connected:
            await self.client.connect()
            await asyncio.sleep(0.1)

        kwargs = {}
        if self._strategy_name:
            if "slave" in self._strategy_name:
                kwargs["slave"] = slave_id
            elif "unit" in self._strategy_name:
                kwargs["unit"] = slave_id
        else:
            kwargs["slave"] = slave_id

        try:
            return await self.client.write_register(address, value, **kwargs)
        except TypeError:
            if "slave" in kwargs:
                kwargs.pop("slave")
                kwargs["unit"] = slave_id
                return await self.client.write_register(address, value, **kwargs)
            raise

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
        
        if index == 1:
            base_address = ADDR_LP1_BASE
        elif index == 2:
            base_address = ADDR_LP2_BASE
        else:
            return None
        
        data = {}

        # --- Block 1: Status/Power/Energy (Input) ---
        start_addr_1 = base_address + OFFSET_STATUS_WORD
        rr_block1 = await self._read_registers_safe("read_input_registers", start_addr_1, 8)
        
        if not rr_block1 or (hasattr(rr_block1, 'isError') and rr_block1.isError()):
            return None

        regs = rr_block1.registers
        if len(regs) >= 8:
            data["status_word"] = regs[0]
            data["current_power"] = regs[1] * 100 
            data["current_l1"] = regs[2] * 0.1    
            data["current_l2"] = regs[3] * 0.1
            data["current_l3"] = regs[4] * 0.1
            data["energy_total"] = regs[7] * 0.1  

        # --- Block 2: Voltages (Input) ---
        start_addr_2 = base_address + OFFSET_PHASE_SWITCHES
        rr_block2 = await self._read_registers_safe("read_input_registers", start_addr_2, 6)
        
        data.update({"status_code": 0, "voltage_l1": 0, "voltage_l2": 0, "voltage_l3": 0})
        
        if rr_block2 and not (hasattr(rr_block2, 'isError') and rr_block2.isError()):
            regs = rr_block2.registers
            if len(regs) >= 6:
                data["phase_switch_count"] = regs[0]
                data["status_code"] = regs[2]
                data["voltage_l1"] = regs[3]
                data["voltage_l2"] = regs[4]
                data["voltage_l3"] = regs[5]

        # --- Phase Mode (Holding) ---
        addr_hold = base_address + OFFSET_PHASE_MODE
        rr_hold = await self._read_registers_safe("read_holding_registers", addr_hold, 1)
        if rr_hold and not (hasattr(rr_hold, 'isError') and rr_hold.isError()) and len(rr_hold.registers) > 0:
            data["phase_mode"] = rr_hold.registers[0]

        return data

    async def _async_update_data(self):
        """Fetch data from the wallbox."""
        try:
            new_data = {"system": {}, "points": {}}
            
            # 1. Global Holdings (Configuration)
            rr = await self._read_registers_safe("read_holding_registers", REG_SYS_POWER_LIMIT, 1)
            if rr and not (hasattr(rr, 'isError') and rr.isError()) and len(rr.registers) > 0:
                new_data["system"]["power_setpoint_abs"] = rr.registers[0]
            
            rr = await self._read_registers_safe("read_holding_registers", REG_SYS_MAX_SCHIEFLAST, 1)
            if rr and not (hasattr(rr, 'isError') and rr.isError()) and len(rr.registers) > 0:
                new_data["system"]["max_schieflast"] = rr.registers[0]

            rr = await self._read_registers_safe("read_holding_registers", REG_SYS_FALLBACK_POWER, 1)
            if rr and not (hasattr(rr, 'isError') and rr.isError()) and len(rr.registers) > 0:
                new_data["system"]["fallback_power"] = rr.registers[0]

            # 2. System Info / Inputs (Firmware, Total Power, Currents)
            rr_sys = await self._read_registers_safe("read_input_registers", REG_SYS_FW_PATCH, 2)
            if rr_sys and not (hasattr(rr_sys, 'isError') and rr_sys.isError()) and len(rr_sys.registers) >= 2:
                patch = rr_sys.registers[0] >> 8 
                major = rr_sys.registers[1] >> 8
                minor = rr_sys.registers[1] & 0xFF
                new_data["system"]["firmware_version"] = f"{major}.{minor}.{patch}"

            # Read Global Input Block (0x0009 - 0x000D) - 5 registers
            rr_ins = await self._read_registers_safe("read_input_registers", REG_SYS_TOTAL_POWER_READ, 5)
            if rr_ins and not (hasattr(rr_ins, 'isError') and rr_ins.isError()) and len(rr_ins.registers) >= 5:
                # 0x0009: Total Power
                new_data["system"]["total_power"] = rr_ins.registers[0] * 100 # Annahme 100W Schritte
                # 0x000A: Total Current L1
                new_data["system"]["total_current_l1"] = rr_ins.registers[1] * 0.1 # Annahme 0.1A
                # 0x000B: Total Current L2
                new_data["system"]["total_current_l2"] = rr_ins.registers[2] * 0.1
                # 0x000C: Total Current L3
                new_data["system"]["total_current_l3"] = rr_ins.registers[3] * 0.1
                # 0x000D: Unused Power
                new_data["system"]["unused_power"] = rr_ins.registers[4] * 100 # Annahme 100W

            # RFID Tag separate read (if string)
            rfid = await self._read_string(REG_SYS_RFID_TAG, 10, "RFID")
            if rfid: new_data["system"]["rfid_tag"] = rfid

            # 3. Strings (Article/Serial)
            art_num = await self._read_string(REG_SYS_ARTICLE_NUM, LEN_STRING_REGISTERS, "Article Num")
            if art_num: new_data["system"]["article_number"] = art_num
            
            ser_num = await self._read_string(REG_SYS_SERIAL_NUM, LEN_STRING_REGISTERS, "Serial Num")
            if ser_num: new_data["system"]["serial_number"] = ser_num

            # 4. Points
            lp1_data = await self._read_charging_point_data(1)
            if lp1_data:
                new_data["points"][1] = lp1_data

            if ADDR_LP2_BASE != ADDR_LP1_BASE:
                lp2_data = await self._read_charging_point_data(2)
                if lp2_data:
                    new_data["points"][2] = lp2_data

            # Check if we have any data
            if not new_data["points"] and not new_data["system"]:
                 raise UpdateFailed("No data received from Wallbox")

            return new_data

        except Exception as err:
            _LOGGER.error("Error updating Compleo data: %s", err)
            raise UpdateFailed(f"Communication error: {err}")