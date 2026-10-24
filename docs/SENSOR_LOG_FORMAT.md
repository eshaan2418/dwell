# Dwell sensor log format (v1)

Contract between `firmware/` (writer) and `ingest/` (reader). Plain-text CSV-like lines,
one file per kit per UTC day: `DWELL_<kitid>_<YYYYMMDD>.log` on the SD card (or the same lines
POSTed in batches to a local collector on the occupant's LAN).

## Privacy invariant
The firmware never persists or transmits audio samples. Only sound *levels* (dB) leave the
audio DSP module. See `firmware/README.md` → "No-raw-audio guarantee" and the CI test.

## Lines

All timestamps are Unix seconds UTC (integer) at the **end** of the averaging interval.
Missing values are written as empty fields. Fields are comma-separated, no quoting.

```
# dwell-fw <fw_version> kit=<kit_id> mic_offset_db=<float> sample_rate=<int> boot=<unix_ts>
M,<ts>,<kit_id>,<lux>,<temp_c>,<rh_pct>,<laeq_60s>,<lamax_60s>,<la90_60s>,<batt_v>,<flags>
S,<ts>,<kit_id>,<laeq_1s>
O,<ts>,<kit_id>,<l63>,<l125>,<l250>,<l500>,<l1k>,<l2k>,<l4k>,<l8k>
E,<ts>,<kit_id>,<event_code>,<free_text_without_commas>
```

- `M` (every 60 s): BH1750 illuminance [lux], SHT31/BME280 temperature [°C] and RH [%],
  A-weighted 60-s equivalent level L_Aeq,60s [dB], max of the 1-s L_Aeq values in the minute
  (`lamax_60s`, i.e. L_AFmax approximated at 1-s resolution — documented), and the 90th-percentile
  exceedance level of the 60 1-s values (`la90_60s`), supply voltage [V], and `flags` (hex bitfield):
  - `0x01` time not NTP-synced yet
  - `0x02` light sensor saturated (BH1750 > 54612 lx in high-res mode; firmware switches to low-res/MT)
  - `0x04` mic clipping detected in this minute
  - `0x08` temp/RH read error
  - `0x10` brown-out / low battery
- `S` (every 1 s, optional, default on): A-weighted 1-s L_Aeq [dB].
- `O` (every 60 s, optional): unweighted octave-band L_eq,60s [dB] at 63 Hz … 8 kHz.
- `E` (events): `BOOT`, `NTP_SYNC`, `SD_ERROR`, `WIFI_UP`, `CAL_OFFSET_SET`, etc.

dB values are already corrected by `mic_offset_db` (the per-kit calibration offset stored in
NVS). Values are rounded to 0.1 dB, 0.01 °C, 0.1 % RH, 0.1 lx.
