"""The Compleo Wallbox integration."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException
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
        # Standard pymodbus v3+ uses 'slave'
        self._param_name = "slave" 
        
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
        """Helper to call Modbus read functions."""
        
        # 1. Ensure Connection
        if not self.client.connected:
            await self.client.connect()
            await asyncio.sleep(0.2)

        func = getattr(self.client, func_name)
        
        # 2. Try Reading (Simplified Logic)
        # Instead of looping wildly, we try the standard 'slave' first.
        # If that fails specifically on parameter error, we fallback.
        try:
            # Attempt 1: Standard 'slave'
            kwargs = {self._param_name: slave_id}
            result = await func(address, count, **kwargs)
            
            # Check for error
            if result is None or result.isError():
                # If it's a connection error, result might be Error or None.
                # We try to reconnect once.
                _LOGGER.debug("Read failed at 0x%04x. Reconnecting...", address)
                self.client.close()
                await asyncio.sleep(0.2)
                await self.client.connect()
                await asyncio.sleep(0.2)
                result = await func(address, count, **kwargs)

            if result is not None and not result.isError():
                return result
            else:
                _LOGGER.warning("Modbus Error reading 0x%04x: %s", address, result)
                return None

        except Exception as e:
            _LOGGER.error("Exception reading 0x%04x: %s", address, e)
            self.client.close()
            return None

    async def _read_charging_point_data(self, index: int) -> dict | None:
        """Read data for a specific charging point (1 or 2)."""
        base_address = index * 0x1000
        data = {}

        # REVERTED TO 0-BASED: 
        # Offset 1 (0xX001) for Status Word
        start_addr_1 = base_address + 0x001
        rr_block1 = await self._read_registers_safe("read_input_registers", start_addr_1, 8)
        
        if not rr_block1 or rr_block1.isError():
            return None

        regs = rr_block1.registers
        data["status_word"] = regs[0]
        data["current_power"] = regs[1] * 100 # W
        data["current_l1"] = regs[2] * 0.1    # A
        data["current_l2"] = regs[3] * 0.1
        data["current_l3"] = regs[4] * 0.1
        data["energy_total"] = regs[7] * 0.1  # kWh

        # REVERTED TO 0-BASED:
        # Offset A (0xX00A)
        start_addr_2 = base_address + 0x00A
        rr_block2 = await self._read_registers_safe("read_input_registers", start_addr_2, 6)
        
        if rr_block2 and not rr_block2.isError():
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
        if rr_hold and not rr_hold.isError():
            data["phase_mode"] = rr_hold.registers[0]

        return data

    async def _async_update_data(self):
        """Fetch data from the wallbox."""
        try:
            new_data = {"system": {}, "points": {}}
            
            # --- 0. Connection Probe ---
            # REVERTED TO 0x0000 based on mbpoll result [1]: 110 (Ref 1 = Addr 0)
            rr_hold = await self._read_registers_safe("read_holding_registers", 0x0000, 1)
            
            if rr_hold and not rr_hold.isError():
                new_data["system"]["power_setpoint_abs"] = rr_hold.registers[0]
            else:
                 # Detailed logging for debugging
                 _LOGGER.error("Probe failed. Result: %s. Connection state: %s", 
                               rr_hold, self.client.connected)
                 raise UpdateFailed("Could not read Global Register 0x0000. Connection failed.")

            # --- 1. System Info ---
            # 0x0006
            rr_sys = await self._read_registers_safe("read_input_registers", 0x0006, 2)
            if rr_sys and not rr_sys.isError():
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