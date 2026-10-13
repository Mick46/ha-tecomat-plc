"""Spínače (typ SWITCH: zásuvky, čerpadla, ...)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import T_SWITCH
from .entity import TecomatEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coord = entry.runtime_data
    async_add_entities(TecomatSwitch(coord, o) for o in coord.desc.objects_of(T_SWITCH))


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
