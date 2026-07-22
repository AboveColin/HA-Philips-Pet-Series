# Philips Pet Series — Home Assistant Integration

A custom [Home Assistant](https://www.home-assistant.io/) integration for
**Philips Pet Series** smart pet feeders (PAW-series, e.g. PAW5320). It lets you
feed on demand, manage the feeding schedule, adjust the built-in camera, and
monitor the device — all from Home Assistant.

The integration signs in with your Philips / home.id account and talks to the
same backend the official app uses. Device control, sensors, motion snapshots,
and live camera video all work from that login with no extra services or camera
credentials.

## Features

- **Feeding** — feed-now button, portion size, automatic-feed portions, and a
  meal-schedule **calendar**.
- **Camera settings** — privacy mode, night vision, motion detection, image
  flip, on-screen display, anti-flicker, siren, and volume.
- **Camera** — live HEVC video and downstream audio through the bundled pure-Go
  Tuya P2P bridge, with the latest cloud motion snapshot as the still image.
- **Monitoring** — device online/offline, cloud connectivity, food-level and
  feeding-fault sensors, filter-replacement reminder, and Wi-Fi / MCU firmware
  versions.
- **Notifications** — recent device events (motion, meals, faults) exposed as
  sensors, plus a motion push-notification toggle.

## Requirements

- A recent version of Home Assistant with [HACS](https://hacs.xyz/) (for the
  recommended install).
- A Philips Pet Series feeder already registered to a Philips / home.id account.
  If it isn't registered yet, do so in the Philips Pet Series app or via the
  [Philips Home Support](https://www.home.id/support) page first.

## Installation

### HACS (recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed.
2. In HACS, open the three-dot menu → **Custom repositories**, add
   `https://github.com/abovecolin/HA-Philips-Pet-Series`, and choose the
   **Integration** category.
3. Search for **Philips Pet Series** in HACS and install it.
4. Restart Home Assistant.

### Manual

Copy `custom_components/philips_pet_series` into your Home Assistant
`config/custom_components/` directory and restart.

## Setup

Setup is a simple email login — no browser cookies, token copying, or Android
device required.

1. Go to **Settings → Devices & Services → Add Integration** and search for
   **Philips Pet Series**.
2. Enter the email address of your Philips / home.id account.
3. Philips emails you a one-time code. Enter it in Home Assistant.

All Philips homes and supported devices on the account are added automatically.

Tokens are then stored and refreshed automatically — you won't normally need to
sign in again. If the login ever expires, Home Assistant shows a
**Reconfigure** prompt that repeats the same email-code step.

## Device control — works out of the box

Camera settings, the feed command, portion size, and all the Tuya-backed sensors
work with **nothing beyond the normal email login**. They ride on Tuya's cloud
API, and the request signing (`thing_security`) is reimplemented in pure Python
inside the `petsseries` package — so there is **no external signer service, no
qemu, and no native libraries** to install, and no local key to extract. This is
handled automatically for every installation.

## Camera

The feeder uses Tuya's proprietary encrypted P2P media transport rather than a
normal camera URL. This integration includes a pure-Go bridge for Linux amd64
and arm64 Home Assistant installations. It starts and supervises the correct
bridge automatically, obtains short-lived WebRTC/MQTT credentials from the
existing Philips login over a protected loopback connection, and exposes the
result through the normal Home Assistant camera entity.

No RTSP URL, Tuya device ID, IP address, local key, external signer, qemu
process, add-on, or system service is required. The camera entity also serves
the latest cloud motion snapshot when Home Assistant requests a still image.

## Contributing

Contributions are welcome — please open an issue or pull request on the
[GitHub repository](https://github.com/abovecolin/HA-Philips-Pet-Series).

## License

Released under the MIT License.
