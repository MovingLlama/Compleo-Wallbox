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
    EntityCategory,
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
    
    # --- 1. System/Total Sensors ---
    # Only Total Power, no separate Info Sensors anymore
    sys_sensors = [
        ("total_power", "Total Power (Station)", UnitOfPower.WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
    ]
    for key, name, unit, dev_class, state_class in sys_sensors:
        sensors.append(
            CompleoSystemSensor(coordinator, uid_prefix, key, name, unit, dev_class, state_class)
        )

    # --- 2. Point Sensors ---
    data = coordinator.data or {"points": {}}
    points_data = data.get("points", {})
    indices = points_data.keys() if points_data else [1]

    for point_index in indices:
        point_sensors = [
            ("current_power", "Power", UnitOfPower.WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
            ("energy_total", "Total Energy", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING),
            ("voltage_l1", "Voltage L1", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT),
            ("voltage_l2", "Voltage L2", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT),
            ("voltage_l3", "Voltage L3", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT),
            ("current_l1", "Current L1", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
            ("current_l2", "Current L2", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
            ("current_l3", "Current L3", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
            ("phase_switch_count", "Phase Switches", None, None, SensorStateClass.MEASUREMENT),
        ]

        for key, name, unit, dev_class, state_class in point_sensors:
            sensors.append(
                CompleoPointSensor(
                    coordinator, uid_prefix, point_index, key, name, 
                    unit, dev_class, state_class
                )
            )
        
        # Status Enum
        sensors.append(
            CompleoPointSensor(
                coordinator, uid_prefix, point_index, "status_code", "Status",
                None, SensorDeviceClass.ENUM, None, icon="mdi:ev-station"
            )
        )
    
    async_add_entities(sensors)

class CompleoSystemSensor(CoordinatorEntity, SensorEntity):
    """Sensor for Global Station Data."""
    _attr_has_entity_name = True
    
    def __init__(self, coordinator, uid_prefix, key, name, unit, device_class, state_class):
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_unique_id = f"{uid_prefix}_system_{key}"

    @property
    def native_value(self):
        if not self.coordinator.data: return None
        return self.coordinator.data.get("system", {}).get(self._key)

    @property
    def device_info(self):
        """Return device registry information."""
        system_data = self.coordinator.data.get("system", {}) if self.coordinator.data else {}
        
        # Build Device Info from fetched data
        fw = system_data.get("firmware_version", "Unknown")
        model = system_data.get("article_number", "Compleo Wallbox")
        serial = system_data.get("serial_number")
        
        # Identifiers: Host is always primary. Add Serial if available.
        identifiers = {(DOMAIN, self.coordinator.host)}
        if serial:
            identifiers.add((DOMAIN, serial))

        return {
            "identifiers": identifiers,
            "name": self.coordinator.device_name,
            "manufacturer": "Compleo",
            "model": model,
            "sw_version": fw,
        }

class CompleoPointSensor(CoordinatorEntity, SensorEntity):
    """Sensor for a specific Charging Point."""

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
        if not self.coordinator.data: return None
        points = self.coordinator.data.get("points", {})
        val = points.get(self._point_index, {}).get(self._key)
        
        if self._key == "status_code" and val is not None:
            return str(val)
            
        return val

    @property
    def device_info(self):
        main_device_id = (DOMAIN, self.coordinator.host)
        point_device_id = (DOMAIN, f"{self.coordinator.host}_lp{self._point_index}")
        return {
            "identifiers": {point_device_id},
            "name": f"{self.coordinator.device_name} Point {self._point_index}",
            "manufacturer": "Compleo",
            "model": "Charging Point",
            "via_device": main_device_id,
        }