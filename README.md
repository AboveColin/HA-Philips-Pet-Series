# Philips Pet Series for Home Assistant

Bring your **Philips Pet Series** smart feeder into
[Home Assistant](https://www.home-assistant.io/). Feed the cat from a dashboard
button, use the meal schedule in your automations, watch the live camera, and
get told when the food is running low.

Signing in takes an email address and a code. That is the whole setup. The
feeder, its sensors and the camera video are all configured for you.

## What you can do with it

**Feeding.** A feed-now button, portion size, the portion used for scheduled
meals, and the full meal schedule as a Home Assistant calendar. You can read the
next meal from an automation, or dispense a portion when you are out and running
late.

**The camera.** Live video and audio, plus the most recent motion snapshot as
the still image. It works straight away. There is no camera URL to hunt down and
nothing to copy across from another app.

**Camera settings.** Privacy mode, night vision, motion detection, image flip,
on-screen display, anti-flicker, siren and volume.

**Knowing what is going on.** Online and offline status, food level, feeding
faults, the filter-replacement reminder, and firmware versions. Recent events
such as motion, meals and faults arrive as sensors you can trigger automations
from.

## Supported devices

Philips Pet Series feeders in the PAW range, including the **PAW5320** smart
feeder with camera. Feeders without a camera work too. You simply get the
feeding and sensor side.

If you have a Pet Series device that is not picked up, please
[open an issue](https://github.com/AboveColin/HA-Philips-Pet-Series/issues) and
say which model you have. Adding one is usually a small change.

## Before you start

You need Home Assistant with [HACS](https://hacs.xyz/) installed, and your
feeder already set up in the Philips Pet Series app on a Philips or home.id
account. If it is not paired yet, do that in the app first.

## Installing

The integration is in the default HACS store, so there is no custom repository
to add.

1. Open **HACS** in Home Assistant.
2. Search for **Philips Pet Series**.
3. Select it, choose **Download**, then restart Home Assistant.

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=AboveColin&repository=HA-Philips-Pet-Series&category=integration)

If you would rather do it by hand, copy `custom_components/philips_pet_series`
into your Home Assistant `config/custom_components/` directory and restart.

## Signing in

1. Go to **Settings**, then **Devices & Services**, then **Add Integration**,
   and search for **Philips Pet Series**.
2. Enter the email address of your Philips or home.id account.
3. Philips emails you a one-time code. Type it in.

Every home and supported device on the account is added automatically. Your
login is kept fresh in the background, so you should not need to do this again.
If it ever does expire, Home Assistant shows a **Reconfigure** prompt that asks
for a new code.

## A note about the camera

The feeder only allows a couple of camera connections at once, and holding one
open permanently can push the Philips app off. So by default the integration
connects only while something is actually watching, and lets go afterwards.

That suits normal dashboard use. If you want a recorder pulling the stream
around the clock, switch **Camera streaming** to **Always on** in the
integration options, and expect the phone app to lose live view while it runs.

Recording in Frigate, go2rtc or a similar NVR is covered in
**[docs/nvr.md](docs/nvr.md)**, including which settings to change first and
what each option costs you in CPU.

## Documentation

Full guides covering installation, day to day use, every entity, automation
examples and troubleshooting live in the
**[wiki](https://github.com/AboveColin/HA-Philips-Pet-Series/wiki)**.

## Getting help

Something not working, or a device not recognised? Open an
[issue](https://github.com/AboveColin/HA-Philips-Pet-Series/issues). For
questions, ideas and showing off what you have automated, there is
[Discussions](https://github.com/AboveColin/HA-Philips-Pet-Series/discussions).

This is an independent community project. It is not made, backed or supported by
Philips or Versuni.

## Contributing

Pull requests are welcome. If you are planning something substantial, open an
issue first so we can talk it through.

## License

MIT.
