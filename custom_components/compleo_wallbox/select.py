"""Support for Compleo Wallbox selection entities."""
from __future__ import annotations

import logging
import asyncio
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Mapping from Value to Text
PHASE_MODE_OPTIONS = {
    0: "Unavailable",
    1: "Automatic",
    2: "1-Phase",
    3: "3-Phase",
}
# Reverse mapping for writing
PHASE_MODE_TO_VALUE = {v: k for k, v in PHASE_MODE_OPTIONS.items()}

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Compleo select entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    uid_prefix = entry.unique_id or coordinator.host
    
    entities = []
    
    data = coordinator.data or {"points": {}}
    points_data = data.get("points", {})
    indices = points_data.keys() if points_data else [1]
    
    for idx in indices:
        entities.append(CompleoPhaseMode(coordinator, uid_prefix, idx))
        
    async_add_entities(entities)

class CompleoPhaseMode(CoordinatorEntity, SelectEntity):
    """Representation of the Phase Mode Selection (0x1009)."""

    _attr_has_entity_name = True
    _attr_name = "Phase Mode"
    _attr_icon = "mdi:current-ac"
    _attr_options = list(PHASE_MODE_OPTIONS.values())

    def __init__(self, coordinator, uid_prefix, point_index):
        super().__init__(coordinator)
        self._point_index = point_index
        self._attr_unique_id = f"{uid_prefix}_lp{point_index}_phase_mode"
        # Register: 0x1009 (LP1), 0x2009 (LP2)
        self._register = (point_index * 0x1000) + 0x009

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
            param = self.coordinator._param_name or "slave"
            if not self.coordinator.client.connected:
                await self.coordinator.client.connect()
                await asyncio.sleep(0.1)
            
            result = await self.coordinator.client.write_register(self._register, value, **{param: 1})
            if not result.isError():
                await self.coordinator.async_request_refresh()
            else:
                _LOGGER.error("Failed to set phase mode: %s", result)
                
        except Exception as err:
            _LOGGER.error("Error setting phase mode: %s", err)