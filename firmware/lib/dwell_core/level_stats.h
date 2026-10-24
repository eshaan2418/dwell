// Per-minute statistics over 1-s levels (platform independent). Input and output are dB levels only.
#pragma once

#include <cstddef>
#include <cstdint>

#include "audio_dsp.h"

namespace dwell {

// Energetic (power) mean of levels: 10 log10(mean(10^(L/10))). NAN entries are skipped; NAN if none.
double energetic_mean_db(const float* levels_db, std::size_t n);
// Statistical level L_N exceeded N % of the time: sort ascending and take the value at index
// floor((100 - N)/100 * n_valid), so that >= N % of the values are at or above it. For n = 60 and
// N = 90 this is the 7th-lowest value. NAN entries are skipped; NAN if none.
float exceedance_level_db(const float* levels_db, std::size_t n, double percent_exceeded);

struct MinuteAudio {
  float laeq_60s;                     // energetic mean of the valid 1-s L_Aeq values
  float lamax_60s;                    // max of the 1-s L_Aeq values (L_AFmax approximated at 1-s resolution)
  float la90_60s;                     // level exceeded by 90 % of the 1-s values
  float band_leq_60s[kNumOctaveBands];  // energetic mean of 1-s octave levels
  uint32_t seconds;                   // number of valid seconds that contributed
  bool clipped;                       // any clipped sample during the minute
};

// Collects up to 60 SecondLevels belonging to the UTC minute (end_ts - 60, end_ts].
class MinuteAudioStats {
 public:
  static constexpr int kMaxSeconds = 60;
  // Minute end (multiple of 60) for the 1-s interval ending at ts.
  static uint32_t minute_end_for(uint32_t ts) { return ((ts + 59) / 60) * 60; }

  void reset();
  // True if a second ending at ts belongs to a different minute than the one being collected.
  bool belongs_elsewhere(uint32_t ts) const { return count_ > 0 && minute_end_for(ts) != end_ts_; }
  void add(uint32_t ts, const SecondLevels& s);
  bool complete_at(uint32_t ts) const { return count_ > 0 && ts == end_ts_; }
  int count() const { return count_; }
  uint32_t end_ts() const { return end_ts_; }
  MinuteAudio summarize() const;

 private:
  float la_[kMaxSeconds] = {};
  float band_[kNumOctaveBands][kMaxSeconds] = {};
  int count_ = 0;
  uint32_t end_ts_ = 0;
  bool clipped_ = false;
};

}  // namespace dwell
