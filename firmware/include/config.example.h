// Dwell per-kit configuration - EXAMPLE.
// Copy to include/config.h (git-ignored) and edit. If config.h is absent the build uses this file.
#pragma once

// ---- Identity ----
#define DWELL_KIT_ID "KIT00"  // letters/digits/underscore only; appears in every log line and file name

// ---- Wi-Fi: used ONLY for NTP time sync and the optional LAN upload. Leave SSID empty for offline. ----
#define DWELL_WIFI_SSID ""
#define DWELL_WIFI_PASSWORD ""
#define DWELL_NTP_SERVER_1 "pool.ntp.org"
#define DWELL_NTP_SERVER_2 "time.nist.gov"
#define DWELL_WIFI_KEEP_ON 0       // 0: radio off after sync (less self-heating/RF); forced on if uploading
#define DWELL_NTP_RESYNC_HOURS 6   // re-connect and re-sync this often when the radio is kept off

// ---- Optional LAN collector on the occupant's own machine (empty = SD card only) ----
// Lines are POSTed as text/plain batches, e.g. "http://192.168.1.50:8765/dwell/ingest".
#define DWELL_COLLECTOR_URL ""
#define DWELL_HTTP_TIMEOUT_MS 3000

// ---- Logging ----
#define DWELL_LOG_SECONDS 1          // S lines (1-s L_Aeq), default on
#define DWELL_LOG_OCTAVES 0          // O lines (octave bands 63 Hz-8 kHz); costs ~25 % of one core
#define DWELL_FLUSH_INTERVAL_S 60    // RAM buffer -> SD at least this often
#define DWELL_LIGHT_PERIOD_S 10      // BH1750 reads per minute = 60 / period (averaged into M)

// ---- Calibration default (overridden by the value stored in NVS via the serial "cal" command) ----
#define DWELL_DEFAULT_MIC_OFFSET_DB 0.0f

// ---- Pins (ESP32-DevKitC / WROOM-32) ----
#define DWELL_PIN_I2C_SDA 21
#define DWELL_PIN_I2C_SCL 22
#define DWELL_PIN_I2S_SCK 26   // INMP441 SCK (bit clock)
#define DWELL_PIN_I2S_WS 25    // INMP441 WS (word select / LRCLK)
#define DWELL_PIN_I2S_SD 33    // INMP441 SD (data out)
#define DWELL_I2S_RIGHT_CHANNEL 0  // INMP441 L/R pin: GND -> 0 (left). Set 1 if L/R tied to VDD.
#define DWELL_PIN_SD_CS 5
#define DWELL_PIN_SD_SCK 18
#define DWELL_PIN_SD_MISO 19
#define DWELL_PIN_SD_MOSI 23
#define DWELL_PIN_BATT_ADC 35      // -1 if not battery powered (batt_v field left empty)
#define DWELL_BATT_DIVIDER 2.0f    // 100k/100k divider from the cell to the ADC pin
#define DWELL_LOW_BATT_V 3.40f     // below this, flag 0x10
#define DWELL_PIN_LED 2

// ---- Climate sensor: SHT31 by default. For BME280 build env esp32dev_bme280 (-DDWELL_CLIMATE_BME280). ----
#define DWELL_SHT31_ADDR 0x44
#define DWELL_BME280_ADDR 0x76
#define DWELL_BH1750_ADDR 0x23
