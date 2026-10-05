"""Integrace Tecomat PLC pro Home Assistant.

PLC samo popisuje své objekty (deskriptor). Integrace si popis načte a vytvoří
zařízení a entity. Konfigurace tlačítek se dělá na stránce „Tecomat PLC“.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_SCAN_INTERVAL,
    CONF_SHOW_IN_SIDEBAR,
    CONF_UNIT_ID,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DOMAIN,
    PANEL_COMPONENT,
    PANEL_URL,
    PLATFORMS,
    STATIC_URL,
)
from .coordinator import TecomatCoordinator
from .descriptor import InvalidDescriptor, read_descriptor
from .modbus_client import ModbusError, ModbusTcpClient
from .versions import VersionStore
from .websocket import async_register_websocket

_LOGGER = logging.getLogger(__name__)

PANEL_VERSION = "0.2.0"

TecomatConfigEntry = ConfigEntry[TecomatCoordinator]


def entry_settings(entry: ConfigEntry) -> dict:
    return {**entry.data, **entry.options}


async def _async_setup_frontend(hass: HomeAssistant) -> None:
    """Statické soubory a websocket API jednou za běh HA."""
    store = hass.data.setdefault(DOMAIN, {})
    if not store.get("static"):
        path = Path(__file__).parent / "frontend"
        await hass.http.async_register_static_paths([StaticPathConfig(STATIC_URL, str(path), False)])
        async_register_websocket(hass)
        store["static"] = True


async def _async_update_panel(hass: HomeAssistant, exclude: str | None = None) -> None:
    """Konfigurační stránka /tecomat-plc.

    Stránka existuje vždy (odkaz z Nastavení → Zařízení a služby → Tecomat PLC a ze stránky
    zařízení). Do bočního menu se přidá jen pokud to má některé PLC zapnuté v nastavení.
    """
    store = hass.data.setdefault(DOMAIN, {})
    entries = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.entry_id != exclude and e.state in (ConfigEntryState.LOADED, ConfigEntryState.SETUP_IN_PROGRESS)
    ]
    wanted: bool | None = None
    if entries:
        wanted = any(e.options.get(CONF_SHOW_IN_SIDEBAR, False) for e in entries)
    current = store.get("panel")  # None = neregistrováno, jinak True/False = v menu
    if current == wanted:
        return
    if current is not None:
        frontend.async_remove_panel(hass, PANEL_URL)
        store["panel"] = None
    if wanted is None:
        return
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL,
        webcomponent_name=PANEL_COMPONENT,
        module_url=f"{STATIC_URL}/tecomat-plc-panel.js?v={PANEL_VERSION}",
        sidebar_title="Tecomat PLC" if wanted else None,
        sidebar_icon="mdi:light-switch" if wanted else None,
        require_admin=True,
        config={},
    )
    store["panel"] = wanted


async def async_setup_entry(hass: HomeAssistant, entry: TecomatConfigEntry) -> bool:
    conf = entry_settings(entry)
    client = ModbusTcpClient(
        conf[CONF_HOST],
        conf.get(CONF_PORT, DEFAULT_PORT),
        conf.get(CONF_UNIT_ID, DEFAULT_UNIT_ID),
    )
    try:
        desc = await read_descriptor(client)
    except (ModbusError, InvalidDescriptor) as err:
        await client.close()
        raise ConfigEntryNotReady(str(err)) from err

    _LOGGER.info(
        "Tecomat %s (program %s): %d skupin, %d objektů",
        desc.plc_model,
        desc.prog_version,
        len(desc.groups),
        len(desc.objects),
    )

    coordinator = TecomatCoordinator(
        hass, entry, client, desc, float(conf.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    )
    coordinator.versions = VersionStore(hass, entry.entry_id)
    await coordinator.versions.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # hlavní zařízení (PLC) musí existovat dřív, než na něj odkážou zařízení CIB
    dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, **coordinator.device_info(0))

    await _async_setup_frontend(hass)
    await _async_update_panel(hass)
    coordinator.start_heartbeat()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: TecomatConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: TecomatConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.async_shutdown()
        await _async_update_panel(hass, exclude=entry.entry_id)
    return ok
