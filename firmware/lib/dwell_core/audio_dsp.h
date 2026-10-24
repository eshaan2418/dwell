// Dwell audio level DSP (platform independent: no Arduino / ESP-IDF / stdio includes).
//
// PRIVACY CONTRACT (see firmware/REVIEW_CHECKLIST.md): this module consumes blocks of raw I2S
// frames and exposes ONLY sound levels in dB (SecondLevels). Sample data is processed in place,
// sample-by-sample; it is never stored beyond the filter state, never returned, and never
// handed to any I/O. tools/check_no_raw_audio.py enforces that no I/O is reachable from here.
//
// Signal chain per sample (fs = 48 kHz):
//   INMP441 32-bit I2S slot -> 24-bit signed sample -> clip detect -> DC blocker (3 Hz 1st-order HP)
//   -> A-weighting (3 cascaded biquads) -> mean-square accumulator (1 s) -> L_Aeq,1s
//   -> [optional] 8 unweighted octave band-passes 63 Hz..8 kHz (3 biquads each) -> L_eq,1s per band
//
// Level calibration: INMP441 sensitivity is -26 dBFS for 94 dB SPL @ 1 kHz, where 0 dBFS is a
// full-scale *sine* (mean square 0.5). Hence  L = 10 log10(2 * ms) + 94 - (-26) + mic_offset_db.
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>

namespace dwell {

constexpr int kNumOctaveBands = 8;
// Nominal octave centre frequencies (labels) and exact base-10 mid-band frequencies (IEC 61260-1).
constexpr std::array<int, kNumOctaveBands> kOctaveNominalHz = {63, 125, 250, 500, 1000, 2000, 4000, 8000};
double octave_midband_hz(int band);  // 1000 * 10^(3(band-4)/10)

// Digital biquad coefficients (a0 normalised to 1), designed in double precision.
struct BiquadCoeffs {
  double b0, b1, b2, a1, a2;
};

// Bilinear transform of an analog biquad (b0 s^2 + b1 s + b2) / (a0 s^2 + a1 s + a2), s = 2 fs (1-z^-1)/(1+z^-1).
BiquadCoeffs bilinear(double b0, double b1, double b2, double a0, double a1, double a2, double fs);
// Pre-warped analog angular frequency for a digital frequency f: 2 fs tan(pi f / fs).
double prewarp(double f_hz, double fs);
// Magnitude response of a cascade of biquads at f_hz, in dB.
double cascade_response_db(const BiquadCoeffs* c, std::size_t n, double f_hz, double fs);

constexpr int kAWeightSections = 3;
constexpr int kOctaveSections = 3;  // 3rd-order Butterworth prototype -> 6th-order band-pass
using AWeightDesign = std::array<BiquadCoeffs, kAWeightSections>;
using OctaveDesign = std::array<BiquadCoeffs, kOctaveSections>;
// A-weighting (IEC 61672-1 analog poles, pre-warped, bilinear), normalised to 0 dB at 1 kHz.
AWeightDesign design_a_weighting(double fs);
// Octave band-pass (Butterworth, band edges fm * 10^(+-0.15), pre-warped, bilinear), 0 dB at fm.
OctaveDesign design_octave_band(int band, double fs);

// Single-precision transposed direct-form-II biquad (the ESP32 has a single-precision FPU).
class Biquad {
 public:
  Biquad() = default;
  explicit Biquad(const BiquadCoeffs& c);
  float process(float x) {
    const float y = b0_ * x + z1_;
    z1_ = b1_ * x - a1_ * y + z2_;
    z2_ = b2_ * x - a2_ * y;
    return y;
  }
  void reset() { z1_ = z2_ = 0.0f; }

 private:
  float b0_ = 1, b1_ = 0, b2_ = 0, a1_ = 0, a2_ = 0, z1_ = 0, z2_ = 0;
};

struct DspConfig {
  double sample_rate = 48000.0;
  double mic_sensitivity_dbfs = -26.0;  // INMP441: -26 dBFS @ 94 dB SPL, 1 kHz
  double reference_spl_db = 94.0;
  double mic_offset_db = 0.0;  // per-kit calibration (NVS), added to every level
  bool octave_bands = false;
  float clip_threshold = 0.999f;  // |sample| >= this fraction of full scale counts as clipped
};

// The only thing the DSP ever outputs: one second of levels. Plain values, no pointers.
struct SecondLevels {
  float laeq_1s;                          // A-weighted L_Aeq,1s [dB], calibrated
  float band_leq_1s[kNumOctaveBands];     // unweighted octave L_eq,1s [dB]; NAN when disabled
  float peak_dbfs;                        // max |raw sample| in the second [dBFS], for diagnostics
  uint32_t clipped_samples;               // number of clipped raw samples in the second
  uint32_t seq;                           // running second counter since start
  bool valid;                             // false for placeholder seconds (no audio received)
};

class AudioDsp {
 public:
  explicit AudioDsp(const DspConfig& cfg = DspConfig());
  void set_mic_offset_db(double offset_db) { cfg_.mic_offset_db = offset_db; }
  double mic_offset_db() const { return cfg_.mic_offset_db; }
  const DspConfig& config() const { return cfg_; }
  void reset();

  // Consume a block of raw INMP441 I2S slots (24-bit data MSB-aligned in 32 bits). The block is
  // processed sample-by-sample and not retained. Returns true if a 1-s result became ready.
  bool process_i2s_frames(const int32_t* frames, std::size_t count);
  // Same, for samples already normalised to [-1, 1) full scale (used by host tests).
  bool process_samples(const float* samples, std::size_t count);
  bool second_ready() const { return ready_; }
  // Returns the latest completed second (levels only) and clears the ready flag.
  SecondLevels take_second();

  // dB conversion used for all outputs: mean square (full scale = 1.0) -> calibrated SPL.
  double ms_to_db(double mean_square) const;

 private:
  void push(float x);
  void finish_second();

  DspConfig cfg_;
  uint32_t samples_per_second_;
  float dc_r_;
  float dc_x1_ = 0, dc_y1_ = 0;
  std::array<Biquad, kAWeightSections> aw_;
  std::array<std::array<Biquad, kOctaveSections>, kNumOctaveBands> oct_;
  // Accumulators: float within a block of kChunk samples, double across chunks.
  static constexpr uint32_t kChunk = 256;
  float a_chunk_ = 0;
  std::array<float, kNumOctaveBands> band_chunk_{};
  double a_ms_ = 0;
  std::array<double, kNumOctaveBands> band_ms_{};
  float peak_ = 0;
  uint32_t clipped_ = 0;
  uint32_t n_ = 0;
  uint32_t seq_ = 0;
  bool ready_ = false;
  SecondLevels out_{};
};

}  // namespace dwell
