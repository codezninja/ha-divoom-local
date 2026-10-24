"""Display as a light: on/off plus brightness."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import DivoomError
from .entity import DivoomEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([DivoomDisplay(entry.runtime_data, entry.entry_id)])


def to_device(ha_brightness: int) -> int:
    """HA 1..255 to frame 1..100 (never 0, so turn_on with low brightness stays visible)."""
    return max(1, min(100, round(ha_brightness * 100 / 255)))


def to_ha(device_brightness: int) -> int:
    return max(0, min(255, round(device_brightness * 255 / 100)))


class DivoomDisplay(DivoomEntity, LightEntity):
    _attr_translation_key = "display"
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "display")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.is_on

    @property
    def brightness(self) -> int:
        return to_ha(self.coordinator.data.brightness)

    async def async_turn_on(self, **kwargs: Any) -> None:
        client = self.coordinator.client
        try:
            if ATTR_BRIGHTNESS in kwargs:
                await client.set_brightness(to_device(kwargs[ATTR_BRIGHTNESS]))
            if not self.is_on:
                await client.set_power(True)
        except DivoomError as err:
            raise HomeAssistantError(f"Divoom command failed: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.client.set_power(False)
        except DivoomError as err:
            raise HomeAssistantError(f"Divoom command failed: {err}") from err
        await self.coordinator.async_request_refresh()
