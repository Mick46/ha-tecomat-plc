"""Integrace v reálném Home Assistant proti simulátoru PLC."""

from __future__ import annotations

import pytest

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tecomat_plc.const import CONF_SCAN_INTERVAL, CONF_UNIT_ID, DOMAIN

from .mock_plc import MockPlc


@pytest.fixture
async def plc():
    p = MockPlc()
    await p.start()
    yield p
    await p.stop()


async def _setup(hass: HomeAssistant, plc: MockPlc) -> MockConfigEntry:
    await async_setup_component(hass, "http", {})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Tecomat CP-1000",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: plc.port, CONF_UNIT_ID: 1},
        options={CONF_SCAN_INTERVAL: 1.0},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


async def _tick(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Jedno čtení PLC (deterministicky, bez posouvání času)."""
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_config_flow(hass: HomeAssistant, plc: MockPlc) -> None:
    await async_setup_component(hass, "http", {})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: plc.port, CONF_UNIT_ID: 1}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Tecomat CP-1000 (127.0.0.1)"
    await hass.async_block_till_done()


async def test_config_flow_cannot_connect(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: 1, CONF_UNIT_ID: 1}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_entities_and_devices(hass: HomeAssistant, plc: MockPlc) -> None:
    entry = await _setup(hass, plc)
    ent = er.async_get(hass)
    devs = dr.async_get(hass)

    entities = er.async_entries_for_config_entry(ent, entry.entry_id)
    by_uid = {e.unique_id.split("_", 1)[1]: e for e in entities}
    assert by_uid["1"].domain == "light"
    assert by_uid["3"].domain == "event"
    assert by_uid["7"].domain == "sensor"
    assert by_uid["7_corr"].domain == "number"
    assert by_uid["8"].domain == "binary_sensor"

    devices = dr.async_entries_for_config_entry(devs, entry.entry_id)
    names = sorted(d.name for d in devices)
    assert names == ["CP-1000", "Vstupy IM2-140M 9DE4", "Vypínač WSB2-20 A2A8"]

    temp = hass.states.get(by_uid["7"].entity_id)
    assert float(temp.state) == 22.3
    hdo = hass.states.get(by_uid["8"].entity_id)
    assert hdo.state == "on"
    light = hass.states.get(by_uid["1"].entity_id)
    assert light.state == "off"
    assert plc.reg[30000] != 0  # heartbeat z HA


async def test_light_and_button(hass: HomeAssistant, plc: MockPlc) -> None:
    entry = await _setup(hass, plc)
    ent = er.async_get(hass)
    light_id = ent.async_get_entity_id("light", DOMAIN, f"{entry.entry_id}_1")
    btn_id = ent.async_get_entity_id("event", DOMAIN, f"{entry.entry_id}_3")

    await hass.services.async_call("light", "turn_on", {"entity_id": light_id}, blocking=True)
    assert plc.reg[30002] == 1
    assert hass.states.get(light_id).state == "on"

    # PLC samo přepne (tlačítko) -> HA to uvidí
    plc.reg[30002] = 0
    await _tick(hass, entry)
    assert hass.states.get(light_id).state == "off"

    plc.press(0, 2)
    await _tick(hass, entry)
    st = hass.states.get(btn_id)
    assert st.attributes["event_type"] == "long"
    plc.press(0, 1)
    await _tick(hass, entry)
    assert hass.states.get(btn_id).attributes["event_type"] == "short"


async def test_temperature_correction(hass: HomeAssistant, plc: MockPlc) -> None:
    entry = await _setup(hass, plc)
    ent = er.async_get(hass)
    num_id = ent.async_get_entity_id("number", DOMAIN, f"{entry.entry_id}_7_corr")
    temp_id = ent.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_7")

    await hass.services.async_call("number", "set_value", {"entity_id": num_id, "value": -1.2}, blocking=True)
    await hass.async_block_till_done()
    assert plc.tcorr[0] == -12
    assert float(hass.states.get(num_id).state) == -1.2
    assert float(hass.states.get(temp_id).state) == 21.1


async def test_websocket_config_and_versions(hass: HomeAssistant, plc: MockPlc, hass_ws_client) -> None:
    entry = await _setup(hass, plc)
    ws = await hass_ws_client(hass)
    eid = entry.entry_id

    await ws.send_json({"id": 1, "type": "tecomat_plc/entries"})
    res = await ws.receive_json()
    assert res["success"] and res["result"][0]["model"] == "CP-1000"

    await ws.send_json({"id": 2, "type": "tecomat_plc/info", "entry_id": eid})
    info = (await ws.receive_json())["result"]
    assert [b["name"] for b in info["buttons"]] == ["Klapka nahoře", "Klapka dole", "Vstup IN10", "Vstup IN11"]
    assert [c["name"] for c in info["circuits"]] == ["Test světlo 1 (DO0)", "Test světlo 2 (DO1)"]

    await ws.send_json({"id": 3, "type": "tecomat_plc/config/get", "entry_id": eid})
    cfg = (await ws.receive_json())["result"]
    assert cfg["map"] == {"0,0": 9, "0,1": 8, "0,2": 0, "0,3": 0, "1,0": 8, "1,1": 9, "1,2": 0, "1,3": 0}
    assert cfg["checksum_plc"] == cfg["checksum_calc"] == 731

    # verze "základ"
    await ws.send_json({"id": 4, "type": "tecomat_plc/versions/save", "entry_id": eid, "name": "základ"})
    ver = (await ws.receive_json())["result"]
    assert ver["map"]["0,0"] == 9

    # změna: IN10 krátký stisk přepne okruh 1
    await ws.send_json({"id": 5, "type": "tecomat_plc/config/set", "entry_id": eid, "pairs": [[1 * 40 + 2, 1]]})
    assert (await ws.receive_json())["success"]
    assert plc.cfg[42] == 1

    await ws.send_json({"id": 6, "type": "tecomat_plc/config/get", "entry_id": eid})
    cfg = (await ws.receive_json())["result"]
    assert cfg["map"]["1,2"] == 1 and cfg["checksum_plc"] == cfg["checksum_calc"]

    # obnovení verze vrátí PLC do původního stavu
    await ws.send_json({"id": 7, "type": "tecomat_plc/versions/restore", "entry_id": eid, "version_id": ver["id"]})
    assert (await ws.receive_json())["success"]
    assert plc.cfg[42] == 0 and plc.checksum() == 731

    # import jen přidá verzi, do PLC nic nezapíše
    writes_before = len(plc.writes)
    await ws.send_json(
        {"id": 8, "type": "tecomat_plc/versions/import", "entry_id": eid, "name": "imp", "map": {"0,0": 1}, "corr": {}}
    )
    assert (await ws.receive_json())["success"]
    assert all(addr == 30000 for addr, _ in plc.writes[writes_before:])  # max heartbeat

    await ws.send_json({"id": 9, "type": "tecomat_plc/versions/list", "entry_id": eid})
    names = [v["name"] for v in (await ws.receive_json())["result"]]
    assert names == ["imp", "základ"]


async def test_program_change_reload(hass: HomeAssistant, plc: MockPlc) -> None:
    entry = await _setup(hass, plc)
    coord = entry.runtime_data
    plc.reg[24003] = 4  # nová verze programu v PLC
    coord._last_hdr_check = 0
    await _tick(hass, entry)
    await hass.async_block_till_done()
    assert entry.runtime_data is not coord  # integrace se znovu načetla
    assert entry.runtime_data.desc.prog_version == 4


async def test_panel_registered(hass: HomeAssistant, plc: MockPlc) -> None:
    """Stránka existuje vždy, v bočním menu jen po zaškrtnutí v Nastavení → Zobrazení."""
    entry = await _setup(hass, plc)
    panels = hass.data.get("frontend_panels", {})
    assert "tecomat-plc" in panels
    assert panels["tecomat-plc"].sidebar_title is None

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "display"})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"show_in_sidebar": True})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.options["show_in_sidebar"] is True
    assert entry.options[CONF_SCAN_INTERVAL] == 1.0  # ostatní nastavení zůstalo
    panels = hass.data.get("frontend_panels", {})
    assert panels["tecomat-plc"].sidebar_title == "Tecomat PLC"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert "tecomat-plc" not in hass.data.get("frontend_panels", {})


async def test_unload(hass: HomeAssistant, plc: MockPlc) -> None:
    entry = await _setup(hass, plc)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_switch_plc_cp1000_to_cp2000(hass: HomeAssistant, plc: MockPlc) -> None:
    """Přechod na jiné PLC změnou IP/portu v nastavení: entity zůstanou (stejná uid objektů)."""
    entry = await _setup(hass, plc)
    ent = er.async_get(hass)
    before = {e.unique_id: e.entity_id for e in er.async_entries_for_config_entry(ent, entry.entry_id)}

    cp2000 = MockPlc(plc_type=2000, swap_bytes=False)
    await cp2000.start()
    try:
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.MENU
        assert result["menu_options"] == ["connection", "display"]
        result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "connection"})
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_HOST: "127.0.0.1", CONF_PORT: cp2000.port, CONF_UNIT_ID: 1, CONF_SCAN_INTERVAL: 1.0},
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        assert entry.runtime_data.desc.plc_model == "CP-2000"
        assert entry.title == "Tecomat CP-2000 (127.0.0.1)"
        after = {e.unique_id: e.entity_id for e in er.async_entries_for_config_entry(ent, entry.entry_id)}
        assert after == before

        light_id = before[f"{entry.entry_id}_1"]
        await hass.services.async_call("light", "turn_on", {"entity_id": light_id}, blocking=True)
        assert cp2000.reg[30002] == 1 and plc.reg.get(30002, 0) == 0
        assert await hass.config_entries.async_unload(entry.entry_id)
    finally:
        await cp2000.stop()


async def test_shared_modbus_connection(hass: HomeAssistant, plc: MockPlc, hass_ws_client) -> None:
    """HA 2026.10+: PLC jde přes sdílené spojení HA a je vidět v panelu Modbus."""
    from custom_components.tecomat_plc import transport

    if not transport.ha_has_shared_modbus():
        pytest.skip("HA bez sdíleného Modbus API (starší než 2026.10)")
    entry = await _setup(hass, plc)
    assert entry.runtime_data.client.shared is True

    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "modbus/connections/list"})
    res = await ws.receive_json()
    assert res["success"]
    conns = [c for c in res["result"]["connections"] if c["source"] == "config_entry"]
    assert len(conns) == 1
    assert conns[0]["units"] == {entry.entry_id: [1]}
    assert conns[0]["connected"] is True
    assert str(plc.port) in [str(x) for x in conns[0]["endpoint"]]

    # po odebrání integrace HA spojení zavře
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    await ws.send_json({"id": 2, "type": "modbus/connections/list"})
    res = await ws.receive_json()
    assert [c for c in res["result"]["connections"] if c["source"] == "config_entry"] == []


async def test_shared_connection_recovers_after_plc_restart(
    hass: HomeAssistant, plc: MockPlc, monkeypatch
) -> None:
    """Po restartu PLC staré spojení neodpovídá: po timeoutu se zahodí a naváže nové."""
    from custom_components.tecomat_plc import transport

    if not transport.ha_has_shared_modbus():
        pytest.skip("HA bez sdíleného Modbus API (starší než 2026.10)")
    import modbus_connection._client as mc_client

    monkeypatch.setattr(mc_client, "_DEFAULT_TIMEOUT", 0.5)
    entry = await _setup(hass, plc)
    coordinator = entry.runtime_data
    assert coordinator.last_update_success

    plc.restart()
    await coordinator.async_refresh()
    assert not coordinator.last_update_success  # timeout na starém spojení

    await coordinator.async_refresh()
    assert coordinator.last_update_success  # nové spojení
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_own_client_fallback(hass: HomeAssistant, plc: MockPlc, monkeypatch) -> None:
    """Starší HA: vlastní Modbus klient, vše funguje stejně."""
    from custom_components.tecomat_plc import transport

    monkeypatch.setattr(transport, "USE_SHARED", False)
    entry = await _setup(hass, plc)
    assert entry.runtime_data.client.shared is False
    ent = er.async_get(hass)
    light_id = ent.async_get_entity_id("light", DOMAIN, f"{entry.entry_id}_1")
    await hass.services.async_call("light", "turn_on", {"entity_id": light_id}, blocking=True)
    assert plc.reg[30002] == 1
    assert await hass.config_entries.async_unload(entry.entry_id)
