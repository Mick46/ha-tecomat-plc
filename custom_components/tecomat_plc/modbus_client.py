"""Minimalistický asynchronní Modbus TCP klient (funkce 03, 06, 16).

Vlastní implementace bez závislosti na pymodbus, aby integrace nebyla citlivá
na změny API pymodbus mezi verzemi Home Assistant.
"""

from __future__ import annotations

import asyncio
import struct


class ModbusError(Exception):
    """Chyba komunikace Modbus."""


class ModbusTcpClient:
    """Jedno trvalé spojení Modbus TCP se sériovým zpracováním požadavků."""

    MAX_READ = 120

    def __init__(self, host: str, port: int, unit_id: int, timeout: float = 3.0) -> None:
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self._tid = 0

    async def _connect(self) -> None:
        if self._writer is not None:
            return
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.timeout
            )
        except (OSError, asyncio.TimeoutError) as err:
            raise ModbusError(f"Nelze se připojit k {self.host}:{self.port}: {err}") from err

    async def close(self) -> None:
        writer = self._writer
        self._reader = self._writer = None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass

    async def _request(self, pdu: bytes) -> bytes:
        async with self._lock:
            await self._connect()
            assert self._reader and self._writer
            self._tid = (self._tid + 1) & 0xFFFF
            mbap = struct.pack(">HHHB", self._tid, 0, len(pdu) + 1, self.unit_id)
            try:
                self._writer.write(mbap + pdu)
                await self._writer.drain()
                head = await asyncio.wait_for(self._reader.readexactly(7), self.timeout)
                tid, _proto, length, _unit = struct.unpack(">HHHB", head)
                body = await asyncio.wait_for(self._reader.readexactly(length - 1), self.timeout)
            except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError) as err:
                await self.close()
                raise ModbusError(f"Chyba komunikace s {self.host}: {err!r}") from err
            if tid != self._tid:
                await self.close()
                raise ModbusError("Nesouhlasí transaction id odpovědi")
            if body[0] & 0x80:
                code = body[1] if len(body) > 1 else 0
                raise ModbusError(f"Modbus výjimka {code} pro funkci {body[0] & 0x7F}")
            if body[0] != pdu[0]:
                raise ModbusError("Neočekávaný kód funkce v odpovědi")
            return body

    async def read_holding(self, address: int, count: int) -> list[int]:
        """Přečte až 125 holding registrů."""
        body = await self._request(struct.pack(">BHH", 3, address, count))
        n = body[1]
        if n != count * 2:
            raise ModbusError("Neočekávaná délka odpovědi")
        return list(struct.unpack(f">{count}H", body[2 : 2 + n]))

    async def read_many(self, address: int, count: int) -> list[int]:
        """Přečte libovolný počet registrů po blocích."""
        out: list[int] = []
        while count > 0:
            n = min(count, self.MAX_READ)
            out.extend(await self.read_holding(address, n))
            address += n
            count -= n
        return out

    async def write_single(self, address: int, value: int) -> None:
        await self._request(struct.pack(">BHH", 6, address, value & 0xFFFF))

    async def write_multiple(self, address: int, values: list[int]) -> None:
        vals = [v & 0xFFFF for v in values]
        pdu = struct.pack(f">BHHB{len(vals)}H", 16, address, len(vals), len(vals) * 2, *vals)
        await self._request(pdu)
