"""Websocket API pro konfigurační stránku „Tecomat PLC“."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, T_TEMP
from .modbus_client import ModbusError


def _coordinator(hass: HomeAssistant, entry_id: str):
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        return None
    return entry.runtime_data


def _with_coordinator(func):
    """Dekorátor: najde koordinátor podle entry_id a ošetří chyby komunikace."""

    async def wrapper(hass, connection, msg):
        coord = _coordinator(hass, msg["entry_id"])
        if coord is None:
            connection.send_error(msg["id"], "not_loaded", "Integrace není načtená")
            return
        try:
            result = await func(hass, coord, msg)
        except ModbusError as err:
            connection.send_error(msg["id"], "plc_error", str(err))
            return
        except ValueError as err:
            connection.send_error(msg["id"], "invalid", str(err))
            return
        connection.send_result(msg["id"], result)

    return wrapper


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/entries"})
@websocket_api.require_admin
@callback
def ws_entries(hass: HomeAssistant, connection, msg) -> None:
    out = []
    for e in hass.config_entries.async_entries(DOMAIN):
        if e.state is ConfigEntryState.LOADED:
            d = e.runtime_data.desc
            out.append({"entry_id": e.entry_id, "title": e.title, "model": d.plc_model})
    connection.send_result(msg["id"], out)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/info", vol.Required("entry_id"): str})
@websocket_api.require_admin
@websocket_api.async_response
@_with_coordinator
async def ws_info(hass, coord, msg) -> dict[str, Any]:
    d = coord.desc
    return {
        "model": d.plc_model,
        "program": d.prog_version,
        "max_b": d.max_b,
        "groups": [{"id": g.id, "name": g.name, "area": g.area} for g in d.groups],
        "circuits": [
            {"m": o.p1, "uid": o.uid, "name": o.name, "group": o.group, "dimmable": bool(o.flags & 2)}
            for o in coord.matrix_circuits()
        ],
        "buttons": [{"m": o.p1, "uid": o.uid, "name": o.name, "group": o.group} for o in coord.matrix_buttons()],
        "temps": [
            {"idx": o.p1, "uid": o.uid, "name": o.name, "group": o.group, "addr": o.addr}
            for o in d.objects_of(T_TEMP)
        ],
    }


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/config/get", vol.Required("entry_id"): str})
@websocket_api.require_admin
@websocket_api.async_response
@_with_coordinator
async def ws_config_get(hass, coord, msg) -> dict[str, Any]:
    cfg = await coord.read_config()
    temps = {}
    for o in coord.desc.objects_of(T_TEMP):
        temps[str(o.p1)] = {
            "raw": coord.get_signed(o.addr),
            "cor": coord.get_signed(o.addr + 1),
        }
    cfg["temps"] = temps
    return cfg


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/config/set",
        vol.Required("entry_id"): str,
        vol.Required("pairs"): [[int]],
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_coordinator
async def ws_config_set(hass, coord, msg) -> dict[str, Any]:
    pairs = []
    for p in msg["pairs"]:
        if len(p) != 2:
            raise ValueError("Každá položka musí být [index, hodnota]")
        pairs.append((p[0], p[1]))
    await coord.write_config(pairs)
    return {"written": len(pairs)}


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/versions/list", vol.Required("entry_id"): str})
@websocket_api.require_admin
@websocket_api.async_response
@_with_coordinator
async def ws_versions_list(hass, coord, msg) -> list[dict]:
    return coord.versions.versions


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/versions/save",
        vol.Required("entry_id"): str,
        vol.Required("name"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_coordinator
async def ws_versions_save(hass, coord, msg) -> dict:
    """Uloží verzi z AKTUÁLNÍHO obsahu PLC (ne z prohlížeče)."""
    cfg = await coord.read_config()
    return await coord.versions.add(msg["name"], cfg["map"], cfg["corr"])


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/versions/restore",
        vol.Required("entry_id"): str,
        vol.Required("version_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_coordinator
async def ws_versions_restore(hass, coord, msg) -> dict:
    ver = coord.versions.get(msg["version_id"])
    if ver is None:
        raise ValueError("Verze neexistuje")
    pairs = coord.all_pairs(ver["map"], ver["corr"])
    await coord.write_config(pairs)
    return {"written": len(pairs)}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/versions/delete",
        vol.Required("entry_id"): str,
        vol.Required("version_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_coordinator
async def ws_versions_delete(hass, coord, msg) -> dict:
    return {"deleted": await coord.versions.delete(msg["version_id"])}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/versions/import",
        vol.Required("entry_id"): str,
        vol.Required("name"): str,
        vol.Required("map"): {str: int},
        vol.Optional("corr", default={}): {str: int},
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_coordinator
async def ws_versions_import(hass, coord, msg) -> dict:
    """Import vytvoří jen novou verzi, do PLC se nic nezapisuje."""
    return await coord.versions.add(msg["name"], msg["map"], msg["corr"], source="import")


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    for handler in (
        ws_entries,
        ws_info,
        ws_config_get,
        ws_config_set,
        ws_versions_list,
        ws_versions_save,
        ws_versions_restore,
        ws_versions_delete,
        ws_versions_import,
    ):
        websocket_api.async_register_command(hass, handler)
