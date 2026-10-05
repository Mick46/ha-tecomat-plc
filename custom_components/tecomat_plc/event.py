"""Tlačítka (typ BUTTON) jako event entity: short / long / double."""

from __future__ import annotations

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import BUTTON_EVENTS, T_BUTTON
from .entity import TecomatEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coord = entry.runtime_data
    async_add_entities(TecomatButton(coord, o) for o in coord.desc.objects_of(T_BUTTON))


class TecomatButton(TecomatEntity, EventEntity):
    _attr_device_class = EventDeviceClass.BUTTON
    _attr_event_types = list(BUTTON_EVENTS.values())

    def __init__(self, coordinator, obj) -> None:
        super().__init__(coordinator, obj)
        self._last: int | None = coordinator.get(obj.addr)

    @callback
    def _handle_coordinator_update(self) -> None:
        v = self.coordinator.get(self.obj.addr)
        if v is not None:
            if self._last is not None and v != self._last:
                typ = BUTTON_EVENTS.get(v & 0xFF)
                if typ:
                    self._trigger_event(typ, {"count": v >> 8})
            self._last = v
        super()._handle_coordinator_update()
