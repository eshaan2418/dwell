#include "log_format.h"

#include <cmath>
#include <cstdio>
#include <cstring>

namespace dwell {
namespace {

// Small bounded string builder; sets ok=false on overflow.
struct Line {
  char* out;
  std::size_t cap, len = 0;
  bool ok = true;

  void raw(const char* s) {
    for (; *s; ++s) put(*s);
  }
  void put(char c) {
    if (len + 1 < cap) {
      out[len++] = c;
    } else {
      ok = false;
    }
  }
  // Text field: commas and line breaks would break the CSV contract, so they are replaced.
  void text(const char* s) {
    for (; *s; ++s) put(*s == ',' ? ';' : (*s == '\n' || *s == '\r') ? ' ' : *s);
  }
  void field_u32(uint32_t v) {
    char b[16];
    std::snprintf(b, sizeof b, ",%lu", static_cast<unsigned long>(v));
    raw(b);
  }
  // ",<v>" rounded to `decimals`, or "," for a missing (NAN/inf) value.
  void field_f(float v, int decimals) {
    put(',');
    if (!std::isfinite(v)) return;
    const double scale = std::pow(10.0, decimals);
    double r = std::round(static_cast<double>(v) * scale) / scale;
    if (r == 0.0) r = 0.0;  // avoid "-0.0"
    char b[24];
    std::snprintf(b, sizeof b, "%.*f", decimals, r);
    raw(b);
  }
  std::size_t finish() {
    put('\n');
    if (!ok || cap == 0) {
      if (cap) out[0] = '\0';
      return 0;
    }
    out[len] = '\0';
    return len;
  }
};

void begin(Line& l, char type, uint32_t ts, const char* kit_id) {
  l.put(type);
  l.field_u32(ts);
  l.put(',');
  l.text(kit_id);
}

}  // namespace

EventRecord make_event(uint32_t ts, const char* code, const char* text) {
  EventRecord e{};
  e.ts = ts;
  std::strncpy(e.code, code ? code : "", sizeof(e.code) - 1);
  std::strncpy(e.text, text ? text : "", sizeof(e.text) - 1);
  return e;
}

std::size_t format_header(const HeaderInfo& h, char* out, std::size_t cap) {
  Line l{out, cap};
  char b[96];
  std::snprintf(b, sizeof b, "# dwell-fw %s kit=", h.fw_version);
  l.raw(b);
  l.text(h.kit_id);
  std::snprintf(b, sizeof b, " mic_offset_db=%.2f sample_rate=%lu boot=%lu", static_cast<double>(h.mic_offset_db),
                static_cast<unsigned long>(h.sample_rate), static_cast<unsigned long>(h.boot_ts));
  l.raw(b);
  return l.finish();
}

std::size_t format_minute(const char* kit_id, const MinuteRecord& r, char* out, std::size_t cap) {
  Line l{out, cap};
  begin(l, 'M', r.ts, kit_id);
  l.field_f(r.lux, 1);
  l.field_f(r.temp_c, 2);
  l.field_f(r.rh_pct, 1);
  l.field_f(r.laeq_60s, 1);
  l.field_f(r.lamax_60s, 1);
  l.field_f(r.la90_60s, 1);
  l.field_f(r.batt_v, 2);
  char b[8];
  std::snprintf(b, sizeof b, ",0x%02x", static_cast<unsigned>(r.flags));
  l.raw(b);
  return l.finish();
}

std::size_t format_second(const char* kit_id, const SecondRecord& r, char* out, std::size_t cap) {
  Line l{out, cap};
  begin(l, 'S', r.ts, kit_id);
  l.field_f(r.laeq_1s, 1);
  return l.finish();
}

std::size_t format_octave(const char* kit_id, const OctaveRecord& r, char* out, std::size_t cap) {
  Line l{out, cap};
  begin(l, 'O', r.ts, kit_id);
  for (float v : r.band_db) l.field_f(v, 1);
  return l.finish();
}

std::size_t format_event(const char* kit_id, const EventRecord& r, char* out, std::size_t cap) {
  Line l{out, cap};
  begin(l, 'E', r.ts, kit_id);
  l.put(',');
  l.text(r.code);
  l.put(',');
  l.text(r.text);
  return l.finish();
}

uint32_t utc_yyyymmdd(uint32_t ts) {
  // Civil-from-days (H. Hinnant), valid for all uint32 timestamps.
  const int64_t z = static_cast<int64_t>(ts / 86400u) + 719468;
  const int64_t era = z / 146097;
  const int64_t doe = z - era * 146097;
  const int64_t yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
  const int64_t doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
  const int64_t mp = (5 * doy + 2) / 153;
  const int64_t d = doy - (153 * mp + 2) / 5 + 1;
  const int64_t m = mp < 10 ? mp + 3 : mp - 9;
  const int64_t y = yoe + era * 400 + (m <= 2 ? 1 : 0);
  return static_cast<uint32_t>(y * 10000 + m * 100 + d);
}

std::size_t log_filename(const char* kit_id, uint32_t ts, char* out, std::size_t cap) {
  Line l{out, cap};
  l.raw("/DWELL_");
  l.text(kit_id);
  char b[24];
  std::snprintf(b, sizeof b, "_%08lu.log", static_cast<unsigned long>(utc_yyyymmdd(ts)));
  l.raw(b);
  if (!l.ok || cap == 0) return 0;
  out[l.len] = '\0';
  return l.len;
}

}  // namespace dwell
