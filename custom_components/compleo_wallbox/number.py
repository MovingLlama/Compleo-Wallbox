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
    DOMAIN, REG_SYS_POWER_LIMIT, REG_SYS_MAX_SCHIEFLAST, REG_SYS_FALLBACK_POWER,
    ADDR_LP1_BASE, ADDR_LP2_BASE, OFFSET_MAX_POWER
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    uid_prefix = entry.unique_id or coordinator.host
    num_points = 1
    if coordinator.data and "system" in coordinator.data:
        num_points = coordinator.data["system"].get("num_points", 1)

    entities = []
    # Global
    entities.append(CompleoNumber(coordinator, uid_prefix, "power_setpoint_abs", REG_SYS_POWER_LIMIT, UnitOfPower.WATT, NumberDeviceClass.POWER, 0, 44000, 100, 100))
    entities.append(CompleoNumber(coordinator, uid_prefix, "max_schieflast", REG_SYS_MAX_SCHIEFLAST, UnitOfElectricCurrent.AMPERE, NumberDeviceClass.CURRENT, 6, 32, 0.1, 0.1))
    entities.append(CompleoNumber(coordinator, uid_prefix, "fallback_power", REG_SYS_FALLBACK_POWER, UnitOfPower.WATT, NumberDeviceClass.POWER, 0, 44000, 100, 100))

    # Per Point
    for idx in range(1, num_points + 1):
        entities.append(CompleoPointNumber(coordinator, uid_prefix, idx, "max_power_limit", OFFSET_MAX_POWER, UnitOfPower.WATT, NumberDeviceClass.POWER, 0, 44000, 100, 100))
        entities.append(CompleoVirtualNumber(coordinator, uid_prefix, idx, "solar_excess", UnitOfPower.WATT, NumberDeviceClass.POWER, 0, 30000, 100))
        entities.append(CompleoVirtualNumber(coordinator, uid_prefix, idx, "manual_limit", UnitOfPower.WATT, NumberDeviceClass.POWER, 0, 22000, 100))
        entities.append(CompleoVirtualNumber(coordinator, uid_prefix, idx, "zoe_min_current", UnitOfElectricCurrent.AMPERE, NumberDeviceClass.CURRENT, 6, 16, 1))

    async_add_entities(entities)

class CompleoNumber(CoordinatorEntity, NumberEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, uid_prefix, key, register, unit, dev_class, min_val, max_val, step, multiplier):
        super().__init__(coordinator)
        self._key = key
        self._attr_translation_key = key
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
        if raw is not None: return float(raw * self._multiplier)
        return None
    
    @property
    def device_info(self): return {"identifiers": {(DOMAIN, self.coordinator.host)}}

    async def async_set_native_value(self, value: float) -> None:
        modbus_val = int(value / self._multiplier)
        await self.coordinator.async_write_register(self._register, modbus_val)
        await self.coordinator.async_request_refresh()

class CompleoPointNumber(CoordinatorEntity, NumberEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, uid_prefix, point_index, key, offset, unit, dev_class, min_val, max_val, step, multiplier):
        super().__init__(coordinator)
        self._point_index = point_index
        self._key = key
        self._attr_translation_key = key
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
        if raw is not None: return float(raw * self._multiplier)
        return None
    
    @property
    def device_info(self): return {"identifiers": {(DOMAIN, f"{self.coordinator.host}_lp{self._point_index}")}, "via_device": (DOMAIN, self.coordinator.host)}

    async def async_set_native_value(self, value: float) -> None:
        modbus_val = int(value / self._multiplier)
        await self.coordinator.async_write_register(self._register, modbus_val)
        await self.coordinator.async_request_refresh()

class CompleoVirtualNumber(CoordinatorEntity, NumberEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, uid_prefix, point_index, key, unit, dev_class, min_val, max_val, step):
        super().__init__(coordinator)
        self._point_index = point_index
        self._key = key
        self._attr_translation_key = key
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = dev_class
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_native_step = step
        self._attr_unique_id = f"{uid_prefix}_lp{point_index}_{key}"

    @property
    def native_value(self):
        val = self.coordinator.logic.get_input(self._point_index, self._key)
        return val if val is not None else 0

    @property
    def device_info(self): return {"identifiers": {(DOMAIN, f"{self.coordinator.host}_lp{self._point_index}")}, "via_device": (DOMAIN, self.coordinator.host)}

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.logic.update_input(self._point_index, self._key, value)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()