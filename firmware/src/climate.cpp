#include "climate.h"

#include <Arduino.h>
#include <cmath>

#include "dwell_config.h"
#include "sensor_math.h"

#ifdef DWELL_CLIMATE_BME280
#include <Adafruit_BME280.h>

namespace {
Adafruit_BME280 g_bme;
}

bool ClimateSensor::begin(TwoWire& wire) {
  if (!g_bme.begin(DWELL_BME280_ADDR, &wire)) return false;
  // Forced mode, x1 oversampling, no filter: one conversion per read() keeps self-heating minimal.
  g_bme.setSampling(Adafruit_BME280::MODE_FORCED, Adafruit_BME280::SAMPLING_X1, Adafruit_BME280::SAMPLING_X1,
                    Adafruit_BME280::SAMPLING_X1, Adafruit_BME280::FILTER_OFF);
  return true;
}

bool ClimateSensor::read(float* temp_c, float* rh_pct) {
  *temp_c = *rh_pct = NAN;
  if (!g_bme.takeForcedMeasurement()) return false;
  const float t = g_bme.readTemperature(), h = g_bme.readHumidity();
  if (std::isnan(t) || std::isnan(h)) return false;
  *temp_c = t;
  *rh_pct = h;
  return true;
}

const char* ClimateSensor::name() const { return "BME280"; }

#else  // SHT31

namespace {
TwoWire* g_wire = nullptr;
}

bool ClimateSensor::begin(TwoWire& wire) {
  g_wire = &wire;
  g_wire->beginTransmission(DWELL_SHT31_ADDR);
  g_wire->write(0x30);  // soft reset
  g_wire->write(0xA2);
  const bool ok = g_wire->endTransmission() == 0;
  delay(2);
  return ok;
}

bool ClimateSensor::read(float* temp_c, float* rh_pct) {
  *temp_c = *rh_pct = NAN;
  if (!g_wire) return false;
  g_wire->beginTransmission(DWELL_SHT31_ADDR);
  g_wire->write(0x24);  // single shot, high repeatability, no clock stretching
  g_wire->write(0x00);
  if (g_wire->endTransmission() != 0) return false;
  delay(16);  // max 15.5 ms
  uint8_t b[6];
  if (g_wire->requestFrom(static_cast<uint8_t>(DWELL_SHT31_ADDR), static_cast<uint8_t>(6)) != 6) return false;
  for (uint8_t& v : b) v = static_cast<uint8_t>(g_wire->read());
  if (dwell::sht31_crc8(b, 2) != b[2] || dwell::sht31_crc8(b + 3, 2) != b[5]) return false;
  *temp_c = dwell::sht31_temp_c(static_cast<uint16_t>((b[0] << 8) | b[1]));
  *rh_pct = dwell::sht31_rh_pct(static_cast<uint16_t>((b[3] << 8) | b[4]));
  return true;
}

const char* ClimateSensor::name() const { return "SHT31"; }

#endif
