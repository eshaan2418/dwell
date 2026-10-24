// Selects include/config.h if present (git-ignored, per kit), else the committed example config.
#pragma once

#if __has_include("config.h")
#include "config.h"
#else
#include "config.example.h"
#endif

#define DWELL_FW_VERSION "0.1.0"
#define DWELL_SAMPLE_RATE 48000

// Fallbacks so an older config.h keeps building when new options are added.
#ifndef DWELL_COLLECTOR_URL
#define DWELL_COLLECTOR_URL ""
#endif
#ifndef DWELL_HTTP_TIMEOUT_MS
#define DWELL_HTTP_TIMEOUT_MS 3000
#endif
#ifndef DWELL_WIFI_KEEP_ON
#define DWELL_WIFI_KEEP_ON 0
#endif
#ifndef DWELL_NTP_RESYNC_HOURS
#define DWELL_NTP_RESYNC_HOURS 6
#endif
#ifndef DWELL_LOG_SECONDS
#define DWELL_LOG_SECONDS 1
#endif
#ifndef DWELL_LOG_OCTAVES
#define DWELL_LOG_OCTAVES 0
#endif
#ifndef DWELL_FLUSH_INTERVAL_S
#define DWELL_FLUSH_INTERVAL_S 60
#endif
#ifndef DWELL_LIGHT_PERIOD_S
#define DWELL_LIGHT_PERIOD_S 10
#endif
#ifndef DWELL_I2S_RIGHT_CHANNEL
#define DWELL_I2S_RIGHT_CHANNEL 0
#endif
