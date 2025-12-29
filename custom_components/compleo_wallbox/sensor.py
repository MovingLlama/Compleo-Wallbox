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
    
    sensors = []
    
    # Safe access to data. If None, default to empty dict inside the structure.
    # The coordinator __init__ now guarantees 'data' is a dict, but we double check.
    data = coordinator.data or {"points": {}}
    points_data = data.get("points", {})
    
    # If no points detected yet (e.g. startup fail), assume at least Point 1 exists
    # so entities are created and show as "Unavailable" instead of missing.
    indices_to_create = points_data.keys() if points_data else [1]

    for point_index in indices_to_create:
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

        for key, name, unit, dev_class, state_class in sensor_types:
            sensors.append(
                CompleoSensor(
                    coordinator, uid_prefix, point_index, key, name, 
                    unit, dev_class, state_class
                )
            )
        
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
        super().__init__(coordinator)
        self._point_index = point_index
        self._key = key
        self._attr_has_entity_name = True
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_icon = icon
        self._attr_unique_id = f"{uid_prefix}_lp{point_index}_{key}"
        
        if key == "status_code":
            self._attr_translation_key = "status_code"
            self._attr_options = ["0", "1", "2", "3", "4", "5", "6", "7", "8"]

    @property
    def native_value(self):
        """Return the current state of the sensor from coordinator data."""
        # Safe navigation through the dictionary
        if not self.coordinator.data:
            return None
            
        points = self.coordinator.data.get("points", {})
        point_data = points.get(self._point_index, {})
        val = point_data.get(self._key)
        
        if self._key == "status_code" and val is not None:
            return str(val)
            
        return val

    @property
    def device_info(self):
        """Return device info."""
        main_device_id = (DOMAIN, self.coordinator.host)
        point_device_id = (DOMAIN, f"{self.coordinator.host}_lp{self._point_index}")
        
        return {
            "identifiers": {point_device_id},
            "name": f"{self.coordinator.device_name} Point {self._point_index}",
            "manufacturer": "Compleo",
            "model": "Charging Point",
            "via_device": main_device_id,
        }