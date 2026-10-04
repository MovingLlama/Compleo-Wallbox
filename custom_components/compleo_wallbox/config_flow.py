"""Config flow for Compleo Wallbox integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from modbus_connection import ModbusError, ModbusExceptionError, ModbusTcpParams

from homeassistant import config_entries
from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_NAME
from homeassistant.data_entry_flow import FlowResult, AbortFlow
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import DOMAIN, DEFAULT_PORT, DEFAULT_NAME, DEFAULT_UNIT_ID, REG_SYS_NUM_POINTS

_LOGGER = logging.getLogger(__name__)

class CompleoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Compleo Wallbox."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: dict[str, Any] = {}

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> FlowResult:
        """Handle zeroconf discovery."""
        host = discovery_info.host
        port = DEFAULT_PORT 
        
        properties = discovery_info.properties
        model = properties.get("CCS-Hardware-Info", "Unknown").split(",")[0].replace("board[", "").replace("]", "")
        name = f"Compleo {model}" if model != "Unknown" else DEFAULT_NAME
        
        # Set unique ID based on host/port
        await self.async_set_unique_id(f"{host}_{port}")
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        self._discovery_info = {
            CONF_HOST: host,
            CONF_PORT: port,
            CONF_NAME: name,
        }

        self.context.update({
            "title_placeholders": {"name": name}
        })

        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm discovery."""
        if user_input is not None:
            return await self.async_step_user(user_input={
                **self._discovery_info,
                CONF_NAME: user_input.get(CONF_NAME, self._discovery_info[CONF_NAME])
            })

        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME, default=self._discovery_info[CONF_NAME]): str,
            }),
            description_placeholders={
                "host": self._discovery_info[CONF_HOST],
                "name": self._discovery_info[CONF_NAME]
            }
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step (manual setup)."""
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            if "://" in host:
                host = host.split("://")[-1]
            
            user_input[CONF_HOST] = host
            port = user_input[CONF_PORT]
            name = user_input[CONF_NAME]

            # 1. Check if configured
            try:
                await self.async_set_unique_id(f"{host}_{port}")
                self._abort_if_unique_id_configured()
            except AbortFlow:
                return self.async_abort(reason="already_configured")

            # 2. Test Connection: the wallbox must answer a Modbus request,
            # an open TCP port alone is not enough
            try:
                async with async_get_temporary_unit(
                    self.hass, ModbusTcpParams(host=host, port=port), DEFAULT_UNIT_ID
                ) as unit:
                    await unit.read_input_registers(REG_SYS_NUM_POINTS, 1)
            except ModbusExceptionError:
                # The wallbox answered (with an exception response): reachable
                pass
            except (ModbusError, HomeAssistantError) as err:
                _LOGGER.debug("Connection test to %s:%s failed: %s", host, port, err)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception in config flow")
                errors["base"] = "cannot_connect"

            if not errors:
                return self.async_create_entry(title=name, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
            }),
            errors=errors
        )