"""Config flow, light and button tests inside a real Home Assistant instance."""

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.divoom_local.api import (
    DisplayState,
    DivoomAuthError,
    DivoomConnectionError,
)
from custom_components.divoom_local.const import DOMAIN

GET_STATE = "custom_components.divoom_local.api.{}.get_state"


async def _start(hass, model):
    r = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(r["flow_id"], {"model": model})


async def test_timesframe_flow(hass):
    r = await _start(hass, "timesframe")
    assert r["step_id"] == "timesframe"
    with patch(GET_STATE.format("TimesFrameClient"),
               AsyncMock(return_value=DisplayState(True, 50, "300123"))):
        r = await hass.config_entries.flow.async_configure(
            r["flow_id"], {"host": "10.69.5.60", "port": 9000})
        await hass.async_block_till_done()
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert r["data"] == {"host": "10.69.5.60", "port": 9000, "model": "timesframe"}
    assert r["result"].unique_id == "300123"
    # entities came up
    assert hass.states.get("light.timesframe_display").state == "on"
    assert hass.states.get("button.timesframe_restart") is not None


async def test_times_gate_flow_and_bad_token(hass):
    r = await _start(hass, "times_gate")
    assert r["step_id"] == "times_gate"
    with patch(GET_STATE.format("TimesGateClient"), AsyncMock(side_effect=DivoomAuthError)):
        r = await hass.config_entries.flow.async_configure(
            r["flow_id"], {"host": "10.69.5.113", "local_token": 1, "revision": "400"})
    assert r["errors"] == {"base": "invalid_auth"}
    with patch(GET_STATE.format("TimesGateClient"),
               AsyncMock(return_value=DisplayState(False, 70, None))):
        r = await hass.config_entries.flow.async_configure(
            r["flow_id"], {"host": "10.69.5.113", "local_token": 42, "revision": "402"})
        await hass.async_block_till_done()
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert r["data"]["revision"] == 402 and r["data"]["local_token"] == 42
    assert hass.states.get("light.times_gate_display").state == "off"
    # no reboot button for the Times Gate
    assert hass.states.get("button.times_gate_restart") is None


async def test_cannot_connect(hass):
    r = await _start(hass, "timesframe")
    with patch(GET_STATE.format("TimesFrameClient"), AsyncMock(side_effect=DivoomConnectionError)):
        r = await hass.config_entries.flow.async_configure(
            r["flow_id"], {"host": "10.0.0.9", "port": 9000})
    assert r["errors"] == {"base": "cannot_connect"}


async def test_light_commands(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="300123",
                            data={"host": "10.69.5.60", "port": 9000, "model": "timesframe"})
    entry.add_to_hass(hass)
    base = "custom_components.divoom_local.api.TimesFrameClient."
    with patch(base + "get_state", AsyncMock(return_value=DisplayState(False, 50, "300123"))), \
         patch(base + "set_power", AsyncMock()) as power, \
         patch(base + "set_brightness", AsyncMock()) as bri:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        await hass.services.async_call("light", "turn_on",
            {"entity_id": "light.timesframe_display", "brightness": 128}, blocking=True)
        bri.assert_awaited_with(50)
        power.assert_awaited_with(True)
        await hass.services.async_call("light", "turn_off",
            {"entity_id": "light.timesframe_display"}, blocking=True)
        power.assert_awaited_with(False)


async def test_bad_token_at_runtime_starts_reauth(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="tg",
        data={"host": "10.69.5.113", "local_token": 1, "revision": 400, "model": "times_gate"})
    entry.add_to_hass(hass)
    with patch(GET_STATE.format("TimesGateClient"), AsyncMock(side_effect=DivoomAuthError)):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)
