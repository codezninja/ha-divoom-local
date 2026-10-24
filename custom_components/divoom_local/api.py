"""Minimal local HTTP client for Divoom LCD displays (TimesFrame, Times Gate).

Both devices accept the same control commands but differ in transport:

TimesFrame
    GET http://<host>:9000/divoom_api with a JSON body, no auth.
    State: Channel/GetClockInfo (Brightness, DeviceId) and
    Channel/GetOnOffScreen (OnOff).

Times Gate
    POST http://<host>/post (hardware revision 400) or
    POST http://<host>:9000/divoom_api (revision 402).
    Every request carries an integer LocalToken from the Divoom app.
    State: Channel/GetAllConf (LightSwitch, Brightness).

This module has no Home Assistant imports so it can be tested on its own.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import aiohttp

REQUEST_TIMEOUT = 10


class Model(StrEnum):
    TIMESFRAME = "timesframe"
    TIMES_GATE = "times_gate"


MODEL_NAMES = {Model.TIMESFRAME: "TimesFrame", Model.TIMES_GATE: "Times Gate"}
TIMES_GATE_REVISIONS = (400, 402)


class DivoomError(Exception):
    """Base error."""


class DivoomConnectionError(DivoomError):
    """The device could not be reached."""


class DivoomAuthError(DivoomError):
    """The device rejected the LocalToken."""


class DivoomResponseError(DivoomError):
    """The device returned something unexpected or rejected the command."""


@dataclass(frozen=True)
class DisplayState:
    is_on: bool
    brightness: int  # 0 to 100
    device_id: str | None


def _fmt_host(host: str) -> str:
    host = host.strip()
    if not host:
        raise ValueError("host is required")
    return f"[{host}]" if ":" in host else host


class DivoomClient:
    """Base client. Use one of the model subclasses or ``create_client``."""

    model: Model
    method: str
    supports_reboot = False

    def __init__(self, session: aiohttp.ClientSession, url: str) -> None:
        self._session = session
        self._url = url

    @property
    def url(self) -> str:
        return self._url

    async def get_state(self) -> DisplayState:
        raise NotImplementedError

    async def set_power(self, on: bool) -> None:
        await self._command("Channel/OnOffScreen", {"OnOff": 1 if on else 0})

    async def set_brightness(self, brightness: int) -> None:
        brightness = int(brightness)
        if not 0 <= brightness <= 100:
            raise ValueError("brightness must be 0 to 100")
        await self._command("Channel/SetBrightness", {"Brightness": brightness})

    async def reboot(self) -> None:
        if not self.supports_reboot:
            raise DivoomError(f"reboot is not supported on {self.model}")
        await self._command("Device/SysReboot")

    def _extra_fields(self) -> dict[str, Any]:
        return {}

    async def _command(
        self, command: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload = {"Command": command, **(params or {}), **self._extra_fields()}
        try:
            async with self._session.request(
                self.method,
                self._url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise DivoomConnectionError(f"{command} failed: {err}") from err
        except ValueError as err:
            raise DivoomResponseError(f"{command} returned invalid JSON") from err

        if not isinstance(data, dict):
            raise DivoomResponseError(f"{command} did not return an object")
        for key in ("error_code", "ReturnCode"):
            code = data.get(key)
            if code is None or str(code) == "0":
                continue
            if "token" in str(code).lower():
                raise DivoomAuthError(f"{command} rejected: {code}")
            raise DivoomResponseError(f"{command} failed with {key}={code}")
        return data

    @staticmethod
    def _validate(on: Any, brightness: Any, device_id: Any) -> DisplayState:
        try:
            on_i, bri_i = int(on), int(brightness)
        except (TypeError, ValueError) as err:
            raise DivoomResponseError("missing power or brightness") from err
        if on_i not in (0, 1) or not 0 <= bri_i <= 100:
            raise DivoomResponseError("power or brightness out of range")
        return DisplayState(
            bool(on_i), bri_i, str(device_id) if device_id is not None else None
        )


class TimesFrameClient(DivoomClient):
    model = Model.TIMESFRAME
    method = "GET"
    supports_reboot = True

    def __init__(
        self, session: aiohttp.ClientSession, host: str, port: int = 9000
    ) -> None:
        if not 1 <= int(port) <= 65535:
            raise ValueError("port out of range")
        super().__init__(session, f"http://{_fmt_host(host)}:{int(port)}/divoom_api")

    async def get_state(self) -> DisplayState:
        clock = await self._command("Channel/GetClockInfo")
        screen = await self._command("Channel/GetOnOffScreen")
        return self._validate(
            screen.get("OnOff"),
            clock.get("Brightness"),
            clock.get("DeviceId", clock.get("DeviceID")),
        )


class TimesGateClient(DivoomClient):
    model = Model.TIMES_GATE
    method = "POST"

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        local_token: int,
        revision: int = 400,
    ) -> None:
        if int(revision) not in TIMES_GATE_REVISIONS:
            raise ValueError("revision must be 400 or 402")
        h = _fmt_host(host)
        url = f"http://{h}:9000/divoom_api" if int(revision) == 402 else f"http://{h}/post"
        super().__init__(session, url)
        self._token = int(local_token)

    def _extra_fields(self) -> dict[str, Any]:
        return {"LocalToken": self._token}

    async def get_state(self) -> DisplayState:
        conf = await self._command("Channel/GetAllConf")
        return self._validate(
            conf.get("LightSwitch"),
            conf.get("Brightness"),
            conf.get("DeviceId", conf.get("DeviceID")),
        )


def create_client(
    session: aiohttp.ClientSession, model: str, host: str, **opts: Any
) -> DivoomClient:
    if model == Model.TIMESFRAME:
        return TimesFrameClient(session, host, opts.get("port", 9000))
    if model == Model.TIMES_GATE:
        return TimesGateClient(
            session, host, opts["local_token"], opts.get("revision", 400)
        )
    raise ValueError(f"unknown model {model!r}")
