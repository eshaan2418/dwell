#include "timesync.h"

#include <Arduino.h>
#include <WiFi.h>
#include <cstring>
#include <ctime>
#include <esp_sntp.h>

#include "dwell_config.h"

namespace dwell_time {
namespace {

enum class State { kDisabled, kConnecting, kWaitSync, kIdle };
State g_state = State::kDisabled;
bool g_keep = false, g_synced = false;
uint32_t g_state_ms = 0, g_next_sync_ms = 0;
uint32_t g_boot_ts = 0;
uint32_t g_prev_now = 0, g_prev_ms = 0;  // clock reading on the previous kWaitSync pass
constexpr uint32_t kStepTimeoutMs = 30000, kRetryMs = 5UL * 60 * 1000;

void enter(State s, uint32_t now_ms) {
  g_state = s;
  g_state_ms = g_prev_ms = now_ms;
  g_prev_now = static_cast<uint32_t>(time(nullptr));
}

void connect(uint32_t now_ms) {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(DWELL_WIFI_SSID, DWELL_WIFI_PASSWORD);
  configTime(0, 0, DWELL_NTP_SERVER_1, DWELL_NTP_SERVER_2);  // UTC, no DST; (re)starts SNTP
  enter(State::kConnecting, now_ms);
}

void radio_off_until(uint32_t now_ms, uint32_t wait_ms) {
  if (!g_keep) {
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
  }
  g_next_sync_ms = now_ms + wait_ms;
  enter(State::kIdle, now_ms);
}

}  // namespace

void begin(bool keep_wifi) {
  g_keep = keep_wifi;
  if (std::strlen(DWELL_WIFI_SSID) == 0) {
    WiFi.mode(WIFI_OFF);
    g_state = State::kDisabled;
    return;
  }
  connect(millis());
}

void loop(uint32_t now_ms, dwell::LogSink& log) {
  switch (g_state) {
    case State::kDisabled:
      return;
    case State::kConnecting:
      if (WiFi.status() == WL_CONNECTED) {
        char t[64];
        snprintf(t, sizeof t, "ip=%s rssi=%d", WiFi.localIP().toString().c_str(),
                 static_cast<int>(WiFi.RSSI()));
        log.log(dwell::make_event(now(), "WIFI_UP", t));
        enter(State::kWaitSync, now_ms);
      } else if (now_ms - g_state_ms > kStepTimeoutMs) {
        log.log(dwell::make_event(now(), "WIFI_FAIL", "connect timeout"));
        radio_off_until(now_ms, kRetryMs);
      }
      return;
    case State::kWaitSync: {
      if (sntp_get_sync_status() == SNTP_SYNC_STATUS_COMPLETED) {
        const uint32_t after = now();
        // Clock step applied by this sync, relative to where the previous loop pass predicted.
        const int64_t before = static_cast<int64_t>(g_prev_now) + (now_ms - g_prev_ms) / 1000;
        if (!g_synced) g_boot_ts = after - millis() / 1000;
        g_synced = true;
        char t[64];
        snprintf(t, sizeof t, "server=%s step_s=%ld", DWELL_NTP_SERVER_1,
                 static_cast<long>(static_cast<int64_t>(after) - before));
        log.log(dwell::make_event(after, "NTP_SYNC", t));
        radio_off_until(now_ms, DWELL_NTP_RESYNC_HOURS * 3600UL * 1000UL);
      } else if (now_ms - g_state_ms > kStepTimeoutMs) {
        log.log(dwell::make_event(now(), "NTP_FAIL", "sync timeout"));
        radio_off_until(now_ms, kRetryMs);
      }
      g_prev_now = now();
      g_prev_ms = now_ms;
      return;
    }
    case State::kIdle:
      if (static_cast<int32_t>(now_ms - g_next_sync_ms) >= 0) {
        if (g_keep && WiFi.status() == WL_CONNECTED) {
          configTime(0, 0, DWELL_NTP_SERVER_1, DWELL_NTP_SERVER_2);
          enter(State::kWaitSync, now_ms);
        } else {
          connect(now_ms);
        }
      }
      return;
  }
}

bool synced() { return g_synced; }
bool wifi_up() { return WiFi.status() == WL_CONNECTED; }
uint32_t now() { return static_cast<uint32_t>(time(nullptr)); }
uint32_t boot_ts() { return g_boot_ts; }

}  // namespace dwell_time
