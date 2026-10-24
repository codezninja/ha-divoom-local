"""Reboot button."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import DivoomError
from .entity import DivoomEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    if coordinator.client.supports_reboot:
        async_add_entities([DivoomReboot(coordinator, entry.entry_id)])


class DivoomReboot(DivoomEntity, ButtonEntity):
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "reboot")

    async def async_press(self) -> None:
        try:
            await self.coordinator.client.reboot()
        except DivoomError as err:
            raise HomeAssistantError(f"Divoom reboot failed: {err}") from err
