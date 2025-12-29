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
    """
    Set up the Compleo sensors.
    
    Reads the coordinator from hass.data and creates the sensor entities.
    """
    coordinator = hass.data[DOMAIN][entry.entry_id]
    # Use the entry unique ID or host as a prefix for sensor IDs
    uid_prefix = entry.unique_id or coordinator.host

    # Define the list of sensors to create
    sensors = [
        CompleoSensor(
            coordinator, uid_prefix, "current_power", "Current Power", 
            UnitOfPower.WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT
        ),
        CompleoSensor(
            coordinator, uid_prefix, "energy_total", "Total Energy", 
            UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING
        ),
        CompleoSensor(
            coordinator, uid_prefix, "voltage_l1", "Voltage L1", 
            UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT
        ),
        CompleoSensor(
            coordinator, uid_prefix, "voltage_l2", "Voltage L2", 
            UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT
        ),
        CompleoSensor(
            coordinator, uid_prefix, "voltage_l3", "Voltage L3", 
            UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT
        ),
        CompleoSensor(
            coordinator, uid_prefix, "current_l1", "Current L1", 
            UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT
        ),
        CompleoSensor(
            coordinator, uid_prefix, "current_l2", "Current L2", 
            UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT
        ),
        CompleoSensor(
            coordinator, uid_prefix, "current_l3", "Current L3", 
            UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT
        ),
        # Status Code needs special handling (enum/translation)
        CompleoSensor(
            coordinator, uid_prefix, "status_code", "Status", 
            None, SensorDeviceClass.ENUM, None, icon="mdi:ev-station"
        ),
    ]
    
    async_add_entities(sensors)

class CompleoSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Compleo Sensor."""

    def __init__(self, coordinator, uid_prefix, key, name, unit=None, device_class=None, state_class=None, icon=None):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._key = key
        self._attr_has_entity_name = True
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_icon = icon
        self._attr_unique_id = f"{uid_prefix}_{key}"
        
        # If this is the status sensor, enable translation keys for localized states
        if key == "status_code":
            self._attr_translation_key = "status_code"
            # Define possible option values (0-8)
            self._attr_options = ["0", "1", "2", "3", "4", "5", "6", "7", "8"]

    @property
    def native_value(self):
        """Return the current state of the sensor from coordinator data."""
        val = self.coordinator.data.get(self._key)
        
        # Ensure status code is returned as a string for Enum sensors
        if self._key == "status_code" and val is not None:
            return str(val)
            
        return val

    @property
    def device_info(self):
        """Return device info to link this entity to the device registry."""
        return self.coordinator.device_info_map