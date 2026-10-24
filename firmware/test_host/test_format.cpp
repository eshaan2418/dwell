// Log line formatting (docs/SENSOR_LOG_FORMAT.md) and sensor conversion tests.
#include <algorithm>
#include <cmath>
#include <cstring>
#include <string>
#include <vector>

#include "harness.h"
#include "log_format.h"
#include "sensor_math.h"

using namespace dwell;

namespace {

// Parse a data line the way ingest/ does: strip '\n', split on ',', keep empty fields.
std::vector<std::string> split(const char* line) {
  std::string s(line);
  CHECK(!s.empty() && s.back() == '\n');
  CHECK(std::count(s.begin(), s.end(), '\n') == 1);
  s.pop_back();
  std::vector<std::string> f;
  std::size_t start = 0;
  for (std::size_t i = 0; i <= s.size(); ++i) {
    if (i == s.size() || s[i] == ',') {
      f.push_back(s.substr(start, i - start));
      start = i + 1;
    }
  }
  return f;
}

}  // namespace

TEST_CASE("M/S/O/E lines parse with the documented field counts and values") {
  char buf[kMaxLineLen];
  MinuteRecord m{1792886400u, 123.456f, 21.2349f, 45.66f, 41.26f, 55.04f, 33.95f, NAN, 0x05};
  CHECK(format_minute("KIT07", m, buf, sizeof buf) == std::strlen(buf));
  std::vector<std::string> f = split(buf);
  CHECK(f.size() == 11);
  CHECK(f[0] == "M" && f[1] == "1792886400" && f[2] == "KIT07");
  CHECK(f[3] == "123.5" && f[4] == "21.23" && f[5] == "45.7");
  CHECK(f[6] == "41.3" && f[7] == "55.0" && f[8] == "34.0");
  CHECK(f[9].empty());  // missing battery voltage -> empty field
  CHECK(f[10] == "0x05" && std::stoul(f[10], nullptr, 16) == 5);

  MinuteRecord empty{60, NAN, NAN, NAN, NAN, NAN, NAN, NAN, 0x09};
  format_minute("K", empty, buf, sizeof buf);
  CHECK(std::string(buf) == "M,60,K,,,,,,,,0x09\n");

  format_second("KIT07", SecondRecord{1792886401u, 38.04f}, buf, sizeof buf);
  f = split(buf);
  CHECK(f.size() == 4 && f[0] == "S" && f[3] == "38.0");
  format_second("KIT07", SecondRecord{5, -0.04f}, buf, sizeof buf);
  CHECK(split(buf)[3] == "0.0");  // no "-0.0"

  OctaveRecord o{1792886460u, {50, 48.25f, 45, 40, 35, 30, 25, NAN}};
  format_octave("KIT07", o, buf, sizeof buf);
  f = split(buf);
  CHECK(f.size() == 11 && f[0] == "O" && f[4] == "48.3" && f[10].empty());

  format_event("KIT07", make_event(1792886400u, "NTP_SYNC", "server=pool.ntp.org, offset\nok"), buf,
               sizeof buf);
  f = split(buf);
  CHECK(f.size() == 5 && f[0] == "E" && f[3] == "NTP_SYNC" && f[4] == "server=pool.ntp.org; offset ok");
}

TEST_CASE("Header line format") {
  HeaderInfo h{};
  std::strcpy(h.fw_version, "0.1.0");
  std::strcpy(h.kit_id, "KIT07");
  h.mic_offset_db = -1.25f;
  h.sample_rate = 48000;
  h.boot_ts = 1792886000u;
  char buf[kMaxLineLen];
  format_header(h, buf, sizeof buf);
  CHECK(std::string(buf) ==
        "# dwell-fw 0.1.0 kit=KIT07 mic_offset_db=-1.25 sample_rate=48000 boot=1792886000\n");
}

TEST_CASE("Too-small buffers fail cleanly; UTC date and file name") {
  char tiny[8];
  CHECK(format_second("KIT07", SecondRecord{1792886401u, 38.0f}, tiny, sizeof tiny) == 0);
  CHECK(tiny[0] == '\0');
  CHECK(utc_yyyymmdd(0) == 19700101u);
  CHECK(utc_yyyymmdd(951782400u) == 20000229u);   // leap day
  CHECK(utc_yyyymmdd(1792886399u) == 20261024u);  // 2026-10-24 23:59:59 UTC
  CHECK(utc_yyyymmdd(1792886400u) == 20261025u);  // rotation at UTC midnight
  CHECK(utc_day(1792886399u) != utc_day(1792886400u));
  char name[48];
  CHECK(log_filename("KIT07", 1792886399u, name, sizeof name) > 0);
  CHECK(std::string(name) == "/DWELL_KIT07_20261024.log");
}

TEST_CASE("BH1750 auto-range: conversions, range switching, saturation flag") {
  CHECK_NEAR(bh1750_full_scale_lux(Bh1750Range::kDefault), 54612.5, 0.1);
  CHECK_NEAR(bh1750_full_scale_lux(Bh1750Range::kExtended), 121556.5, 1.0);
  CHECK_NEAR(bh1750_lux(Bh1750Range::kIndoor, 1200), 500.0, 1e-3);
  // Sunlight: saturated default-range reading is discarded, next measurement in extended range.
  Bh1750Step s = bh1750_step(Bh1750Range::kDefault, 65535);
  CHECK(!s.accept && s.next == Bh1750Range::kExtended);
  s = bh1750_step(Bh1750Range::kExtended, 40000);  // 40000/1.2*69/31 = 74194 lx
  CHECK(s.accept && s.saturated_flag && s.next == Bh1750Range::kExtended);
  CHECK_NEAR(s.lux, 74193.5, 1.0);
  s = bh1750_step(Bh1750Range::kExtended, 65535);  // beyond ~121.6 klx: clipped value, flagged
  CHECK(s.accept && s.saturated_flag);
  s = bh1750_step(Bh1750Range::kExtended, 5000);  // 9274 lx -> step down to the default range
  CHECK(s.accept && !s.saturated_flag && s.next == Bh1750Range::kDefault);
  s = bh1750_step(Bh1750Range::kNight, 30);
  CHECK(s.accept && s.next == Bh1750Range::kNight);
  CHECK_NEAR(s.lux, 30 / 1.2 / 2 * 69.0 / 254.0, 1e-3);  // 3.40 lx, 0.11 lx steps
  s = bh1750_step(Bh1750Range::kNight, 61000);
  CHECK(s.accept && s.next == Bh1750Range::kIndoor);
}

TEST_CASE("SHT31 CRC and conversion") {
  const uint8_t example[] = {0xBE, 0xEF};  // datasheet example: CRC = 0x92
  CHECK(sht31_crc8(example, 2) == 0x92);
  CHECK_NEAR(sht31_temp_c(0x6666), -45.0 + 175.0 * 0x6666 / 65535.0, 1e-4);
  CHECK_NEAR(sht31_rh_pct(65535), 100.0, 1e-4);
}
