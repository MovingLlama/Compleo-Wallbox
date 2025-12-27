"""Number entities for Compleo Solo."""
from homeassistant.components.number import NumberEntity, NumberDeviceClass
from homeassistant.const import UnitOfPower
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, REG_POWER_ABS_SETPOINT

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up number entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([CompleoPowerLimit(coordinator)])

class CompleoPowerLimit(CoordinatorEntity, NumberEntity):
    """Control Power Limit (Absolute)."""

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_name = "Compleo Power Limit"
        self._attr_unique_id = f"{coordinator.host}_power_limit"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = NumberDeviceClass.POWER
        # Assuming 11kW max, 6A (4140W) min usually, but allowing 0 to max
        self._attr_native_min_value = 0
        self._attr_native_max_value = 22000 # 22kW max safety
        self._attr_native_step = 100

    @property
    def native_value(self):
        """Return the current value."""
        return self.coordinator.data.get("power_setpoint")

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        # Convert Watts to 100W steps (Integer)
        # 1000W -> 10
        val_int = int(value / 100)
        await self.coordinator.async_write_register(REG_POWER_ABS_SETPOINT, val_int)
        # Update local state immediately for responsiveness
        self.coordinator.data["power_setpoint"] = val_int * 100
        self.async_write_ha_state()