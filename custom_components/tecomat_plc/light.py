"""Světla (typ LIGHT) a stmívače (typ DIMMER)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import T_DIMMER, T_LIGHT
from .entity import TecomatEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coord = entry.runtime_data
    entities: list[LightEntity] = [TecomatLight(coord, o) for o in coord.desc.objects_of(T_LIGHT)]
    entities += [TecomatDimmer(coord, o) for o in coord.desc.objects_of(T_DIMMER)]
    async_add_entities(entities)


class TecomatLight(TecomatEntity, LightEntity):
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_color_mode = ColorMode.ONOFF

    @property
    def is_on(self) -> bool | None:
        v = self.coordinator.get(self.obj.addr)
        return None if v is None else v != 0

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.write_register(self.obj.addr, 1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.write_register(self.obj.addr, 0)


class TecomatDimmer(TecomatEntity, LightEntity):
    """Stmívač: +0 žádaný jas 0–100 % (zápis), +1 skutečný jas. Rampu a max. jas řeší PLC."""

    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS

    def _target(self) -> int | None:
        return self.coordinator.get(self.obj.addr)

    @property
    def is_on(self) -> bool | None:
        v = self._target()
        return None if v is None else v > 0

    @property
    def brightness(self) -> int | None:
        v = self._target()
        return None if v is None else round(min(v, 100) * 255 / 100)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"skutecny_jas": self.coordinator.get(self.obj.addr + 1)}

    async def async_turn_on(self, **kwargs: Any) -> None:
        pct = 100
        if ATTR_BRIGHTNESS in kwargs:
            pct = max(1, round(kwargs[ATTR_BRIGHTNESS] * 100 / 255))
        await self.coordinator.write_register(self.obj.addr, pct)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.write_register(self.obj.addr, 0)
