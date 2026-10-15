"""Žaluzie a markýzy (typ COVER) a garážová vrata (typ GATE)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import T_COVER, T_GATE
from .entity import TecomatEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coord = entry.runtime_data
    entities: list[CoverEntity] = [TecomatCover(coord, o) for o in coord.desc.objects_of(T_COVER)]
    entities += [TecomatGate(coord, o) for o in coord.desc.objects_of(T_GATE)]
    async_add_entities(entities)


class TecomatCover(TecomatEntity, CoverEntity):
    """Poloha a lamely počítá PLC z doby jízdy (0 = zavřeno / dole, 100 = otevřeno / nahoře)."""

    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, coordinator, obj) -> None:
        super().__init__(coordinator, obj)
        self._attr_device_class = CoverDeviceClass.BLIND if obj.flags & 1 else CoverDeviceClass.AWNING

    def _reg(self, k: int) -> int | None:
        return self.coordinator.get(self.obj.addr + k)

    @property
    def current_cover_position(self) -> int | None:
        return self._reg(2)

    @property
    def current_cover_tilt_position(self) -> int | None:
        return self._reg(3) if self.obj.flags & 1 else None

    @property
    def is_closed(self) -> bool | None:
        v = self._reg(2)
        return None if v is None else v <= 0

    @property
    def is_opening(self) -> bool:
        return self._reg(4) == 1

    @property
    def is_closing(self) -> bool:
        return self._reg(4) == 2

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self.coordinator.write_register(self.obj.addr, 1)

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self.coordinator.write_register(self.obj.addr, 2)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self.coordinator.write_register(self.obj.addr, 3)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        await self.coordinator.write_register(self.obj.addr + 1, int(kwargs[ATTR_POSITION]))
        await self.coordinator.write_register(self.obj.addr, 4)


class TecomatGate(TecomatEntity, CoverEntity):
    """Garážová vrata ovládaná impulzem; stav z koncového kontaktu."""

    _attr_device_class = CoverDeviceClass.GARAGE
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    @property
    def is_closed(self) -> bool | None:
        v = self.coordinator.get(self.obj.addr + 1)
        return None if v is None else v == 0

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self.coordinator.write_register(self.obj.addr, 1)

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self.coordinator.write_register(self.obj.addr, 2)
