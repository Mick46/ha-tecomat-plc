"""Koordinátor: pravidelné čtení PLC, heartbeat, zápis konfigurace."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    AUTO_INDEX_BASE,
    AUTO_REGS,
    BTN_SLOTS,
    CORR_INDEX_BASE,
    DOMAIN,
    F_VALUE_32,
    F_VALUE_UNSIGNED,
    H_MAGIC,
    H_PROG_VERSION,
    MAILBOX_BATCH,
    NO_MATRIX,
    PARAM_INDEX_BASE,
    PANEL_URL,
    S_CFG_ACK,
    S_CFG_CHECKSUM,
    S_HB_IN,
    S_WINDOW_REQ,
    STATUS_LEN,
    T_BINARY,
    T_BUTTON,
    T_COVER,
    T_GATE,
    T_DIMMER,
    T_LIGHT,
    T_ACTION,
    T_NUMBER,
    T_SELECT,
    F_READONLY,
    T_SWITCH,
    T_TEMP,
    T_VALUE,
    WINDOW_BYTES,
    WINDOW_REGS,
)
from .descriptor import Descriptor, read_header
from .modbus_client import ModbusError
from .transport import PlcTransport

_LOGGER = logging.getLogger(__name__)

# HA 2026.8+: propojení zařízení přes id v registru (via_device je zastaralé)
VIA_DEVICE_ID = "via_device_id" in DeviceInfo.__annotations__

HEARTBEAT_INTERVAL = timedelta(seconds=30)
HEADER_CHECK_S = 60


def signed16(v: int | None) -> int | None:
    if v is None:
        return None
    return v - 65536 if v > 32767 else v


def build_ranges(addrs: set[int], max_gap: int = 16, max_len: int = 120) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for a in sorted(addrs):
        if ranges:
            start, cnt = ranges[-1]
            end = start + cnt
            if a < end:
                continue
            if a - end <= max_gap and a - start + 1 <= max_len:
                ranges[-1] = (start, a - start + 1)
                continue
        ranges.append((a, 1))
    return ranges


def config_checksum(cfg_map: dict[str, int], corr: dict[int, int], max_b: int, protocol: int = 1) -> int:
    """Stejný výpočet jako v PLC.

    Protokol 1: klíč mapy „okruh,tlačítko“, index = okruh·max_b + tlačítko.
    Protokol 2: klíč mapy = index ve schránce (tlačítka 0.., parametry 20000..).
    """
    chk = 0
    for key, code in cfg_map.items():
        if not code:
            continue
        if protocol >= 2:
            i = int(key)
        else:
            c, b = (int(x) for x in key.split(","))
            i = c * max_b + b
        chk = (chk + (int(code) & 0xFFFF) * ((i % 251) + 1)) % 65536
    for idx, val in corr.items():
        u = val + 65536 if val < 0 else val
        chk = (chk + u * (((CORR_INDEX_BASE + int(idx)) % 251) + 1)) % 65536
    return chk


class TecomatCoordinator(DataUpdateCoordinator[dict[int, int]]):
    """Čte všechny adresy z deskriptoru po blocích jedním spojením."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: PlcTransport,
        desc: Descriptor,
        scan_interval: float,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {client.host}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.desc = desc
        self._cfg_lock = asyncio.Lock()
        self._hb = 0
        self._unsub_hb = None
        self._last_hdr_check = 0.0
        self.versions = None  # VersionStore, nastaví __init__.py
        self.root_device_id: str | None = None  # id zařízení PLC (skupina 0) v registru
        self.options_snapshot: dict = dict(entry.options)

        sb = desc.status_base
        addrs: set[int] = set(range(sb, sb + STATUS_LEN))
        for o in desc.objects:
            if o.type in (T_LIGHT, T_SWITCH, T_BUTTON, T_BINARY):
                addrs.add(o.addr)
            elif o.type == T_TEMP:
                addrs.update((o.addr, o.addr + 1, o.addr + 2))
            elif o.type == T_DIMMER:
                addrs.update((o.addr, o.addr + 1))
            elif o.type == T_COVER:
                addrs.update(range(o.addr, o.addr + 5))
            elif o.type == T_GATE:
                addrs.update((o.addr, o.addr + 1))
            elif o.type in (T_NUMBER, T_SELECT, T_ACTION):
                addrs.add(o.addr)
            elif o.type == T_VALUE:
                addrs.add(o.addr)
                if o.flags & F_VALUE_32:
                    addrs.add(o.addr + 1)
        self._ranges = build_ranges(addrs)

    # ------------------------------------------------------------------ data
    async def _async_update_data(self) -> dict[int, int]:
        data: dict[int, int] = {}
        try:
            for start, cnt in self._ranges:
                vals = await self.client.read_holding(start, cnt)
                data.update({start + i: v for i, v in enumerate(vals)})
            if time.monotonic() - self._last_hdr_check > HEADER_CHECK_S:
                self._last_hdr_check = time.monotonic()
                await self._check_program_change()
        except ModbusError as err:
            raise UpdateFailed(str(err)) from err
        return data

    async def _check_program_change(self) -> None:
        try:
            hdr = await read_header(self.client)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Popis v PLC není dostupný: %s", err)
            return
        if hdr[H_PROG_VERSION] != self.desc.prog_version or hdr[H_MAGIC] == 0:
            _LOGGER.info(
                "V PLC je nový program (verze %s -> %s), integrace se znovu načte",
                self.desc.prog_version,
                hdr[H_PROG_VERSION],
            )
            self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)

    def get(self, addr: int) -> int | None:
        return self.data.get(addr) if self.data else None

    def get_signed(self, addr: int) -> int | None:
        return signed16(self.get(addr))

    def get_value(self, addr: int, flags: int) -> int | None:
        """Celé číslo z 1 nebo 2 registrů (vyšší slovo první) podle příznaků objektu."""
        hi = self.get(addr)
        if hi is None:
            return None
        if flags & F_VALUE_32:
            lo = self.get(addr + 1)
            if lo is None:
                return None
            v = (hi << 16) | lo
            return v if flags & F_VALUE_UNSIGNED or v < 0x80000000 else v - 0x100000000
        return hi if flags & F_VALUE_UNSIGNED else signed16(hi)

    def status(self, offset: int) -> int | None:
        return self.get(self.desc.status_base + offset)

    async def write_register(self, addr: int, value: int) -> None:
        try:
            await self.client.write_single(addr, value)
        except ModbusError as err:
            raise HomeAssistantError(f"Zápis do PLC selhal: {err}") from err
        if self.data is not None:
            self.data[addr] = value & 0xFFFF
            self.async_update_listeners()
        await self.async_request_refresh()

    # ------------------------------------------------------------- heartbeat
    @callback
    def start_heartbeat(self) -> None:
        self._unsub_hb = async_track_time_interval(self.hass, self._send_heartbeat, HEARTBEAT_INTERVAL)
        self.hass.async_create_task(self._send_heartbeat())

    async def _send_heartbeat(self, _now=None) -> None:
        self._hb = (self._hb % 30000) + 1
        try:
            await self.client.write_single(self.desc.status_base + S_HB_IN, self._hb)
        except ModbusError as err:
            _LOGGER.debug("Heartbeat se nepodařilo zapsat: %s", err)

    async def async_shutdown(self) -> None:
        if self._unsub_hb:
            self._unsub_hb()
            self._unsub_hb = None
        await super().async_shutdown()
        await self.client.close()

    # --------------------------------------------------------------- zařízení
    def device_info(self, group: int) -> DeviceInfo:
        entry_id = self.config_entry.entry_id
        g = self.desc.group(group)
        info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_g{group}")},
            name=g.name,
            manufacturer="Teco a.s.",
            configuration_url=f"homeassistant://{PANEL_URL}",
        )
        if g.area:
            info["suggested_area"] = g.area
        if group == 0:
            info["model"] = self.desc.plc_model
            info["sw_version"] = f"program {self.desc.prog_version}"
        else:
            info["model"] = "CIB"
            if VIA_DEVICE_ID:
                if self.root_device_id:
                    info["via_device_id"] = self.root_device_id
            else:
                info["via_device"] = (DOMAIN, f"{entry_id}_g0")
        return info

    # ----------------------------------------------------------- konfigurace
    @property
    def protocol(self) -> int:
        return self.desc.protocol

    def matrix_circuits(self):
        if self.protocol >= 2:
            return []
        return [o for o in self.desc.objects_of(T_LIGHT, T_SWITCH) if o.p1 != NO_MATRIX]

    def matrix_buttons(self):
        if self.protocol >= 2:
            return []
        return [o for o in self.desc.objects_of(T_BUTTON) if o.p1 != NO_MATRIX]

    # protokol 2: tlačítka a cíle akcí
    def buttons_v2(self):
        return self.desc.objects_of(T_BUTTON)

    def targets_v2(self):
        return [o for o in self.desc.objects_of(T_LIGHT, T_SWITCH, T_DIMMER, T_COVER, T_GATE) if not o.flags & F_READONLY]

    def params_v2(self):
        """Parametry v PLC (schránka 20000 + p3): čísla a volby (ne stavové volby)."""
        return [o for o in self.desc.objects_of(T_NUMBER, T_SELECT) if not (o.type == T_SELECT and o.flags & F_READONLY)]

    def config_ranges_v2(self) -> list[tuple[int, int]]:
        """Oblasti konfigurace (začátek, počet) pro čtecí okno a zálohy."""
        ranges = []
        nb = len(self.buttons_v2())
        if nb:
            ranges.append((0, nb * BTN_SLOTS))
        if self.desc.autos:
            ranges.append((AUTO_INDEX_BASE, len(self.desc.autos) * AUTO_REGS))
        params = self.params_v2()
        if params:
            ranges.append((PARAM_INDEX_BASE, max(o.p3 for o in params) + 1))
        return ranges

    async def _read_status(self, offset: int) -> int:
        return (await self.client.read_holding(self.desc.status_base + offset, 1))[0]

    async def write_config(self, pairs: list[tuple[int, int]]) -> None:
        """Zapíše dvojice (index, hodnota) přes schránku a počká na potvrzení PLC."""
        async with self._cfg_lock:
            for i in range(0, len(pairs), MAILBOX_BATCH):
                chunk = pairs[i : i + MAILBOX_BATCH]
                ack = await self._read_status(S_CFG_ACK)
                seq = 1 if ack >= 30000 else ack + 1
                values = [seq, len(chunk)]
                for idx, val in chunk:
                    values += [int(idx) & 0xFFFF, int(val) & 0xFFFF]
                await self.client.write_multiple(self.desc.mailbox_base, values)
                for _ in range(60):
                    await asyncio.sleep(0.05)
                    if await self._read_status(S_CFG_ACK) == seq:
                        break
                else:
                    raise ModbusError(f"PLC nepotvrdilo zápis konfigurace (seq {seq})")
        await self.async_request_refresh()

    async def _read_window(self, start: int) -> list[int]:
        await self.client.write_single(self.desc.status_base + S_WINDOW_REQ, start)
        for _ in range(40):
            vals = await self.client.read_holding(self.desc.window_base, WINDOW_REGS)
            if vals[0] == start:
                return vals[1:]
            await asyncio.sleep(0.03)
        raise ModbusError(f"PLC neodpovědělo na čtení bloku {start}")

    async def _read_config_v2(self) -> dict:
        d = self.desc
        cfg_map: dict[str, int] = {}
        async with self._cfg_lock:
            for start, count in self.config_ranges_v2():
                for blk in range(start, start + count, WINDOW_REGS - 1):
                    vals = await self._read_window(blk)
                    for j, v in enumerate(vals):
                        if blk + j < start + count:
                            cfg_map[str(blk + j)] = v
            corr: dict[int, int] = {}
            for t in d.objects_of(T_TEMP):
                v = (await self.client.read_holding(t.addr + 2, 1))[0]
                corr[t.p1] = signed16(v)
            chk_plc = await self._read_status(S_CFG_CHECKSUM)
        return {
            "protocol": 2,
            "map": cfg_map,
            "corr": {str(k): v for k, v in corr.items()},
            "checksum_plc": chk_plc,
            "checksum_calc": config_checksum(cfg_map, corr, d.max_b, 2),
        }

    async def read_config(self) -> dict:
        """Načte konfiguraci přímo z PLC (protokol 1: matice tlačítko × okruh, 2: akce tlačítek a parametry)."""
        if self.protocol >= 2:
            return await self._read_config_v2()
        d = self.desc
        circuits = self.matrix_circuits()
        buttons = self.matrix_buttons()
        blocks = sorted(
            {((c.p1 * d.max_b + b.p1) // WINDOW_BYTES) * WINDOW_BYTES for c in circuits for b in buttons}
        )
        raw: dict[int, int] = {}
        async with self._cfg_lock:
            for start in blocks:
                await self.client.write_single(d.status_base + S_WINDOW_REQ, start)
                for _ in range(40):
                    vals = await self.client.read_holding(d.window_base, WINDOW_REGS)
                    if vals[0] == start:
                        break
                    await asyncio.sleep(0.03)
                else:
                    raise ModbusError(f"PLC neodpovědělo na čtení bloku {start}")
                for j, v in enumerate(vals[1:]):
                    raw[start + 2 * j] = v & 0xFF
                    raw[start + 2 * j + 1] = (v >> 8) & 0xFF
            corr: dict[int, int] = {}
            for t in d.objects_of(T_TEMP):
                v = (await self.client.read_holding(t.addr + 2, 1))[0]
                corr[t.p1] = signed16(v)
            chk_plc = await self._read_status(S_CFG_CHECKSUM)
        cfg_map = {f"{c.p1},{b.p1}": raw.get(c.p1 * d.max_b + b.p1, 0) for c in circuits for b in buttons}
        return {
            "map": cfg_map,
            "corr": {str(k): v for k, v in corr.items()},
            "checksum_plc": chk_plc,
            "checksum_calc": config_checksum(cfg_map, corr, d.max_b),
        }

    def all_pairs(self, cfg_map: dict[str, int], corr: dict) -> list[tuple[int, int]]:
        d = self.desc
        pairs = []
        if self.protocol >= 2:
            pairs = [(int(k), int(v)) for k, v in cfg_map.items()]
            for t in d.objects_of(T_TEMP):
                pairs.append((CORR_INDEX_BASE + t.p1, int(corr.get(str(t.p1), corr.get(t.p1, 0)) or 0)))
            return pairs
        for c in self.matrix_circuits():
            for b in self.matrix_buttons():
                pairs.append((c.p1 * d.max_b + b.p1, int(cfg_map.get(f"{c.p1},{b.p1}", 0))))
        for t in d.objects_of(T_TEMP):
            pairs.append((CORR_INDEX_BASE + t.p1, int(corr.get(str(t.p1), corr.get(t.p1, 0)) or 0)))
        return pairs
