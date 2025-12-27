"""Config flow for Compleo Wallbox integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from pymodbus.client import AsyncModbusTcpClient

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, DEFAULT_PORT

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema({
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
            # Eingabe bereinigen: Leerzeichen entfernen
            host = user_input[CONF_HOST].strip()
            
            # Falls versehentlich http:// oder https:// eingegeben wurde, entfernen
            if host.startswith("http://"):
                host = host[7:]
            elif host.startswith("https://"):
                host = host[8:]
            
            # Bereinigten Host zurückschreiben für die Speicherung
            user_input[CONF_HOST] = host
            
            port = user_input[CONF_PORT]

            # Validate connection
            client = AsyncModbusTcpClient(host, port=port)
            try:
                await client.connect()
                if not client.connected:
                    # Wenn pymodbus keine Verbindung aufbauen kann
                    errors["base"] = "cannot_connect"
                else:
                    # Connection successful, try to read a register to verify (e.g., HW Type at 0x000E)
                    # Using slave=1 as default
                    rr = await client.read_input_registers(0x000E, 1, slave=1)
                    client.close()
                    
                    if rr.isError():
                         _LOGGER.warning("Connected to %s but failed to read register: %s", host, rr)
                    
                    await self.async_set_unique_id(f"{host}:{port}")
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=f"Compleo {host}",
                        data=user_input
                    )
            except Exception:
                _LOGGER.exception("Unexpected exception in config flow")
                errors["base"] = "cannot_connect"
            finally:
                # Sicherstellen, dass der Client geschlossen wird
                client.close()

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )