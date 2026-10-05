"""Spínače (typ SWITCH: zásuvky, čerpadla, ...)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import T_SWITCH
from .entity import TecomatEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coord = entry.runtime_data
    async_add_entities(TecomatSwitch(coord, o) for o in coord.desc.objects_of(T_SWITCH))


class TecomatSwitch(TecomatEntity, SwitchEntity):
    @property
    def is_on(self) -> bool | None:
        v = self.coordinator.get(self.obj.addr)
        return None if v is None else v != 0

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.write_register(self.obj.addr, 1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.write_register(self.obj.addr, 0)
