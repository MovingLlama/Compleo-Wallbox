"""Support for Compleo Wallbox number settings."""
from __future__ import annotations

import logging
import asyncio
from homeassistant.components.number import NumberEntity, NumberDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """
    Set up the Compleo number entities.
    
    Creates the 'Charging Power Limit' entity.
    """
    coordinator = hass.data[DOMAIN][entry.entry_id]
    uid_prefix = entry.unique_id or coordinator.host
    async_add_entities([CompleoPowerLimit(coordinator, uid_prefix)])


class CompleoPowerLimit(CoordinatorEntity, NumberEntity):
    """
    Representation of the Charging Power Limit.
    
    Allows the user to set the maximum charging power (in Watts).
    Writes to Modbus Holding Register 0x0000.
    """

    _attr_has_entity_name = True
    _attr_name = "Charging Power Limit"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = NumberDeviceClass.POWER
    # Range defined by spec or reasonable hardware limits (0 to 22kW)
    _attr_native_min_value = 0
    _attr_native_max_value = 22000 
    _attr_native_step = 100
    _attr_icon = "mdi:speedometer"

    def __init__(self, coordinator, uid_prefix):
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{uid_prefix}_power_limit"

    @property
    def native_value(self):
        """
        Return the current value.
        
        Reads 'power_setpoint_abs' from coordinator data.
        Register value is in 100W steps, so we multiply by 100 to get Watts.
        """
        raw = self.coordinator.data.get("power_setpoint_abs")
        if raw is not None:
            return float(raw * 100)
        return None

    @property
    def device_info(self):
        """Return device info."""
        return self.coordinator.device_info_map

    async def async_set_native_value(self, value: float) -> None:
        """
        Update the current value.
        
        Writes the new value to the Modbus register.
        """
        # Convert Watts back to 100W units for the register
        modbus_val = int(value / 100)
        
        try:
            # Use the detected Modbus parameter name (slave/unit/device_id)
            param = self.coordinator._param_name or "slave"
            
            # Ensure connection is open
            if not self.coordinator.client.connected:
                await self.coordinator.client.connect()
                await asyncio.sleep(0.5) # Short pause after reconnect

            # Write to Holding Register 0x0000
            result = await self.coordinator.client.write_register(0x0000, modbus_val, **{param: 1})
            
            if result.isError():
                _LOGGER.error("Modbus error while writing power limit: %s", result)
            else:
                # Trigger an immediate refresh to update the UI
                await self.coordinator.async_request_refresh()
                
        except Exception as err:
            _LOGGER.error("Error writing power limit to Compleo Wallbox: %s", err)