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

    # Erster Refresh darf fehlschlagen, damit die Integration trotzdem geladen wird
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        _LOGGER.warning("Initial data fetch failed for %s. Will retry in background.", host)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator.client.close()
    return unload_ok

class CompleoDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Compleo Wallbox data."""

    def __init__(self, hass: HomeAssistant, host: str, port: int, name: str) -> None:
        """Initialize."""
        self.host = host
        self.client = AsyncModbusTcpClient(host, port=port, timeout=10)
        self.device_name = name
        self.device_info_map = {}
        self._param_name = "slave" # Default
        
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{host}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _read_registers_safe(self, func_name, address, count, slave_id=1):
        """Helper to call read functions with automatic parameter detection."""
        if not self.client.connected:
            await self.client.connect()

        func = getattr(self.client, func_name)
        # Teste slave, unit und device_id (je nach pymodbus Version)
        for p_name in [self._param_name, "slave", "unit", "device_id"]:
            try:
                result = await func(address, count, **{p_name: slave_id})
                if result is not None and not result.isError():
                    self._param_name = p_name
                    return result
            except Exception:
                continue
        return None

    async def _async_update_data(self):
        """Fetch data from the wallbox based on PDF specs."""
        try:
            data = {}
            
            # 1. System Info (Firmware etc)
            # Register 0x0006 = Patch/Major/Minor
            rr_sys = await self._read_registers_safe("read_input_registers", 0x0006, 2)
            if rr_sys:
                data["firmware_version"] = f"{(rr_sys.registers[1]>>8)}.{(rr_sys.registers[1]&0xFF)}.{(rr_sys.registers[0]>>8)}"

            # 2. Charging Status (Base 0x1001 / 4097)
            # Laut PDF ist Status Wort bei 0x1001
            rr_status = await self._read_registers_safe("read_input_registers", 0x1001, 15)
            if rr_status:
                regs = rr_status.registers
                data["status_word"] = regs[0]
                data["current_power"] = regs[1] * 100 
                data["current_l1"] = regs[2] * 0.1
                data["current_l2"] = regs[3] * 0.1
                data["current_l3"] = regs[4] * 0.1
                # Energie (Register 0x1008/0x1009)
                data["energy_total"] = (regs[7] << 16 | regs[8]) * 0.1
                data["status_code"] = regs[11] # ChargePointStatus
                
            # 3. Voltages (Register 0x000D bis 0x000F)
            rr_volt = await self._read_registers_safe("read_input_registers", 0x000D, 3)
            if rr_volt:
                data["voltage_l1"] = rr_volt.registers[0]
                data["voltage_l2"] = rr_volt.registers[1]
                data["voltage_l3"] = rr_volt.registers[2]

            # 4. Holding Register (Leistungsvorgabe)
            rr_hold = await self._read_registers_safe("read_holding_registers", 0x0000, 1)
            if rr_hold:
                data["power_setpoint_abs"] = rr_hold.registers[0]

            # Device Info Update
            self.device_info_map = {
                "identifiers": {(DOMAIN, self.host)},
                "name": self.device_name,
                "manufacturer": "Compleo",
                "sw_version": data.get("firmware_version", "Unknown"),
            }

            return data

        except Exception as err:
            raise UpdateFailed(f"Communication error: {err}")