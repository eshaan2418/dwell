# HUMAN_TODO — things only you can do

Everything below is prepared; the agent cannot do these steps. Ordered by urgency (sensor data
takes weeks — start first). Status of each unit lives in `DATA_STATUS.md` (pseudonymous IDs only).

> **Ethics first.** If you intend to publish (paper / dataset) results involving volunteers' homes or
> the decision study, get approval from a research ethics board (university REB, or an independent
> IRB/REB service) **before** collecting data, and use the consent forms below (adapt to the board's
> template). Do not collect from anyone who has not signed.

---

## 1. Recruit 8–20 volunteer units (start now)

Aim for variety: orientations (N/E/S/W main windows), floors (ground, mid, high), street types
(quiet residential, arterial, streetcar street, near rail), building ages (pre-1960 brick, 1960–89,
post-2000 condo). Two rooms per unit (bedroom + living room).

**Recruiting message (copy/paste):**

> Hi! I'm running a small research project called *Dwell* that tries to predict how sunny, quiet and
> hot an apartment is from a 2-minute phone video plus public map data. To check whether it works, I
> need a few real homes. If you take part I'd lend you two small sensor boxes (about the size of a deck
> of cards) for 2–4 weeks: one on your bedroom windowsill, one in your living room. They measure light,
> temperature/humidity and **sound level only (a number in decibels — no audio is ever recorded or
> transmitted)**. I'd also ask you to film a slow 2-minute walkthrough and spend 5 minutes with a tape
> measure. Your address never leaves my computer; anything published is anonymised (neighbourhood +
> orientation + floor band only). You can withdraw at any time and I'll delete your data. Interested?

Landlord permission: sensors sit on a sill / shelf (no drilling); usually no permission is needed, but
if the lease requires it, ask.

## 2. Consent form (one per unit, signed by every adult occupant)

Save signed forms in `data/private/consent/` (git-ignored). Record the consent scope per unit in
`DATA_STATUS.md` (codes below).

```
DWELL — Volunteer home measurement: information and consent

What: Two sensor kits in your home for 2–4 weeks measuring light (lux), temperature, humidity and
sound LEVEL (decibels). The microphone signal is converted to a level on the device every second;
no audio is stored or sent anywhere. You will also film a ~2-minute walkthrough video and take a few
tape measurements.

Data handling: Your address, unit number and the raw video are stored only on the researcher's
encrypted computer (never in any shared repository). Faces, documents, screens and personal
photos are blurred in any image used for analysis or figures. Published data are aggregated per room
(e.g. "average night-time noise level") with location coarsened to neighbourhood + orientation +
floor band.

Your choices (tick each you agree to):
[ ] S  Sensor measurements for research analysis                         (required)
[ ] V  Walkthrough video processed into a 3D/floor-plan model            (required for full use)
[ ] R  De-identified, aggregated data included in a public dataset release
[ ] F  Redacted images/3D views of my home used in a paper/demo figure
[ ] D  My unit may be shown (anonymously, as a video tour + report) to decision-study participants

Withdrawal: at any time, without reason; data will be deleted from the researcher's machine and
excluded from future releases (already-published aggregates cannot be recalled).
Risks: minimal; sensors are low-voltage USB devices. Benefits: you receive your own report.
Contact: <your name, email>.  Ethics approval: <board, reference number>.

Name(s) ______________________  Signature(s) ______________________  Date __________
```

## 3. Buy / assemble / flash sensor kits (~$30–40 each; 2 per unit + 1 spare)

Parts list, wiring table and flashing steps: **`firmware/README.md`**. Summary per kit: ESP32 dev
board, BH1750 lux sensor, SHT31 (or BME280) temp/RH on a ~1.5 m cable, INMP441 I2S MEMS mic (an
ICS-43434 is a quieter drop-in alternative — see the measurement-floor note), microSD module +
card, USB power supply + cable, small enclosure.

1. Assemble per the wiring table; flash with `pio run -d firmware -t upload` after copying
   `firmware/include/config.example.h` to `config.h` and setting the **kit ID** (e.g. `K07`) and
   (optionally) Wi-Fi for NTP time sync.
2. Label each kit with its ID. Keep the kit ↔ unit/room mapping in `data/private/kits.csv`:
   `kit_id,unit_pid,room,installed_utc,removed_utc,placement_notes` (unit_pid = pseudonym such as `U03`).

## 4. Calibrate all kits together BEFORE deployment (24 h)

1. Put all kits side by side on a table in one room, away from windows/heaters, powered, for 24 h
   (include a quiet night). Note start/end times.
2. Sound reference: during that period play pink noise (or a 1 kHz tone) from a speaker for 2 minutes
   at a steady level and measure it at the kits with a reference sound-level meter (best: class 2
   meter; acceptable: a calibrated phone app such as NIOSH SLM on iOS — uncertainty ±2–3 dB). Write
   the meter reading and time in `data/private/calibration.csv`.
3. Copy the SD cards to `data/private/raw/colocation/`. Run `make ingest-colocation` → per-kit temp/dB/lux
   offsets and the inter-kit agreement report (written to `results/m1/colocation_<date>.json`). The kit noise
   floor (quietest-minute level) is measured here too.

## 5. Install in each unit (2–4 weeks; longer is better)

**Placement guide (print for volunteers):**
- **Box position:** on the *inside windowsill* of the room's **largest window**, centred, about 8 cm
  behind the glass, light sensor facing straight up, not under a plant or curtain fold. If the sill is
  too narrow, use a small shelf at sill height touching the window frame. Photograph the placement.
- **Temperature probe:** on its cable, hang/tape it to an **interior wall** at 1.1–1.7 m height, in
  shade, at least 1 m from radiators, heaters, lamps, the fridge, and the window. Never in direct sun.
- **Mic:** the box's mic port faces into the room (not against the glass).
- Do **not** move the kit during the deployment. If you must, note the time.
- Keep blinds/curtains as you normally would — but please use the **window diary**.

**Window diary (one tap per change):** a shared note or paper sheet per room with lines like
`2026-11-14 22:30 bedroom window OPEN` / `07:10 CLOSED`, and the same for blinds closed during the
day and for AC/heater use. This lets the evaluation separate closed-window nights (the sensor-only
heuristic is unreliable — `results/m1/target_derivation.json`).

## 6. Film the walkthrough (2 minutes, per unit)

- Phone in **landscape**, 1080p or 4K, 30 fps, default lens (no ultra-wide), good daylight, lights on.
- Start at the entrance; walk slowly through each room. **At every window: stop, pan slowly across the
  whole window (frame, glass, sill, any balcony above), then tilt to show the view outside.**
- Show the ceiling–wall corner and a door once in each room (scale cues). Keep the phone ~1.5 m high.
- Avoid filming people, documents, screens and personal photos where possible (they will be
  blurred anyway).
- Optional: if you have an iPhone with LiDAR or an ARCore Android phone, also record a scan with a
  free app that exports poses (e.g. Polycam/RoomPlan export) — metric scale improves.
- Save as `data/private/video/<unit_pid>.mp4`. Write `data/private/units.csv`:
  `unit_pid,address,unit_number,floor,building_year_if_known,main_window_compass_deg,notes`.
  Use the phone compass app standing at the main window, back to the room, phone flat, facing out.

## 7. Five-minute measuring guide (ground truth for the scan accuracy test)

With a tape measure, per room: (1) room length and width at floor level; (2) ceiling height; (3) for each
window: glass width, glass height, sill height above the floor; (4) wall thickness at the window (reveal
depth from glass to inner wall face); (5) balcony/overhang depth above the window if any. Also record what
you *know* about the windows (single/double/triple, if known from landlord or a sticker on the spacer bar)
— this lets the hidden-property model be adapted to real units. Save as `data/private/measurements/<unit_pid>.csv`
(template: `docs/templates/measurements_template.csv`).

## 8. After the deployment

Copy SD cards to `data/private/raw/<unit_pid>/<kit_id>/`, then run `make ingest UNIT=<unit_pid>` and
`make validate`. As soon as **≥ 3 units** exist, run `make freeze-test-units` **once** (freezes the real
test units with a checksum; never tune on them).

## 9. Decision study (M11) — after ethics approval and ≥ 4 consented (D) units

See `study/README.md` for the protocol, consent form, session script and randomisation. You run the
sessions (15–30 participants, ~30 minutes each); results go in `study/data/` and the analysis runs
automatically (`make study-analysis`).
