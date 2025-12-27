"""Config flow for Compleo Wallbox integration."""
from __future__ import annotations

import logging
import asyncio
from typing import Any

import voluptuous as vol
from pymodbus.client import AsyncModbusTcpClient

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_NAME
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, DEFAULT_PORT, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
    vol.Required(CONF_HOST): str,
    vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
})

class CompleoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Compleo Wallbox."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            if "://" in host:
                host = host.split("://")[-1]
            
            user_input[CONF_HOST] = host
            port = user_input[CONF_PORT]
            name = user_input[CONF_NAME]

            client = AsyncModbusTcpClient(host, port=port, timeout=5)
            try:
                connected = await client.connect()
                if not connected:
                    errors["base"] = "cannot_connect"
                else:
                    # Kurze Pause, da manche Modbus-Stacks Zeit nach dem Connect brauchen
                    await asyncio.sleep(1)
                    
                    success = False
                    # Wir testen verschiedene Slave-IDs, da Compleo-Modelle variieren können
                    for slave_id in [1, 255, 0]:
                        for param in ["slave", "unit", "device_id"]:
                            try:
                                # Teste Firmware-Register (0x0006)
                                rr = await client.read_input_registers(0x0006, 1, **{param: slave_id})
                                if rr is not None and not rr.isError():
                                    success = True
                                    _LOGGER.info("Successfully communicated with Slave ID %s using %s", slave_id, param)
                                    break
                            except Exception:
                                continue
                        if success:
                            break
                    
                    if not success:
                        _LOGGER.warning(
                            "Modbus connection to %s established, but could not read registers. "
                            "Will proceed anyway, but sensors might be unavailable initially.", 
                            host
                        )
                    
                    await self.async_set_unique_id(f"{host}_{port}")
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=name,
                        data=user_input
                    )
            except Exception:
                _LOGGER.exception("Unexpected exception in config flow")
                errors["base"] = "cannot_connect"
            finally:
                client.close()

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )