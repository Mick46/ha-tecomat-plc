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


async def test_value_sensors(hass: HomeAssistant) -> None:
    """Typ VALUE: 16 i 32 bit, znaménko, desetinná místa, jednotka a třída."""
    from .mock_plc import OBJECTS

    objs = OBJECTS + [
        (6, 0, 30060, 0, 1, 1, 1, 310, "Výkon L1"),       # S32, W, power
        (6, 0, 30062, 1, 2, 2, 3, 314, "Odběr"),          # U32, 0,1 kWh, energy
        (6, 0, 30064, 2, 3, 3, 0, 43, "Baterie"),         # S16, 0,01 %, battery
    ]
    plc = MockPlc(objects=objs)
    await plc.start()
    try:
        plc.reg[30060], plc.reg[30061] = 0xFFFF, 0xFC18   # -1000 W
        plc.reg[30062], plc.reg[30063] = 0x0001, 0x0000   # 65536 -> 6553,6 kWh
        plc.reg[30064] = 8750                             # 87,50 %
        entry = await _setup(hass, plc)
        ent = er.async_get(hass)

        def state(uid: int):
            eid = ent.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{uid}")
            return hass.states.get(eid)

        p = state(310)
        assert float(p.state) == -1000 and p.attributes["unit_of_measurement"] == "W"
        assert p.attributes["device_class"] == "power" and p.attributes["state_class"] == "measurement"
        e = state(314)
        assert float(e.state) == 6553.6 and e.attributes["state_class"] == "total_increasing"
        assert float(state(43).state) == 87.5
        assert await hass.config_entries.async_unload(entry.entry_id)
    finally:
        await plc.stop()


async def test_protocol2(hass: HomeAssistant, hass_ws_client) -> None:
    """Protokol 2 (program z generátoru): stmívač, parametry, akce tlačítek v panelu, verze."""
    from .mock_plc_v2 import MockPlcV2

    plc = MockPlcV2()
    await plc.start()
    try:
        entry = await _setup(hass, plc)
        coord = entry.runtime_data
        assert coord.protocol == 2
        ent = er.async_get(hass)
        dev = dr.async_get(hass)

        # zařízení podle oblastí
        names = {d.name for d in dr.async_entries_for_config_entry(dev, entry.entry_id)}
        assert {"CP-1000", "Kuchyň", "Chodba"} <= names

        # stmívač
        dim = ent.async_get_entity_id("light", DOMAIN, f"{entry.entry_id}_2")
        await hass.services.async_call("light", "turn_on", {"entity_id": dim, "brightness": 128}, blocking=True)
        assert plc.reg[30301] == 50
        await coord.async_refresh()
        await hass.async_block_till_done()
        st = hass.states.get(dim)
        assert st.state == "on" and st.attributes["brightness"] == 128
        await hass.services.async_call("light", "turn_off", {"entity_id": dim}, blocking=True)
        assert plc.reg[30301] == 0

        # parametr (0,1 s) přes schránku
        par = ent.async_get_entity_id("number", DOMAIN, f"{entry.entry_id}_30013")
        assert float(hass.states.get(par).state) == 2.0
        assert hass.states.get(par).attributes["unit_of_measurement"] == "s"
        await hass.services.async_call("number", "set_value", {"entity_id": par, "value": 3.5}, blocking=True)
        assert plc.box[20001] == 35
        await coord.async_refresh()
        await hass.async_block_till_done()
        assert float(hass.states.get(par).state) == 3.5

        # panel: info a konfigurace
        ws = await hass_ws_client(hass)
        await ws.send_json({"id": 1, "type": f"{DOMAIN}/info", "entry_id": entry.entry_id})
        info = (await ws.receive_json())["result"]
        assert info["protocol"] == 2 and info["buttons"] == [] and info["circuits"] == []
        assert [b["uid"] for b in info["buttons2"]] == [2091, 203]
        tg = {t["uid"]: t for t in info["targets"]}
        assert tg[20]["dimmer"] is False and tg[2]["dimmer"] is True
        assert tg[20]["sub"] == "Světlo" and tg[2]["sub"] == "Stmívač"
        assert [(p["p"], p["unit"], p["dec"]) for p in info["params"]][:2] == [(0, "min", 0), (1, "s", 1)]
        # parametr bez příznaku „entita“ je jen v panelu, korekce teplot v protokolu 2 také
        assert ent.async_get_entity_id("number", DOMAIN, f"{entry.entry_id}_30101") is None
        assert ent.async_get_entity_id("number", DOMAIN, f"{entry.entry_id}_402_corr") is None

        await ws.send_json({"id": 2, "type": f"{DOMAIN}/config/get", "entry_id": entry.entry_id})
        cfg = (await ws.receive_json())["result"]
        assert cfg["map"]["0"] == 20 and cfg["map"]["1"] == 256 and cfg["map"]["9"] == 4 * 256 + 50
        assert cfg["map"]["20001"] == 35
        assert cfg["checksum_plc"] == cfg["checksum_calc"]

        # zápis akce tlačítka 1 (b = 1): krátce zapni bodovky
        await ws.send_json({"id": 3, "type": f"{DOMAIN}/config/set", "entry_id": entry.entry_id,
                            "pairs": [[16, 20], [17, 2 * 256]]})
        assert (await ws.receive_json())["success"]
        assert plc.box[16] == 20 and plc.box[17] == 512

        # verze: uložit, změnit, obnovit
        await ws.send_json({"id": 4, "type": f"{DOMAIN}/versions/save", "entry_id": entry.entry_id, "name": "v1"})
        ver = (await ws.receive_json())["result"]
        await ws.send_json({"id": 5, "type": f"{DOMAIN}/config/set", "entry_id": entry.entry_id, "pairs": [[16, 0], [20001, 99]]})
        await ws.receive_json()
        await ws.send_json({"id": 6, "type": f"{DOMAIN}/versions/restore", "entry_id": entry.entry_id, "version_id": ver["id"]})
        assert (await ws.receive_json())["success"]
        assert plc.box[16] == 20 and plc.box[20001] == 35
        # žaluzie a vrata
        cov = ent.async_get_entity_id("cover", DOMAIN, f"{entry.entry_id}_5701")
        await hass.services.async_call("cover", "set_cover_position", {"entity_id": cov, "position": 40}, blocking=True)
        await coord.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(cov).attributes["current_position"] == 40
        gate = ent.async_get_entity_id("cover", DOMAIN, f"{entry.entry_id}_226")
        assert hass.states.get(gate).state == "closed"
        imp = ent.async_get_entity_id("button", DOMAIN, f"{entry.entry_id}_226_impulse")
        await hass.services.async_call("button", "press", {"entity_id": imp}, blocking=True)
        await coord.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(gate).state == "open"

        # panel: žaluzie nahoru/dolů jako cíle, vrata, čidla, automatika, plynoměr, parametr ano/ne
        await ws.send_json({"id": 7, "type": f"{DOMAIN}/info", "entry_id": entry.entry_id})
        info = (await ws.receive_json())["result"]
        kinds = {t["uid"]: t["kind"] for t in info["targets"]}
        assert kinds[5701] == "cover" and kinds[5702] == "cover" and kinds[226] == "gate"
        assert [x["uid"] for x in info["sensors"]] == [216]
        assert info["autos"] == [{"a": 0, "name": "PIR vstup"}]
        assert info["meters"][0]["uid"] == 241
        assert [p["bool"] for p in info["params"]] == [False, False, True, False, True]
        sel = next(p for p in info["params"] if p["uid"] == 65000)
        assert sel["options"] == ["Vypnuto", "Zapnuto", "Auto"] and sel["tech"] == "heat" and sel["n"] == 0
        assert info["tech"]["outputs"]["kotel"][0]["uid"] == 227
        assert info["tech"]["states"]["7000"]["options"][2] == "Řídí HA"
        assert 227 not in {t["uid"] for t in info["targets"]}  # výstup řízený PLC není cíl tlačítek
        await ws.send_json({"id": 8, "type": f"{DOMAIN}/config/get", "entry_id": entry.entry_id})
        cfg = (await ws.receive_json())["result"]
        assert cfg["map"]["4001"] == 216 and cfg["map"]["4016"] == 20
        assert cfg["meters"]["0"] == 1192265
        assert cfg["checksum_plc"] == cfg["checksum_calc"]
        # nastavení plynoměru přes schránku
        await ws.send_json({"id": 9, "type": f"{DOMAIN}/config/set", "entry_id": entry.entry_id,
                            "pairs": [[9000, 1250000 % 65536], [9001, 1250000 // 65536]]})
        assert (await ws.receive_json())["success"]
        assert plc.gas == 1250000

        # část 3: volba režimu, stav, kotel jen ke čtení, parametr ano/ne jako switch, akce
        assert ent.async_get_entity_id("switch", DOMAIN, f"{entry.entry_id}_227") is None
        kotel = ent.async_get_entity_id("binary_sensor", DOMAIN, f"{entry.entry_id}_227")
        mode = ent.async_get_entity_id("select", DOMAIN, f"{entry.entry_id}_65000")
        state = ent.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_7000")
        assert hass.states.get(mode).state == "Auto"
        assert hass.states.get(state).state == "Řídí HA"
        assert hass.states.get(kotel).state == "off"
        await hass.services.async_call("select", "select_option", {"entity_id": mode, "option": "Zapnuto"}, blocking=True)
        assert plc.box[20003] == 1
        await coord.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(mode).state == "Zapnuto"
        assert hass.states.get(kotel).state == "on"
        pool = ent.async_get_entity_id("switch", DOMAIN, f"{entry.entry_id}_65103")
        assert ent.async_get_entity_id("number", DOMAIN, f"{entry.entry_id}_65103") is None
        await hass.services.async_call("switch", "turn_on", {"entity_id": pool}, blocking=True)
        assert plc.box[20004] == 1
        dis = ent.async_get_entity_id("button", DOMAIN, f"{entry.entry_id}_7012")
        await hass.services.async_call("button", "press", {"entity_id": dis}, blocking=True)
        await coord.async_refresh()
        assert plc.presses == 1
        await ws.send_json({"id": 10, "type": f"{DOMAIN}/press", "entry_id": entry.entry_id, "addr": 30324})
        assert (await ws.receive_json())["success"]
        await coord.async_refresh()
        assert plc.presses == 2
        await ws.send_json({"id": 11, "type": f"{DOMAIN}/live", "entry_id": entry.entry_id})
        live = (await ws.receive_json())["result"]
        assert live["30321"] == 1 and live["30323"] == 2
        await ws.send_json({"id": 12, "type": f"{DOMAIN}/config/get", "entry_id": entry.entry_id})
        cfg = (await ws.receive_json())["result"]
        assert cfg["map"]["20003"] == 1 and cfg["checksum_plc"] == cfg["checksum_calc"]

        # podlaží z HA: oblast Kuchyň v podlaží Přízemí
        from homeassistant.helpers import area_registry as ar, floor_registry as fr
        floor = fr.async_get(hass).async_create("Přízemí", level=0)
        area = ar.async_get(hass).async_get_area_by_name("Kuchyň") or ar.async_get(hass).async_create("Kuchyň")
        ar.async_get(hass).async_update(area.id, floor_id=floor.floor_id)
        await ws.send_json({"id": 13, "type": f"{DOMAIN}/info", "entry_id": entry.entry_id})
        groups = {g["name"]: g for g in (await ws.receive_json())["result"]["groups"]}
        assert groups["Kuchyň"]["floor"] == "Přízemí" and groups["Kuchyň"]["flevel"] == 0
        assert groups["Chodba"]["floor"] is None

        # úklid: entita z dřívějšího programu (např. kotel jako switch) je neplatná, ostatní ne
        old = ent.async_get_or_create("switch", DOMAIN, f"{entry.entry_id}_999", config_entry=entry)
        # stejné unique_id jako binary_sensor kotle, ale jiná platforma (dřívější switch) = také neplatné
        old2 = ent.async_get_or_create("switch", DOMAIN, f"{entry.entry_id}_227", config_entry=entry)
        await ws.send_json({"id": 14, "type": f"{DOMAIN}/stale", "entry_id": entry.entry_id})
        stale = (await ws.receive_json())["result"]
        assert sorted(e["entity_id"] for e in stale["entities"]) == sorted([old.entity_id, old2.entity_id])
        assert stale["devices"] == []
        await ws.send_json({"id": 15, "type": f"{DOMAIN}/stale/remove", "entry_id": entry.entry_id})
        assert (await ws.receive_json())["result"] == {"entities": 2, "devices": 0}
        assert ent.async_get(kotel) is not None
        assert ent.async_get(old.entity_id) is None
        assert ent.async_get(mode) is not None

        # část 4: role hodnot pro panel, elektroměr jako druhé nastavitelné měřidlo (kWh)
        await ws.send_json({"id": 16, "type": f"{DOMAIN}/info", "entry_id": entry.entry_id})
        info = (await ws.receive_json())["result"]
        assert info["tech"]["values"]["grid1"]["uid"] == 311 and info["tech"]["values"]["e_imp"]["unit"] == "kWh"
        assert [(m["uid"], m["unit"]) for m in info["meters"]] == [(241, "m³"), (314, "kWh")]
        await ws.send_json({"id": 17, "type": f"{DOMAIN}/config/set", "entry_id": entry.entry_id,
                            "pairs": [[9002, 2000000 % 65536], [9003, 2000000 // 65536]]})
        assert (await ws.receive_json())["success"]
        assert plc.e_imp == 2000000
        await coord.async_refresh()
        await hass.async_block_till_done()
        odb = ent.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_314")
        assert float(hass.states.get(odb).state) == 2000.0
        l1 = ent.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_311")
        assert ent.async_get(l1).disabled_by is not None   # okamžitá hodnota EM03 je ve výchozím stavu vypnutá
        assert hass.states.get(l1) is None
        assert await hass.config_entries.async_unload(entry.entry_id)
    finally:
        await plc.stop()
