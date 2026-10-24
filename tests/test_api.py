"""Tests for the Divoom Local API client against fake devices."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import aiohttp
import pytest
from aiohttp import web

# Load api.py directly so tests do not need Home Assistant installed.
_API = pathlib.Path(__file__).parents[1] / "custom_components/divoom_local/api.py"
_spec = importlib.util.spec_from_file_location("divoom_api", _API)
api = importlib.util.module_from_spec(_spec)
sys.modules["divoom_api"] = api
_spec.loader.exec_module(api)

TOKEN = 123456


class FakeDevice:
    """Speaks either the TimesFrame or the Times Gate dialect."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.on = 1
        self.brightness = 60
        self.calls: list[tuple[str, dict]] = []
        self.override = None

    async def handle(self, request: web.Request) -> web.Response:
        body = await request.json()
        self.calls.append((request.method, body))
        if self.override is not None:
            if isinstance(self.override, str):
                return web.Response(text=self.override)
            return web.json_response(self.override)

        if self.model == "times_gate" and body.get("LocalToken") != TOKEN:
            return web.json_response({"error_code": "DeviceToken is err"})

        cmd = body["Command"]
        ok = {"error_code": 0} if self.model == "times_gate" else {"ReturnCode": 0}
        if cmd == "Channel/GetClockInfo" and self.model == "timesframe":
            return web.json_response({**ok, "Brightness": self.brightness, "DeviceId": 300123})
        if cmd == "Channel/GetOnOffScreen" and self.model == "timesframe":
            return web.json_response({**ok, "OnOff": self.on})
        if cmd == "Channel/GetAllConf" and self.model == "times_gate":
            return web.json_response(
                {**ok, "Brightness": self.brightness, "LightSwitch": self.on}
            )
        if cmd == "Channel/OnOffScreen":
            self.on = body["OnOff"]
        elif cmd == "Channel/SetBrightness":
            self.brightness = body["Brightness"]
        return web.json_response(ok)


async def _serve(model: str, path: str):
    fake = FakeDevice(model)
    app = web.Application()
    app.router.add_route("*", path, fake.handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return fake, runner, site._server.sockets[0].getsockname()[1]


@pytest.fixture
async def frame():
    fake, runner, port = await _serve("timesframe", "/divoom_api")
    async with aiohttp.ClientSession() as session:
        yield fake, api.TimesFrameClient(session, "127.0.0.1", port)
    await runner.cleanup()


@pytest.fixture
async def gate():
    """Times Gate rev 402 shape (9000/divoom_api) so the test can pick the port."""
    fake, runner, port = await _serve("times_gate", "/post")
    async with aiohttp.ClientSession() as session:
        client = api.TimesGateClient(session, "127.0.0.1", TOKEN, 400)
        client._url = f"http://127.0.0.1:{port}/post"  # rev 400 uses port 80
        yield fake, client
    await runner.cleanup()


# TimesFrame


async def test_frame_state_and_wire_format(frame):
    fake, client = frame
    assert await client.get_state() == api.DisplayState(True, 60, "300123")
    assert all(m == "GET" for m, _ in fake.calls)
    assert all("LocalToken" not in b for _, b in fake.calls)


async def test_frame_controls(frame):
    fake, client = frame
    await client.set_power(False)
    await client.set_brightness(25)
    assert fake.calls[-2][1] == {"Command": "Channel/OnOffScreen", "OnOff": 0}
    assert fake.calls[-1][1] == {"Command": "Channel/SetBrightness", "Brightness": 25}
    assert await client.get_state() == api.DisplayState(False, 25, "300123")


async def test_frame_reboot(frame):
    fake, client = frame
    await client.reboot()
    assert fake.calls[-1][1] == {"Command": "Device/SysReboot"}


# Times Gate


async def test_gate_state_and_wire_format(gate):
    fake, client = gate
    assert await client.get_state() == api.DisplayState(True, 60, None)
    method, body = fake.calls[-1]
    assert method == "POST"
    assert body == {"Command": "Channel/GetAllConf", "LocalToken": TOKEN}


async def test_gate_controls(gate):
    fake, client = gate
    await client.set_power(False)
    await client.set_brightness(80)
    assert fake.calls[-2][1] == {"Command": "Channel/OnOffScreen", "OnOff": 0, "LocalToken": TOKEN}
    assert fake.calls[-1][1] == {"Command": "Channel/SetBrightness", "Brightness": 80, "LocalToken": TOKEN}
    assert await client.get_state() == api.DisplayState(False, 80, None)


async def test_gate_bad_token(gate):
    _, client = gate
    client._token = 999
    with pytest.raises(api.DivoomAuthError):
        await client.get_state()


async def test_gate_has_no_reboot(gate):
    fake, client = gate
    with pytest.raises(api.DivoomError):
        await client.reboot()
    assert fake.calls == []  # nothing was sent


# Shared behavior


@pytest.mark.parametrize("value", [-1, 101])
async def test_brightness_bounds(frame, value):
    _, client = frame
    with pytest.raises(ValueError):
        await client.set_brightness(value)


@pytest.mark.parametrize(
    "payload",
    [{"ReturnCode": 1}, {"error_code": 5}, ["not", "an", "object"], "<html>"],
)
async def test_bad_responses(frame, payload):
    fake, client = frame
    fake.override = payload
    with pytest.raises(api.DivoomResponseError):
        await client.set_power(True)


async def test_out_of_range_state(gate):
    fake, client = gate
    fake.brightness = 250
    with pytest.raises(api.DivoomResponseError):
        await client.get_state()


async def test_unreachable():
    async with aiohttp.ClientSession() as session:
        client = api.TimesFrameClient(session, "127.0.0.1", 1)
        with pytest.raises(api.DivoomConnectionError):
            await client.get_state()


def test_urls_and_factory():
    tf = api.create_client(None, "timesframe", " 10.0.0.5 ")
    assert tf.url == "http://10.0.0.5:9000/divoom_api"
    assert api.TimesFrameClient(None, "fe80::1").url == "http://[fe80::1]:9000/divoom_api"
    g400 = api.create_client(None, "times_gate", "10.0.0.6", local_token=1)
    g402 = api.create_client(None, "times_gate", "10.0.0.6", local_token=1, revision=402)
    assert g400.url == "http://10.0.0.6/post"
    assert g402.url == "http://10.0.0.6:9000/divoom_api"
    for bad in (
        lambda: api.TimesFrameClient(None, ""),
        lambda: api.TimesFrameClient(None, "10.0.0.5", 70000),
        lambda: api.TimesGateClient(None, "10.0.0.6", 1, 401),
        lambda: api.create_client(None, "pixoo", "10.0.0.7"),
    ):
        with pytest.raises(ValueError):
            bad()


async def test_send_command_frame(frame):
    fake, client = frame
    reply = await client.send_command({"Command": "Channel/GetClockInfo"})
    assert reply["DeviceId"] == 300123
    await client.send_command({"Command": "Device/ExitCustomControlMode"})
    assert fake.calls[-1] == ("GET", {"Command": "Device/ExitCustomControlMode"})


async def test_send_command_gate_adds_token_and_ignores_callers(gate):
    fake, client = gate
    await client.send_command({"Command": "Channel/GetAllConf", "LocalToken": 1})
    assert fake.calls[-1][1] == {"Command": "Channel/GetAllConf", "LocalToken": TOKEN}


@pytest.mark.parametrize("payload", [{}, {"Command": ""}, {"Command": 5}, ["x"]])
async def test_send_command_rejects_bad_payload(frame, payload):
    fake, client = frame
    with pytest.raises(ValueError):
        await client.send_command(payload)
    assert fake.calls == []
