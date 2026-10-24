// BH1750 illuminance sensor with auto-ranging (see lib/dwell_core/sensor_math.h).
#pragma once

#include <Wire.h>

#include <cmath>

#include "sensor_math.h"

class LightSensor {
 public:
  bool begin(TwoWire& wire, uint8_t addr);
  // Non-blocking state machine: starts a one-time measurement when `start` is true and none is
  // pending, and collects it after the conversion time. Returns true when a reading was accepted.
  bool poll(uint32_t now_ms, bool start);
  float lux() const { return lux_; }
  bool saturated() const { return saturated_; }  // last accepted reading sets flag 0x02
  bool ok() const { return ok_; }
  bool busy() const { return pending_; }

 private:
  bool command(uint8_t c);
  bool start_measurement(uint32_t now_ms);

  TwoWire* wire_ = nullptr;
  uint8_t addr_ = 0x23;
  dwell::Bh1750Range range_ = dwell::Bh1750Range::kIndoor;
  bool pending_ = false;
  uint32_t started_ms_ = 0;
  float lux_ = NAN;
  bool saturated_ = false;
  bool ok_ = false;
};
