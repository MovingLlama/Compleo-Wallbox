"""Support for Compleo Wallbox switch entities."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ADDR_LP1_BASE, ADDR_LP2_BASE, OFFSET_PHASE_MODE

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    uid_prefix = entry.unique_id or coordinator.host
    num_points = 1
    if coordinator.data and "system" in coordinator.data:
        num_points = coordinator.data["system"].get("num_points", 1)

    entities = []
    for idx in range(1, num_points + 1):
        entities.append(CompleoZoeSwitch(coordinator, uid_prefix, idx))
    
    async_add_entities(entities)

class CompleoZoeSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to enable Alternative Logic (e.g. for Zoe)."""
    _attr_has_entity_name = True
    _attr_name = "ALT Mode"
    _attr_icon = "mdi:car-electric"

    def __init__(self, coordinator, uid_prefix, point_index):
        super().__init__(coordinator)
        self._point_index = point_index
        self._attr_unique_id = f"{uid_prefix}_lp{point_index}_zoe_mode"

    @property
    def is_on(self):
        return self.coordinator.logic.get_input(self._point_index, "zoe_mode")

    async def async_turn_on(self, **kwargs):
        self.coordinator.logic.update_input(self._point_index, "zoe_mode", True)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        self.coordinator.logic.update_input(self._point_index, "zoe_mode", False)
        
        # Reset Phase Mode to Automatic (1) when disabling ALT Mode
        base = ADDR_LP1_BASE if self._point_index == 1 else ADDR_LP2_BASE
        if base is not None:
             # 1 = Automatic
             await self.coordinator.async_write_register(base + OFFSET_PHASE_MODE, 1)

        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, f"{self.coordinator.host}_lp{self._point_index}")},
            "via_device": (DOMAIN, self.coordinator.host),
        }