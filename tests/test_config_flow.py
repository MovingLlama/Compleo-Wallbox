"""Config flow: the connection test must get a Modbus answer."""
from __future__ import annotations

from modbus_connection import IllegalFunctionError, ModbusConnectionError

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.compleo_wallbox.const import DOMAIN

from .conftest import HOST, PORT

USER_INPUT = {"name": "Carport", "host": HOST, "port": PORT}


async def _start(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    return result


async def test_user_flow_creates_entry(hass, mock_unit) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Carport"
    assert result["result"].unique_id == f"{HOST}_{PORT}"


async def test_user_flow_strips_scheme(hass, mock_unit) -> None:
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, "host": f"http://{HOST}"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["host"] == HOST


async def test_user_flow_cannot_connect(hass, mock_unit) -> None:
    mock_unit.fail_requests(ModbusConnectionError("refused"))
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_exception_response_counts_as_reachable(hass, mock_unit) -> None:
    mock_unit.fail_read(0x0008, IllegalFunctionError("old firmware"), register_type="input")
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] is FlowResultType.CREATE_ENTRY
