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
    CORR_INDEX_BASE,
    DOMAIN,
    H_MAGIC,
    H_PROG_VERSION,
    MAILBOX_BATCH,
    NO_MATRIX,
    PANEL_URL,
    S_CFG_ACK,
    S_CFG_CHECKSUM,
    S_HB_IN,
    S_WINDOW_REQ,
    STATUS_LEN,
    T_BINARY,
    T_BUTTON,
    T_LIGHT,
    T_SWITCH,
    T_TEMP,
    WINDOW_BYTES,
    WINDOW_REGS,
)
from .descriptor import Descriptor, read_header
from .modbus_client import ModbusError, ModbusTcpClient

_LOGGER = logging.getLogger(__name__)

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


def config_checksum(cfg_map: dict[str, int], corr: dict[int, int], max_b: int) -> int:
    """Stejný výpočet jako v PLC."""
    chk = 0
    for key, code in cfg_map.items():
        if not code:
            continue
        c, b = (int(x) for x in key.split(","))
        i = c * max_b + b
        chk = (chk + code * ((i % 251) + 1)) % 65536
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
        client: ModbusTcpClient,
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

        sb = desc.status_base
        addrs: set[int] = set(range(sb, sb + STATUS_LEN))
        for o in desc.objects:
            if o.type in (T_LIGHT, T_SWITCH, T_BUTTON, T_BINARY):
                addrs.add(o.addr)
            elif o.type == T_TEMP:
                addrs.update((o.addr, o.addr + 1, o.addr + 2))
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
            info["via_device"] = (DOMAIN, f"{entry_id}_g0")
        return info

    # ----------------------------------------------------------- konfigurace
    def matrix_circuits(self):
        return [o for o in self.desc.objects_of(T_LIGHT, T_SWITCH) if o.p1 != NO_MATRIX]

    def matrix_buttons(self):
        return [o for o in self.desc.objects_of(T_BUTTON) if o.p1 != NO_MATRIX]

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

    async def read_config(self) -> dict:
        """Načte matici tlačítko × okruh a korekce teplot přímo z PLC."""
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
        for c in self.matrix_circuits():
            for b in self.matrix_buttons():
                pairs.append((c.p1 * d.max_b + b.p1, int(cfg_map.get(f"{c.p1},{b.p1}", 0))))
        for t in d.objects_of(T_TEMP):
            pairs.append((CORR_INDEX_BASE + t.p1, int(corr.get(str(t.p1), corr.get(t.p1, 0)) or 0)))
        return pairs
