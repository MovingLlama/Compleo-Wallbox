"""Support for Compleo Wallbox sensors."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.restore_state import RestoreEntity, RestoredExtraData
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
            "total_energy_total", "energy_session", # Target key, Source key (summed over all points)
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
        return self.coordinator.system_device_info()

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
        return self.coordinator.point_device_info(self._point_index)

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
        # Last seen session value per charging point (the station sensor tracks all points)
        self._last_sessions: dict[int, float] = {}
        self._restored = False

    def _source_points(self) -> list[int]:
        if self._point_index != 0:
            return [self._point_index]
        num_points = 1
        if self.coordinator.data:
            num_points = self.coordinator.data.get("system", {}).get("num_points", 1)
        return list(range(1, num_points + 1))

    @property
    def native_value(self):
        return self._total_value

    @property
    def extra_state_attributes(self):
        """Expose the tracked session values (informational)."""
        if self._point_index == 0:
            return {"last_session_values": {str(k): v for k, v in self._last_sessions.items()}}
        return {"last_session_value": self._last_sessions.get(self._point_index, 0.0)}

    @property
    def extra_restore_state_data(self) -> RestoredExtraData:
        """Stored independently of the state, so it survives an 'unavailable' state at shutdown."""
        return RestoredExtraData({
            "total": self._total_value,
            "last_sessions": {str(k): v for k, v in self._last_sessions.items()},
        })

    async def async_added_to_hass(self):
        """Restore state after restart."""
        await super().async_added_to_hass()
        extra = await self.async_get_last_extra_data()
        data = extra.as_dict() if extra else {}
        if "total" in data:
            try:
                self._total_value = float(data["total"])
                for k, v in data.get("last_sessions", {}).items():
                    self._last_sessions[int(k)] = float(v)
                self._restored = True
                return
            except (ValueError, TypeError):
                pass

        # Migration from older versions: total in the state, session in an attribute
        last_state = await self.async_get_last_state()
        if last_state:
            try:
                self._total_value = float(last_state.state)
                self._restored = True
                if self._point_index != 0 and "last_session_value" in last_state.attributes:
                    self._last_sessions[self._point_index] = float(last_state.attributes["last_session_value"])
            except (ValueError, TypeError):
                pass

    def _handle_coordinator_update(self) -> None:
        """Calculate delta per charging point and add it to the total."""
        if not self.coordinator.last_update_success or not self.coordinator.data:
            return
        points = self.coordinator.data.get("points", {})

        for idx in self._source_points():
            current_session = points.get(idx, {}).get(self._source_key)
            if current_session is None:
                # Value not read in this cycle: skip instead of assuming 0,
                # otherwise the whole session would be counted again later.
                continue

            last = self._last_sessions.get(idx)
            if last is None:
                # First value for this point. On a fresh install count the running
                # session, after a restore/migration we cannot know the history.
                delta = 0.0 if self._restored else current_session
            else:
                delta = current_session - last
                if delta < 0:
                    # New session started: the new value is the energy since 0
                    delta = current_session

            self._total_value += delta
            self._last_sessions[idx] = current_session

        self.async_write_ha_state()

    @property
    def device_info(self):
        if self._point_index == 0:
            return self.coordinator.system_device_info()
        return self.coordinator.point_device_info(self._point_index)