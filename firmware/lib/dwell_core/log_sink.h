// Abstract logger interface. It accepts ONLY the record structs from records.h - never sample
// pointers, sample arrays or raw byte buffers (enforced by static_asserts in test_host/test_api.cpp
// and by tools/check_no_raw_audio.py).
#pragma once

#include "records.h"

namespace dwell {

class LogSink {
 public:
  virtual ~LogSink() = default;
  virtual void log(const MinuteRecord& r) = 0;
  virtual void log(const SecondRecord& r) = 0;
  virtual void log(const OctaveRecord& r) = 0;
  virtual void log(const EventRecord& r) = 0;
};

}  // namespace dwell
