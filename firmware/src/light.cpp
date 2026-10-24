#include "light.h"

#include <Arduino.h>

bool LightSensor::begin(TwoWire& wire, uint8_t addr) {
  wire_ = &wire;
  addr_ = addr;
  ok_ = command(0x01) && command(0x07);  // power on, reset data register
  return ok_;
}

bool LightSensor::command(uint8_t c) {
  wire_->beginTransmission(addr_);
  wire_->write(c);
  return wire_->endTransmission() == 0;
}

bool LightSensor::start_measurement(uint32_t now_ms) {
  const dwell::Bh1750Mode m = dwell::bh1750_mode(range_);
  // MTreg is written as two opcodes: 01000_hhh (high 3 bits) and 011_lllll (low 5 bits).
  ok_ = command(0x01) && command(0x40 | (m.mtreg >> 5)) && command(0x60 | (m.mtreg & 0x1F)) && command(m.command);
  pending_ = ok_;
  started_ms_ = now_ms;
  return ok_;
}

bool LightSensor::poll(uint32_t now_ms, bool start) {
  if (!wire_) return false;
  if (!pending_) {
    if (start) start_measurement(now_ms);
    return false;
  }
  if (now_ms - started_ms_ < dwell::bh1750_mode(range_).conv_ms) return false;
  pending_ = false;
  if (wire_->requestFrom(addr_, static_cast<uint8_t>(2)) != 2) {
    ok_ = false;
    return false;
  }
  const int hi = wire_->read();  // two statements: operand evaluation order is unspecified
  const int lo = wire_->read();
  const uint16_t raw = static_cast<uint16_t>((hi << 8) | lo);
  ok_ = true;
  const dwell::Bh1750Step s = dwell::bh1750_step(range_, raw);
  range_ = s.next;
  if (!s.accept) {  // saturated count: re-measure immediately in the less sensitive range
    start_measurement(now_ms);
    return false;
  }
  lux_ = s.lux;
  saturated_ = s.saturated_flag;
  return true;
}
