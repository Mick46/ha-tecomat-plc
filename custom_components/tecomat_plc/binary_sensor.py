"""Binární vstupy (typ BINARY) a stav spojení HA ↔ PLC."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import F_READONLY, S_HA_ONLINE, T_LIGHT, T_BINARY, T_SWITCH
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
    entities += [
        TecomatOutputState(coord, o) for o in coord.desc.objects_of(T_LIGHT, T_SWITCH) if o.flags & F_READONLY
    ]
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


# protokol 2: podtyp výstupu -> ikona (stejné jako switch.py)
ICONS = {4: "mdi:pump", 5: "mdi:fan", 7: "mdi:water-boiler", 8: "mdi:water-thermometer", 9: "mdi:power-plug"}


class TecomatOutputState(TecomatEntity, BinarySensorEntity):
    """Výstup, který řídí logika PLC (kotel, ohřev vody, čerpadla …): v HA jen stav."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator, obj) -> None:
        super().__init__(coordinator, obj)
        if obj.p2 in ICONS:
            self._attr_icon = ICONS[obj.p2]

    @property
    def is_on(self) -> bool | None:
        v = self.coordinator.get(self.obj.addr)
        return None if v is None else v != 0


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
