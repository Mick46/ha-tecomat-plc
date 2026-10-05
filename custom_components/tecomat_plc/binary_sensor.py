"""Binární vstupy (typ BINARY) a stav spojení HA ↔ PLC."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import S_HA_ONLINE, T_BINARY
from .entity import TecomatEntity, TecomatStatusEntity

DEVICE_CLASSES = {
    1: BinarySensorDeviceClass.PROBLEM,
    2: BinarySensorDeviceClass.CONNECTIVITY,
    3: BinarySensorDeviceClass.POWER,
    4: BinarySensorDeviceClass.DOOR,
    5: BinarySensorDeviceClass.WINDOW,
    6: BinarySensorDeviceClass.MOTION,
    7: BinarySensorDeviceClass.OPENING,
}


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coord = entry.runtime_data
    entities: list[BinarySensorEntity] = [TecomatBinary(coord, o) for o in coord.desc.objects_of(T_BINARY)]
    entities.append(TecomatHaOnline(coord))
    async_add_entities(entities)


class TecomatBinary(TecomatEntity, BinarySensorEntity):
    def __init__(self, coordinator, obj) -> None:
        super().__init__(coordinator, obj)
        self._attr_device_class = DEVICE_CLASSES.get(obj.p2)
        if self._attr_device_class == BinarySensorDeviceClass.PROBLEM:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool | None:
        v = self.coordinator.get(self.obj.addr)
        if v is None:
            return None
        bit = bool((v >> (self.obj.p1 & 15)) & 1)
        return bit != bool(self.obj.flags & 1)


class TecomatHaOnline(TecomatStatusEntity, BinarySensorEntity):
    """PLC potvrzuje, že od HA dostává heartbeat (při výpadku přejde PLC do záložního režimu)."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "ha_online", "Spojení s HA (z pohledu PLC)")

    @property
    def is_on(self) -> bool | None:
        v = self.coordinator.status(S_HA_ONLINE)
        return None if v is None else v == 1
