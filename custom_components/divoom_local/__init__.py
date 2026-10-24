"""Divoom Local: control Divoom TimesFrame and Times Gate over the LAN only."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import DisplayState, DivoomAuthError, DivoomClient, DivoomError, create_client
from .const import (
    CONF_LOCAL_TOKEN,
    CONF_MODEL,
    CONF_REVISION,
    DOMAIN,
    PLATFORMS,
    SCAN_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


def client_from_data(hass: HomeAssistant, data: dict) -> DivoomClient:
    opts = {k: data[k] for k in (CONF_PORT, CONF_LOCAL_TOKEN, CONF_REVISION) if k in data}
    return create_client(
        async_get_clientsession(hass), data[CONF_MODEL], data[CONF_HOST], **opts
    )


class DivoomCoordinator(DataUpdateCoordinator[DisplayState]):
    """Polls the display for power and brightness."""

    def __init__(self, hass: HomeAssistant, client: DivoomClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.client = client

    async def _async_update_data(self) -> DisplayState:
        try:
            return await self.client.get_state()
        except DivoomAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except DivoomError as err:
            raise UpdateFailed(str(err)) from err


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = DivoomCoordinator(hass, client_from_data(hass, dict(entry.data)))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
