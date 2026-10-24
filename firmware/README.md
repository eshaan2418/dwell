# Dwell sensor kit firmware

ESP32 firmware for the Dwell in-home sensor kits. Each kit logs illuminance, temperature,
relative humidity and **A-weighted sound levels** (never audio) to a microSD card, in the format
defined by [`docs/SENSOR_LOG_FORMAT.md`](../docs/SENSOR_LOG_FORMAT.md). It can also POST the
same lines to a collector on the occupant's own LAN.

```
firmware/
  platformio.ini            PlatformIO project (env esp32dev = SHT31, esp32dev_bme280 = BME280)
  include/config.example.h  per-kit settings template (copy to include/config.h, git-ignored)
  src/                      Arduino-side modules: audio_input (I2S, the only I2S reader), light (BH1750),
                            climate (SHT31/BME280), logger (SD + HTTP), timesync (Wi-Fi/NTP),
                            calibration (NVS), main.cpp
  lib/dwell_core/           platform-independent code, compiled on the host too:
                            audio_dsp (A-weighting, octave bands, L_Aeq,1s), level_stats (LAeq/LAmax/LA90),
                            log_format (pure line formatting), sensor_math (BH1750 ranging, SHT31 CRC),
                            records.h + log_sink.h (the only types the logger accepts)
  test_host/                host C++17 unit tests (own tiny harness)
  tools/                    check_no_raw_audio.py (+ pytest), pio_config.py (config selection)
```

## Make targets

| Target | What it does |
|---|---|
| `make -C firmware host-test` | builds `test_host/` + `lib/dwell_core/` with `c++ -std=c++17 -Wall -Wextra -Werror` and runs it |
| `make -C firmware lint` | `clang-format --dry-run --Werror` (Google style, 110 cols; `make format` fixes) |
| `make -C firmware check-privacy` | runs `tools/check_no_raw_audio.py` and its pytest suite |
| `make -C firmware build` | `pio run` (needs PlatformIO; first run downloads the ESP32 toolchain, ~10 min) |
| `make -C firmware all` | all of the above |

`CLANG_FORMAT`, `PYTHON` and `PIO` default to the repo's `.venv` / `~/.local/bin` tools and can be overridden.

## Bill of materials (per kit)

Generic part names; prices are rough ranges in CAD from common hobby-electronics retailers and
marketplaces (approx., Oct 2026, not verified against specific vendors). Buying in multi-packs for all kits
lowers the per-kit cost.

| Part | Notes | Approx. CAD |
|---|---|---|
| ESP32 dev board (ESP32-DevKitC / WROOM-32, 38-pin) | any board exposing the GPIOs below | 8 - 20 |
| BH1750 breakout (GY-302 style) | I2C, address 0x23 (ADDR low) | 3 - 8 |
| SHT31 breakout (or BME280 breakout) | I2C, 0x44 / 0x76; buy genuine Sensirion/Bosch-based boards if possible | 5 - 20 |
| INMP441 I2S MEMS microphone breakout | bottom-port, omnidirectional | 4 - 10 |
| microSD SPI module (3.3 V capable) + 8-32 GB microSD (FAT32) | a 1-year log is ~150 MB | 3 - 8 + 6 - 12 |
| USB cable + 5 V USB power adapter (>= 1 A) | | 8 - 15 |
| Optional: 18650 cell + TP4056-type charger/protection board + 2 x 100 kOhm divider | battery backup; voltage on GPIO35 | 10 - 20 |
| Jumper wires / perfboard, 20-30 cm 4-wire cable for the climate sensor, enclosure with vents | | 5 - 15 |
| **Total** | | **~45 - 110** |

## Wiring (ESP32-DevKitC)

All modules run from **3.3 V**. Pins are set in `config.h`.

| Module | Module pin | ESP32 GPIO |
|---|---|---|
| I2C bus (BH1750 + SHT31/BME280) | SDA | GPIO21 |
| | SCL | GPIO22 |
| | VCC / GND | 3V3 / GND |
| BH1750 | ADDR | GND (address 0x23) |
| INMP441 (I2S) | SCK (bit clock) | GPIO26 |
| | WS (word select) | GPIO25 |
| | SD (data out) | GPIO33 |
| | L/R | GND (left channel; if tied to 3V3 set `DWELL_I2S_RIGHT_CHANNEL 1`) |
| | VDD / GND | 3V3 / GND |
| microSD (VSPI) | CS | GPIO5 |
| | SCK | GPIO18 |
| | MISO | GPIO19 |
| | MOSI | GPIO23 |
| | VCC / GND | 3V3 (or 5V if the module has its own regulator) / GND |
| Battery (optional) | cell + -> 100k -> GPIO35 -> 100k -> GND | GPIO35 (ADC1, input-only) |

Most breakouts already include I2C pull-ups; with two modules on the bus that is fine. If neither
does, add 4.7 kOhm pull-ups from SDA/SCL to 3V3.

## Assembly notes

- **Microphone**: the INMP441 is *bottom-ported* - the sound hole is on the side opposite the
  components. Mount it so that hole faces into the room through an enclosure opening (>= 3 mm, a
  short tube is fine), not against the board or a wall. Keep it away from the SD card module and the
  ESP32 antenna; no foam that seals the port.
- **Light sensor**: place the kit on the windowsill / agreed measurement location with the BH1750
  window **facing straight up**, unobstructed, nothing shading it. Cover the ESP32 board's red power
  LED (and any module LEDs) with opaque tape; the firmware keeps GPIO2's LED off.
- **Temperature/RH**: the ESP32 warms itself and its surroundings by 1-5 C (more with Wi-Fi on).
  Put the SHT31/BME280 on a **20-30 cm cable outside the enclosure** or in a separately vented
  compartment, below the board, out of direct sun. Firmware reads it once per minute in single-shot
  mode and turns Wi-Fi off after time sync (`DWELL_WIFI_KEEP_ON 0`) to limit self-heating.
- Use a FAT32-formatted microSD card. Cards can be swapped while running: the logger re-mounts within
  ~10 s and retries buffered data (up to 16 KB in RAM, about 10 min of S + M lines).

## Flashing

1. Install PlatformIO Core: `uv tool install platformio` (or `pip install platformio`).
2. `cp firmware/include/config.example.h firmware/include/config.h` and set at least
   `DWELL_KIT_ID` (unique per kit, e.g. `KIT07`), and `DWELL_WIFI_SSID` / `DWELL_WIFI_PASSWORD`
   for NTP time. Optionally set `DWELL_COLLECTOR_URL`. `config.h` is git-ignored; without it the build
   uses the example config (`tools/pio_config.py` picks the file).
3. Connect the board via USB and run from `firmware/`:
   ```
   pio run -t upload        # build + flash (env esp32dev, SHT31)
   pio run -e esp32dev_bme280 -t upload   # BME280 variant
   pio device monitor       # serial console at 115200 baud
   ```
4. In the serial console, `status` prints kit ID, time sync, SD state and the last 1-s level.

Without Wi-Fi the kit still logs, but timestamps count from 1970-01-01 at boot and every M line
carries flag `0x01`; such files must be re-timed from the `boot=` header field and an external
reference during ingest.

## Log output

One file per kit per UTC day, `DWELL_<kit>_<YYYYMMDD>.log`, header line on each new file. Minute
(`M`), second (`S`, `DWELL_LOG_SECONDS`), octave (`O`, `DWELL_LOG_OCTAVES`) and event (`E`) lines exactly
as in the format doc. Implementation choices within that contract:

- `flags` is written as `0x` + two lowercase hex digits (e.g. `0x05`); parse with `int(s, 16)`.
- `lux` is the mean of the BH1750 readings taken in the minute (every `DWELL_LIGHT_PERIOD_S` = 10 s);
  `temp_c`/`rh_pct` are a single read at the end of the minute; `batt_v` is rounded to 0.01 V and empty
  when no cell is connected.
- Minutes are aligned to UTC (`ts` divisible by 60) and contain the 1-s intervals `(ts-60, ts]`.
  1-s intervals are timed by the I2S sample clock; their timestamps are kept consecutive and are
  re-aligned to the RTC when they drift by more than 1 s (so a rare minute may hold 59 or 61 values).
- After an NTP step the current minute is closed early and logged with fewer seconds.
- If the microphone delivers nothing for 3 s, `MIC_ERROR` is logged and the minute clock continues
  with empty sound fields, so light/climate are not lost.
- Additional event codes used: `WIFI_FAIL`, `NTP_FAIL`, `SD_MOUNTED`, `MIC_ERROR`, `LOG_DROPPED`.
- LAN upload: each POST body is the header line followed by the buffered lines (`text/plain`).
  The SD card is the authoritative copy; failed uploads are not retried if the SD write succeeded.

## Audio processing

INMP441 -> I2S at 48 kHz, 32-bit slots (24 data bits, MSB-aligned) -> `>> 8` -> float in [-1, 1)
-> clip detection (|x| >= 0.999 FS; sets flag `0x04`) -> DC blocker (first-order high-pass, 3 Hz)
-> A-weighting -> mean square over exactly 48 000 samples -> L_Aeq,1s. Per minute: L_Aeq,60s =
energetic mean of the 1-s values, LAmax = max of the 1-s values (an approximation of L_AFmax at
1-s resolution), LA90 = level exceeded by 90 % of the 1-s values (ascending sort, index
floor(0.1 n), i.e. the 7th-lowest of 60). Optional octave bands (63 Hz - 8 kHz, unweighted)
use the same DC-blocked signal.

Level calibration: INMP441 sensitivity is -26 dBFS at 94 dB SPL (1 kHz), where 0 dBFS is a full-scale
sine (mean square 0.5), so `L = 10 log10(2 ms) + 120 + mic_offset_db`. The maximum level before
clipping is therefore ~120 dB SPL. The DSP runs in single precision on the ESP32 FPU (coefficients are
designed in double); a host test shows the float chain within 0.2 dB of a double reference down to
-95 dBFS noise.

### A-weighting filter design

The analog A-weighting function of IEC 61672-1 (Annex E) is

    H_A(s) = K s^4 / ((s + w1)^2 (s + w2) (s + w3) (s + w4)^2),
    f1 = 20.598997 Hz, f2 = 107.65265 Hz, f3 = 737.86223 Hz, f4 = 12194.217 Hz.

It is factored into three second-order sections, s^2/(s+w1)^2, s^2/((s+w2)(s+w3)) and
w4^2/(s+w4)^2, and each section is mapped to z with the bilinear transform s = 2 fs (1 - z^-1)/(1 + z^-1).
Each pole frequency is **pre-warped**, w_i = 2 fs tan(pi f_i / fs), so the digital poles land on the
analog corner frequencies; the overall gain is normalised to exactly 0 dB at 1 kHz from the digital
response. Coefficients are computed at start-up (`design_a_weighting(48000)`), so the derivation is
the code. Plain (un-warped) bilinear would be within 0.1 dB up to 4 kHz but -1.2 dB at 10 kHz,
-2.7 dB at 12.5 kHz and -6.2 dB at 16 kHz; pre-warping trades that for a small positive bump.

Measured deviation of the implemented filter from the IEC 61672-1 table (exact base-10 frequencies,
`make host-test` prints this table):

| f [Hz] | 31.5 | 63 | 125 | 250 | 500 | 1k | 2k | 4k | 8k | 10k | 12.5k | 16k |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| IEC A [dB] | -39.4 | -26.2 | -16.1 | -8.6 | -3.2 | 0.0 | +1.2 | +1.0 | -1.1 | -2.5 | -4.3 | -6.6 |
| error [dB] | -0.07 | -0.03 | -0.03 | -0.06 | -0.05 | 0.00 | +0.07 | +0.26 | +0.69 | +0.60 | -0.22 | -2.85 |
| class 1 tol. | +-2.0 | +-1.5 | +-1.5 | +-1.4 | +-1.4 | +-1.1 | +-1.6 | +-1.6 | +2.1/-3.1 | +2.6/-3.6 | +3.0/-6.0 | +3.5/-17 |

All points are inside the IEC 61672-1 class 1 limits (the remaining -2.9 dB at 16 kHz is the
bilinear zero at Nyquist; it is irrelevant for room noise). The time-domain test pushes sines
through the float implementation and agrees with this design to 0.1 dB. Note that this verifies the
*filter*; the INMP441's own frequency response (roughly flat 100 Hz-10 kHz, roll-off below ~60 Hz)
is not compensated, so the complete kit is not a class 1 meter.

### Octave bands

Each band is a 3rd-order Butterworth low-pass prototype transformed to a band-pass (6th order,
3 biquads) with -3 dB edges at fm * 10^(+-0.15) (base-10 octaves, fm = 63.1 ... 7943 Hz), pre-warped
and normalised to 0 dB at fm. Analog-equivalent attenuation one octave from fm is ~19.6 dB, two
octaves ~43 dB. Enable with `DWELL_LOG_OCTAVES 1` (about 24 extra biquads per sample).

## Measurement floor of the INMP441

The datasheet gives SNR = 61 dBA referenced to the 94 dB SPL, 1 kHz sensitivity point. The
A-weighted self-noise is therefore equivalent to an acoustic input of

    L_floor = 94 dB SPL - 61 dB = 33 dBA        (in digital terms: -26 dBFS - 61 dB = -87 dBFS(A))

A quiet room measured with this microphone can never read below ~33 dBA; the reading is the
energetic sum of room noise and self-noise. A true room level of 33 dBA reads ~36 dBA; 25 dBA reads
~33.6 dBA. **Quiet bedrooms at night (often 20-30 dBA) are below this floor**, so night-time
L_Aeq/LA90 values within ~3 dB of 33 dBA must be treated as "at or below floor" (censored) in
analysis, not as measurements. The per-kit floor should be checked in the co-location step
(e.g. in a quiet closet at night: the LA90 there is the practical floor of that kit).

## Calibration procedures

1. **24-h co-location (all kits)**: place all kits side by side (mics facing the same way, light
   sensors up, same shading) for at least 24 h including a night. Use the per-minute data to
   compute each kit's offset from the across-kit median for L_Aeq,60s (using minutes well above
   the floor, e.g. > 45 dBA), temperature, RH and lux. Expected spread: sound +-1-2 dB (INMP441
   sensitivity tolerance is +-1 dB), temperature +-0.3 C, RH +-2 %, lux +-20 %. Kits that deviate
   beyond that are reworked or flagged.
2. **Sound level offset vs. a reference**: in a quiet room, play a steady 1 kHz tone or pink noise at
   ~70-80 dB at the kit, with the reference sound level meter (class 1/2, A-weighting, slow) or a
   calibrated phone app at the same position (mic-to-mic < 5 cm). Average 30 s on both. Then
   `new_offset = current_offset + (L_reference - L_kit)` and set it on the serial console:
   `cal <new_offset>` (stored in NVS, logged as `E,...,CAL_OFFSET_SET,...`; applied to all
   subsequent levels and to the `mic_offset_db=` field of new file headers). Uncertainty: about
   +-0.5-1 dB with a class 1/2 meter, **+-2-3 dB with a phone app** (record which was used). With
   pink noise the comparison also includes the mic's frequency response, which is what matters for
   broadband room noise.
3. **Lux sanity check**: compare against a phone light meter app or a lux meter under (a) indoor
   lamp light (~100-500 lx) and (b) overcast/clear daylight on the windowsill. Expect agreement
   within +-20 % (phone apps are themselves +-20-30 %). Confirm that direct sun reads > 54 klx with
   flag `0x02` rather than clipping at 54612 lx.

## Light sensor range extension

The BH1750 in its default mode (H-resolution, MTreg = 69) counts 1/1.2 lx per LSB and saturates at
65535 / 1.2 = **54 612 lx**, below direct sunlight (~100 klx). The L-resolution mode does *not* help
(same 16-bit counter, coarser steps); the range is extended by lowering the measurement-time
register to its minimum, MTreg = 31, which scales full scale by 69/31 to **121 557 lx** at 1.85 lx per
count. The firmware auto-ranges between four settings - night (H-res2, MTreg 254, 0.11 lx steps),
indoor (H-res2, MTreg 69), default (H-res, MTreg 69) and extended (H-res, MTreg 31) - switching up at
92 % of full scale (a saturated count is discarded and re-measured) and down when a reading would use
< 40 % of the more sensitive range. Flag `0x02` is set for a minute if any reading exceeded the
default range (> 54 612 lx, i.e. came from the extended range), or saturated even there.

## No-raw-audio guarantee (privacy)

Dwell kits are installed in people's homes. The firmware **never stores, transmits or prints
audio samples**; only sound *levels* in dB leave the DSP. How this is guaranteed:

1. **Architecture**: `src/audio_input.cpp` is the only file that calls `i2s_read`. Its 1 KB
   sample buffer is a static scratch array overwritten every 5.3 ms block and passed only to
   `AudioDsp::process_i2s_frames()`. The DSP (`lib/dwell_core/audio_dsp.*`, no I/O headers)
   processes samples one at a time into filter state and mean-square accumulators and exposes only
   `SecondLevels` (L_Aeq,1s, octave levels, peak dBFS, clip count). Only that struct crosses the
   FreeRTOS queue to the main loop.
2. **Type-level**: the logger implements `dwell::LogSink`, whose only methods take
   `MinuteRecord`, `SecondRecord`, `OctaveRecord` and `EventRecord`. `test_host/test_api.cpp`
   static-asserts that it cannot be called with `int32_t*`, `float*`, `void*`, `uint8_t*`,
   `std::vector<float>`, `std::array<int32_t, N>`, etc., and that all level/record structs are small
   trivially-copyable values (<= 128 bytes; a single 1-ms block would be 192 bytes).
3. **Static check**: `tools/check_no_raw_audio.py` (run by `make check-privacy`) fails if an I2S read
   occurs outside `audio_input.cpp`, if the I2S buffer (or any alias/copy) reaches anything other
   than the DSP entry point (SD/File, Serial, HTTP/WiFi/UDP, queues, logger, returns), if the DSP
   module gains I/O, if the logger API gains non-record parameters, or if any file in `firmware/`
   contains a WAV/PCM writer (RIFF/WAVE headers, `.wav` paths, `audio/wav`/`audio/L16`, ...).
   `tools/test_check_no_raw_audio.py` proves it passes on the real tree and fails on synthetic leaks.
4. **Review**: [`REVIEW_CHECKLIST.md`](REVIEW_CHECKLIST.md) items must be ticked for every change
   touching `firmware/`.

A 1-s A-weighted level cannot be inverted to recover speech. The S lines (1 Hz) do reveal activity
patterns (e.g. when a room is occupied), which is covered by the study consent; disable them with
`DWELL_LOG_SECONDS 0` if a participant prefers minute data only.
