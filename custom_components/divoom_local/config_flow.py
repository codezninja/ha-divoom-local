"""Config flow: pick the model, then enter its connection details."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from . import client_from_data
from .api import (
    MODEL_NAMES,
    DivoomAuthError,
    DivoomConnectionError,
    DivoomError,
    Model,
)
from .const import CONF_LOCAL_TOKEN, CONF_MODEL, CONF_REVISION, DOMAIN

MODEL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MODEL): SelectSelector(
            SelectSelectorConfig(
                options=[m.value for m in Model],
                translation_key="model",
                mode=SelectSelectorMode.LIST,
            )
        )
    }
)

TIMESFRAME_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=9000): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
    }
)

TIMES_GATE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_LOCAL_TOKEN): vol.Coerce(int),
        vol.Required(CONF_REVISION, default="400"): SelectSelector(
            SelectSelectorConfig(options=["400", "402"], mode=SelectSelectorMode.DROPDOWN)
        ),
    }
)

TOKEN_SCHEMA = vol.Schema({vol.Required(CONF_LOCAL_TOKEN): vol.Coerce(int)})


class DivoomLocalConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await (
                self.async_step_timesframe()
                if user_input[CONF_MODEL] == Model.TIMESFRAME
                else self.async_step_times_gate()
            )
        return self.async_show_form(step_id="user", data_schema=MODEL_SCHEMA)

    async def async_step_timesframe(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._connect_step(
            "timesframe", TIMESFRAME_SCHEMA, Model.TIMESFRAME, user_input
        )

    async def async_step_times_gate(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            user_input = {**user_input, CONF_REVISION: int(user_input[CONF_REVISION])}
        return await self._connect_step(
            "times_gate", TIMES_GATE_SCHEMA, Model.TIMES_GATE, user_input
        )

    async def _connect_step(
        self,
        step_id: str,
        schema: vol.Schema,
        model: Model,
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**user_input, CONF_HOST: user_input[CONF_HOST].strip(), CONF_MODEL: model}
            try:
                state = await client_from_data(self.hass, data).get_state()
            except DivoomAuthError:
                errors["base"] = "invalid_auth"
            except DivoomConnectionError:
                errors["base"] = "cannot_connect"
            except DivoomError:
                errors["base"] = "invalid_response"
            else:
                # Prefer the device's own id so an IP change updates the entry
                # instead of creating a duplicate.
                await self.async_set_unique_id(
                    state.device_id or f"{model}:{data[CONF_HOST]}"
                )
                self._abort_if_unique_id_configured(updates=data)
                return self.async_create_entry(
                    title=f"{MODEL_NAMES[model]} ({data[CONF_HOST]})", data=data
                )
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(schema, user_input or {}),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Times Gate only: ask for a new LocalToken after re pairing."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            data = {**entry.data, CONF_LOCAL_TOKEN: user_input[CONF_LOCAL_TOKEN]}
            try:
                await client_from_data(self.hass, data).get_state()
            except DivoomAuthError:
                errors["base"] = "invalid_auth"
            except DivoomConnectionError:
                errors["base"] = "cannot_connect"
            except DivoomError:
                errors["base"] = "invalid_response"
            else:
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=TOKEN_SCHEMA, errors=errors
        )
