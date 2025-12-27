"""Select entities for Compleo Solo."""
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, REG_CP_SINK_MODE, SINK_MODE_MAP, SINK_MODE_REVERSE

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up select entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([CompleoSinkMode(coordinator)])

class CompleoSinkMode(CoordinatorEntity, SelectEntity):
    """Control Charging Phase Mode."""

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Compleo Phase Mode"
        self._attr_unique_id = f"{coordinator.host}_sink_mode"
        self._attr_options = list(SINK_MODE_REVERSE.keys())

    @property
    def current_option(self):
        """Return the current value."""
        val = self.coordinator.data.get("cp_sink_mode")
        return SINK_MODE_MAP.get(val)

    async def async_select_option(self, option: str) -> None:
        """Update the current value."""
        val_int = SINK_MODE_REVERSE.get(option)
        if val_int is not None:
            await self.coordinator.async_write_register(REG_CP_SINK_MODE, val_int)
            self.coordinator.data["cp_sink_mode"] = val_int
            self.async_write_ha_state()