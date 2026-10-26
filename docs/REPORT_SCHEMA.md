# Dwell report bundle (schema `dwell-report/1`)

Produced by `make predict UNIT=<id>` (`hybrid/report.py`) into `reports/<unit_id>/`:

```
reports/<unit_id>/report.json
reports/<unit_id>/audio/<room_id>_0200_closed.wav   # illustrative "night listen" (16-bit mono 22.05 kHz, 12 s)
reports/<unit_id>/audio/<room_id>_0200_open.wav
```

Coordinates: local ENU metres (x east, y north, z up, street level = 0). Azimuth: degrees clockwise
from north. `{pred, lo, hi}` = point estimate and 90 % prediction interval.

```jsonc
{
  "schema": "dwell-report/1",
  "generated_utc": "2026-10-24T18:00:00Z",
  "data_kind": "synthetic",              // "synthetic" | "real" — app must show a SYNTHETIC badge if synthetic
  "disclaimer": "Estimates with uncertainty, not a building inspection ...",
  "unit": {"id": "B0003_u0", "label": "Unit B0003-0 (synthetic)", "floor": 4, "building_kind": "midrise",
           "year_built": 1978, "main_orientation": "S", "has_ac": false},
  "geometry": {
    "rooms": [{"id": "B0003_u0_bedroom", "kind": "bedroom", "name": "Bedroom",
               "polygon": [[x, y], ...], "floor_z": 12.0, "ceiling_height": 2.6}],
    "windows": [{"id": "...", "room_id": "...", "corners": [[x,y,z],[x,y,z],[x,y,z],[x,y,z]],
                 "azimuth": 163.3, "overhang_depth": 0.0}],
    "context_buildings": [{"footprint": [[x, y], ...], "height": 18.0, "own": false}],   // within ~150 m
    "roads": [{"coords": [[x, y], ...], "road_class": "primary"}],
    "trees": [{"x": 0, "y": 0, "radius": 3, "height": 10}]
  },
  "sun": {
    "dates": ["2026-12-21", "2026-03-20", "2026-06-21", "2026-09-22"],   // slider dates
    "hours": [6.0, 6.5, ..., 20.0],                                         // local solar-clock hours
    "sun_position": [[[az, el], ...per hour], ...per date],
    "patches": {"<room_id>": [[ [[x,y],...] | null, ...per hour ], ...per date]},   // floor sun patch polygons
    "rooms": {"<room_id>": {
        "winter_sun_h": {"pred": 1.2, "lo": 0.4, "hi": 2.1},   // Dec-Feb mean direct-sun h/day (typical weather)
        "summer_sun_h": {"pred": 3.0, "lo": 2.0, "hi": 4.1},
        "monthly_sun_h": [12 numbers],                          // typical-weather expected h/day per month
        "clear_sky_winter_solstice_h": 2.5,
        "daylight_factor_pct": 2.1}}
  },
  "noise": {
    "rooms": {"<room_id>": {
        "night_laeq_closed": {"pred": 31.0, "lo": 27.0, "hi": 36.0},   // dB(A), 23:00-07:00, windows closed
        "night_laeq_open":   {"pred": 42.0, "lo": 37.0, "hi": 47.0},   // window ajar
        "outdoor_night_facade": 58.0,
        "attribution_db": {"road": 30.5, "streetcar": 24.0},          // indoor night level by source class
        "hourly_closed": [24 numbers],
        "who_guideline_note": "..."}},
    "audio": {"<room_id>": {"closed": "audio/<room>_0200_closed.wav", "open": "audio/<room>_0200_open.wav",
                            "label": "Illustrative synthesis, not a recording"}}
  },
  "heat": {
    "rooms": {"<room_id>": {
        "typical_summer_peak": {"pred": 27.5, "lo": 26.0, "hi": 29.3},   // mean daily peak, Jun-Aug, typical year
        "heatwave_peak": {"pred": 31.0, "lo": 29.0, "hi": 33.5},         // hottest day of the reference heat wave
        "hours_above_26_typical_summer": 210, "hours_above_28_typical_summer": 60}}
  },
  "uncertainty": {"<room_id>": {"what_we_couldnt_see": [
      {"property": "glazing", "posterior": {"single": 0.1, "double": 0.6, "double_lowe": 0.3, "triple": 0.0},
       "variance_share": {"noise": 0.55, "heat": 0.20},
       "explanation": "We could not confirm the glazing type from the video ..."}]}},
  "provenance": {"commit": "...", "model": "...", "calibration": "synthetic world_v1"}
}
```
