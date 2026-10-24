#include "logger.h"

#include <Arduino.h>
#include <HTTPClient.h>
#include <SD.h>
#include <SPI.h>
#include <WiFi.h>
#include <cstring>
#include <ctime>

#include "dwell_config.h"
#include "log_format.h"

namespace {
SPIClass g_spi(VSPI);
constexpr uint32_t kRemountIntervalMs = 10000;
}  // namespace

bool SdLogger::begin(const dwell::HeaderInfo& header) {
  header_ = header;
  upload_ = std::strlen(DWELL_COLLECTOR_URL) > 0;
  g_spi.begin(DWELL_PIN_SD_SCK, DWELL_PIN_SD_MISO, DWELL_PIN_SD_MOSI, DWELL_PIN_SD_CS);
  return mount();
}

bool SdLogger::mount() {
  last_mount_ms_ = millis();
  SD.end();
  sd_ok_ = SD.begin(DWELL_PIN_SD_CS, g_spi, 10000000) && SD.cardType() != CARD_NONE;
  return sd_ok_;
}

void SdLogger::log(const dwell::MinuteRecord& r) {
  char line[dwell::kMaxLineLen];
  append(r.ts, line, dwell::format_minute(header_.kit_id, r, line, sizeof line));
}

void SdLogger::log(const dwell::SecondRecord& r) {
  char line[dwell::kMaxLineLen];
  append(r.ts, line, dwell::format_second(header_.kit_id, r, line, sizeof line));
}

void SdLogger::log(const dwell::OctaveRecord& r) {
  char line[dwell::kMaxLineLen];
  append(r.ts, line, dwell::format_octave(header_.kit_id, r, line, sizeof line));
}

void SdLogger::log(const dwell::EventRecord& r) {
  char line[dwell::kMaxLineLen];
  append(r.ts, line, dwell::format_event(header_.kit_id, r, line, sizeof line));
}

void SdLogger::event(const char* code, const char* text) {
  log(dwell::make_event(static_cast<uint32_t>(time(nullptr)), code, text));
}

void SdLogger::append(uint32_t ts, const char* line, size_t n) {
  if (n == 0) return;
  // Daily rotation (UTC): a buffer never spans two days, so it maps to exactly one file.
  const bool new_day = len_ > 0 && dwell::utc_day(ts) != dwell::utc_day(buf_ts_);
  if (new_day || len_ + n > kBufSize) flush(net_up_);
  // Still not empty: the flush failed (SD out, no upload). Drop the old batch rather than mixing
  // two days in one buffer or overflowing; the loss is reported as a LOG_DROPPED event.
  if (len_ > 0 && (new_day || len_ + n > kBufSize)) {
    for (size_t i = 0; i < len_; ++i) dropped_lines_ += buf_[kHeaderRoom + i] == '\n';
    len_ = 0;
  }
  if (len_ == 0) buf_ts_ = ts;
  std::memcpy(buf_ + kHeaderRoom + len_, line, n);
  len_ += n;
}

bool SdLogger::write_sd() {
  char path[64];
  if (dwell::log_filename(header_.kit_id, buf_ts_, path, sizeof path) == 0) return false;
  const bool fresh = !SD.exists(path);
  // Open-append-close per flush: no file handle is held open, so pulling the card loses at most
  // the RAM buffer that is retried after re-mount.
  File f = SD.open(path, FILE_APPEND);
  if (!f) return false;
  bool ok = true;
  if (fresh) {
    char h[dwell::kMaxLineLen];
    const size_t hn = dwell::format_header(header_, h, sizeof h);
    ok = f.write(reinterpret_cast<const uint8_t*>(h), hn) == hn;
  }
  ok = ok && f.write(reinterpret_cast<const uint8_t*>(buf_ + kHeaderRoom), len_) == len_;
  f.close();
  return ok;
}

bool SdLogger::post_http() {
  // Body = header line + buffered lines (same text as on the SD card). The header is placed in
  // the reserved room directly in front of the lines to avoid a second buffer.
  char h[kHeaderRoom];
  const size_t hn = dwell::format_header(header_, h, sizeof h);
  if (hn == 0) return false;
  char* body = buf_ + kHeaderRoom - hn;
  std::memcpy(body, h, hn);
  HTTPClient http;
  http.setConnectTimeout(DWELL_HTTP_TIMEOUT_MS);
  http.setTimeout(DWELL_HTTP_TIMEOUT_MS);
  if (!http.begin(DWELL_COLLECTOR_URL)) return false;
  http.addHeader("Content-Type", "text/plain; charset=utf-8");
  const int code = http.POST(reinterpret_cast<uint8_t*>(body), hn + len_);
  http.end();
  return code >= 200 && code < 300;
}

void SdLogger::flush(bool net_up) {
  if (len_ == 0) return;
  last_flush_ms_ = millis();
  bool stored = false;
  if (sd_ok_) {
    stored = write_sd();
    if (!stored) {
      sd_ok_ = false;
      SD.end();
    }
  }
  const bool posted = upload_ && net_up && post_http();
  if (stored || posted) len_ = 0;  // otherwise keep the batch for a retry after re-mount
}

void SdLogger::loop(uint32_t now_ms, bool net_up) {
  net_up_ = net_up;
  if (!sd_ok_ && now_ms - last_mount_ms_ >= kRemountIntervalMs) {
    if (mount()) event("SD_MOUNTED", "card re-mounted");
  }
  if (len_ > 0 && (now_ms - last_flush_ms_ >= DWELL_FLUSH_INTERVAL_S * 1000UL || len_ > kBufSize * 3 / 4)) {
    const bool was_ok = sd_ok_;
    flush(net_up);
    if (was_ok && !sd_ok_) event("SD_ERROR", "write failed; buffering in RAM");
  }
  if (dropped_lines_ != reported_dropped_) {
    char t[48];
    snprintf(t, sizeof t, "lines_dropped_total=%lu", static_cast<unsigned long>(dropped_lines_));
    reported_dropped_ = dropped_lines_;
    event("LOG_DROPPED", t);
  }
}
