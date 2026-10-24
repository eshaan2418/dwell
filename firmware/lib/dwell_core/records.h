// Log record types (docs/SENSOR_LOG_FORMAT.md). These are the ONLY things the logger accepts.
// Missing values are NAN (written as empty fields). All timestamps: Unix seconds UTC, end of interval.
#pragma once

#include <cstdint>

#include "audio_dsp.h"

namespace dwell {

enum MinuteFlags : uint8_t {
  kFlagTimeNotSynced = 0x01,
  kFlagLightSaturated = 0x02,
  kFlagMicClipping = 0x04,
  kFlagClimateError = 0x08,
  kFlagBrownoutLowBattery = 0x10,
};

struct HeaderInfo {
  char fw_version[16];
  char kit_id[24];
  float mic_offset_db;
  uint32_t sample_rate;
  uint32_t boot_ts;
};

struct MinuteRecord {  // M line
  uint32_t ts;
  float lux, temp_c, rh_pct, laeq_60s, lamax_60s, la90_60s, batt_v;
  uint8_t flags;
};

struct SecondRecord {  // S line
  uint32_t ts;
  float laeq_1s;
};

struct OctaveRecord {  // O line
  uint32_t ts;
  float band_db[kNumOctaveBands];
};

struct EventRecord {  // E line
  uint32_t ts;
  char code[24];
  char text[96];  // commas / newlines are replaced when formatting
};

EventRecord make_event(uint32_t ts, const char* code, const char* text);

}  // namespace dwell
