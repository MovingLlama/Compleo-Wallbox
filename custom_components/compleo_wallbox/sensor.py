"""Support for Compleo Wallbox sensors."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Compleo sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    uid_prefix = entry.unique_id or coordinator.host

    sensors = [
        CompleoSensor(coordinator, uid_prefix, "current_power", "Current Power", UnitOfPower.WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
        CompleoSensor(coordinator, uid_prefix, "energy_total", "Total Energy", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING),
        CompleoSensor(coordinator, uid_prefix, "voltage_l1", "Voltage L1", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT),
        CompleoSensor(coordinator, uid_prefix, "voltage_l2", "Voltage L2", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT),
        CompleoSensor(coordinator, uid_prefix, "voltage_l3", "Voltage L3", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT),
        CompleoSensor(coordinator, uid_prefix, "current_l1", "Current L1", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
        CompleoSensor(coordinator, uid_prefix, "current_l2", "Current L2", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
        CompleoSensor(coordinator, uid_prefix, "current_l3", "Current L3", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
        CompleoSensor(coordinator, uid_prefix, "status_code", "Status", None, SensorDeviceClass.ENUM, None, icon="mdi:ev-station"),
    ]
    async_add_entities(sensors)

class CompleoSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Compleo Sensor."""

    def __init__(self, coordinator, uid_prefix, key, name, unit=None, device_class=None, state_class=None, icon=None):
        """Initialize."""
        super().__init__(coordinator)
        self._key = key
        self._attr_has_entity_name = True
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_icon = icon
        self._attr_unique_id = f"{uid_prefix}_{key}"
        
        if key == "status_code":
            self._attr_translation_key = "status_code"
            self._attr_options = ["0", "1", "2", "3", "4", "5", "6", "7", "8"]

    @property
    def native_value(self):
        """Return the state of the sensor."""
        val = self.coordinator.data.get(self._key)
        if self._key == "status_code" and val is not None:
            return str(val)
        return val

    @property
    def device_info(self):
        """Return device info."""
        return self.coordinator.device_info_map