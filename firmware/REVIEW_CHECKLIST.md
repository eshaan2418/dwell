# Firmware code-review checklist

Every change under `firmware/` must be reviewed against this list. The reviewer ticks each item in
the PR description; any "no" blocks the merge.

## No-raw-audio guarantee (blocking)

- [ ] `make -C firmware check-privacy` passes (static checker + its pytest suite), and the checker
      configuration (`ALLOWED_I2S_FILES`, `ALLOWED_CONSUMERS`, `DSP_FILES`, `LOGGER_HEADERS`) was
      **not** widened. Any change to the checker itself needs a second reviewer.
- [ ] `i2s_read` / any I2S/ADC audio read happens only in `src/audio_input.cpp`, into a local or
      file-static scratch buffer that is overwritten every block.
- [ ] The sample buffer (or a pointer, copy, slice, or element of it) is passed to nothing except
      `AudioDsp::process_i2s_frames()` - not to the logger, SD/`File`, `Serial`, HTTP/Wi-Fi/UDP
      clients, queues/ring buffers, other tasks, globals, or return values.
- [ ] The DSP (`lib/dwell_core/audio_dsp.*`, `level_stats.*`) has no I/O includes or calls, keeps
      no sample history beyond filter state, and its public outputs are level structs in dB only.
- [ ] The logger (`dwell::LogSink`, `SdLogger`) still accepts only `MinuteRecord`, `SecondRecord`,
      `OctaveRecord`, `EventRecord`; no new overloads taking pointers, arrays, strings of numbers,
      or byte buffers. `test_host/test_api.cpp` static_asserts are unchanged or stricter.
- [ ] No new record/struct field could carry waveform data (arrays longer than the 8 octave bands,
      sample counts encoded as text, "debug dump" fields, etc.); `EventRecord` text never contains
      sample values.
- [ ] No WAV/PCM/raw-audio writer, audio streaming, or "debug recording" mode exists, even behind a
      compile flag; no new network destinations other than NTP and the configured LAN collector.

## Data contract

- [ ] Output still matches `docs/SENSOR_LOG_FORMAT.md` (field order and counts; `make host-test`
      parses the lines). Format changes require a version bump and an update to `ingest/`.
- [ ] dB values include `mic_offset_db`; rounding as documented; missing values are empty fields.

## General

- [ ] `make -C firmware host-test lint` pass; `pio run` builds without new warnings in `src/`/`lib/`.
- [ ] No credentials committed (`include/config.h` stays git-ignored).
