// SD-card logger (+ optional HTTP POST to a LAN collector). Implements dwell::LogSink, so it only
// accepts the level/record structs from records.h - there is no API for raw buffers or samples.
#pragma once

#include <cstddef>
#include <cstdint>

#include "log_sink.h"

class SdLogger : public dwell::LogSink {
 public:
  bool begin(const dwell::HeaderInfo& header);
  void set_boot_ts(uint32_t boot_ts) { header_.boot_ts = boot_ts; }
  void set_mic_offset_db(float offset_db) { header_.mic_offset_db = offset_db; }

  void log(const dwell::MinuteRecord& r) override;
  void log(const dwell::SecondRecord& r) override;
  void log(const dwell::OctaveRecord& r) override;
  void log(const dwell::EventRecord& r) override;

  // Periodic work: timed flush, SD re-mount after removal. `net_up`: Wi-Fi connected.
  void loop(uint32_t now_ms, bool net_up);
  bool sd_ok() const { return sd_ok_; }
  uint32_t dropped_lines() const { return dropped_lines_; }

 private:
  static constexpr size_t kHeaderRoom = 192;  // space before the lines for the POST header line
  static constexpr size_t kBufSize = 16 * 1024;

  void append(uint32_t ts, const char* line, size_t n);
  void event(const char* code, const char* text);
  void flush(bool net_up);
  bool write_sd();
  bool post_http();
  bool mount();

  dwell::HeaderInfo header_{};
  char buf_[kHeaderRoom + kBufSize];
  size_t len_ = 0;           // bytes of log lines at buf_ + kHeaderRoom
  uint32_t buf_ts_ = 0;      // timestamp of the first buffered line (selects the daily file)
  uint32_t last_flush_ms_ = 0, last_mount_ms_ = 0;
  uint32_t dropped_lines_ = 0, reported_dropped_ = 0;
  bool sd_ok_ = false;
  bool upload_ = false;
  bool net_up_ = false;
};
