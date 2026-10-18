"""Spínače (typ SWITCH: zásuvky, čerpadla, ...)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import F_PARAM_ENTITY, F_READONLY, PARAM_INDEX_BASE, T_NUMBER, T_SWITCH, UNIT_BOOL
from .entity import TecomatEntity
from .modbus_client import ModbusError


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coord = entry.runtime_data
    entities: list[SwitchEntity] = [
        TecomatSwitch(coord, o) for o in coord.desc.objects_of(T_SWITCH) if not o.flags & F_READONLY
    ]
    entities += [
        TecomatParamSwitch(coord, o)
        for o in coord.desc.objects_of(T_NUMBER)
        if o.flags & F_PARAM_ENTITY and (o.flags >> 8) == UNIT_BOOL
    ]
    async_add_entities(entities)


# protokol 2: podtyp výstupu -> třída a ikona
ICONS = {4: "mdi:pump", 5: "mdi:fan", 7: "mdi:water-boiler", 8: "mdi:water-thermometer", 9: "mdi:power-plug",
         10: "mdi:radiator"}


class TecomatSwitch(TecomatEntity, SwitchEntity):
    def __init__(self, coordinator, obj) -> None:
        super().__init__(coordinator, obj)
        if coordinator.protocol >= 2:
            if obj.p2 == 3:
                self._attr_device_class = SwitchDeviceClass.OUTLET
            elif obj.p2 in ICONS:
                self._attr_icon = ICONS[obj.p2]

    @property
    def is_on(self) -> bool | None:
        v = self.coordinator.get(self.obj.addr)
        return None if v is None else v != 0

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.write_register(self.obj.addr, 1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.write_register(self.obj.addr, 0)


class TecomatParamSwitch(TecomatEntity, SwitchEntity):
    """Parametr ano/ne uložený v PLC (např. ohřev bazénu povolen)."""

    _attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self) -> bool | None:
        v = self.coordinator.get(self.obj.addr)
        return None if v is None else v != 0

    async def _set(self, value: int) -> None:
        try:
            await self.coordinator.write_config([(PARAM_INDEX_BASE + self.obj.p3, value)])
        except ModbusError as err:
            raise HomeAssistantError(f"Zápis parametru selhal: {err}") from err

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(0)
