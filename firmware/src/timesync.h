// Wi-Fi + NTP (UTC). Wi-Fi is used only for time sync and the optional LAN upload.
#pragma once

#include <cstdint>

#include "log_sink.h"

namespace dwell_time {

// keep_wifi: leave the radio on after sync (required for LAN upload).
void begin(bool keep_wifi);
// Drives the connect -> sync -> (radio off) -> periodic re-sync state machine; logs WIFI_UP/NTP_SYNC.
void loop(uint32_t now_ms, dwell::LogSink& log);
bool synced();  // at least one successful NTP sync since boot
bool wifi_up();
uint32_t now();  // Unix seconds UTC (seconds since boot + 0 before the first sync)
// Unix time of boot (valid after sync), for the log header.
uint32_t boot_ts();

}  // namespace dwell_time
