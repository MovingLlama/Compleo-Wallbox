"""Support for Compleo Wallbox selection entities."""
from __future__ import annotations

import logging
import asyncio
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ADDR_LP1_BASE, ADDR_LP2_BASE, OFFSET_PHASE_MODE

_LOGGER = logging.getLogger(__name__)

PHASE_MODE_OPTIONS = {
    0: "Unavailable",
    1: "Automatic",
    2: "1-Phase",
    3: "3-Phase",
}
PHASE_MODE_TO_VALUE = {v: k for k, v in PHASE_MODE_OPTIONS.items()}

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Compleo select entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    uid_prefix = entry.unique_id or coordinator.host
    
    # Get dynamic point count
    num_points = 1
    if coordinator.data and "system" in coordinator.data:
        num_points = coordinator.data["system"].get("num_points", 1)

    entities = []
    
    for idx in range(1, num_points + 1):
        entities.append(CompleoPhaseMode(coordinator, uid_prefix, idx))
        
    async_add_entities(entities)

class CompleoPhaseMode(CoordinatorEntity, SelectEntity):
    """Representation of the Phase Mode Selection."""

    _attr_has_entity_name = True
    _attr_name = "Phase Mode"
    _attr_icon = "mdi:current-ac"
    _attr_options = list(PHASE_MODE_OPTIONS.values())

    def __init__(self, coordinator, uid_prefix, point_index):
        super().__init__(coordinator)
        self._point_index = point_index
        self._attr_unique_id = f"{uid_prefix}_lp{point_index}_phase_mode"
        
        # Calculate Register Address dynamically
        base = ADDR_LP1_BASE if point_index == 1 else ADDR_LP2_BASE
        self._register = base + OFFSET_PHASE_MODE

    @property
    def current_option(self) -> str | None:
        """Return the selected entity option to represent the entity state."""
        if not self.coordinator.data: return None
        points = self.coordinator.data.get("points", {})
        val = points.get(self._point_index, {}).get("phase_mode")
        
        if val in PHASE_MODE_OPTIONS:
            return PHASE_MODE_OPTIONS[val]
        return None

    @property
    def device_info(self):
        main_device_id = (DOMAIN, self.coordinator.host)
        point_device_id = (DOMAIN, f"{self.coordinator.host}_lp{self._point_index}")
        return {
            "identifiers": {point_device_id},
            "via_device": main_device_id,
        }

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        value = PHASE_MODE_TO_VALUE.get(option)
        if value is None:
            return

        try:
            # Use the new robust write function
            result = await self.coordinator.async_write_register(self._register, value)
            
            if result is not None and not (hasattr(result, 'isError') and result.isError()):
                await self.coordinator.async_request_refresh()
            else:
                _LOGGER.error("Failed to set phase mode: %s", result)
                
        except Exception as err:
            _LOGGER.error("Error setting phase mode: %s", err)