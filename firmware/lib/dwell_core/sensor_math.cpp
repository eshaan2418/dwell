#include "sensor_math.h"

namespace dwell {

Bh1750Mode bh1750_mode(Bh1750Range r) {
  switch (r) {
    case Bh1750Range::kNight:
      return {0x21, 254, 180 * 254 / 69 + 20};
    case Bh1750Range::kIndoor:
      return {0x21, 69, 200};
    case Bh1750Range::kDefault:
      return {0x20, 69, 200};
    case Bh1750Range::kExtended:
    default:
      return {0x20, 31, 180 * 31 / 69 + 20};
  }
}

float bh1750_lux(Bh1750Range r, uint16_t raw) {
  const Bh1750Mode m = bh1750_mode(r);
  float lux = static_cast<float>(raw) / 1.2f * (69.0f / static_cast<float>(m.mtreg));
  return m.command == 0x21 ? lux * 0.5f : lux;
}

float bh1750_full_scale_lux(Bh1750Range r) { return bh1750_lux(r, 65535); }

Bh1750Step bh1750_step(Bh1750Range r, uint16_t raw) {
  Bh1750Step s{true, bh1750_lux(r, raw), false, r};
  const int idx = static_cast<int>(r);
  if (raw >= 60000 && r != Bh1750Range::kExtended) {  // ~92 % of full scale: go less sensitive
    s.next = static_cast<Bh1750Range>(idx + 1);
    s.accept = raw < 65535;  // a saturated count is not a measurement; re-measure in the next range
  } else if (idx > 0 && s.lux < 0.4f * bh1750_full_scale_lux(static_cast<Bh1750Range>(idx - 1))) {
    s.next = static_cast<Bh1750Range>(idx - 1);
  }
  // Flag 0x02: the scene exceeded the default high-res range (> 54612 lx), so the value came from
  // the extended MTreg range - or the extended range itself saturated (value clipped at 121557 lx).
  s.saturated_flag =
      s.accept && (s.lux > kBh1750DefaultFullScaleLux || (r == Bh1750Range::kExtended && raw == 65535));
  return s;
}

uint8_t sht31_crc8(const uint8_t* data, int len) {
  uint8_t crc = 0xFF;
  for (int i = 0; i < len; ++i) {
    crc ^= data[i];
    for (int b = 0; b < 8; ++b)
      crc = (crc & 0x80) ? static_cast<uint8_t>((crc << 1) ^ 0x31) : static_cast<uint8_t>(crc << 1);
  }
  return crc;
}

}  // namespace dwell
