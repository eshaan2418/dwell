// Pure line formatting for docs/SENSOR_LOG_FORMAT.md (host-testable, no I/O).
// Each function writes one line terminated by '\n' (plus NUL) into out and returns its length
// (excluding NUL), or 0 if the buffer is too small.
#pragma once

#include <cstddef>
#include <cstdint>

#include "records.h"

namespace dwell {

constexpr std::size_t kMaxLineLen = 192;

std::size_t format_header(const HeaderInfo& h, char* out, std::size_t cap);
std::size_t format_minute(const char* kit_id, const MinuteRecord& r, char* out, std::size_t cap);
std::size_t format_second(const char* kit_id, const SecondRecord& r, char* out, std::size_t cap);
std::size_t format_octave(const char* kit_id, const OctaveRecord& r, char* out, std::size_t cap);
std::size_t format_event(const char* kit_id, const EventRecord& r, char* out, std::size_t cap);

// UTC civil date of a Unix timestamp as YYYYMMDD (e.g. 20261024); days since epoch for rotation.
uint32_t utc_yyyymmdd(uint32_t ts);
inline uint32_t utc_day(uint32_t ts) { return ts / 86400u; }
// "/DWELL_<kit>_<YYYYMMDD>.log"
std::size_t log_filename(const char* kit_id, uint32_t ts, char* out, std::size_t cap);

}  // namespace dwell
