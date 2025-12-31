"""Support for Compleo Wallbox number settings."""
from __future__ import annotations

import logging
import asyncio
from homeassistant.components.number import NumberEntity, NumberDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, REG_SYS_POWER_LIMIT

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Compleo number entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    uid_prefix = entry.unique_id or coordinator.host
    
    entities = []
    
    # 1. Global Station Power Limit
    entities.append(CompleoStationLimit(coordinator, uid_prefix))
        
    async_add_entities(entities)


class CompleoStationLimit(CoordinatorEntity, NumberEntity):
    """Global Charging Power Limit."""

    _attr_has_entity_name = True
    _attr_name = "Station Power Limit"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_min_value = 0
    _attr_native_max_value = 44000 
    _attr_native_step = 100
    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, coordinator, uid_prefix):
        super().__init__(coordinator)
        self._attr_unique_id = f"{uid_prefix}_station_limit"

    @property
    def native_value(self):
        if not self.coordinator.data: return None
        raw = self.coordinator.data.get("system", {}).get("power_setpoint_abs")
        return float(raw * 100) if raw is not None else None

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.host)},
            "name": self.coordinator.device_name,
            "manufacturer": "Compleo",
            "model": "Wallbox (System)",
        }

    async def async_set_native_value(self, value: float) -> None:
        modbus_val = int(value / 100)
        await self._write_register(REG_SYS_POWER_LIMIT, modbus_val)

    async def _write_register(self, address, value):
        try:
            # We reuse the param name found during read
            param = self.coordinator._param_name or "slave"
            
            if not self.coordinator.client.connected:
                await self.coordinator.client.connect()
                await asyncio.sleep(0.1)
            
            # Simple write attempt (assuming param name is correct from read phase)
            kwargs = {param: 1}
            result = await self.coordinator.client.write_register(address, value, **kwargs)
            
            if not result.isError():
                await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error("Error writing to Compleo: %s", err)