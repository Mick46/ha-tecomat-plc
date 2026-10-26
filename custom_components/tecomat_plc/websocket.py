"""Websocket API pro konfigurační stránku „Tecomat PLC“."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import floor_registry as fr

from .const import (
    DOMAIN,
    F_DIRECT,
    F_READONLY,
    F_VALUE_SET,
    ROLE_OUT,
    ROLE_TEMP,
    T_ACTION,
    T_TEXT,
    T_LIGHT,
    T_SELECT,
    TECH_PARAM_BASES,
    VALUE_ROLES,
    SUBTYPES,
    T_BINARY,
    T_COVER,
    T_DIMMER,
    T_GATE,
    T_NUMBER,
    T_SWITCH,
    T_TEMP,
    T_VALUE,
    UNIT_BOOL,
    UNIT_TIME,
    S_HA_ONLINE,
)
from .sensor import UNITS

UNIT_LABELS = {k: str(v) for k, v in UNITS.items()}
TECH_SUBTYPES = (7, 8, 9, 10)
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


def _targets(coord) -> list[dict]:
    """Cíle akcí tlačítek: výstupy, stmívače, žaluzie (nahoru i dolů zvlášť) a vrata."""
    out = []
    for o in coord.targets_v2():
        if o.type == T_SWITCH and o.p2 in TECH_SUBTYPES:
            continue  # kotel, TUV, napájení hlavic, topné okruhy řídí logika topení, ne tlačítka
        base = {"name": o.name, "group": o.group, "dimmer": o.type == T_DIMMER}
        if o.type == T_COVER:
            sub = "Žaluzie" if o.flags & 1 else "Markýza"
            out.append({**base, "uid": o.uid, "kind": "cover", "sub": sub, "name": f"{o.name} nahoru", "obj": o.uid})
            out.append({**base, "uid": o.p1, "kind": "cover", "sub": sub, "name": f"{o.name} dolů", "obj": o.uid})
        elif o.type == T_GATE:
            out.append({**base, "uid": o.uid, "kind": "gate", "sub": "Vrata", "obj": o.uid})
        else:
            sub = SUBTYPES.get(o.p2, "Světlo" if o.type != 2 else "Spínač")
            out.append({**base, "uid": o.uid, "kind": "dimmer" if o.type == T_DIMMER else "output", "sub": sub, "obj": o.uid})
    return out


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
        "groups": _groups(hass, coord),
        "circuits": [
            {"m": o.p1, "uid": o.uid, "name": o.name, "group": o.group, "dimmable": bool(o.flags & 2)}
            for o in coord.matrix_circuits()
        ],
        "buttons": [{"m": o.p1, "uid": o.uid, "name": o.name, "group": o.group} for o in coord.matrix_buttons()],
        "temps": [
            {"idx": o.p1, "uid": o.uid, "name": o.name, "group": o.group, "addr": o.addr, "sw": o.p2 if d.protocol >= 2 else 0}
            for o in d.objects_of(T_TEMP)
        ],
        "protocol": d.protocol,
        "buttons2": [
            {
                "b": i,
                "uid": o.uid,
                "name": o.name,
                "group": o.group,
                "sw": o.p1,  # číslo vypínače (0 = tlačítko na vstupu)
                "pos": o.p2,  # klapka: 1 UP1, 2 DOWN1, 3 UP2, 4 DOWN2
                "swtype": o.p3 or 1,  # 2 = WSB2-20, 4 = WSB2-40, 1 = vstup
            }
            for i, o in enumerate(coord.buttons_v2())
        ]
        if d.protocol >= 2
        else [],
        "targets": _targets(coord) if d.protocol >= 2 else [],
        "sensors": [
            {"uid": o.uid, "name": o.name, "group": o.group}
            for o in d.objects_of(T_BINARY)
            if not 7000 <= o.uid < 7100  # stavy technologie (pojistky exportu) nejsou čidla pro automatiky
        ]
        if d.protocol >= 2
        else [],
        "autos": [{"a": i, "name": n} for i, n in enumerate(d.autos)],
        "meters": [
            {"i": i, "uid": o.uid, "name": o.name, "group": o.group, "addr": o.addr, "dec": o.p1,
             "unit": UNIT_LABELS.get(o.p2, "")}
            for i, o in enumerate(x for x in d.objects_of(T_VALUE) if x.flags & F_VALUE_SET)
        ],
        "params": [_param(o) for o in coord.params_v2()] if d.protocol >= 2 else [],
        "tech": _tech(coord) if d.protocol >= 2 else {},
    }


def _groups(hass: HomeAssistant, coord) -> list[dict[str, Any]]:
    """Skupiny PLC s podlažím z HA (oblast zařízení, jinak oblast podle názvu) pro řazení v panelu."""
    devs, areas, floors = dr.async_get(hass), ar.async_get(hass), fr.async_get(hass)
    out = []
    for g in coord.desc.groups:
        dev = devs.async_get_device(identifiers={(DOMAIN, f"{coord.config_entry.entry_id}_g{g.id}")})
        area = areas.async_get_area(dev.area_id) if dev and dev.area_id else None
        if area is None and g.area:
            area = areas.async_get_area_by_name(g.area)
        floor = floors.async_get_floor(area.floor_id) if area and area.floor_id else None
        if floor is None and g.floor:  # oblast v HA bez podlaží: podlaží z xlsx (podle názvu i úroveň z HA)
            floor = floors.async_get_floor_by_name(g.floor)
        out.append({
            "id": g.id,
            "name": g.name,
            "area": g.area,
            "floor": floor.name if floor else (g.floor or None),
            "flevel": floor.level if floor else None,
            "ficon": floor.icon if floor else None,
        })
    return out


def _stale(hass: HomeAssistant, coord) -> tuple[list, list]:
    """Entity a zařízení integrace, které aktuální program PLC už nevytváří."""
    entry_id = coord.config_entry.entry_id
    ents = [
        e for e in er.async_entries_for_config_entry(er.async_get(hass), entry_id)
        if f"{e.domain}:{e.unique_id}" not in coord.expected_uids
    ]
    groups = {f"{entry_id}_g{g.id}" for g in coord.desc.groups}
    devs = [
        d for d in dr.async_entries_for_config_entry(dr.async_get(hass), entry_id)
        if not any(i[0] == DOMAIN and i[1] in groups for i in d.identifiers)
    ]
    return ents, devs


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/stale", vol.Required("entry_id"): str})
@websocket_api.require_admin
@websocket_api.async_response
@_with_coordinator
async def ws_stale(hass, coord, msg) -> dict[str, Any]:
    ents, devs = _stale(hass, coord)
    return {
        "entities": [
            {"entity_id": e.entity_id, "name": e.name or e.original_name or "", "uid": e.unique_id} for e in ents
        ],
        "devices": [{"id": d.id, "name": d.name_by_user or d.name or ""} for d in devs],
    }


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/stale/remove", vol.Required("entry_id"): str}
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_coordinator
async def ws_stale_remove(hass, coord, msg) -> dict[str, Any]:
    """Odstraní neplatné entity a zařízení (jen ty, které aktuální program nevytváří)."""
    if not coord.expected_uids:
        raise ValueError("Integrace ještě nevytvořila entity, úklid nelze provést")
    ents, devs = _stale(hass, coord)
    ereg, dreg = er.async_get(hass), dr.async_get(hass)
    for e in ents:
        ereg.async_remove(e.entity_id)
    for d in devs:
        dreg.async_update_device(d.id, remove_config_entry_id=coord.config_entry.entry_id)
    return {"entities": len(ents), "devices": len(devs)}


def _param(o) -> dict[str, Any]:
    sel = o.type == T_SELECT
    out = {
        "p": o.p3,
        "uid": o.uid,
        "addr": o.addr,
        "name": o.name,
        "group": o.group,
        "min": 0 if sel else (o.p1 - 65536 if o.p1 > 32767 else o.p1),
        "max": len(o.options) - 1 if sel else (o.p2 - 65536 if o.p2 > 32767 else o.p2),
        "dec": 0 if sel else o.flags & 7,
        "unit": "" if sel else UNIT_LABELS.get(o.flags >> 8, ""),
        "bool": not sel and (o.flags >> 8) == UNIT_BOOL,
        "time": not sel and (o.flags >> 8) == UNIT_TIME,
        "options": o.options if sel else None,
        # generátor: UID parametru = 30000 + UID objektu·5 + druh (1 max. doba, 2 max. jas, 3 náběh; okruh 1 den, 2 noc, 3 záloha)
        "target": (o.uid - 30000) // 5 if o.uid > 30000 else 0,
        "kind": (o.uid - 30000) % 5 if o.uid > 30000 else 0,
    }
    for sec, base in TECH_PARAM_BASES.items():  # technologie: sekce a číslo parametru
        if base <= o.uid < base + 50:
            out["tech"], out["n"] = sec, o.uid - base
    return out


def _tech(coord) -> dict[str, Any]:
    """Technologie (topení, TUV, bazén): role výstupů a teplot podle meta p3, stavové objekty."""
    d = coord.desc
    outs = {}
    circuits = []
    for o in d.objects_of(T_LIGHT, T_SWITCH):
        role = ROLE_OUT.get(o.p3) if d.protocol >= 2 else None
        if role == "circuit":
            circuits.append({"uid": o.uid, "name": o.name, "group": o.group, "addr": o.addr, "temp": o.p1})
        elif role:
            outs.setdefault(role, []).append(
                {"uid": o.uid, "name": o.name, "group": o.group, "addr": o.addr, "circuit": o.p1}
            )
    temps = {
        ROLE_TEMP[o.p3]: {"uid": o.uid, "name": o.name, "addr": o.addr}
        for o in d.objects_of(T_TEMP)
        if o.p3 in ROLE_TEMP
    }
    state = {
        o.uid: {"uid": o.uid, "name": o.name, "addr": o.addr, "options": o.options}
        for o in d.objects_of(T_SELECT)
        if o.flags & F_READONLY
    }
    extra = {
        o.uid: {"uid": o.uid, "name": o.name, "addr": o.addr, "dec": o.p1 if o.type == T_VALUE else 0,
                "unit": UNIT_LABELS.get(o.p2, "") if o.type == T_VALUE else ""}
        for o in d.objects_of(T_VALUE, T_ACTION, T_BINARY, T_TEXT)
        if 7000 <= o.uid < 7100
    }
    values = {
        VALUE_ROLES[o.flags >> 8]: {"uid": o.uid, "name": o.name, "addr": o.addr, "dec": o.p1, "unit": UNIT_LABELS.get(o.p2, "")}
        for o in d.objects_of(T_VALUE)
        if (o.flags >> 8) in VALUE_ROLES
    }
    return {"outputs": outs, "circuits": circuits, "temps": temps, "states": state, "extra": extra, "values": values,
            "inverter": _inverter(d)}


INV_UID_MIN, INV_UID_MAX = 50000, 59999  # generátor: objekty z listu FVE registry


def _inverter(d) -> dict[str, Any]:
    """Střídač (list FVE registry): nastavení s přímým zápisem, stavy a texty pro kartu v panelu."""
    inv = [o for o in d.objects if INV_UID_MIN <= o.uid <= INV_UID_MAX]
    settings = []
    for o in inv:
        if o.type not in (T_SELECT, T_NUMBER) or not o.flags & F_DIRECT:
            continue
        sel = o.type == T_SELECT
        settings.append({
            "uid": o.uid, "name": o.name, "addr": o.addr, "options": o.options if sel else None,
            "min": 0 if sel else (o.p1 - 65536 if o.p1 > 32767 else o.p1),
            "max": 0 if sel else (o.p2 - 65536 if o.p2 > 32767 else o.p2),
            "dec": 0 if sel else o.flags & 7, "unit": "" if sel else UNIT_LABELS.get(o.flags >> 8, ""),
        })
    states = [{"uid": o.uid, "name": o.name, "addr": o.addr, "options": o.options}
              for o in inv if o.type == T_SELECT and o.flags & F_READONLY]
    texts = [{"uid": o.uid, "name": o.name, "addr": o.addr} for o in inv if o.type == T_TEXT]
    return {"settings": settings, "states": states, "texts": texts}


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
    vals = [o for o in coord.desc.objects_of(T_VALUE)]
    cfg["meters"] = {
        str(i): coord.get_value(o.addr, o.flags) for i, o in enumerate(x for x in vals if x.flags & F_VALUE_SET)
    }
    lux = next((o for o in vals if o.p3 == 7), None)  # třída illuminance
    cfg["lux"] = coord.get_value(lux.addr, lux.flags) if lux else None
    cfg["live"] = _live(coord)
    return cfg


def _live(coord) -> dict[str, Any]:
    """Aktuální hodnoty registrů objektů podle adresy (panel: stavy technologie)."""
    out: dict[str, Any] = {"ha_online": coord.status(S_HA_ONLINE)}
    for o in coord.desc.objects:
        if o.type == T_TEMP:
            out[str(o.addr)] = coord.get_signed(o.addr + 1)
        elif o.type == T_VALUE:
            out[str(o.addr)] = coord.get_value(o.addr, o.flags)
        elif o.type == T_TEXT:
            out[str(o.addr)] = coord.get_text(o.addr)
        else:
            out[str(o.addr)] = coord.get(o.addr)
    return out


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/live",
        vol.Required("entry_id"): str,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_coordinator
async def ws_live(hass, coord, msg) -> dict[str, Any]:
    """Jen aktuální hodnoty z posledního čtení (bez čtení konfigurace), panel je obnovuje periodicky."""
    return _live(coord)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/press",
        vol.Required("entry_id"): str,
        vol.Required("addr"): int,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_coordinator
async def ws_press(hass, coord, msg) -> dict[str, Any]:
    """Akce PLC (typ ACTION): zápis 1 do registru akce."""
    if not any(o.addr == msg["addr"] for o in coord.desc.objects_of(T_ACTION)):
        raise ValueError("Neznámá akce")
    await coord.write_register(msg["addr"], 1)
    return {"ok": True}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/direct",
        vol.Required("entry_id"): str,
        vol.Required("addr"): int,
        vol.Required("value"): int,
    }
)
@websocket_api.require_admin
@websocket_api.async_response
@_with_coordinator
async def ws_direct(hass, coord, msg) -> dict[str, Any]:
    """Nastavení zařízení za PLC (střídač, přímý zápis): +1 požadovaná hodnota, +2 povel; PLC zapíše jednorázově."""
    o = next((x for x in coord.desc.objects_of(T_SELECT, T_NUMBER) if x.addr == msg["addr"] and x.flags & F_DIRECT), None)
    if o is None:
        raise ValueError("Neznámé nastavení")
    v = msg["value"]
    if o.type == T_SELECT:
        if not 0 <= v < len(o.options):
            raise ValueError("Volba mimo rozsah")
    else:
        lo = o.p1 - 65536 if o.p1 > 32767 else o.p1
        hi = o.p2 - 65536 if o.p2 > 32767 else o.p2
        if not lo <= v <= hi:
            raise ValueError("Hodnota mimo rozsah")
    await coord.write_registers(o.addr + 1, [v, 1])
    return {"ok": True}


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
    return await coord.versions.add(msg["name"], cfg["map"], cfg["corr"], protocol=coord.protocol)


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
    if ver.get("protocol", 1) != coord.protocol:
        raise ValueError("Verze je uložená pro jiný program PLC (jiný formát konfigurace), nelze ji obnovit")
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
    return await coord.versions.add(msg["name"], msg["map"], msg["corr"], source="import", protocol=coord.protocol)


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    for handler in (
        ws_entries,
        ws_info,
        ws_config_get,
        ws_live,
        ws_press,
        ws_direct,
        ws_stale,
        ws_stale_remove,
        ws_config_set,
        ws_versions_list,
        ws_versions_save,
        ws_versions_restore,
        ws_versions_delete,
        ws_versions_import,
    ):
        websocket_api.async_register_command(hass, handler)
