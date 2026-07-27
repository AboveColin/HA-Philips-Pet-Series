# Recording the feeder camera (Frigate, go2rtc, Scrypted)

Your feeder's camera can be recorded by a video recorder such as Frigate, the
same way an ordinary security camera would be. The integration does the hard
part: it turns the feeder's camera into a normal camera stream that any recorder
can read.

This page uses Frigate as the example, because it is the most common. The same
ideas apply to other recorders.

---

## Step 1: two settings to change first

### In Home Assistant: set camera streaming to "Always on"

Go to **Settings → Devices & services → Philips Pet Series → Configure** and set
**Camera streaming** to **Always on**.

Normally the integration only connects to the camera while you are actually
looking at it, and disconnects afterwards. That is on purpose: the feeder only
allows a couple of connections at the same time, and keeping one open can knock
the Philips phone app offline. A recorder needs the camera available all day, so
it needs this setting.

### In Frigate: turn on "Preload camera stream"

In Frigate, open the camera's settings and enable **Preload camera stream**.

Without it, Frigate only asks for the picture when it needs it, and then has to
wait for the connection to the camera to be built up from scratch, which often
takes longer than Frigate is willing to wait, so it gives up and tries again.
Preloading keeps the connection ready, so there is never a wait.

---

## Step 2: find your camera's address

The address looks like this:

```
rtsp://<your-home-assistant-ip>:8560/philips-pet-<device-id>
```

You need to fill in two things:

- **your Home Assistant IP address**: the address you use to open Home
  Assistant, without the port
- **your feeder's device id**: enable the **LAN address** entity on the feeder's
  device page to see it, or switch on debug logging for
  `custom_components.philips_pet_series` and look in the log

### An example

Imagine your home network looks like this (these are made-up numbers):

| | Address |
|---|---|
| Home Assistant | `192.168.1.10` |
| Frigate | `192.168.1.20` |
| The feeder itself | `192.168.1.55` |
| The feeder's device id | `01ab2cd3ef4gh5ij6kl7mn8op9` |

Then your camera address is:

```
rtsp://192.168.1.10:8560/philips-pet-01ab2cd3ef4gh5ij6kl7mn8op9
```

Two things worth knowing:

- **You never use the feeder's own address** (`192.168.1.55`). The camera does not
  hand out video by itself. Everything goes through Home Assistant.
- **You never use Frigate's address either** (`192.168.1.20`). Frigate does not
  need to refer to itself.

> ### Easy mistakes to avoid
>
> Writing `127.0.0.1:8560` instead of Home Assistant's real address.
>
> `127.0.0.1` means "this machine". When Frigate reads it, it looks inside
> **itself**, but the camera connection lives inside **Home Assistant**, so
> Frigate finds nothing and reports *connection refused*.
>
> This is true even if Frigate runs as a Home Assistant add-on: the add-on is
> still separate from Home Assistant itself.
>
> Confusingly, the `127.0.0.1:8554` further down in the config **is** correct.
> That one points at a part of Frigate, so "this machine" is right there.

---

## Step 3: pick one of these two configurations

Both are complete. Copy one into your Frigate configuration and replace
`<your-home-assistant-ip>` and `<device-id>` with your own values.

### Option A: recording only (recommended)

Choose this if you want the feeder recorded and shown in Frigate, and you are
happy to watch it in the Frigate app or Home Assistant rather than needing it to
play in every web browser. It is **by far** the lighter option. See
[why](#why-these-settings) below.

```yaml
go2rtc:
  streams:
    feeder:
      - "rtsp://<your-home-assistant-ip>:8560/philips-pet-<device-id>"

cameras:
  petfeeder:
    ffmpeg:
      input_args: preset-rtsp-restream -analyzeduration 1000000 -probesize 1000000
      inputs:
        - path: rtsp://127.0.0.1:8554/feeder
          roles:
            - record
    detect:
      enabled: false
    motion:
      enabled: true
    record:
      enabled: true
```

### Option B: recording plus live view in a web browser

Choose this if you want the camera to play in a normal browser tab. The feeder
sends its video in a format (HEVC) that most browsers cannot play, so it has to
be converted, and converting uses roughly one processor core the whole time it
is running.

```yaml
go2rtc:
  streams:
    feeder_source:
      - "rtsp://<your-home-assistant-ip>:8560/philips-pet-<device-id>"
    feeder:
      - "ffmpeg:feeder_source#video=h264#rotate=90#audio=copy"

cameras:
  petfeeder:
    ffmpeg:
      input_args: preset-rtsp-restream -analyzeduration 1000000 -probesize 1000000
      inputs:
        - path: rtsp://127.0.0.1:8554/feeder
          roles:
            - record
    detect:
      enabled: false
    motion:
      enabled: true
    record:
      enabled: true
```

The only difference is the `go2rtc` part at the top: Option B adds a second
stream that converts the video, and the camera then reads that converted one.

---

## Why these settings

These are measurements from a real feeder on a small Intel home server. Your own
numbers will be different, but the differences between the options should look
similar.

| How the stream is set up | Time until a picture appears | Processor use |
|---|---|---|
| convert video, re-encode audio | 3.0s | 0.94 of a core |
| keep video, re-encode audio | 6.5s | 0.06 of a core |
| **no conversion (Option A)** | 3.8s | **0.03 of a core** |
| **convert video, keep audio (Option B)** | **3.0s** | 0.87 of a core |

What this means in plain terms:

- **Converting the video is the expensive part**: about a whole processor core,
  continuously, for one camera. If you only want recordings, don't convert:
  Frigate stores the original perfectly well.
- **If you do convert, leave the audio alone.** Re-encoding the sound as well
  costs a little extra and gains nothing.
- **The `analyzeduration` and `probesize` numbers matter.** They tell Frigate how
  long to spend working out what the stream is. This camera sends few pictures
  per second, so the normal setting is over-generous. One second brings the
  startup delay down from about 3 seconds to about 2. Do not set them much lower
  than this: if the value is very small, Frigate cannot work the stream out at
  all and waits forever.

---

## Object detection

Both configurations above have detection switched **off** on purpose.

The feeder's camera is tall rather than wide (1080 x 1920) and sends few pictures
per second, and running detection on top of a conversion is expensive. Recording
plus motion detection is usually the better trade.

If you do want object detection, give it a size, and remember the picture is
tall, so the height must be **larger** than the width:

```yaml
    detect:
      enabled: true
      width: 270
      height: 480
      fps: 2
```

Frigate assumes a normal wide picture by default, and that alone is enough to
stop the detection stream from working.

---

## Talking through the feeder

The connection supports talking back to the feeder, but **converting the video
switches it off**. The conversion drops the microphone channel.

If two-way audio matters to you, point your live view at the unconverted stream
(`feeder_source` in Option B) rather than the converted one.

---

## If it does not work

**"Connection refused"**: nearly always `127.0.0.1:8560` instead of Home
Assistant's real address. See [easy mistakes to avoid](#easy-mistakes-to-avoid).
Also check Camera streaming is set to "Always on".

**"No frames have been received"**: usually object detection. Switch it off, or
give it a tall size as shown above.

**It only starts after a long wait, or works on and off**: turn on Preload, and
make sure the `analyzeduration` and `probesize` settings are present. Connecting
over and over in quick succession can also be refused by the camera; preloading
avoids reconnecting at all.

**Nothing works after restarting Home Assistant**: the connection to the camera
is rebuilt from scratch, which takes a moment. Preload plus "Always on" keeps
that delay away from your recorder.
