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
    """
    Set up Compleo Wallbox from a config entry.
    
    This function initializes the data coordinator and forwards the setup
    to the sensor and number platforms.
    """
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    name = entry.data.get(CONF_NAME, "Compleo Wallbox")

    # Initialize the coordinator
    coordinator = CompleoDataUpdateCoordinator(hass, host, port, name)

    # Perform the first refresh. We allow this to fail (e.g., if the wallbox is offline)
    # so that the integration is still loaded and can retry later.
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        _LOGGER.warning("Initial data fetch failed for %s. Will retry in background.", host)

    # Store the coordinator in hass.data
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    
    # Forward setup to platforms (sensor, number)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """
    Unload a config entry.
    
    Closes the Modbus connection and removes the data from Home Assistant.
    """
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        if coordinator.client.connected:
            coordinator.client.close()
    return unload_ok

class CompleoDataUpdateCoordinator(DataUpdateCoordinator):
    """
    Class to manage fetching Compleo Wallbox data.
    
    Handles the Modbus connection and data retrieval logic.
    """

    def __init__(self, hass: HomeAssistant, host: str, port: int, name: str) -> None:
        """Initialize the coordinator."""
        self.host = host
        # Initialize Modbus client with a timeout
        self.client = AsyncModbusTcpClient(host, port=port, timeout=10)
        self.device_name = name
        self.device_info_map = {}
        # Default parameter name for slave ID (changes based on pymodbus version)
        self._param_name = "slave" 
        
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{host}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _read_registers_safe(self, func_name, address, count, slave_id=1):
        """
        Helper to call Modbus read functions with automatic parameter detection.
        
        Different versions of pymodbus use different arguments for the Unit ID
        ('slave', 'unit', or 'device_id'). This function tries them all.
        """
        if not self.client.connected:
            await self.client.connect()

        func = getattr(self.client, func_name)
        
        # Try different parameter names for the slave ID
        for p_name in [self._param_name, "slave", "unit", "device_id"]:
            try:
                kwargs = {p_name: slave_id}
                result = await func(address, count, **kwargs)
                
                # If we get a valid response, remember the correct parameter name
                if result is not None and not result.isError():
                    self._param_name = p_name
                    return result
            except Exception:
                continue
                
        # Return None if all attempts fail
        return None

    async def _async_update_data(self):
        """
        Fetch data from the wallbox.
        
        Based on the PDF specification (Modbus Register v16).
        We split reads to avoid mixing Input and Holding registers, which can causing errors.
        """
        try:
            data = {}
            
            # --- 1. System Info ---
            # Register 0x0006 = Firmware Patch
            # Register 0x0007 = Firmware Major/Minor
            rr_sys = await self._read_registers_safe("read_input_registers", 0x0006, 2)
            if rr_sys and not rr_sys.isError():
                # Format: Major.Minor.Patch
                # 0x0007 contains Major (High Byte) and Minor (Low Byte)
                # 0x0006 contains Patch (High Byte)
                major = rr_sys.registers[1] >> 8
                minor = rr_sys.registers[1] & 0xFF
                patch = rr_sys.registers[0] >> 8
                data["firmware_version"] = f"{major}.{minor}.{patch}"

            # --- 2. Charging Data Block 1 (Inputs) ---
            # Reading from 0x1001 to 0x1008 (8 Registers)
            # We stop before 0x1009 because 0x1009 is a HOLDING register (Mode).
            # Attempting to read Holding register via read_input_registers often fails.
            #
            # Mapping (Base 0x1000 + Offset):
            # 0x1001 (Offset 1): Status Word
            # 0x1002 (Offset 2): Current Power (100W steps)
            # 0x1003 (Offset 3): Current L1 (0.1A steps)
            # 0x1004 (Offset 4): Current L2
            # 0x1005 (Offset 5): Current L3
            # 0x1006 (Offset 6): Time (2 registers)
            # 0x1008 (Offset 8): Energy (1 register, 100Wh steps)
            
            rr_block1 = await self._read_registers_safe("read_input_registers", 0x1001, 8)
            if rr_block1 and not rr_block1.isError():
                regs = rr_block1.registers
                data["status_word"] = regs[0]
                data["current_power"] = regs[1] * 100  # Convert 100W steps to Watt
                data["current_l1"] = regs[2] * 0.1     # Convert 0.1A steps to Ampere
                data["current_l2"] = regs[3] * 0.1
                data["current_l3"] = regs[4] * 0.1
                # Energy at index 7 (0x1008). 100Wh steps -> kWh ( * 0.1 )
                data["energy_total"] = regs[7] * 0.1
            
            # --- 3. Charging Data Block 2 (Inputs) ---
            # Reading from 0x100A to 0x100F (6 Registers)
            # We skip 0x1009 (Holding) to prevent errors.
            #
            # Mapping:
            # 0x100A (Offset A): Phase Switches
            # 0x100B (Offset B): Error Code
            # 0x100C (Offset C): Status Code (OCPP Status)
            # 0x100D (Offset D): Voltage L1
            # 0x100E (Offset E): Voltage L2
            # 0x100F (Offset F): Voltage L3
            
            rr_block2 = await self._read_registers_safe("read_input_registers", 0x100A, 6)
            if rr_block2 and not rr_block2.isError():
                regs = rr_block2.registers
                data["status_code"] = regs[2] # Index 2 is 0x100C
                data["voltage_l1"] = regs[3]  # Index 3 is 0x100D
                data["voltage_l2"] = regs[4]  # Index 4 is 0x100E
                data["voltage_l3"] = regs[5]  # Index 5 is 0x100F

            # --- 4. Holding Register (Power Setpoint) ---
            # Register 0x0000 (Global Holding)
            rr_hold = await self._read_registers_safe("read_holding_registers", 0x0000, 1)
            if rr_hold and not rr_hold.isError():
                data["power_setpoint_abs"] = rr_hold.registers[0]

            # Update Device Info for Home Assistant
            self.device_info_map = {
                "identifiers": {(DOMAIN, self.host)},
                "name": self.device_name,
                "manufacturer": "Compleo",
                "sw_version": data.get("firmware_version", "Unknown"),
            }

            return data

        except Exception as err:
            _LOGGER.error("Error updating Compleo data: %s", err)
            raise UpdateFailed(f"Communication error: {err}")