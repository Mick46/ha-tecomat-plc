"""Tlačítko „Impulz“ u garážových vrat (typ GATE)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import T_GATE
from .entity import TecomatEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coord = entry.runtime_data
    async_add_entities(TecomatGateImpulse(coord, o) for o in coord.desc.objects_of(T_GATE))


class TecomatGateImpulse(TecomatEntity, ButtonEntity):
    """Impulz jako tlačítko na zdi: otevřít / stop / zavřít podle pohonu."""

    _attr_icon = "mdi:garage-alert"

    def __init__(self, coordinator, obj) -> None:
        super().__init__(coordinator, obj, "_impulse")
        self._attr_name = f"{obj.name} impulz"

    async def async_press(self) -> None:
        await self.coordinator.write_register(self.obj.addr, 3)
