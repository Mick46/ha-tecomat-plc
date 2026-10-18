"""Volby uložené v PLC (typ SELECT): režim topení, režim teplé vody, filtrace bazénu."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import F_PARAM_ENTITY, F_READONLY, PARAM_INDEX_BASE, T_SELECT
from .entity import TecomatEntity
from .modbus_client import ModbusError

ICONS = {"režim": "mdi:tune-variant", "filtrace": "mdi:pool"}


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coord = entry.runtime_data
    async_add_entities(
        TecomatSelect(coord, o)
        for o in coord.desc.objects_of(T_SELECT)
        if o.flags & F_PARAM_ENTITY and not o.flags & F_READONLY
    )


class TecomatSelect(TecomatEntity, SelectEntity):
    """Volba = parametr v PLC (index volby). Zápis přes schránku, PLC ji uloží (RETAIN)."""

    def __init__(self, coordinator, obj) -> None:
        super().__init__(coordinator, obj)
        self._attr_options = obj.options
        self._attr_icon = next((i for k, i in ICONS.items() if k in obj.name.lower()), "mdi:form-select")

    @property
    def current_option(self) -> str | None:
        v = self.coordinator.get(self.obj.addr)
        if v is None or v >= len(self.obj.options):
            return None
        return self.obj.options[v]

    async def async_select_option(self, option: str) -> None:
        try:
            await self.coordinator.write_config([(PARAM_INDEX_BASE + self.obj.p3, self.obj.options.index(option))])
        except ModbusError as err:
            raise HomeAssistantError(f"Zápis volby selhal: {err}") from err
