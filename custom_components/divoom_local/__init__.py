"""Divoom Local: control Divoom TimesFrame and Times Gate over the LAN only."""

from __future__ import annotations

from datetime import timedelta
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv
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


CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required("config_entry_id"): cv.string,
        vol.Required("payload"): dict,
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the send_command action once for the whole integration."""

    async def send_command(call: ServiceCall) -> ServiceResponse:
        entry = hass.config_entries.async_get_entry(call.data["config_entry_id"])
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError("Unknown Divoom Local config entry")
        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(f"{entry.title} is not loaded")
        coordinator: DivoomCoordinator = entry.runtime_data
        try:
            reply = await coordinator.client.send_command(call.data["payload"])
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        except DivoomError as err:
            raise HomeAssistantError(f"{entry.title}: {err}") from err
        await coordinator.async_request_refresh()
        return reply

    hass.services.async_register(
        DOMAIN,
        "send_command",
        send_command,
        schema=SEND_COMMAND_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = DivoomCoordinator(hass, client_from_data(hass, dict(entry.data)))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
