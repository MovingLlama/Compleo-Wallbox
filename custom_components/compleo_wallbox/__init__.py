"""The Compleo Wallbox integration."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import struct

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_HOST, CONF_PORT
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

    coordinator = CompleoDataUpdateCoordinator(hass, host, port)

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

    def __init__(self, hass: HomeAssistant, host: str, port: int) -> None:
        """Initialize."""
        self.host = host
        self.client = AsyncModbusTcpClient(host, port=port)
        self.device_info_map = {}
        self._param_name = None # Merkt sich, welcher Parameter funktioniert
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _read_registers_safe(self, func_name, address, count, slave_id=1):
        """Helper to call read functions with either 'device_id', 'slave' or 'unit'."""
        func = getattr(self.client, func_name)
        
        # Wenn wir schon wissen, was funktioniert, nutzen wir es
        if self._param_name:
            return await func(address, count, **{self._param_name: slave_id})

        # Sonst probieren wir es aus (Wichtig für den ersten Start)
        for param in ["device_id", "slave", "unit"]:
            try:
                result = await func(address, count, **{param: slave_id})
                self._param_name = param
                return result
            except TypeError:
                continue
        
        raise UpdateFailed("Could not determine correct Modbus parameter (device_id/slave/unit)")

    async def _async_update_data(self):
        """Fetch data from the wallbox."""
        if not self.client.connected:
            await self.client.connect()

        try:
            data = {}
            
            # --- READ GLOBAL REGISTERS ---
            rr_hold = await self._read_registers_safe("read_holding_registers", 0, 6)
            if not rr_hold.isError():
                data["power_setpoint_abs"] = rr_hold.registers[0]
                data["power_setpoint_percent"] = rr_hold.registers[1]
            
            rr_input_sys = await self._read_registers_safe("read_input_registers", 6, 11)
            if not rr_input_sys.isError():
                regs = rr_input_sys.registers
                patch = regs[0] >> 8
                major = regs[1] >> 8
                minor = regs[1] & 0xFF
                data["firmware_version"] = f"{major}.{minor}.{patch}"
                
                hw_type_map = {1: "P4", 2: "P51/PM51", 3: "P52"}
                hw_val = regs[8]
                data["model"] = hw_type_map.get(hw_val, f"Unknown ({hw_val})")
                
                rr_serial = await self._read_registers_safe("read_input_registers", 32, 16)
                if not rr_serial.isError():
                    data["serial_number"] = self._decode_string(rr_serial.registers)
                
            # --- READ CHARGE POINT 1 REGISTERS (Base 0x1000) ---
            rr_cp_hold = await self._read_registers_safe("read_holding_registers", 0x1000, 1)
            if not rr_cp_hold.isError():
                data["cp_max_power"] = rr_cp_hold.registers[0]

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

            if "serial_number" in data:
                self.device_info_map = {
                    "identifiers": {(DOMAIN, data["serial_number"])},
                    "name": "Compleo Wallbox",
                    "manufacturer": "Compleo",
                    "model": data.get("model", "Solo"),
                    "sw_version": data.get("firmware_version"),
                }

            return data

        except ModbusException as exception:
            raise UpdateFailed(f"Modbus connection error: {exception}")
        except Exception as exception:
            raise UpdateFailed(f"Unexpected error: {exception}")

    def _decode_string(self, registers):
        """Decode a list of registers to a string."""
        result = ""
        for reg in registers:
            if reg == 0:
                continue
            b = struct.pack('>H', reg)
            result += b.decode('ascii', errors='ignore')
        return result.strip('\x00').strip()