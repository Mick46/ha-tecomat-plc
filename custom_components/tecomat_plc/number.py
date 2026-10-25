"""Konfigurační čísla: korekce teploty (typ TEMP) a parametry PLC (typ NUMBER)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CORR_INDEX_BASE, F_DIRECT, F_PARAM_ENTITY, PARAM_INDEX_BASE, T_NUMBER, T_TEMP, UNIT_BOOL
from .entity import TecomatEntity
from .modbus_client import ModbusError
from .sensor import UNITS


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coord = entry.runtime_data
    entities: list[NumberEntity] = []
    if coord.protocol < 2:
        # protokol 2: korekce teplot a parametry se nastavují v panelu ovladačů
        entities += [TecomatTempCorrection(coord, o) for o in coord.desc.objects_of(T_TEMP)]
    entities += [
        TecomatParam(coord, o)
        for o in coord.desc.objects_of(T_NUMBER)
        if o.flags & F_PARAM_ENTITY and not o.flags & F_DIRECT and (o.flags >> 8) != UNIT_BOOL  # ano/ne je switch
    ]
    entities += [TecomatDirectNumber(coord, o) for o in coord.desc.objects_of(T_NUMBER) if o.flags & F_DIRECT]
    async_add_entities(entities)


class TecomatTempCorrection(TecomatEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = -10.0
    _attr_native_max_value = 10.0
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:thermometer-plus"

    def __init__(self, coordinator, obj) -> None:
        super().__init__(coordinator, obj, "_corr")
        self._attr_name = f"{obj.name} korekce"

    @property
    def native_value(self) -> float | None:
        v = self.coordinator.get_signed(self.obj.addr + 2)
        return None if v is None else v / 10

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.coordinator.write_config([(CORR_INDEX_BASE + self.obj.p1, round(value * 10))])
        except ModbusError as err:
            raise HomeAssistantError(f"Zápis korekce selhal: {err}") from err


def _s16(v: int) -> int:
    return v - 65536 if v > 32767 else v


class TecomatParam(TecomatEntity, NumberEntity):
    """Parametr uložený v PLC (doby, jasy, teploty …). Zápis přes schránku, PLC ho uloží (RETAIN)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, obj) -> None:
        super().__init__(coordinator, obj)
        self._dec = obj.flags & 0x07
        self._div = 10**self._dec
        self._attr_native_min_value = _s16(obj.p1) / self._div
        self._attr_native_max_value = _s16(obj.p2) / self._div
        self._attr_native_step = 1 / self._div
        self._attr_native_unit_of_measurement = UNITS.get(obj.flags >> 8)

    @property
    def native_value(self) -> float | None:
        v = self.coordinator.get_signed(self.obj.addr)
        if v is None:
            return None
        return v / self._div if self._dec else v

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.coordinator.write_config([(PARAM_INDEX_BASE + self.obj.p3, round(value * self._div))])
        except ModbusError as err:
            raise HomeAssistantError(f"Zápis parametru selhal: {err}") from err


class TecomatDirectNumber(TecomatParam):
    """Nastavení zařízení za PLC (střídač): +0 přečtená hodnota, +1 požadovaná, +2 povel; PLC zapíše jednorázově."""

    _attr_mode = NumberMode.BOX
    _attr_entity_category = None  # mezi ovládacími prvky spolu s volbami

    @property
    def native_value(self) -> float | None:
        v = self.coordinator.get(self.obj.addr)
        if v is None or v == 0x8000:  # 0x8000 = zařízení ještě nepřečteno (např. po nahrání programu)
            return None
        return v / self._div if self._dec else v

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.write_registers(self.obj.addr + 1, [round(value * self._div), 1])
