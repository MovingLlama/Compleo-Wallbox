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
    REG_SYS_FALLBACK_POWER,
    ADDR_LP1_BASE,
    ADDR_LP2_BASE,
    OFFSET_MAX_POWER
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
    
    # Get dynamic point count
    num_points = 1
    if coordinator.data and "system" in coordinator.data:
        num_points = coordinator.data["system"].get("num_points", 1)

    entities = []
    
    # 1. Global Station Power Limit
    entities.append(CompleoNumber(
        coordinator, uid_prefix, "power_setpoint_abs", "Station Power Limit", 
        REG_SYS_POWER_LIMIT, UnitOfPower.WATT, NumberDeviceClass.POWER,
        0, 44000, 100, 100
    ))

    # 2. Max Schieflast
    entities.append(CompleoNumber(
        coordinator, uid_prefix, "max_schieflast", "Max Unbalanced Load", 
        REG_SYS_MAX_SCHIEFLAST, UnitOfElectricCurrent.AMPERE, NumberDeviceClass.CURRENT,
        6, 32, 0.1, 0.1
    ))

    # 3. Fallback Power
    entities.append(CompleoNumber(
        coordinator, uid_prefix, "fallback_power", "Fallback Power", 
        REG_SYS_FALLBACK_POWER, UnitOfPower.WATT, NumberDeviceClass.POWER,
        0, 44000, 100, 100
    ))

    # 4. Per-Point Max Power (Dynamic)
    for idx in range(1, num_points + 1):
        entities.append(CompleoPointNumber(
            coordinator, uid_prefix, idx, "max_power_limit", "Max Power Limit",
            OFFSET_MAX_POWER, UnitOfPower.WATT, NumberDeviceClass.POWER,
            0, 44000, 100, 100
        ))
        
    async_add_entities(entities)


class CompleoNumber(CoordinatorEntity, NumberEntity):
    """Generic Compleo Number Entity (System)."""
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
        modbus_val = int(value / self._multiplier)
        try:
            result = await self.coordinator.async_write_register(self._register, modbus_val)
            if result is not None and not (hasattr(result, 'isError') and result.isError()):
                await self.coordinator.async_request_refresh()
            else:
                _LOGGER.error("Error writing to Compleo at 0x%04x: %s", self._register, result)
        except Exception as err:
            _LOGGER.error("Exception writing to Compleo: %s", err)


class CompleoPointNumber(CoordinatorEntity, NumberEntity):
    """Compleo Number Entity for Charging Points."""
    _attr_has_entity_name = True

    def __init__(self, coordinator, uid_prefix, point_index, key, name, offset, unit, dev_class, min_val, max_val, step, multiplier):
        super().__init__(coordinator)
        self._point_index = point_index
        self._key = key
        self._attr_name = name
        
        # Calc register
        base = ADDR_LP1_BASE if point_index == 1 else ADDR_LP2_BASE
        self._register = base + offset
        
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = dev_class
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_native_step = step
        self._multiplier = multiplier
        self._attr_unique_id = f"{uid_prefix}_lp{point_index}_{key}"

    @property
    def native_value(self):
        if not self.coordinator.data: return None
        points = self.coordinator.data.get("points", {})
        raw = points.get(self._point_index, {}).get(self._key)
        if raw is not None:
            return float(raw * self._multiplier)
        return None

    @property
    def device_info(self):
        main_device_id = (DOMAIN, self.coordinator.host)
        point_device_id = (DOMAIN, f"{self.coordinator.host}_lp{self._point_index}")
        return {
            "identifiers": {point_device_id},
            "via_device": main_device_id,
        }

    async def async_set_native_value(self, value: float) -> None:
        modbus_val = int(value / self._multiplier)
        try:
            result = await self.coordinator.async_write_register(self._register, modbus_val)
            if result is not None and not (hasattr(result, 'isError') and result.isError()):
                await self.coordinator.async_request_refresh()
            else:
                _LOGGER.error("Error writing to Point %d at 0x%04x: %s", self._point_index, self._register, result)
        except Exception as err:
            _LOGGER.error("Exception writing to Point: %s", err)