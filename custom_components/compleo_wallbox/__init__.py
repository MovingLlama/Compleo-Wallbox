"""The Compleo Wallbox integration."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

# Import Modbus client and exceptions
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_HOST, CONF_PORT, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL

# Define supported platforms
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER]

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Compleo Wallbox from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    name = entry.data.get(CONF_NAME, "Compleo Wallbox")

    _LOGGER.debug("Setting up Compleo Wallbox entry for host: %s", host)

    # Initialize the coordinator
    coordinator = CompleoDataUpdateCoordinator(hass, host, port, name)

    # Perform the first refresh. We allow this to fail (e.g., if the wallbox is offline)
    # so that the integration is still loaded and can retry later.
    # CRITICAL: We catch the exception so async_setup_entry returns True.
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as e:
        _LOGGER.warning("Initial data fetch failed for %s (%s). Will retry in background.", host, e)

    # Store the coordinator in hass.data
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    
    # Forward setup to platforms (sensor, number)
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
        """Initialize the coordinator."""
        self.host = host
        # Initialize Modbus client with a timeout
        self.client = AsyncModbusTcpClient(host, port=port, timeout=10)
        self.device_name = name
        self.device_info_map = {} 
        self._param_name = "slave" 
        
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{host}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        
        # Initialize data structure immediately to prevent NoneType errors in sensors
        # if the first update fails.
        self.data = {
            "system": {},
            "points": {}
        }

    async def _read_registers_safe(self, func_name, address, count, slave_id=1):
        """Helper to call Modbus read functions with automatic parameter detection."""
        
        # Ensure connection
        if not self.client.connected:
            _LOGGER.debug("Connecting to Modbus server at %s", self.host)
            await self.client.connect()
            # Give the connection a moment to settle
            await asyncio.sleep(0.1)

        func = getattr(self.client, func_name)
        
        # Try different parameter names for the slave ID
        for p_name in [self._param_name, "slave", "unit", "device_id"]:
            try:
                kwargs = {p_name: slave_id}
                
                # Add a small delay before sending request (Message Wait)
                await asyncio.sleep(0.05)
                
                result = await func(address, count, **kwargs)
                
                if result is not None and not result.isError():
                    self._param_name = p_name
                    return result
                elif result is not None and result.isError():
                    _LOGGER.debug("Modbus error reading address 0x%04x: %s", address, result)

            except Exception as e:
                _LOGGER.debug("Exception reading address 0x%04x with param %s: %s", address, p_name, e)
                # Force reconnect on exception
                self.client.close()
                await asyncio.sleep(0.1)
                await self.client.connect()
                continue
                
        _LOGGER.warning("Failed to read registers at address 0x%04x after trying all parameters", address)
        return None

    async def _read_charging_point_data(self, index: int) -> dict | None:
        """Read data for a specific charging point (1 or 2)."""
        base_address = index * 0x1000
        data = {}

        # --- Block 1 (Inputs) ---
        start_addr_1 = base_address + 0x001
        rr_block1 = await self._read_registers_safe("read_input_registers", start_addr_1, 8)
        
        if not rr_block1 or rr_block1.isError():
            return None

        regs = rr_block1.registers
        data["status_word"] = regs[0]
        data["current_power"] = regs[1] * 100
        data["current_l1"] = regs[2] * 0.1
        data["current_l2"] = regs[3] * 0.1
        data["current_l3"] = regs[4] * 0.1
        data["energy_total"] = regs[7] * 0.1

        # --- Block 2 (Inputs) ---
        start_addr_2 = base_address + 0x00A
        rr_block2 = await self._read_registers_safe("read_input_registers", start_addr_2, 6)
        
        if rr_block2 and not rr_block2.isError():
            regs = rr_block2.registers
            data["status_code"] = regs[2]
            data["voltage_l1"] = regs[3]
            data["voltage_l2"] = regs[4]
            data["voltage_l3"] = regs[5]
        else:
            data.update({"status_code": 0, "voltage_l1": 0, "voltage_l2": 0, "voltage_l3": 0})

        return data

    async def _async_update_data(self):
        """Fetch data from the wallbox."""
        try:
            # We build a temporary dict so we don't overwrite self.data with partial trash if it fails halfway
            new_data = {
                "system": {},
                "points": {}
            }
            
            # --- 1. System Info ---
            rr_sys = await self._read_registers_safe("read_input_registers", 0x0006, 2)
            if rr_sys and not rr_sys.isError():
                major = rr_sys.registers[1] >> 8
                minor = rr_sys.registers[1] & 0xFF
                patch = rr_sys.registers[0] >> 8
                new_data["system"]["firmware_version"] = f"{major}.{minor}.{patch}"

            # --- 2. Global Holding ---
            rr_hold = await self._read_registers_safe("read_holding_registers", 0x0000, 1)
            if rr_hold and not rr_hold.isError():
                new_data["system"]["power_setpoint_abs"] = rr_hold.registers[0]

            # --- 3. Charging Points ---
            lp1_data = await self._read_charging_point_data(1)
            if lp1_data:
                new_data["points"][1] = lp1_data
            else:
                # If LP1 fails, assume communication error, but don't crash entirely.
                # Just return what we have (or raise specific error to trigger retry)
                _LOGGER.warning("Could not read Charging Point 1 data.")
                # If we have NO data at all, raise UpdateFailed
                if not new_data["system"]:
                     raise UpdateFailed("Communication lost")

            lp2_data = await self._read_charging_point_data(2)
            if lp2_data:
                new_data["points"][2] = lp2_data

            return new_data

        except Exception as err:
            _LOGGER.error("Error updating Compleo data: %s", err)
            # If update fails, return the LAST KNOWN GOOD data if available, 
            # or the empty structure (via self.data access in sensor)
            # Raising UpdateFailed makes the entities 'unavailable' which is correct.
            raise UpdateFailed(f"Communication error: {err}")