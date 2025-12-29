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
    
    Dynamically creates sensors for each detected Charging Point.
    """
    coordinator = hass.data[DOMAIN][entry.entry_id]
    uid_prefix = entry.unique_id or coordinator.host
    
    sensors = []

    # Iterate over detected charging points (e.g., 1 and 2)
    # The 'points' dictionary is populated in __init__.py
    points_data = coordinator.data.get("points", {})
    
    for point_index in points_data:
        # Create a set of sensors for THIS charging point
        # Define the sensors configuration
        # Format: (key, name, unit, device_class, state_class)
        sensor_types = [
            ("current_power", "Power", UnitOfPower.WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
            ("energy_total", "Total Energy", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING),
            ("voltage_l1", "Voltage L1", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT),
            ("voltage_l2", "Voltage L2", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT),
            ("voltage_l3", "Voltage L3", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT),
            ("current_l1", "Current L1", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
            ("current_l2", "Current L2", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
            ("current_l3", "Current L3", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
        ]

        # Add standard measurement sensors
        for key, name, unit, dev_class, state_class in sensor_types:
            sensors.append(
                CompleoSensor(
                    coordinator, uid_prefix, point_index, key, name, 
                    unit, dev_class, state_class
                )
            )
        
        # Add Status Code Sensor (Enum) separate due to different init signature
        sensors.append(
            CompleoSensor(
                coordinator, uid_prefix, point_index, "status_code", "Status",
                None, SensorDeviceClass.ENUM, None, icon="mdi:ev-station"
            )
        )
    
    async_add_entities(sensors)


class CompleoSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Compleo Sensor for a specific Charging Point."""

    def __init__(self, coordinator, uid_prefix, point_index, key, name, unit=None, device_class=None, state_class=None, icon=None):
        """
        Initialize the sensor.
        
        point_index: The detected charging point number (1 or 2).
        """
        super().__init__(coordinator)
        self._point_index = point_index
        self._key = key
        self._attr_has_entity_name = True
        
        # Name is relative to the device. Device name will be "Charging Point X".
        # Entity name will just be "Power", "Voltage L1", etc.
        self._attr_name = name
        
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_icon = icon
        
        # Unique ID needs to include the point index
        # e.g., "host_lp1_current_power"
        self._attr_unique_id = f"{uid_prefix}_lp{point_index}_{key}"
        
        # If this is the status sensor, enable translation keys for localized states
        if key == "status_code":
            self._attr_translation_key = "status_code"
            self._attr_options = ["0", "1", "2", "3", "4", "5", "6", "7", "8"]

    @property
    def native_value(self):
        """Return the current state of the sensor from coordinator data."""
        # Navigate to points -> index -> key
        points = self.coordinator.data.get("points", {})
        point_data = points.get(self._point_index, {})
        val = point_data.get(self._key)
        
        if self._key == "status_code" and val is not None:
            return str(val)
            
        return val

    @property
    def device_info(self):
        """
        Return device info.
        
        Creates a 'Sub-Device' for the specific Charging Point.
        This device is linked to the Main Device via `via_device`.
        """
        main_device_id = (DOMAIN, self.coordinator.host)
        point_device_id = (DOMAIN, f"{self.coordinator.host}_lp{self._point_index}")
        
        return {
            "identifiers": {point_device_id},
            "name": f"{self.coordinator.device_name} Point {self._point_index}",
            "manufacturer": "Compleo",
            "model": "Charging Point",
            "via_device": main_device_id, # Link to the main wallbox
        }