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

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL

# Supported platforms
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.SELECT]

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Compleo Wallbox from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    name = entry.data.get(CONF_NAME, "Compleo Wallbox")

    coordinator = CompleoDataUpdateCoordinator(hass, host, port, name)

    # Allow startup even if offline
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
        # Slightly longer timeout for stability
        self.client = AsyncModbusTcpClient(host, port=port, timeout=5)
        self.device_name = name
        self.device_info_map = {} 
        self._strategy_name = None
        # Track if we found LP1 at 0x1000 or 0x0000
        self._lp_base_offset = None 
        
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
        # Group A: Positional Count
        strategies.append(("slave_pos_cnt", [address, count], {"slave": slave_id}))
        strategies.append(("unit_pos_cnt", [address, count], {"unit": slave_id}))
        strategies.append(("no_unit_pos_cnt", [address, count], {}))
        
        # Group B: Keyword Count (Fix for 'takes 2 but 3 given')
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
                    # Functional error (device responded with error or timeout)
                    # This implies the args were accepted.
                    if self._strategy_name == name or not self._strategy_name:
                         pass # Debug logging skipped to reduce noise
                    return result

                # Check register count to prevent "list index out of range"
                if hasattr(result, 'registers') and len(result.registers) < count:
                    _LOGGER.debug("Strategy '%s' returned %d regs, expected %d", name, len(result.registers), count)
                    continue

                self._strategy_name = name
                return result

            except TypeError:
                continue
            except Exception as e:
                last_error = e
                continue

        _LOGGER.debug("Failed to read 0x%04x. Last error: %s", address, last_error)
        return None

    async def _read_string(self, address, count) -> str | None:
        """Helper to read a string from registers."""
        rr = await self._read_registers_safe("read_input_registers", address, count)
        if rr and not (hasattr(rr, 'isError') and rr.isError()) and len(rr.registers) == count:
            try:
                # Convert registers to string (2 chars per register)
                s = b""
                for reg in rr.registers:
                    s += reg.to_bytes(2, 'big')
                return s.decode('ascii').rstrip('\x00').strip()
            except Exception:
                pass
        return None

    async def _read_charging_point_data(self, index: int) -> dict | None:
        """Read data for a specific charging point."""
        
        # Determine Base Address
        # If we haven't determined the map yet, try 0x1000 first, then 0x0000 (for LP1)
        base_address = index * 0x1000
        
        if index == 1 and self._lp_base_offset == 0:
            base_address = 0x0000
        
        data = {}

        # --- Block 1: Status/Power/Energy ---
        # Try reading at offset 1
        # If base is 0x0000, 0x0001 might overlap with Holding 0x0001 (Limit %)
        # BUT Input and Holding are different memory areas.
        start_addr_1 = base_address + 0x001
        
        rr_block1 = await self._read_registers_safe("read_input_registers", start_addr_1, 8)
        
        # FALLBACK DETECTION (Only for LP1)
        if (not rr_block1 or (hasattr(rr_block1, 'isError') and rr_block1.isError())) and index == 1 and self._lp_base_offset is None:
            _LOGGER.debug("LP1 at 0x1000 failed, trying 0x0000 map...")
            base_address = 0x0000
            start_addr_1 = 0x0001
            rr_block1 = await self._read_registers_safe("read_input_registers", start_addr_1, 8)
            if rr_block1 and not (hasattr(rr_block1, 'isError') and rr_block1.isError()):
                self._lp_base_offset = 0 # Remember that we are on a flat map
                _LOGGER.info("Detected Compleo Legacy Map (Base 0x0000)")

        if not rr_block1 or (hasattr(rr_block1, 'isError') and rr_block1.isError()):
            return None

        # Safe parsing
        regs = rr_block1.registers
        if len(regs) >= 8:
            data["status_word"] = regs[0]
            data["current_power"] = regs[1] * 100 
            data["current_l1"] = regs[2] * 0.1    
            data["current_l2"] = regs[3] * 0.1
            data["current_l3"] = regs[4] * 0.1
            data["energy_total"] = regs[7] * 0.1  

        # --- Block 2: Voltages ---
        start_addr_2 = base_address + 0x00A
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
        addr_hold = base_address + 0x009
        rr_hold = await self._read_registers_safe("read_holding_registers", addr_hold, 1)
        if rr_hold and not (hasattr(rr_hold, 'isError') and rr_hold.isError()) and len(rr_hold.registers) > 0:
            data["phase_mode"] = rr_hold.registers[0]

        return data

    async def _async_update_data(self):
        """Fetch data from the wallbox."""
        try:
            new_data = {"system": {}, "points": {}}
            
            # 1. Global Limit (Probe) - 0x0000
            rr_hold = await self._read_registers_safe("read_holding_registers", 0x0000, 1)
            if rr_hold and not (hasattr(rr_hold, 'isError') and rr_hold.isError()) and len(rr_hold.registers) > 0:
                new_data["system"]["power_setpoint_abs"] = rr_hold.registers[0]
            else:
                 raise UpdateFailed(f"Could not read Global Register 0x0000. Result: {rr_hold}")

            # 2. System Info (Firmware) - 0x0006 (2 regs)
            rr_sys = await self._read_registers_safe("read_input_registers", 0x0006, 2)
            if rr_sys and not (hasattr(rr_sys, 'isError') and rr_sys.isError()) and len(rr_sys.registers) >= 2:
                # 0x0006: Patch, 0x0007: Major/Minor
                patch = rr_sys.registers[0]
                major = rr_sys.registers[1] >> 8
                minor = rr_sys.registers[1] & 0xFF
                # Note: PDF says 0x0006 is "Patch << 8". 
                # If reading 0x0006 gave a value like 0x0500 (1280), Patch is 5.
                patch = patch >> 8 
                new_data["system"]["firmware_version"] = f"{major}.{minor}.{patch}"

            # 3. New Infos (Article/Serial) - Try Common Registers
            # These are guessed based on standard Compleo maps
            # Article Number often around 0x0020 (String)
            art_num = await self._read_string(0x0020, 10)
            if art_num: new_data["system"]["article_number"] = art_num
            
            # Serial Number often around 0x0030 (String)
            ser_num = await self._read_string(0x0030, 10)
            if ser_num: new_data["system"]["serial_number"] = ser_num

            # 4. Points
            lp1_data = await self._read_charging_point_data(1)
            if lp1_data:
                new_data["points"][1] = lp1_data

            # Only check LP2 if we are NOT on the flat map (Solo typically flat)
            if self._lp_base_offset != 0:
                lp2_data = await self._read_charging_point_data(2)
                if lp2_data:
                    new_data["points"][2] = lp2_data

            # 5. Totals
            total_power = 0
            for p in new_data["points"].values():
                total_power += p.get("current_power", 0)
            new_data["system"]["total_power"] = total_power

            return new_data

        except Exception as err:
            _LOGGER.error("Error updating Compleo data: %s", err)
            raise UpdateFailed(f"Communication error: {err}")