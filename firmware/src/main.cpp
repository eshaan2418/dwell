// Dwell sensor kit firmware: light (BH1750), climate (SHT31/BME280), sound levels (INMP441).
// Output format: docs/SENSOR_LOG_FORMAT.md. No audio samples ever leave src/audio_input.cpp.
#include <Arduino.h>
#include <Wire.h>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <esp_system.h>

#include "audio_input.h"
#include "calibration.h"
#include "climate.h"
#include "dwell_config.h"
#include "level_stats.h"
#include "light.h"
#include "logger.h"
#include "timesync.h"

namespace {

SdLogger g_log;
LightSensor g_light;
ClimateSensor g_climate;
dwell::MinuteAudioStats g_minute;

float g_mic_offset_db = 0;
bool g_audio_ok = false, g_brownout_boot = false, g_mic_error_logged = false;
uint32_t g_last_ts = 0;                       // timestamp of the previous 1-s interval
uint32_t g_last_audio_ms = 0, g_last_fake_ms = 0, g_light_start_ms = 0;
double g_lux_sum = 0;
uint32_t g_lux_n = 0;
bool g_lux_saturated = false;
float g_last_laeq = NAN;

void event(const char* code, const char* text) { g_log.log(dwell::make_event(dwell_time::now(), code, text)); }

// 1-s blocks come from the I2S clock, not the RTC: keep consecutive timestamps unless the clock
// moved by more than 1 s (NTP step, drift), then re-align.
uint32_t next_second_ts() {
  const uint32_t now = dwell_time::now();
  const uint32_t expected = g_last_ts + 1;
  g_last_ts = (g_last_ts != 0 && std::labs(static_cast<long>(now) - static_cast<long>(expected)) <= 1) ? expected : now;
  return g_last_ts;
}

float read_battery_v() {
  if (DWELL_PIN_BATT_ADC < 0) return NAN;
  uint32_t mv = 0;
  for (int i = 0; i < 8; ++i) mv += analogReadMilliVolts(DWELL_PIN_BATT_ADC);
  const float v = mv / 8.0f / 1000.0f * DWELL_BATT_DIVIDER;
  return v < 0.5f ? NAN : v;  // no cell connected (USB only)
}

void close_minute(uint32_t end_ts) {
  const dwell::MinuteAudio a = g_minute.summarize();
  dwell::MinuteRecord r{};
  r.ts = end_ts;
  r.lux = g_lux_n ? static_cast<float>(g_lux_sum / g_lux_n) : NAN;
  const bool climate_ok = g_climate.read(&r.temp_c, &r.rh_pct);
  r.laeq_60s = a.laeq_60s;
  r.lamax_60s = a.lamax_60s;
  r.la90_60s = a.la90_60s;
  r.batt_v = read_battery_v();
  uint8_t f = 0;
  if (!dwell_time::synced()) f |= dwell::kFlagTimeNotSynced;
  if (g_lux_saturated) f |= dwell::kFlagLightSaturated;
  if (a.clipped) f |= dwell::kFlagMicClipping;
  if (!climate_ok) f |= dwell::kFlagClimateError;
  if (g_brownout_boot || (!std::isnan(r.batt_v) && r.batt_v < DWELL_LOW_BATT_V)) f |= dwell::kFlagBrownoutLowBattery;
  r.flags = f;
  g_log.log(r);
  if (DWELL_LOG_OCTAVES) {
    dwell::OctaveRecord o{};
    o.ts = end_ts;
    for (int b = 0; b < dwell::kNumOctaveBands; ++b) o.band_db[b] = a.band_leq_60s[b];
    g_log.log(o);
  }
  g_minute.reset();
  g_lux_sum = 0;
  g_lux_n = 0;
  g_lux_saturated = false;
  g_brownout_boot = false;
}

void handle_second(const dwell::SecondLevels& lv) {
  const uint32_t ts = next_second_ts();
  if (lv.valid) g_last_laeq = lv.laeq_1s;
  if (DWELL_LOG_SECONDS) g_log.log(dwell::SecondRecord{ts, lv.valid ? lv.laeq_1s : NAN});
  if (g_minute.belongs_elsewhere(ts)) close_minute(g_minute.end_ts());  // clock jumped mid-minute
  g_minute.add(ts, lv);
  if (g_minute.complete_at(ts)) close_minute(ts);
}

// Serial console: "cal <offset_db>" stores the microphone calibration offset in NVS; "status".
void poll_console() {
  static char line[48];
  static size_t n = 0;
  while (Serial.available()) {
    const char c = static_cast<char>(Serial.read());
    if (c != '\n' && c != '\r') {
      if (n + 1 < sizeof line) line[n++] = c;
      continue;
    }
    line[n] = '\0';
    n = 0;
    if (std::strncmp(line, "cal ", 4) == 0) {
      const float v = std::strtof(line + 4, nullptr);
      if (dwell_cal::store_mic_offset_db(v)) {
        char t[64];
        snprintf(t, sizeof t, "mic_offset_db=%.2f previous=%.2f", v, g_mic_offset_db);
        g_mic_offset_db = v;
        dwell_audio::set_mic_offset_db(v);
        g_log.set_mic_offset_db(v);
        event("CAL_OFFSET_SET", t);
        Serial.printf("ok %s\n", t);
      } else {
        Serial.println("error: offset must be within +-20 dB");
      }
    } else if (std::strcmp(line, "status") == 0) {
      Serial.printf("kit=%s fw=%s t=%lu ntp=%d sd=%d audio=%d mic_offset_db=%.2f last_laeq_1s=%.1f lux=%.1f "
                    "dropped_s=%lu dropped_lines=%lu\n",
                    DWELL_KIT_ID, DWELL_FW_VERSION, static_cast<unsigned long>(dwell_time::now()),
                    dwell_time::synced(), g_log.sd_ok(), g_audio_ok, g_mic_offset_db, g_last_laeq, g_light.lux(),
                    static_cast<unsigned long>(dwell_audio::dropped_seconds()),
                    static_cast<unsigned long>(g_log.dropped_lines()));
    } else if (line[0]) {
      Serial.println("commands: cal <offset_db> | status");
    }
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);
  pinMode(DWELL_PIN_LED, OUTPUT);
  digitalWrite(DWELL_PIN_LED, LOW);  // keep LEDs dark: they would bias the light sensor
  g_brownout_boot = esp_reset_reason() == ESP_RST_BROWNOUT;
  g_mic_offset_db = dwell_cal::load_mic_offset_db();

  Wire.begin(DWELL_PIN_I2C_SDA, DWELL_PIN_I2C_SCL, 100000);
  const bool light_ok = g_light.begin(Wire, DWELL_BH1750_ADDR);
  const bool climate_ok = g_climate.begin(Wire);

  dwell::HeaderInfo h{};
  std::strncpy(h.fw_version, DWELL_FW_VERSION, sizeof(h.fw_version) - 1);
  std::strncpy(h.kit_id, DWELL_KIT_ID, sizeof(h.kit_id) - 1);
  h.mic_offset_db = g_mic_offset_db;
  h.sample_rate = DWELL_SAMPLE_RATE;
  h.boot_ts = dwell_time::now();
  const bool sd_ok = g_log.begin(h);

  g_audio_ok = dwell_audio::begin(g_mic_offset_db, DWELL_LOG_OCTAVES);
  dwell_time::begin(DWELL_WIFI_KEEP_ON || std::strlen(DWELL_COLLECTOR_URL) > 0);

  char t[96];
  snprintf(t, sizeof t, "reset=%d light=%d climate=%s:%d sd=%d audio=%d mic_offset_db=%.2f",
           static_cast<int>(esp_reset_reason()), light_ok, g_climate.name(), climate_ok, sd_ok, g_audio_ok,
           g_mic_offset_db);
  event("BOOT", t);
  if (!sd_ok) event("SD_ERROR", "no card at boot");
  Serial.printf("dwell-fw %s kit=%s %s\n", DWELL_FW_VERSION, DWELL_KIT_ID, t);
  g_last_audio_ms = g_last_fake_ms = millis();
}

void loop() {
  const uint32_t now_ms = millis();
  const bool was_synced = dwell_time::synced();
  dwell_time::loop(now_ms, g_log);
  if (!was_synced && dwell_time::synced()) g_log.set_boot_ts(dwell_time::boot_ts());

  const bool want_light = now_ms - g_light_start_ms >= DWELL_LIGHT_PERIOD_S * 1000UL;
  if (want_light && !g_light.busy()) g_light_start_ms = now_ms;
  if (g_light.poll(now_ms, want_light)) {
    g_lux_sum += g_light.lux();
    ++g_lux_n;
    g_lux_saturated = g_lux_saturated || g_light.saturated();
  }

  dwell::SecondLevels lv;
  while (dwell_audio::receive(&lv)) {
    g_last_audio_ms = now_ms;
    g_mic_error_logged = false;
    handle_second(lv);
  }
  // No audio (mic missing / I2S failure): keep the minute clock running so light and climate are
  // still logged; sound fields stay empty.
  if (now_ms - g_last_audio_ms > 3000 && now_ms - g_last_fake_ms >= 1000) {
    if (!g_mic_error_logged) event("MIC_ERROR", "no audio levels for 3 s");
    g_mic_error_logged = true;
    g_last_fake_ms = now_ms;
    dwell::SecondLevels none{};
    none.valid = false;
    handle_second(none);
  }

  poll_console();
  g_log.loop(now_ms, dwell_time::wifi_up());
  delay(5);
}
