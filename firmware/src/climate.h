// Temperature / relative humidity: SHT31 (default) or BME280 (build flag DWELL_CLIMATE_BME280).
#pragma once

#include <Wire.h>

class ClimateSensor {
 public:
  bool begin(TwoWire& wire);
  // Blocking single-shot read (~16 ms on SHT31). On failure both outputs are NAN and false is returned.
  bool read(float* temp_c, float* rh_pct);
  const char* name() const;
};
