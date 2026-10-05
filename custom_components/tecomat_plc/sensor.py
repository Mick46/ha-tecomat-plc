"""Teploty (typ TEMP) a diagnostika PLC."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import S_CFG_CHECKSUM, S_HB_OUT, T_TEMP
from .entity import TecomatEntity, TecomatStatusEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coord = entry.runtime_data
    entities: list[SensorEntity] = []
    for o in coord.desc.objects_of(T_TEMP):
        entities.append(TecomatTemp(coord, o, offset=1, suffix=""))
        entities.append(TecomatTemp(coord, o, offset=0, suffix="_raw"))
    entities.append(TecomatStatusSensor(coord, "heartbeat", "Heartbeat PLC", S_HB_OUT))
    entities.append(TecomatStatusSensor(coord, "checksum", "Kontrolní součet konfigurace", S_CFG_CHECKSUM))
    async_add_entities(entities)


class TecomatTemp(TecomatEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, obj, offset: int, suffix: str) -> None:
        super().__init__(coordinator, obj, suffix)
        self._offset = offset
        if offset == 0:
            # surová hodnota bez korekce: jen diagnostika, ve výchozím stavu vypnutá
            self._attr_name = f"{obj.name} (bez korekce)"
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> float | None:
        v = self.coordinator.get_signed(self.obj.addr + self._offset)
        return None if v is None else v / 10


class TecomatStatusSensor(TecomatStatusEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, key: str, name: str, offset: int) -> None:
        super().__init__(coordinator, key, name)
        self._offset = offset

    @property
    def native_value(self) -> int | None:
        return self.coordinator.status(self._offset)
