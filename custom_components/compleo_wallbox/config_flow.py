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
            # Eingabe bereinigen
            host = user_input[CONF_HOST].strip()
            if host.startswith("http://"):
                host = host[7:]
            elif host.startswith("https://"):
                host = host[8:]
            
            user_input[CONF_HOST] = host
            port = user_input[CONF_PORT]

            client = AsyncModbusTcpClient(host, port=port)
            try:
                await client.connect()
                if not client.connected:
                    errors["base"] = "cannot_connect"
                else:
                    # Wir versuchen ein sehr sicheres Register zu lesen: 0x0000 (Holding)
                    # Dies ist die Leistungsvorgabe und sollte immer existieren.
                    success = False
                    for param in ["device_id", "slave", "unit"]:
                        try:
                            kwargs = {param: 1}
                            # Versuche Register 0x0000 (Holding) statt 0x000E (Input)
                            rr = await client.read_holding_registers(0x0000, 1, **kwargs)
                            if rr is not None and not rr.isError():
                                success = True
                                break
                        except TypeError:
                            continue
                        except Exception:
                            continue
                    
                    client.close()
                    
                    # Wenn wir verbunden sind, lassen wir das Setup zu, auch wenn das 
                    # Test-Lesen fehlschlug (manche Boxen sind im Standby sehr restriktiv)
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
                client.close()

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )