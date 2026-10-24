#include "calibration.h"

#include <Preferences.h>
#include <cmath>

#include "dwell_config.h"

namespace dwell_cal {
namespace {
constexpr const char* kNamespace = "dwell";
constexpr const char* kKey = "mic_off_db";
}  // namespace

float load_mic_offset_db() {
  Preferences p;
  if (!p.begin(kNamespace, true)) return DWELL_DEFAULT_MIC_OFFSET_DB;
  const float v = p.getFloat(kKey, DWELL_DEFAULT_MIC_OFFSET_DB);
  p.end();
  return std::isfinite(v) && std::fabs(v) <= kMaxAbsOffsetDb ? v : DWELL_DEFAULT_MIC_OFFSET_DB;
}

bool store_mic_offset_db(float offset_db) {
  if (!std::isfinite(offset_db) || std::fabs(offset_db) > kMaxAbsOffsetDb) return false;
  Preferences p;
  if (!p.begin(kNamespace, false)) return false;
  const bool ok = p.putFloat(kKey, offset_db) == sizeof(float);
  p.end();
  return ok;
}

}  // namespace dwell_cal
