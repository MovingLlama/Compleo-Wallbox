"""Config flow for Compleo Solo."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from pymodbus.client import AsyncModbusTcpClient

from .const import DOMAIN, DEFAULT_PORT, DEFAULT_SCAN_INTERVAL

class CompleoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Validate connection
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            
            client = AsyncModbusTcpClient(host, port=port)
            try:
                await client.connect()
                if client.connected:
                    client.close()
                    return self.async_create_entry(title=f"Compleo {host}", data=user_input)
                else:
                    errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
            }),
            errors=errors,
        )