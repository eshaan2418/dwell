// Pure sensor conversion / auto-ranging logic (host-testable; the I2C drivers live in src/).
#pragma once

#include <cstdint>

namespace dwell {

// ---------------- BH1750 auto-range ----------------
// lux = raw / 1.2 * (69 / MTreg) / (2 if H-res mode 2).  Default (MTreg 69, H-res) saturates at
// 65535 / 1.2 = 54612 lx. Range is extended for direct sun by lowering MTreg to its minimum 31,
// which scales the full scale to 54612 * 69/31 = 121557 lx (1.85 lx resolution). Note: the BH1750
// "L-res" mode does NOT extend range (same counts, 4 lx steps) - only MTreg does.
enum class Bh1750Range : uint8_t {
  kNight = 0,     // H-res2, MTreg 254: 0.11 lx steps, full scale 7417 lx
  kIndoor = 1,    // H-res2, MTreg 69: 0.42 lx steps, full scale 27306 lx
  kDefault = 2,   // H-res,  MTreg 69: 0.83 lx steps, full scale 54612 lx (datasheet default)
  kExtended = 3,  // H-res,  MTreg 31: 1.85 lx steps, full scale 121557 lx (sunlight)
};

struct Bh1750Mode {
  uint8_t command;     // one-time measurement opcode (0x20 H-res, 0x21 H-res2)
  uint8_t mtreg;       // measurement-time register
  uint16_t conv_ms;    // worst-case conversion time (datasheet max 180 ms @ MTreg 69, scaled) + margin
};

constexpr float kBh1750DefaultFullScaleLux = 65535.0f / 1.2f;  // 54612.5 lx

Bh1750Mode bh1750_mode(Bh1750Range r);
float bh1750_full_scale_lux(Bh1750Range r);
float bh1750_lux(Bh1750Range r, uint16_t raw);

struct Bh1750Step {
  bool accept;            // reading is usable (not saturated, or saturated in the top range)
  float lux;              // value when accepted
  bool saturated_flag;    // contributes to log flag 0x02 (above default-mode range / hard saturation)
  Bh1750Range next;       // range to use for the next measurement
};
// Decide what to do with a raw reading: switch up at >= 92 % of full scale (and discard
// saturated readings), switch down when the value would use < 40 % of the next-lower range.
Bh1750Step bh1750_step(Bh1750Range r, uint16_t raw);

// ---------------- SHT31 ----------------
uint8_t sht31_crc8(const uint8_t* data, int len);  // poly 0x31, init 0xFF
inline float sht31_temp_c(uint16_t raw) { return -45.0f + 175.0f * static_cast<float>(raw) / 65535.0f; }
inline float sht31_rh_pct(uint16_t raw) { return 100.0f * static_cast<float>(raw) / 65535.0f; }

}  // namespace dwell
