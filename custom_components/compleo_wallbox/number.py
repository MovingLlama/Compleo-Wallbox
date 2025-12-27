"""Support for Compleo Wallbox number settings."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Compleo numbers."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([CompleoPowerLimit(coordinator)])


class CompleoPowerLimit(CoordinatorEntity, NumberEntity):
    """Representation of the Charging Power Limit."""

    _attr_name = "Charging Power Limit"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_min_value = 0
    _attr_native_max_value = 22000 
    _attr_native_step = 100
    _attr_icon = "mdi:speedometer"

    def __init__(self, coordinator):
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.host}_power_limit"

    @property
    def native_value(self):
        """Return the current value."""
        raw = self.coordinator.data.get("power_setpoint_abs")
        return raw * 100 if raw is not None else None

    @property
    def device_info(self):
        """Return device info."""
        return self.coordinator.device_info_map

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        modbus_val = int(value / 100)
        try:
            # Nutzt den erkannten Parameter (device_id, slave oder unit)
            param = self.coordinator._param_name or "slave"
            await self.coordinator.client.write_register(0x0000, modbus_val, **{param: 1})
            await self.coordinator.async_request_refresh()
        except Exception as err:
            self.coordinator.logger.error("Error writing power limit: %s", err)