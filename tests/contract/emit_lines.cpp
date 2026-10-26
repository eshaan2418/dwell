// Emits sample log lines with the REAL firmware formatter (contract test with ingest/logs.py).
#include <cmath>
#include <cstdio>
#include <cstring>

#include "log_format.h"
#include "records.h"

using namespace dwell;

int main() {
  char buf[kMaxLineLen];
  HeaderInfo h{};
  std::strcpy(h.fw_version, "1.0.0");
  std::strcpy(h.kit_id, "K07");
  h.mic_offset_db = 0.5f;
  h.sample_rate = 48000;
  h.boot_ts = 1767225600u;
  format_header(h, buf, sizeof buf);
  std::printf("%s\n", buf);
  for (int m = 0; m < 180; ++m) {
    uint32_t ts = 1767225600u + 60u * (m + 1);
    for (int s = 0; s < 60; ++s) {
      SecondRecord sr{ts - 59u + s, 30.0f + 0.1f * s};
      format_second("K07", sr, buf, sizeof buf);
      std::printf("%s\n", buf);
    }
    MinuteRecord r{ts, 1234.5f + m, 21.5f + 0.01f * m, 45.0f, 35.2f, 41.0f, 31.0f, NAN, 0};
    if (m == 10) r.temp_c = NAN;
    if (m == 20) r.flags = kFlagClimateError;
    format_minute("K07", r, buf, sizeof buf);
    std::printf("%s\n", buf);
  }
  EventRecord e = make_event(1767225601u, "NTP_SYNC", "offset 0.2 s, ok");
  format_event("K07", e, buf, sizeof buf);
  std::printf("%s\n", buf);
  return 0;
}
