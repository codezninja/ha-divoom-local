# Divoom Local

A small Home Assistant integration for Divoom LCD displays that talks to them over your LAN only.

Supported: **TimesFrame** and **Times Gate**.

* No Divoom cloud calls and no account
* No third party Python dependencies (uses Home Assistant's own `aiohttp` session)
* About 450 lines of code you can read in one sitting

## Entities

| Entity | Type | TimesFrame | Times Gate |
| --- | --- | --- | --- |
| Display | `light` | on/off, brightness | on/off, brightness |
| Restart | `button` | yes | not exposed (no confirmed reboot command) |

State is polled every 30 seconds and refreshed right after any command.

## Install

1. HACS, then the menu, then **Custom repositories**. Add `https://github.com/codezninja/ha-divoom-local` as an **Integration**.
2. Download **Divoom Local** and restart Home Assistant.
3. Settings, Devices & services, **Add integration**, **Divoom Local**, then pick your device.

**TimesFrame:** enter the IP. Port defaults to `9000`.

**Times Gate:** enter the IP, the **LocalToken** (Divoom app, device settings) and the hardware revision (`400` for the original model, `402` for the newer one). If you re pair the device and the token changes, Home Assistant prompts you for the new one.

Give each device a DHCP reservation. Re adding a device at a new IP updates the existing entry when the device reports its own id.

## How it talks to the devices

| | TimesFrame | Times Gate |
| --- | --- | --- |
| Endpoint | `GET http://<ip>:9000/divoom_api` | `POST http://<ip>/post` (rev 400) or `POST http://<ip>:9000/divoom_api` (rev 402) |
| Auth | none | `LocalToken` added to every request |
| Read state | `Channel/GetClockInfo` (`Brightness`, `DeviceId`) and `Channel/GetOnOffScreen` (`OnOff`) | `Channel/GetAllConf` (`LightSwitch`, `Brightness`) |
| Power | `Channel/OnOffScreen` with `OnOff` 0 or 1 | same |
| Brightness | `Channel/SetBrightness` with `Brightness` 0 to 100 | same |
| Reboot | `Device/SysReboot` | not used |

The request bodies are JSON. Divoom's own docs live at docin.divoom-gz.com; the transport details above match what the community TimesFrame and Times Gate projects observed on real hardware.

## Advanced: send_command

`divoom_local.send_command` sends any command object to a device and returns its reply. The integration adds transport details itself (GET vs POST, the Times Gate LocalToken).

```yaml
action: divoom_local.send_command
data:
  config_entry_id: <your entry id>
  payload:
    Command: Channel/GetClockInfo
response_variable: reply
```

Use it for features this integration does not wrap yet, such as TimesFrame custom layouts (`Device/EnterCustomControlMode`, then `Device/ExitCustomControlMode` plus `Channel/SetClockSelectId` to restore the previous face).

## Security notes

The TimesFrame API has no authentication, and the Times Gate LocalToken is a static number. Anything that can reach these devices can control them. Keep them on a trusted network or VLAN and never forward their ports.

## Development

```
pip install -r requirements_test.txt
pytest                      # API client against fake devices, no Home Assistant needed

pip install -r requirements_test_ha.txt
pytest tests_ha -o asyncio_mode=auto   # config flow and entities inside Home Assistant
```

## License

MIT
