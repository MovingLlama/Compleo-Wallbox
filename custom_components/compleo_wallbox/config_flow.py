"""Config flow for Compleo Wallbox integration."""
from __future__ import annotations

import logging
import asyncio
from typing import Any

import voluptuous as vol
from pymodbus.client import AsyncModbusTcpClient

from homeassistant import config_entries
from homeassistant.components import zeroconf
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_NAME
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, DEFAULT_PORT, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)

class CompleoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Compleo Wallbox."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: dict[str, Any] = {}

    async def async_step_zeroconf(
        self, discovery_info: zeroconf.ZeroconfServiceInfo
    ) -> FlowResult:
        """
        Handle zeroconf discovery.
        
        Automatically detected when the device is on the network.
        """
        host = discovery_info.host
        # Modbus usually runs on port 502, not the HTTP port returned by Zeroconf
        port = DEFAULT_PORT 
        
        # Extract information from TXT Records
        # Example format: "CCS-Hardware-Info=board[P51]..."
        properties = discovery_info.properties
        model = properties.get("CCS-Hardware-Info", "Unknown").split(",")[0].replace("board[", "").replace("]", "")
        
        # Construct a default name
        name = f"Compleo {model}" if model != "Unknown" else DEFAULT_NAME
        
        # Use host_port as a unique ID to prevent duplicates
        await self.async_set_unique_id(f"{host}_{port}")
        self._abort_if_unique_id_configured()

        # Store discovery info for the next step
        self._discovery_info = {
            CONF_HOST: host,
            CONF_PORT: port,
            CONF_NAME: name,
        }

        # Update context to show the discovered name in the UI
        self.context.update({
            "title_placeholders": {"name": name}
        })

        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """
        Confirm discovery.
        
        Shows a confirmation dialog to the user with the discovered data.
        """
        if user_input is not None:
            # User confirmed, proceed to creation
            return await self.async_step_user(user_input={
                **self._discovery_info,
                CONF_NAME: user_input.get(CONF_NAME, self._discovery_info[CONF_NAME])
            })

        # Show the confirmation form
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
        """
        Handle the initial step (manual setup).
        
        Also handles the final creation step from discovery.
        """
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            # Clean up URL format if user accidentally entered http://
            if "://" in host:
                host = host.split("://")[-1]
            
            user_input[CONF_HOST] = host
            port = user_input[CONF_PORT]
            name = user_input[CONF_NAME]

            # Test the connection
            client = AsyncModbusTcpClient(host, port=port, timeout=5)
            try:
                connected = await client.connect()
                if not connected:
                    errors["base"] = "cannot_connect"
                else:
                    await asyncio.sleep(1)
                    
                    # Set unique ID to prevent duplicates
                    await self.async_set_unique_id(f"{host}_{port}")
                    self._abort_if_unique_id_configured()

                    # Connection successful, create the entry
                    return self.async_create_entry(
                        title=name,
                        data=user_input
                    )
            except Exception:
                _LOGGER.exception("Unexpected exception in config flow")
                errors["base"] = "cannot_connect"
            finally:
                client.close()

        # Show the form if we are here (either first run or error)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
            }),
            errors=errors
        )