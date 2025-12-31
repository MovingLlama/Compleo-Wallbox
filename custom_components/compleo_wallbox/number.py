"""Support for Compleo Wallbox number settings."""
from __future__ import annotations

import logging
from homeassistant.components.number import NumberEntity, NumberDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN, 
    REG_SYS_POWER_LIMIT,
    REG_SYS_MAX_SCHIEFLAST,
    REG_SYS_FALLBACK_POWER
)

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
    
    # 1. Global Station Power Limit (Watt, factor 100)
    entities.append(CompleoNumber(
        coordinator, uid_prefix, "power_setpoint_abs", "Station Power Limit", 
        REG_SYS_POWER_LIMIT, UnitOfPower.WATT, NumberDeviceClass.POWER,
        0, 44000, 100, 100
    ))

    # 2. Max Schieflast (Ampere, factor 0.1 -> divide by 0.1 equals multiply by 10)
    entities.append(CompleoNumber(
        coordinator, uid_prefix, "max_schieflast", "Max Unbalanced Load", 
        REG_SYS_MAX_SCHIEFLAST, UnitOfElectricCurrent.AMPERE, NumberDeviceClass.CURRENT,
        6, 32, 0.1, 0.1
    ))

    # 3. Fallback Power (Watt, factor 100)
    entities.append(CompleoNumber(
        coordinator, uid_prefix, "fallback_power", "Fallback Power", 
        REG_SYS_FALLBACK_POWER, UnitOfPower.WATT, NumberDeviceClass.POWER,
        0, 44000, 100, 100
    ))
        
    async_add_entities(entities)


class CompleoNumber(CoordinatorEntity, NumberEntity):
    """Generic Compleo Number Entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, uid_prefix, key, name, register, unit, dev_class, min_val, max_val, step, multiplier):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._register = register
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = dev_class
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_native_step = step
        self._multiplier = multiplier
        
        self._attr_unique_id = f"{uid_prefix}_{key}"

    @property
    def native_value(self):
        if not self.coordinator.data: return None
        raw = self.coordinator.data.get("system", {}).get(self._key)
        if raw is not None:
            return float(raw * self._multiplier)
        return None

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.host)},
            "name": self.coordinator.device_name,
            "manufacturer": "Compleo",
            "model": "Wallbox (System)",
        }

    async def async_set_native_value(self, value: float) -> None:
        # Conversion:
        # If multiplier is 100 (W) -> value / 100
        # If multiplier is 0.1 (A) -> value / 0.1 (same as value * 10)
        modbus_val = int(value / self._multiplier)
        
        try:
            # Call the new robust write function
            result = await self.coordinator.async_write_register(self._register, modbus_val)
            
            if result is not None and not (hasattr(result, 'isError') and result.isError()):
                await self.coordinator.async_request_refresh()
            else:
                _LOGGER.error("Error writing to Compleo at 0x%04x: %s", self._register, result)
                
        except Exception as err:
            _LOGGER.error("Exception writing to Compleo: %s", err)