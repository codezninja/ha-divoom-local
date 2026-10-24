"""Shared entity base."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DivoomCoordinator
from .api import MODEL_NAMES
from .const import DOMAIN


class DivoomEntity(CoordinatorEntity[DivoomCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: DivoomCoordinator, entry_id: str, key: str) -> None:
        super().__init__(coordinator)
        unique_base = coordinator.config_entry.unique_id or entry_id
        model_name = MODEL_NAMES[coordinator.client.model]
        self._attr_unique_id = f"{unique_base}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_base)},
            name=model_name,
            manufacturer="Divoom",
            model=model_name,
        )
