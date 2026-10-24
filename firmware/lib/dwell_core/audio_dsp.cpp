// Dwell audio level DSP - see audio_dsp.h and firmware/README.md ("A-weighting filter design").
#include "audio_dsp.h"

#include <cmath>
#include <complex>

namespace dwell {
namespace {

constexpr double kPi = 3.14159265358979323846;
// IEC 61672-1:2013 Annex E pole frequencies of the A-weighting function.
constexpr double kF1 = 20.598997, kF2 = 107.65265, kF3 = 737.86223, kF4 = 12194.217;
constexpr double kDcBlockHz = 3.0;

void scale_numerator(BiquadCoeffs* c, double g) {
  c->b0 *= g;
  c->b1 *= g;
  c->b2 *= g;
}

}  // namespace

double octave_midband_hz(int band) { return 1000.0 * std::pow(10.0, 3.0 * (band - 4) / 10.0); }

double prewarp(double f_hz, double fs) { return 2.0 * fs * std::tan(kPi * f_hz / fs); }

BiquadCoeffs bilinear(double b0, double b1, double b2, double a0, double a1, double a2, double fs) {
  const double k = 2.0 * fs, k2 = k * k;
  const double A0 = a0 * k2 + a1 * k + a2;
  return BiquadCoeffs{(b0 * k2 + b1 * k + b2) / A0, (2.0 * b2 - 2.0 * b0 * k2) / A0,
                      (b0 * k2 - b1 * k + b2) / A0, (2.0 * a2 - 2.0 * a0 * k2) / A0,
                      (a0 * k2 - a1 * k + a2) / A0};
}

double cascade_response_db(const BiquadCoeffs* c, std::size_t n, double f_hz, double fs) {
  const std::complex<double> z1 = std::polar(1.0, -2.0 * kPi * f_hz / fs);  // z^-1
  std::complex<double> h = 1.0;
  for (std::size_t i = 0; i < n; ++i) {
    h *= (c[i].b0 + c[i].b1 * z1 + c[i].b2 * z1 * z1) / (1.0 + c[i].a1 * z1 + c[i].a2 * z1 * z1);
  }
  return 20.0 * std::log10(std::abs(h));
}

AWeightDesign design_a_weighting(double fs) {
  // H_A(s) = K s^4 / ((s + w1)^2 (s + w2) (s + w3) (s + w4)^2). Each pole frequency is pre-warped
  // so the digital poles sit at the analog corner frequencies; this keeps the 4-12.5 kHz region
  // within 0.7 dB of the IEC table at fs = 48 kHz (plain bilinear sags by -2.7 dB at 12.5 kHz).
  const double w1 = prewarp(kF1, fs), w2 = prewarp(kF2, fs), w3 = prewarp(kF3, fs), w4 = prewarp(kF4, fs);
  AWeightDesign d = {
      bilinear(1, 0, 0, 1, 2 * w1, w1 * w1, fs),        // s^2 / (s + w1)^2
      bilinear(1, 0, 0, 1, w2 + w3, w2 * w3, fs),       // s^2 / ((s + w2)(s + w3))
      bilinear(0, 0, w4 * w4, 1, 2 * w4, w4 * w4, fs),  // w4^2 / (s + w4)^2
  };
  scale_numerator(&d[0], std::pow(10.0, -cascade_response_db(d.data(), d.size(), 1000.0, fs) / 20.0));
  return d;
}

OctaveDesign design_octave_band(int band, double fs) {
  // Butterworth low-pass prototype of order N=3, low-pass -> band-pass s' = (s^2 + w0^2) / (B s).
  // Each prototype pole p maps to the roots of s^2 - p B s + w0^2; pairing each root with its
  // conjugate gives real biquads B s / (s^2 - 2 Re(r) s + |r|^2).
  const double fm = octave_midband_hz(band);
  const double wl = prewarp(fm * std::pow(10.0, -0.15), fs), wh = prewarp(fm * std::pow(10.0, 0.15), fs);
  const double w0sq = wl * wh, bw = wh - wl;
  OctaveDesign d{};
  int k = 0;
  // Prototype poles for N=3: -1 and exp(+-j 2pi/3). The real pole yields one biquad directly.
  d[k++] = bilinear(0, bw, 0, 1, bw, w0sq, fs);
  const std::complex<double> p = std::polar(1.0, 2.0 * kPi / 3.0);
  const std::complex<double> disc = std::sqrt(p * p * bw * bw - 4.0 * w0sq);
  for (const std::complex<double>& r : {(p * bw + disc) / 2.0, (p * bw - disc) / 2.0}) {
    d[k++] = bilinear(0, bw, 0, 1, -2.0 * r.real(), std::norm(r), fs);
  }
  scale_numerator(&d[0], std::pow(10.0, -cascade_response_db(d.data(), d.size(), fm, fs) / 20.0));
  return d;
}

Biquad::Biquad(const BiquadCoeffs& c)
    : b0_(static_cast<float>(c.b0)),
      b1_(static_cast<float>(c.b1)),
      b2_(static_cast<float>(c.b2)),
      a1_(static_cast<float>(c.a1)),
      a2_(static_cast<float>(c.a2)) {}

AudioDsp::AudioDsp(const DspConfig& cfg)
    : cfg_(cfg),
      samples_per_second_(static_cast<uint32_t>(std::lround(cfg.sample_rate))),
      dc_r_(static_cast<float>(std::exp(-2.0 * kPi * kDcBlockHz / cfg.sample_rate))) {
  const AWeightDesign a = design_a_weighting(cfg.sample_rate);
  for (int i = 0; i < kAWeightSections; ++i) aw_[i] = Biquad(a[i]);
  if (cfg_.octave_bands) {
    for (int b = 0; b < kNumOctaveBands; ++b) {
      const OctaveDesign o = design_octave_band(b, cfg.sample_rate);
      for (int i = 0; i < kOctaveSections; ++i) oct_[b][i] = Biquad(o[i]);
    }
  }
  reset();
}

void AudioDsp::reset() {
  for (Biquad& s : aw_) s.reset();
  for (auto& band : oct_)
    for (Biquad& s : band) s.reset();
  dc_x1_ = dc_y1_ = 0;
  a_chunk_ = 0;
  a_ms_ = 0;
  band_chunk_.fill(0);
  band_ms_.fill(0);
  peak_ = 0;
  clipped_ = 0;
  n_ = 0;
  ready_ = false;
}

double AudioDsp::ms_to_db(double mean_square) const {
  const double ms = mean_square > 1e-30 ? mean_square : 1e-30;
  return 10.0 * std::log10(2.0 * ms) + cfg_.reference_spl_db - cfg_.mic_sensitivity_dbfs + cfg_.mic_offset_db;
}

void AudioDsp::push(float x) {
  const float ax = std::fabs(x);
  if (ax > peak_) peak_ = ax;
  if (ax >= cfg_.clip_threshold) ++clipped_;
  // DC blocker y[n] = x[n] - x[n-1] + R y[n-1]: removes the INMP441 DC offset before the
  // low-frequency A-weighting poles see it.
  const float d = x - dc_x1_ + dc_r_ * dc_y1_;
  dc_x1_ = x;
  dc_y1_ = d;
  float y = d;
  for (Biquad& s : aw_) y = s.process(y);
  a_chunk_ += y * y;
  if (cfg_.octave_bands) {
    for (int b = 0; b < kNumOctaveBands; ++b) {
      float v = d;
      for (Biquad& s : oct_[b]) v = s.process(v);
      band_chunk_[b] += v * v;
    }
  }
  ++n_;
  if (n_ % kChunk == 0 || n_ == samples_per_second_) {
    a_ms_ += a_chunk_;
    a_chunk_ = 0;
    for (int b = 0; b < kNumOctaveBands; ++b) {
      band_ms_[b] += band_chunk_[b];
      band_chunk_[b] = 0;
    }
  }
  if (n_ == samples_per_second_) finish_second();
}

void AudioDsp::finish_second() {
  const double n = static_cast<double>(n_);
  out_.laeq_1s = static_cast<float>(ms_to_db(a_ms_ / n));
  for (int b = 0; b < kNumOctaveBands; ++b) {
    out_.band_leq_1s[b] = cfg_.octave_bands ? static_cast<float>(ms_to_db(band_ms_[b] / n)) : NAN;
  }
  out_.peak_dbfs = static_cast<float>(20.0 * std::log10(peak_ > 1e-12f ? peak_ : 1e-12f));
  out_.clipped_samples = clipped_;
  out_.seq = seq_++;
  out_.valid = true;
  ready_ = true;
  a_ms_ = 0;
  band_ms_.fill(0);
  peak_ = 0;
  clipped_ = 0;
  n_ = 0;
}

bool AudioDsp::process_i2s_frames(const int32_t* frames, std::size_t count) {
  for (std::size_t i = 0; i < count; ++i) {
    // INMP441: 24-bit two's complement, MSB first, left-aligned in the 32-bit slot.
    const int32_t s24 = frames[i] >> 8;
    push(static_cast<float>(s24) * (1.0f / 8388608.0f));
  }
  return ready_;
}

bool AudioDsp::process_samples(const float* samples, std::size_t count) {
  for (std::size_t i = 0; i < count; ++i) push(samples[i]);
  return ready_;
}

SecondLevels AudioDsp::take_second() {
  ready_ = false;
  return out_;
}

}  // namespace dwell
