"""Sensors for Compleo Solo."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfElectricPotential, UnitOfElectricCurrent, UnitOfPower, UnitOfEnergy
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, STATUS_CODE_MAP, ERROR_CODE_MAP

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    
    entities = [
        CompleoSensor(coordinator, "status_code", "Status", None, None, STATUS_CODE_MAP),
        CompleoSensor(coordinator, "error_code", "Error Code", None, None, ERROR_CODE_MAP),
        CompleoSensor(coordinator, "current_power", "Power", UnitOfPower.WATT, SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT),
        CompleoSensor(coordinator, "energy", "Energy Charged", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING),
        CompleoSensor(coordinator, "volt_l1", "Voltage L1", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT),
        CompleoSensor(coordinator, "volt_l2", "Voltage L2", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT),
        CompleoSensor(coordinator, "volt_l3", "Voltage L3", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT),
        CompleoSensor(coordinator, "current_l1", "Current L1", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, state_class=SensorStateClass.MEASUREMENT),
        CompleoSensor(coordinator, "current_l2", "Current L2", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, state_class=SensorStateClass.MEASUREMENT),
        CompleoSensor(coordinator, "current_l3", "Current L3", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, state_class=SensorStateClass.MEASUREMENT),
        CompleoSensor(coordinator, "serial", "Serial Number", None, None),
    ]
    async_add_entities(entities)

class CompleoSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Compleo Sensor."""

    def __init__(self, coordinator, key, name, unit, device_class, map_dict=None, state_class=None):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = f"Compleo {name}"
        self._attr_unique_id = f"{coordinator.host}_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._map_dict = map_dict
        self._attr_state_class = state_class

    @property
    def native_value(self):
        val = self.coordinator.data.get(self._key)
        if self._map_dict and val is not None:
            return self._map_dict.get(val, f"Unknown ({val})")
        return val