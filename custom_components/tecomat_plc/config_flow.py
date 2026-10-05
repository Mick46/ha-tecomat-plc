"""Průvodce přidáním a nastavení integrace."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback

from .const import (
    CONF_SCAN_INTERVAL,
    CONF_SHOW_IN_SIDEBAR,
    CONF_UNIT_ID,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DOMAIN,
    PANEL_URL,
)
from .descriptor import Descriptor, InvalidDescriptor, read_descriptor
from .modbus_client import ModbusError, ModbusTcpClient


async def _probe(host: str, port: int, unit: int) -> Descriptor:
    client = ModbusTcpClient(host, port, unit)
    try:
        return await read_descriptor(client)
    finally:
        await client.close()


def _conn_schema(defaults: dict[str, Any], with_scan: bool) -> vol.Schema:
    fields: dict = {
        vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
        vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): int,
        vol.Required(CONF_UNIT_ID, default=defaults.get(CONF_UNIT_ID, DEFAULT_UNIT_ID)): int,
    }
    if with_scan:
        fields[
            vol.Required(CONF_SCAN_INTERVAL, default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        ] = vol.All(vol.Coerce(float), vol.Range(min=0.2, max=60))
    return vol.Schema(fields)


async def _validate(user_input: dict[str, Any]) -> tuple[Descriptor | None, dict[str, str]]:
    try:
        desc = await _probe(user_input[CONF_HOST], user_input[CONF_PORT], user_input[CONF_UNIT_ID])
    except ModbusError:
        return None, {"base": "cannot_connect"}
    except InvalidDescriptor:
        return None, {"base": "no_descriptor"}
    return desc, {}


class TecomatConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            desc, errors = await _validate(user_input)
            if desc is not None:
                await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Tecomat {desc.plc_model} ({user_input[CONF_HOST]})",
                    data=user_input,
                )
        return self.async_show_form(
            step_id="user",
            data_schema=_conn_schema(user_input or {}, with_scan=False),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return TecomatOptionsFlow()


class TecomatOptionsFlow(OptionsFlow):
    """Nastavení: odkaz na konfiguraci ovladačů, připojení (změna PLC) a zobrazení v menu."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["connection", "display"],
            description_placeholders={"panel_url": f"/{PANEL_URL}"},
        )

    async def async_step_connection(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Změna IP / PLC (např. přechod CP-1000 -> CP-2000) a intervalu čtení.

        Entity zůstanou zachované, pokud program v novém PLC používá stejná uid objektů.
        """
        errors: dict[str, str] = {}
        current = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            desc, errors = await _validate(user_input)
            if desc is not None:
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    title=f"Tecomat {desc.plc_model} ({user_input[CONF_HOST]})",
                )
                return self.async_create_entry(data={**self.config_entry.options, **user_input})
        return self.async_show_form(
            step_id="connection",
            data_schema=_conn_schema(user_input or current, with_scan=True),
            errors=errors,
        )

    async def async_step_display(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={**self.config_entry.options, **user_input})
        show = self.config_entry.options.get(CONF_SHOW_IN_SIDEBAR, False)
        return self.async_show_form(
            step_id="display",
            data_schema=vol.Schema({vol.Required(CONF_SHOW_IN_SIDEBAR, default=show): bool}),
            description_placeholders={"panel_url": f"/{PANEL_URL}"},
        )
