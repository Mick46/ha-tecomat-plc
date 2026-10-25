"""Teploty (typ TEMP), měřené hodnoty (typ VALUE) a diagnostika PLC."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import (
    LIGHT_LUX,
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPressure,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import F_READONLY, F_VALUE_DIAG, S_CFG_CHECKSUM, S_HB_OUT, T_SELECT, T_TEMP, T_TEXT, T_VALUE
from .entity import TecomatEntity, TecomatStatusEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coord = entry.runtime_data
    entities: list[SensorEntity] = []
    for o in coord.desc.objects_of(T_TEMP):
        entities.append(TecomatTemp(coord, o, offset=1, suffix=""))
        entities.append(TecomatTemp(coord, o, offset=0, suffix="_raw"))
    entities.extend(TecomatValue(coord, o) for o in coord.desc.objects_of(T_VALUE))
    entities.extend(TecomatState(coord, o) for o in coord.desc.objects_of(T_SELECT) if o.flags & F_READONLY)
    entities.extend(TecomatText(coord, o) for o in coord.desc.objects_of(T_TEXT))
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
        # -999 = neplatná teplota (čidlo vadné nebo PLC po startu ještě nemá data) -> neznámá
        return None if v is None or v <= -999 else v / 10


# kódy jednotek (p2) a tříd (p3) objektu VALUE – stejné čísluje generátor programu PLC
UNITS = {
    1: UnitOfPower.WATT,
    2: UnitOfEnergy.KILO_WATT_HOUR,
    3: PERCENTAGE,
    4: UnitOfTemperature.CELSIUS,
    5: UnitOfElectricPotential.VOLT,
    6: UnitOfElectricCurrent.AMPERE,
    7: LIGHT_LUX,
    8: UnitOfVolume.CUBIC_METERS,
    9: UnitOfTime.SECONDS,
    10: UnitOfTime.MINUTES,
    12: UnitOfTime.DAYS,
    14: UnitOfFrequency.HERTZ,
    15: UnitOfPressure.BAR,
}
CLASSES = {
    1: SensorDeviceClass.POWER,
    2: SensorDeviceClass.ENERGY,
    3: SensorDeviceClass.BATTERY,
    4: SensorDeviceClass.TEMPERATURE,
    5: SensorDeviceClass.VOLTAGE,
    6: SensorDeviceClass.CURRENT,
    7: SensorDeviceClass.ILLUMINANCE,
    8: SensorDeviceClass.GAS,
    9: SensorDeviceClass.DURATION,
    10: SensorDeviceClass.FREQUENCY,
    11: SensorDeviceClass.PRESSURE,
}
TOTALS = {SensorDeviceClass.ENERGY, SensorDeviceClass.GAS}


class TecomatValue(TecomatEntity, SensorEntity):
    """Obecná měřená hodnota: celé číslo z PLC dělené 10^p1."""

    def __init__(self, coordinator, obj) -> None:
        super().__init__(coordinator, obj)
        self._div = 10 ** min(obj.p1, 6)
        self._attr_native_unit_of_measurement = UNITS.get(obj.p2)
        self._attr_device_class = CLASSES.get(obj.p3)
        self._attr_suggested_display_precision = min(obj.p1, 6)
        self._attr_state_class = (
            SensorStateClass.TOTAL_INCREASING
            if self._attr_device_class in TOTALS
            else SensorStateClass.MEASUREMENT
        )
        if obj.flags & F_VALUE_DIAG:
            # okamžitá hodnota, která se mění každou sekundu: jen diagnostika, ve výchozím stavu vypnutá
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
            self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> float | int | None:
        v = self.coordinator.get_value(self.obj.addr, self.obj.flags)
        if v is None:
            return None
        return v / self._div if self._div > 1 else v


class TecomatState(TecomatEntity, SensorEntity):
    """Stav logiky PLC jako výčet (např. kdo řídí topení, režim teplé vody teď)."""

    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, coordinator, obj) -> None:
        super().__init__(coordinator, obj)
        self._attr_options = obj.options

    @property
    def native_value(self) -> str | None:
        v = self.coordinator.get(self.obj.addr)
        if v is None or v >= len(self.obj.options):
            return None
        return self.obj.options[v]


class TecomatText(TecomatEntity, SensorEntity):
    """Text z PLC (např. popis poruchy kotle z knihovny OpenThermLib)."""

    @property
    def native_value(self) -> str | None:
        return self.coordinator.get_text(self.obj.addr) or None


class TecomatStatusSensor(TecomatStatusEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, key: str, name: str, offset: int) -> None:
        super().__init__(coordinator, key, name)
        self._offset = offset

    @property
    def native_value(self) -> int | None:
        return self.coordinator.status(self._offset)
