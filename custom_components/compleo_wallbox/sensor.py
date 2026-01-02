"""Support for Compleo Wallbox sensors."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CHARGE_POINT_ERROR_CODES, DERATING_STATUS_MAP

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Compleo sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    uid_prefix = entry.unique_id or coordinator.host
    
    num_points = 1
    if coordinator.data and "system" in coordinator.data:
        num_points = coordinator.data["system"].get("num_points", 1)

    sensors = []
    
    # --- 1. System Sensors ---
    sys_sensors = [
        ("total_power", UnitOfPower.WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
        ("total_current_l1", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
        ("total_current_l2", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
        ("total_current_l3", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
        ("unused_power", UnitOfPower.WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
        ("total_energy_session", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING),
        # Removed hardcoded "total_energy_total", added virtual one below
    ]
    for key, unit, dev_class, state_class in sys_sensors:
        sensors.append(
            CompleoSystemSensor(coordinator, uid_prefix, key, unit, dev_class, state_class)
        )
    
    # Virtual System Total (Accumulates Station Sessions)
    sensors.append(
        CompleoAccumulatedSensor(
            coordinator, uid_prefix, 0, # 0 = System
            "total_energy_total", "total_energy_session", # Target key, Source key
            UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING
        )
    )
        
    # --- 2. Point Sensors ---
    for point_index in range(1, num_points + 1):
        point_sensors = [
            ("current_power", UnitOfPower.WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
            ("energy_session", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING),
            # "meter_reading" removed here, handled by Virtual Sensor below
            ("voltage_l1", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT),
            ("voltage_l2", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT),
            ("voltage_l3", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT),
            ("current_l1", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
            ("current_l2", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
            ("current_l3", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
            ("phase_switch_count", None, None, SensorStateClass.MEASUREMENT),
            ("charging_time", UnitOfTime.SECONDS, SensorDeviceClass.DURATION, SensorStateClass.MEASUREMENT),
        ]

        for key, unit, dev_class, state_class in point_sensors:
            sensors.append(
                CompleoPointSensor(coordinator, uid_prefix, point_index, key, unit, dev_class, state_class)
            )
        
        # Virtual Meter Reading (Accumulates Session)
        sensors.append(
            CompleoAccumulatedSensor(
                coordinator, uid_prefix, point_index,
                "meter_reading", "energy_session", # Target key, Source key
                UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL_INCREASING
            )
        )

        sensors.append(CompleoPointSensor(coordinator, uid_prefix, point_index, "rfid_tag", None, None, None, icon="mdi:card-account-details"))

        sensors.append(CompleoPointSensor(coordinator, uid_prefix, point_index, "status_code", None, SensorDeviceClass.ENUM, None, icon="mdi:ev-station"))
        sensors.append(CompleoPointSensor(coordinator, uid_prefix, point_index, "error_code", None, SensorDeviceClass.ENUM, None, icon="mdi:alert-circle"))
        sensors.append(CompleoPointSensor(coordinator, uid_prefix, point_index, "derating_status", None, SensorDeviceClass.ENUM, None, icon="mdi:thermometer-alert"))
    
    async_add_entities(sensors)

class CompleoSystemSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, uid_prefix, key, unit, device_class, state_class, icon=None):
        super().__init__(coordinator)
        self._key = key
        self._attr_translation_key = key
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_unique_id = f"{uid_prefix}_system_{key}"
        if icon: self._attr_icon = icon

    @property
    def native_value(self):
        if not self.coordinator.data: return None
        return self.coordinator.data.get("system", {}).get(self._key)

    @property
    def device_info(self):
        system_data = self.coordinator.data.get("system", {}) if self.coordinator.data else {}
        return {
            "identifiers": {(DOMAIN, self.coordinator.host)},
            "name": self.coordinator.device_name,
            "manufacturer": "Compleo",
            "model": system_data.get("article_number", "Compleo Wallbox"),
            "sw_version": system_data.get("firmware_version", "Unknown"),
        }

class CompleoPointSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, uid_prefix, point_index, key, unit=None, device_class=None, state_class=None, icon=None):
        super().__init__(coordinator)
        self._point_index = point_index
        self._key = key
        self._attr_translation_key = key
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_icon = icon
        self._attr_unique_id = f"{uid_prefix}_lp{point_index}_{key}"
        
        if key == "status_code": self._attr_options = ["0", "1", "2", "3", "4", "5", "6", "7", "8"]
        elif key == "error_code": self._attr_options = list(CHARGE_POINT_ERROR_CODES.values())
        elif key == "derating_status": self._attr_options = list(DERATING_STATUS_MAP.values())

    @property
    def native_value(self):
        if not self.coordinator.data: return None
        points = self.coordinator.data.get("points", {})
        val = points.get(self._point_index, {}).get(self._key)
        
        if self._key == "error_code" and val is not None: return CHARGE_POINT_ERROR_CODES.get(val, "unknown_error")
        if self._key == "derating_status" and val is not None: return DERATING_STATUS_MAP.get(val, "unknown_status")
        if self._key == "status_code" and val is not None: return str(val)
        return val

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, f"{self.coordinator.host}_lp{self._point_index}")},
            "name": f"{self.coordinator.device_name} Point {self._point_index}",
            "manufacturer": "Compleo",
            "model": "Charging Point",
            "via_device": (DOMAIN, self.coordinator.host),
        }

class CompleoAccumulatedSensor(CoordinatorEntity, RestoreEntity, SensorEntity):
    """Virtual Sensor that accumulates session energy into a lifetime total."""
    _attr_has_entity_name = True

    def __init__(self, coordinator, uid_prefix, point_index, key, source_key, unit, device_class, state_class):
        super().__init__(coordinator)
        self._point_index = point_index
        self._key = key           # e.g., meter_reading
        self._source_key = source_key # e.g., energy_session
        self._attr_translation_key = key
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        
        if point_index == 0:
            self._attr_unique_id = f"{uid_prefix}_system_{key}"
        else:
            self._attr_unique_id = f"{uid_prefix}_lp{point_index}_{key}"

        self._total_value = 0.0
        self._last_session_value = 0.0

    @property
    def native_value(self):
        return self._total_value

    @property
    def extra_state_attributes(self):
        """Record the last session value to handle restarts correctly."""
        return {"last_session_value": self._last_session_value}

    async def async_added_to_hass(self):
        """Restore state after restart."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state:
            try:
                self._total_value = float(last_state.state)
                # Restore the tracking variable
                if "last_session_value" in last_state.attributes:
                    self._last_session_value = float(last_state.attributes["last_session_value"])
            except (ValueError, TypeError):
                pass

    def _handle_coordinator_update(self) -> None:
        """Calculate delta and add to total."""
        current_session = 0.0
        
        # Get source data
        if self._point_index == 0:
            # System
            current_session = self.coordinator.data.get("system", {}).get(self._source_key, 0.0)
        else:
            # Point
            points = self.coordinator.data.get("points", {})
            current_session = points.get(self._point_index, {}).get(self._source_key, 0.0)
            
        if current_session is None:
            return

        # Calculate Delta
        delta = current_session - self._last_session_value
        
        # Handle Reset (New Session started) or Restart
        if delta < 0:
            # Session reset to 0 (or lower value).
            # Assume the new value is the total gained since 0.
            delta = current_session
        
        # Sanity check: Ignore huge jumps? (Optional)
        
        self._total_value += delta
        self._last_session_value = current_session
        
        self.async_write_ha_state()

    @property
    def device_info(self):
        # Same logic as other sensors to attach to correct device
        if self._point_index == 0:
            return {
                "identifiers": {(DOMAIN, self.coordinator.host)},
                "name": self.coordinator.device_name,
                "manufacturer": "Compleo",
                "model": "Wallbox (System)",
            }
        else:
            return {
                "identifiers": {(DOMAIN, f"{self.coordinator.host}_lp{self._point_index}")},
                "name": f"{self.coordinator.device_name} Point {self._point_index}",
                "manufacturer": "Compleo",
                "model": "Charging Point",
                "via_device": (DOMAIN, self.coordinator.host),
            }