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

    _LOGGER.debug("Setting up Compleo Wallbox entry for host: %s", host)

    # Initialize the coordinator
    coordinator = CompleoDataUpdateCoordinator(hass, host, port, name)

    # Perform the first refresh. We allow this to fail (e.g., if the wallbox is offline)
    # so that the integration is still loaded and can retry later.
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
    """
    Unload a config entry.
    
    Closes the Modbus connection and removes the data from Home Assistant.
    """
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        if coordinator.client.connected:
            coordinator.client.close()
            _LOGGER.debug("Modbus connection closed for %s", coordinator.host)
    return unload_ok

class CompleoDataUpdateCoordinator(DataUpdateCoordinator):
    """
    Class to manage fetching Compleo Wallbox data.
    
    Handles the Modbus connection and data retrieval logic.
    Supports detecting multiple charging points (Solo/Duo).
    """

    def __init__(self, hass: HomeAssistant, host: str, port: int, name: str) -> None:
        """Initialize the coordinator."""
        self.host = host
        # Initialize Modbus client with a timeout
        self.client = AsyncModbusTcpClient(host, port=port, timeout=10)
        self.device_name = name
        self.device_info_map = {} # Main device info
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
        """
        if not self.client.connected:
            _LOGGER.debug("Connecting to Modbus server at %s", self.host)
            await self.client.connect()

        func = getattr(self.client, func_name)
        
        # Try different parameter names for the slave ID
        # (This logic helps compatibility with different pymodbus versions)
        for p_name in [self._param_name, "slave", "unit", "device_id"]:
            try:
                kwargs = {p_name: slave_id}
                _LOGGER.debug("Reading %s register(s) at address 0x%04x using %s=%s", count, address, p_name, slave_id)
                
                result = await func(address, count, **kwargs)
                
                # If we get a valid response, remember the correct parameter name
                if result is not None and not result.isError():
                    self._param_name = p_name
                    # _LOGGER.debug("Read success: %s", result.registers)
                    return result
                elif result is not None and result.isError():
                    _LOGGER.debug("Modbus error reading address 0x%04x: %s", address, result)

            except Exception as e:
                _LOGGER.debug("Exception reading address 0x%04x with param %s: %s", address, p_name, e)
                continue
                
        # Return None if all attempts fail
        _LOGGER.warning("Failed to read registers at address 0x%04x after trying all parameters", address)
        return None

    async def _read_charging_point_data(self, index: int) -> dict | None:
        """
        Read data for a specific charging point (1 or 2).
        
        Calculates offsets based on index:
        LP1 starts at 0x1000
        LP2 starts at 0x2000
        """
        base_address = index * 0x1000
        data = {}

        _LOGGER.debug("Reading data for Charging Point %d (Base Address: 0x%04x)", index, base_address)

        # --- Block 1 (Inputs) ---
        # 0xX001 to 0xX008 (Status, Power, Currents, Time, Energy)
        # Skip 0xX009 (Holding Register - Mode)
        start_addr_1 = base_address + 0x001
        rr_block1 = await self._read_registers_safe("read_input_registers", start_addr_1, 8)
        
        if not rr_block1 or rr_block1.isError():
            # If we can't read the first block of LP1, it's an error.
            # If we can't read LP2, it probably just doesn't exist (Solo model).
            _LOGGER.debug("Could not read Block 1 for Charging Point %d. It might not exist.", index)
            return None

        regs = rr_block1.registers
        _LOGGER.debug("Charging Point %d Block 1 raw data: %s", index, regs)

        data["status_word"] = regs[0]
        data["current_power"] = regs[1] * 100  # 100W steps -> Watt
        data["current_l1"] = regs[2] * 0.1     # 0.1A steps -> Ampere
        data["current_l2"] = regs[3] * 0.1
        data["current_l3"] = regs[4] * 0.1
        # Energy at index 7 (Offset 8)
        data["energy_total"] = regs[7] * 0.1   # 100Wh steps -> kWh

        # --- Block 2 (Inputs) ---
        # 0xX00A to 0xX00F (Phase Switch, Errors, Status, Voltages)
        start_addr_2 = base_address + 0x00A
        rr_block2 = await self._read_registers_safe("read_input_registers", start_addr_2, 6)
        
        if rr_block2 and not rr_block2.isError():
            regs = rr_block2.registers
            _LOGGER.debug("Charging Point %d Block 2 raw data: %s", index, regs)

            data["status_code"] = regs[2] # Offset C
            data["voltage_l1"] = regs[3]  # Offset D
            data["voltage_l2"] = regs[4]  # Offset E
            data["voltage_l3"] = regs[5]  # Offset F
        else:
            # Should not happen if Block 1 worked, but fill with 0/None to be safe
            _LOGGER.warning("Read Block 1 but failed Block 2 for Point %d. Using zeroes.", index)
            data.update({"status_code": 0, "voltage_l1": 0, "voltage_l2": 0, "voltage_l3": 0})

        return data

    async def _async_update_data(self):
        """
        Fetch data from the wallbox.
        
        Structure:
        {
            "system": { ... global data ... },
            "points": {
                1: { ... LP1 data ... },
                2: { ... LP2 data ... } (if available)
            }
        }
        """
        try:
            _LOGGER.debug("Starting update for Compleo Wallbox")
            full_data = {
                "system": {},
                "points": {}
            }
            
            # --- 1. System Info (Firmware) ---
            # Register 0x0006 = Firmware Patch, 0x0007 = Major/Minor
            rr_sys = await self._read_registers_safe("read_input_registers", 0x0006, 2)
            if rr_sys and not rr_sys.isError():
                major = rr_sys.registers[1] >> 8
                minor = rr_sys.registers[1] & 0xFF
                patch = rr_sys.registers[0] >> 8
                fw_version = f"{major}.{minor}.{patch}"
                full_data["system"]["firmware_version"] = fw_version
                _LOGGER.debug("Firmware Version: %s", fw_version)

            # --- 2. Global Holding (Power Setpoint) ---
            # Register 0x0000
            rr_hold = await self._read_registers_safe("read_holding_registers", 0x0000, 1)
            if rr_hold and not rr_hold.isError():
                full_data["system"]["power_setpoint_abs"] = rr_hold.registers[0]
                _LOGGER.debug("Power Setpoint: %s (x100W)", rr_hold.registers[0])

            # --- 3. Charging Points ---
            # Try to read LP1 and LP2
            
            # Read LP1
            lp1_data = await self._read_charging_point_data(1)
            if lp1_data:
                full_data["points"][1] = lp1_data
            else:
                # If LP1 fails, the whole device is probably unreachable
                _LOGGER.error("Failed to read Charging Point 1. Aborting update.")
                raise UpdateFailed("Could not read data from Charging Point 1")

            # Read LP2 (Optional)
            lp2_data = await self._read_charging_point_data(2)
            if lp2_data:
                full_data["points"][2] = lp2_data
                _LOGGER.debug("Charging Point 2 found.")
            else:
                _LOGGER.debug("Charging Point 2 not found (Solo or offline).")

            _LOGGER.debug("Update finished successfully.")
            return full_data

        except Exception as err:
            _LOGGER.error("Error updating Compleo data: %s", err)
            raise UpdateFailed(f"Communication error: {err}")