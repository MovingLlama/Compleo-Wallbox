"""Support for Compleo Wallbox selection entities."""
from __future__ import annotations

import logging
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN, ADDR_LP1_BASE, ADDR_LP2_BASE, OFFSET_PHASE_MODE,
    CHARGING_MODES
)

_LOGGER = logging.getLogger(__name__)

# Map internal register values to translation keys
PHASE_MODE_MAP = {
    0: "unavailable",
    1: "automatic",
    2: "1_phase",
    3: "3_phase"
}
# Map keys back to register values
PHASE_MODE_KEYS_TO_VALUE = {v: k for k, v in PHASE_MODE_MAP.items()}

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    uid_prefix = entry.unique_id or coordinator.host
    num_points = 1
    if coordinator.data and "system" in coordinator.data:
        num_points = coordinator.data["system"].get("num_points", 1)

    entities = []
    for idx in range(1, num_points + 1):
        entities.append(CompleoPhaseMode(coordinator, uid_prefix, idx))
        entities.append(CompleoChargingMode(coordinator, uid_prefix, idx))
        
    async_add_entities(entities)

class CompleoPhaseMode(CoordinatorEntity, SelectEntity):
    """Real Phase Mode Register."""
    _attr_has_entity_name = True
    _attr_translation_key = "phase_mode"
    _attr_icon = "mdi:current-ac"
    
    # Options are now keys, translated by HA
    _attr_options = list(PHASE_MODE_MAP.values())

    def __init__(self, coordinator, uid_prefix, point_index):
        super().__init__(coordinator)
        self._point_index = point_index
        self._attr_unique_id = f"{uid_prefix}_lp{point_index}_phase_mode"
        base = ADDR_LP1_BASE if point_index == 1 else ADDR_LP2_BASE
        self._register = base + OFFSET_PHASE_MODE

    @property
    def current_option(self):
        if not self.coordinator.data: return None
        points = self.coordinator.data.get("points", {})
        val = points.get(self._point_index, {}).get("phase_mode")
        if val in PHASE_MODE_MAP: return PHASE_MODE_MAP[val]
        return None
    
    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, f"{self.coordinator.host}_lp{self._point_index}")},
            "via_device": (DOMAIN, self.coordinator.host),
        }

    async def async_select_option(self, option: str) -> None:
        value = PHASE_MODE_KEYS_TO_VALUE.get(option)
        if value is None: return
        await self.coordinator.async_write_register(self._register, value)
        await self.coordinator.async_request_refresh()

class CompleoChargingMode(CoordinatorEntity, SelectEntity):
    """Virtual Smart Charging Mode Selector."""
    _attr_has_entity_name = True
    _attr_translation_key = "charging_mode"
    _attr_icon = "mdi:car-electric-mode-selector"
    
    # Options are keys ("fast", "limited", "solar") defined in const.py
    _attr_options = CHARGING_MODES

    def __init__(self, coordinator, uid_prefix, point_index):
        super().__init__(coordinator)
        self._point_index = point_index
        self._attr_unique_id = f"{uid_prefix}_lp{point_index}_charging_mode"

    @property
    def current_option(self):
        return self.coordinator.logic.get_input(self._point_index, "mode")

    async def async_select_option(self, option: str) -> None:
        self.coordinator.logic.update_input(self._point_index, "mode", option)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, f"{self.coordinator.host}_lp{self._point_index}")},
            "via_device": (DOMAIN, self.coordinator.host),
        }