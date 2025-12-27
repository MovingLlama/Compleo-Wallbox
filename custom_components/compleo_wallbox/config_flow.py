"""Config flow for Compleo Wallbox integration."""
from __future__ import annotations

import logging
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
            # Protokoll-Präfixe entfernen, falls der User sie eingegeben hat
            if "://" in host:
                host = host.split("://")[-1]
            
            user_input[CONF_HOST] = host
            port = user_input[CONF_PORT]
            name = user_input[CONF_NAME]

            client = AsyncModbusTcpClient(host, port=port)
            try:
                connected = await client.connect()
                if not connected:
                    errors["base"] = "cannot_connect"
                else:
                    success = False
                    for param in ["slave", "unit", "device_id"]:
                        try:
                            # 0x0006 ist die Firmware (Input Register)
                            rr = await client.read_input_registers(0x0006, 1, **{param: 1})
                            if rr is not None and not rr.isError():
                                success = True
                                break
                        except Exception:
                            continue
                    
                    if not success:
                        _LOGGER.warning("Modbus connection established but registers could not be read. Check Slave ID or Firewall.")
                    
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
                # Korrektur: close() ist bei AsyncModbusTcpClient keine awaitable Methode
                client.close()

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )