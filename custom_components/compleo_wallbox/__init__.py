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

# Added SELECT platform for Phase Mode
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.SELECT]

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Compleo Wallbox from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    name = entry.data.get(CONF_NAME, "Compleo Wallbox")

    _LOGGER.debug("Setting up Compleo Wallbox entry for host: %s", host)

    coordinator = CompleoDataUpdateCoordinator(hass, host, port, name)

    # First refresh: We try to fetch data, but suppress errors to allow HA startup
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
        
        self.data = {
            "system": {},
            "points": {}
        }

    async def _read_registers_safe(self, func_name, address, count, slave_id=1):
        """Helper to call Modbus read functions with automatic parameter detection."""
        
        # Ensure connection
        if not self.client.connected:
            await self.client.connect()
            # Increased delay after connect for stability
            await asyncio.sleep(0.5)

        func = getattr(self.client, func_name)
        
        # Try different parameter names for the slave ID
        for p_name in [self._param_name, "slave", "unit", "device_id"]:
            try:
                kwargs = {p_name: slave_id}
                # Increased delay before each request (Message Wait)
                await asyncio.sleep(0.1) 
                
                result = await func(address, count, **kwargs)
                
                if result is not None and not result.isError():
                    self._param_name = p_name
                    return result
            except Exception:
                # Force reconnect if something went wrong inside the loop
                self.client.close()
                await asyncio.sleep(0.2)
                await self.client.connect()
                continue
                
        return None

    async def _read_charging_point_data(self, index: int) -> dict | None:
        """Read data for a specific charging point (1 or 2)."""
        base_address = index * 0x1000
        data = {}

        # --- Block 1 (Inputs) ---
        # SHIFTED +1: Doc 0xX001 -> Wire 0xX002
        start_addr_1 = base_address + 0x002
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

        # --- Block 2 (Inputs) ---
        # SHIFTED +1: Doc 0xX00A -> Wire 0xX00B
        start_addr_2 = base_address + 0x00B
        rr_block2 = await self._read_registers_safe("read_input_registers", start_addr_2, 6)
        
        if rr_block2 and not rr_block2.isError():
            regs = rr_block2.registers
            data["phase_switch_count"] = regs[0] # Wire 0xX00B (Doc 0xX00A)
            # regs[1] -> Wire 0xX00C (Doc 0xX00B)
            data["status_code"] = regs[2]        # Wire 0xX00D (Doc 0xX00C Status)
            data["voltage_l1"] = regs[3]         # Wire 0xX00E (Doc 0xX00D)
            data["voltage_l2"] = regs[4]         # Wire 0xX00F (Doc 0xX00E)
            data["voltage_l3"] = regs[5]         # Wire 0xX010 (Doc 0xX00F)
        else:
            data.update({"status_code": 0, "voltage_l1": 0, "voltage_l2": 0, "voltage_l3": 0})
            
        # --- Point Holding Registers (Phase Mode) ---
        # SHIFTED +1: Doc 0xX009 -> Wire 0xX00A
        addr_hold = base_address + 0x00A
        rr_hold = await self._read_registers_safe("read_holding_registers", addr_hold, 1)
        if rr_hold and not rr_hold.isError():
            data["phase_mode"] = rr_hold.registers[0]

        return data

    async def _async_update_data(self):
        """Fetch data from the wallbox."""
        try:
            new_data = {"system": {}, "points": {}}
            
            # --- 0. Connection Probe & Global Settings ---
            # SHIFTED +1: Doc 0x0000 -> Wire 0x0001
            rr_hold = await self._read_registers_safe("read_holding_registers", 0x0001, 1)
            if rr_hold and not rr_hold.isError():
                new_data["system"]["power_setpoint_abs"] = rr_hold.registers[0]
            else:
                 raise UpdateFailed("Could not read Global Register 0x0001. Connection failed.")

            # --- 1. System Info ---
            # SHIFTED +1: Doc 0x0006 -> Wire 0x0007
            rr_sys = await self._read_registers_safe("read_input_registers", 0x0007, 2)
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

            # --- 3. Calculate Station Totals ---
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