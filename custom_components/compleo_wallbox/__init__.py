"""The Compleo Wallbox integration."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import struct

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

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER]

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Compleo Wallbox from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    name = entry.data.get(CONF_NAME, "Compleo Wallbox")

    coordinator = CompleoDataUpdateCoordinator(hass, host, port, name)

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(f"Failed to connect to Compleo Wallbox at {host}") from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.client.close()

    return unload_ok


class CompleoDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Compleo Wallbox data."""

    def __init__(self, hass: HomeAssistant, host: str, port: int, name: str) -> None:
        """Initialize."""
        self.host = host
        self.client = AsyncModbusTcpClient(host, port=port)
        self.device_name = name
        self.device_info_map = {}
        self._param_name = None 
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _read_registers_safe(self, func_name, address, count, slave_id=1):
        """Helper to call read functions with automatic parameter detection."""
        if not self.client.connected:
            await self.client.connect()

        func = getattr(self.client, func_name)
        
        if self._param_name:
            return await func(address, count, **{self._param_name: slave_id})

        for param in ["slave", "unit", "device_id"]:
            try:
                result = await func(address, count, **{param: slave_id})
                if result is not None and not result.isError():
                    self._param_name = param
                    return result
            except (TypeError, Exception):
                continue
        
        raise UpdateFailed("Could not communicate with Modbus device")

    async def _async_update_data(self):
        """Fetch data from the wallbox."""
        try:
            data = {}
            
            # Global Registers (System Info)
            rr_input_sys = await self._read_registers_safe("read_input_registers", 6, 11)
            if not rr_input_sys.isError():
                regs = rr_input_sys.registers
                patch = regs[0] >> 8
                major = regs[1] >> 8
                minor = regs[1] & 0xFF
                data["firmware_version"] = f"{major}.{minor}.{patch}"
                
                hw_type_map = {1: "P4", 2: "P51/PM51", 3: "P52"}
                hw_val = regs[8]
                data["model"] = hw_type_map.get(hw_val, f"Solo ({hw_val})")
                
            rr_serial = await self._read_registers_safe("read_input_registers", 32, 16)
            if not rr_serial.isError():
                data["serial_number"] = self._decode_string(rr_serial.registers)
                
            # Charging Point Registers (Base 0x1000)
            rr_hold = await self._read_registers_safe("read_holding_registers", 0, 1)
            if not rr_hold.isError():
                data["power_setpoint_abs"] = rr_hold.registers[0]

            rr_cp_input = await self._read_registers_safe("read_input_registers", 0x1001, 26)
            if not rr_cp_input.isError():
                regs = rr_cp_input.registers
                data["status_word"] = regs[0]
                data["current_power"] = regs[1] * 100 
                data["current_l1"] = regs[2] * 0.1
                data["current_l2"] = regs[3] * 0.1
                data["current_l3"] = regs[4] * 0.1
                data["energy_total"] = regs[7] * 0.1
                data["status_code"] = regs[11]
                data["voltage_l1"] = regs[12]
                data["voltage_l2"] = regs[13]
                data["voltage_l3"] = regs[14]
                rfid_regs = regs[15:25]
                data["rfid_tag"] = self._decode_string(rfid_regs)

            # Update device info with serial number if available
            serial = data.get("serial_number", self.host)
            self.device_info_map = {
                "identifiers": {(DOMAIN, serial)},
                "name": self.device_name,
                "manufacturer": "Compleo",
                "model": data.get("model", "Solo"),
                "sw_version": data.get("firmware_version"),
            }

            return data

        except Exception as exception:
            raise UpdateFailed(f"Error communicating with Modbus: {exception}")

    def _decode_string(self, registers):
        """Decode a list of registers to a string."""
        result = ""
        for reg in registers:
            if reg == 0:
                continue
            try:
                b = struct.pack('>H', reg)
                result += b.decode('ascii', errors='ignore')
            except Exception:
                continue
        return result.strip('\x00').strip() 