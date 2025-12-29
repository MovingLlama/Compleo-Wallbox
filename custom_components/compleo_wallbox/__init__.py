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
        # Stores the name of the working strategy (e.g. "slave_kw", "no_unit_cnt_kw")
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
        
        # 1. Ensure Connection
        if not self.client.connected:
            await self.client.connect()
            await asyncio.sleep(0.2)

        func = getattr(self.client, func_name)
        
        # Define strategies: (name, args_list, kwargs_dict)
        strategies = []
        
        # Group A: Positional Count (Standard)
        # 1. slave keyword
        strategies.append(("slave_pos_cnt", [address, count], {"slave": slave_id}))
        # 2. unit keyword
        strategies.append(("unit_pos_cnt", [address, count], {"unit": slave_id}))
        # 3. No ID (Fallback)
        strategies.append(("no_unit_pos_cnt", [address, count], {}))
        
        # Group B: Keyword Count (For strict signatures causing "takes 2 but 3 given")
        # 4. slave keyword, count keyword
        strategies.append(("slave_kw_cnt", [address], {"count": count, "slave": slave_id}))
        # 5. unit keyword, count keyword
        strategies.append(("unit_kw_cnt", [address], {"count": count, "unit": slave_id}))
        # 6. No ID, count keyword
        strategies.append(("no_unit_kw_cnt", [address], {"count": count}))
        
        # Group C: Positional ID (Old pymodbus)
        # 7. Positional ID
        strategies.append(("pos_all", [address, count, slave_id], {}))
        
        # Optimization: Try the last successful strategy first
        if self._strategy_name:
             for i, (name, _, _) in enumerate(strategies):
                 if name == self._strategy_name:
                     strategies.insert(0, strategies.pop(i))
                     break

        last_error = None

        for name, args, kwargs in strategies:
            try:
                # Execute strategy
                result = await func(*args, **kwargs)
                
                # Check for functional failure (Timeout/Modbus Exception)
                if result is None or (hasattr(result, 'isError') and result.isError()):
                    # The call signature was accepted, but the device didn't reply correctly.
                    # We accept this as the "correct" strategy but failed communication.
                    
                    # Log debug info but don't spam warning unless it's the strategy we thought worked
                    if self._strategy_name == name or not self._strategy_name:
                         if result is None:
                             _LOGGER.debug("Read None (Timeout?) with strategy '%s' at 0x%04x", name, address)
                         else:
                             _LOGGER.debug("Modbus Error with strategy '%s' at 0x%04x: %s", name, address, result)
                    
                    return result

                # Check if we got the expected number of registers
                # (Prevents "list index out of range" if device returns partial data)
                if hasattr(result, 'registers') and len(result.registers) < count:
                    _LOGGER.debug("Strategy '%s' returned fewer registers (%d) than requested (%d)", 
                                  name, len(result.registers), count)
                    # Treat as failure for this strategy
                    continue

                # Success!
                self._strategy_name = name
                return result

            except TypeError as te:
                # Signature mismatch (unexpected keyword, wrong arg count)
                # This is normal during discovery
                last_error = te
                continue
                
            except Exception as e:
                # Other errors (connection lost, etc)
                _LOGGER.warning("Exception reading 0x%04x with strategy '%s': %s", address, name, e)
                last_error = e
                continue

        _LOGGER.error("Failed to read 0x%04x. All strategies failed. Last error: %s", address, last_error)
        return None

    async def _read_charging_point_data(self, index: int) -> dict | None:
        """Read data for a specific charging point (1 or 2)."""
        base_address = index * 0x1000
        data = {}

        # Offset 1 (0xX001) for Status Word
        start_addr_1 = base_address + 0x001
        rr_block1 = await self._read_registers_safe("read_input_registers", start_addr_1, 8)
        
        if not rr_block1 or (hasattr(rr_block1, 'isError') and rr_block1.isError()):
            return None

        regs = rr_block1.registers
        data["status_word"] = regs[0]
        data["current_power"] = regs[1] * 100 # W
        data["current_l1"] = regs[2] * 0.1    # A
        data["current_l2"] = regs[3] * 0.1
        data["current_l3"] = regs[4] * 0.1
        data["energy_total"] = regs[7] * 0.1  # kWh

        # Offset A (0xX00A)
        start_addr_2 = base_address + 0x00A
        rr_block2 = await self._read_registers_safe("read_input_registers", start_addr_2, 6)
        
        if rr_block2 and not (hasattr(rr_block2, 'isError') and rr_block2.isError()):
            regs = rr_block2.registers
            data["phase_switch_count"] = regs[0] # 0xX00A
            data["status_code"] = regs[2]        # 0xX00C
            data["voltage_l1"] = regs[3]         # 0xX00D
            data["voltage_l2"] = regs[4]         # 0xX00E
            data["voltage_l3"] = regs[5]         # 0xX00F
        else:
            data.update({"status_code": 0, "voltage_l1": 0, "voltage_l2": 0, "voltage_l3": 0})
            
        # Holding Register for Phase Mode (0xX009)
        addr_hold = base_address + 0x009
        rr_hold = await self._read_registers_safe("read_holding_registers", addr_hold, 1)
        if rr_hold and not (hasattr(rr_hold, 'isError') and rr_hold.isError()):
            data["phase_mode"] = rr_hold.registers[0]

        return data

    async def _async_update_data(self):
        """Fetch data from the wallbox."""
        try:
            new_data = {"system": {}, "points": {}}
            
            # --- 0. Connection Probe ---
            # Using 0x0000 (Holding)
            rr_hold = await self._read_registers_safe("read_holding_registers", 0x0000, 1)
            
            if rr_hold and not (hasattr(rr_hold, 'isError') and rr_hold.isError()):
                new_data["system"]["power_setpoint_abs"] = rr_hold.registers[0]
            else:
                 # If probe fails, raise error to mark availability
                 raise UpdateFailed(f"Could not read Global Register 0x0000. Result: {rr_hold}")

            # --- 1. System Info ---
            # 0x0006
            rr_sys = await self._read_registers_safe("read_input_registers", 0x0006, 2)
            if rr_sys and not (hasattr(rr_sys, 'isError') and rr_sys.isError()):
                major = rr_sys.registers[1] >> 8
                minor = rr_sys.registers[1] & 0xFF
                patch = rr_sys.registers[0] >> 8
                new_data["system"]["firmware_version"] = f"{major}.{minor}.{patch}"

            # --- 2. Charging Points ---
            lp1_data = await self._read_charging_point_data(1)
            if lp1_data:
                new_data["points"][1] = lp1_data

            lp2_data = await self._read_charging_point_data(2)
            if lp2_data:
                new_data["points"][2] = lp2_data

            # --- 3. Totals ---
            total_power = 0
            total_l1 = 0
            total_l2 = 0
            total_l3 = 0
            
            for p in new_data["points"].values():
                total_power += p.get("current_power", 0)
                total_l1 += p.get("current_l1", 0)
                total_l2 += p.get("current_l2", 0)
                total_l3 += p.get("current_l3", 0)
            
            new_data["system"]["total_power"] = total_power
            new_data["system"]["total_current_l1"] = total_l1
            new_data["system"]["total_current_l2"] = total_l2
            new_data["system"]["total_current_l3"] = total_l3

            return new_data

        except Exception as err:
            _LOGGER.error("Error updating Compleo data: %s", err)
            raise UpdateFailed(f"Communication error: {err}")