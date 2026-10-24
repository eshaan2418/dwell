#include "level_stats.h"

#include <algorithm>
#include <cmath>

namespace dwell {

double energetic_mean_db(const float* levels_db, std::size_t n) {
  double sum = 0;
  std::size_t k = 0;
  for (std::size_t i = 0; i < n; ++i) {
    if (std::isnan(levels_db[i])) continue;
    sum += std::pow(10.0, levels_db[i] / 10.0);
    ++k;
  }
  return k ? 10.0 * std::log10(sum / static_cast<double>(k)) : NAN;
}

float exceedance_level_db(const float* levels_db, std::size_t n, double percent_exceeded) {
  float v[MinuteAudioStats::kMaxSeconds];
  std::size_t k = 0;
  for (std::size_t i = 0; i < n && k < MinuteAudioStats::kMaxSeconds; ++i) {
    if (!std::isnan(levels_db[i])) v[k++] = levels_db[i];
  }
  if (k == 0) return NAN;
  std::sort(v, v + k);
  std::size_t idx = static_cast<std::size_t>(std::floor((100.0 - percent_exceeded) / 100.0 * k + 1e-9));
  return v[std::min(idx, k - 1)];
}

void MinuteAudioStats::reset() {
  count_ = 0;
  end_ts_ = 0;
  clipped_ = false;
}

void MinuteAudioStats::add(uint32_t ts, const SecondLevels& s) {
  if (count_ == 0) end_ts_ = minute_end_for(ts);
  if (count_ >= kMaxSeconds) return;  // clock hiccup: more than 60 seconds mapped to one minute
  la_[count_] = s.valid ? s.laeq_1s : NAN;
  for (int b = 0; b < kNumOctaveBands; ++b) band_[b][count_] = s.valid ? s.band_leq_1s[b] : NAN;
  clipped_ = clipped_ || (s.valid && s.clipped_samples > 0);
  ++count_;
}

MinuteAudio MinuteAudioStats::summarize() const {
  MinuteAudio m{};
  const std::size_t n = static_cast<std::size_t>(count_);
  m.laeq_60s = static_cast<float>(energetic_mean_db(la_, n));
  m.lamax_60s = NAN;
  m.seconds = 0;
  for (std::size_t i = 0; i < n; ++i) {
    if (std::isnan(la_[i])) continue;
    ++m.seconds;
    if (std::isnan(m.lamax_60s) || la_[i] > m.lamax_60s) m.lamax_60s = la_[i];
  }
  m.la90_60s = exceedance_level_db(la_, n, 90.0);
  for (int b = 0; b < kNumOctaveBands; ++b)
    m.band_leq_60s[b] = static_cast<float>(energetic_mean_db(band_[b], n));
  m.clipped = clipped_;
  return m;
}

}  // namespace dwell
