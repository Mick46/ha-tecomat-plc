"""Společný základ entit."""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import TecomatCoordinator
from .descriptor import PlcObject


class TecomatEntity(CoordinatorEntity[TecomatCoordinator]):
    """Entita navázaná na objekt z popisu PLC. unique_id = uid objektu (stabilní mezi PLC)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TecomatCoordinator, obj: PlcObject, suffix: str = "") -> None:
        super().__init__(coordinator)
        self.obj = obj
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{obj.uid}{suffix}"
        self._attr_name = obj.name
        self._attr_device_info = coordinator.device_info(obj.group)
        self._attr_extra_state_attributes = {"plc_uid": obj.uid, "plc_address": obj.addr}


class TecomatStatusEntity(CoordinatorEntity[TecomatCoordinator]):
    """Diagnostická entita PLC (stavový blok), patří k zařízení skupiny 0."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: TecomatCoordinator, key: str, name: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_status_{key}"
        self._attr_name = name
        self._attr_device_info = coordinator.device_info(0)
