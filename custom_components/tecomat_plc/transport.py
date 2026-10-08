"""Komunikace s PLC: sdílené Modbus spojení Home Assistant, nebo vlastní klient.

Od HA 2026.10 integrace žádá o spojení vestavěnou integraci Modbus
(`modbus.async_get_unit`). Spojení je pak vidět v *Nastavení → Připojení → Modbus*
a sdílí ho všechny integrace, které mluví se stejným PLC. Na starším HA se použije
vlastní Modbus TCP klient (`modbus_client.py`) a integrace Modbus se vůbec nenačítá.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Protocol

import homeassistant.components as ha_components
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from .modbus_client import ModbusError, ModbusTcpClient

_LOGGER = logging.getLogger(__name__)

MAX_READ = 120

# Lze vypnout (testy, nouzové řešení): False = vždy vlastní klient
USE_SHARED = True


class PlcTransport(Protocol):
    """Co integrace od spojení potřebuje."""

    shared: bool
    host: str

    async def read_holding(self, address: int, count: int) -> list[int]: ...
    async def read_many(self, address: int, count: int) -> list[int]: ...
    async def write_single(self, address: int, value: int) -> None: ...
    async def write_multiple(self, address: int, values: list[int]) -> None: ...
    async def close(self) -> None: ...


class OwnTransport(ModbusTcpClient):
    """Vlastní Modbus TCP klient (HA starší než 2026.10)."""

    shared = False


class SharedTransport:
    """Jednotka na sdíleném spojení HA (modbus_connection.ModbusUnit)."""

    shared = True

    def __init__(self, unit: Any, host: str, error_cls: type[Exception]) -> None:
        self._unit = unit
        self.host = host
        self._error_cls = error_cls

    async def _call(self, coro):
        try:
            return await coro
        except (self._error_cls, OSError, TimeoutError) as err:
            raise ModbusError(f"{self.host}: {err}") from err

    async def read_holding(self, address: int, count: int) -> list[int]:
        return list(await self._call(self._unit.read_holding_registers(address, count)))

    async def read_many(self, address: int, count: int) -> list[int]:
        out: list[int] = []
        while count > 0:
            n = min(count, MAX_READ)
            out.extend(await self.read_holding(address, n))
            address += n
            count -= n
        return out

    async def write_single(self, address: int, value: int) -> None:
        await self._call(self._unit.write_register(address, value & 0xFFFF))

    async def write_multiple(self, address: int, values: list[int]) -> None:
        await self._call(self._unit.write_registers(address, [v & 0xFFFF for v in values]))

    async def close(self) -> None:
        """Spojení uvolní HA sám při odebrání nebo znovunačtení integrace."""


def ha_has_shared_modbus() -> bool:
    """HA má sdílené Modbus API (2026.10+). Kontrola bez importu integrace Modbus."""
    return any((Path(p) / "modbus" / "connection.py").is_file() for p in ha_components.__path__)


async def _shared_api(hass: HomeAssistant):
    """Vrátí (async_get_unit, async_get_temporary_unit, ModbusTcpParams, ModbusError), nebo None.

    Sdílené API má HA od 2026.10 (homeassistant/components/modbus/connection.py).
    Integrace Modbus se načte jen tehdy, když ho HA má. Tím se doinstalují její
    knihovny (modbus-connection) a zaregistruje panel spojení.
    """
    if not USE_SHARED:
        return None
    if not ha_has_shared_modbus():
        return None
    if not await async_setup_component(hass, "modbus", {}):
        _LOGGER.warning("Integraci Modbus se nepodařilo načíst, použiji vlastní Modbus klient")
        return None
    try:
        from homeassistant.components.modbus import (  # noqa: PLC0415
            async_get_temporary_unit,
            async_get_unit,
        )
        from modbus_connection import ModbusTcpParams  # noqa: PLC0415
        from modbus_connection.exceptions import ModbusError as SharedModbusError  # noqa: PLC0415
    except ImportError as err:
        _LOGGER.warning("Sdílené Modbus API není dostupné (%s), použiji vlastní klient", err)
        return None
    return async_get_unit, async_get_temporary_unit, ModbusTcpParams, SharedModbusError


async def async_create_transport(
    hass: HomeAssistant, entry: ConfigEntry, host: str, port: int, unit_id: int
) -> PlcTransport:
    """Spojení pro běžící integraci."""
    if api := await _shared_api(hass):
        get_unit, _tmp, params_cls, err_cls = api
        unit = get_unit(hass, entry, params_cls(host=host, port=port), unit_id)
        _LOGGER.debug("Sdílené Modbus spojení HA k %s:%s", host, port)
        return SharedTransport(unit, host, err_cls)
    return OwnTransport(host, port, unit_id)


@asynccontextmanager
async def temporary_transport(
    hass: HomeAssistant, host: str, port: int, unit_id: int
) -> AsyncIterator[PlcTransport]:
    """Krátkodobé spojení pro průvodce (ověření PLC před uložením)."""
    if api := await _shared_api(hass):
        _get, get_tmp, params_cls, err_cls = api
        async with get_tmp(hass, params_cls(host=host, port=port), unit_id) as unit:
            yield SharedTransport(unit, host, err_cls)
        return
    client = OwnTransport(host, port, unit_id)
    try:
        yield client
    finally:
        await client.close()
