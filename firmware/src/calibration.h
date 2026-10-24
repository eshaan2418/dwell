// Per-kit microphone calibration offset stored in NVS (survives re-flashing of the application).
#pragma once

namespace dwell_cal {

constexpr float kMaxAbsOffsetDb = 20.0f;
float load_mic_offset_db();             // DWELL_DEFAULT_MIC_OFFSET_DB if never set
bool store_mic_offset_db(float offset_db);  // rejects |offset| > kMaxAbsOffsetDb

}  // namespace dwell_cal
