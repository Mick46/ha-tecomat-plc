"""Konfigurační čísla: korekce teploty (typ TEMP)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CORR_INDEX_BASE, T_TEMP
from .entity import TecomatEntity
from .modbus_client import ModbusError


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coord = entry.runtime_data
    async_add_entities(TecomatTempCorrection(coord, o) for o in coord.desc.objects_of(T_TEMP))


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
