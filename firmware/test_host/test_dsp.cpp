// DSP tests: A-weighting vs IEC 61672-1, absolute calibration, averaging, LA90, octave bands.
#include <cmath>
#include <cstdint>
#include <random>
#include <vector>

#include "audio_dsp.h"
#include "harness.h"
#include "level_stats.h"

using namespace dwell;

namespace {

constexpr double kFs = 48000.0;
constexpr double kPi = 3.14159265358979323846;

// IEC 61672-1:2013 Table 3: nominal frequency, A-weighting [dB], class 1 tolerance (+, -).
struct IecRow {
  double nominal, exact, a_db, tol_plus, tol_minus;
};
const IecRow kIec[] = {
    {31.5, 31.623, -39.4, 2.0, 2.0},   {63, 63.096, -26.2, 1.5, 1.5},    {125, 125.89, -16.1, 1.5, 1.5},
    {250, 251.19, -8.6, 1.4, 1.4},     {500, 501.19, -3.2, 1.4, 1.4},    {1000, 1000.0, 0.0, 1.1, 1.1},
    {2000, 1995.3, 1.2, 1.6, 1.6},     {4000, 3981.1, 1.0, 1.6, 1.6},    {8000, 7943.3, -1.1, 2.1, 3.1},
    {10000, 10000.0, -2.5, 2.6, 3.6},  {12500, 12589.0, -4.3, 3.0, 6.0}, {16000, 15849.0, -6.6, 3.5, 17.0},
};

// Feed `seconds` of a sine through the DSP; return the levels of the last complete second.
SecondLevels run_sine(AudioDsp& dsp, double f, double amp, int seconds) {
  std::vector<float> block(480);
  SecondLevels last{};
  double phase = 0;
  const double dphi = 2 * kPi * f / kFs;
  for (int n = 0; n < seconds * 100; ++n) {
    for (float& x : block) {
      x = static_cast<float>(amp * std::sin(phase));
      phase = std::fmod(phase + dphi, 2 * kPi);
    }
    if (dsp.process_samples(block.data(), block.size())) last = dsp.take_second();
  }
  return last;
}

// Double-precision reference implementation of the A-weighted chain (for float-precision check).
double reference_laeq(const std::vector<float>& x, int skip) {
  const AWeightDesign d = design_a_weighting(kFs);
  double z[kAWeightSections][2] = {};
  const double r = std::exp(-2 * kPi * 3.0 / kFs);
  double x1 = 0, y1 = 0, ms = 0;
  for (std::size_t i = 0; i < x.size(); ++i) {
    double v = x[i] - x1 + r * y1;
    x1 = x[i];
    y1 = v;
    for (int s = 0; s < kAWeightSections; ++s) {
      const double y = d[s].b0 * v + z[s][0];
      z[s][0] = d[s].b1 * v - d[s].a1 * y + z[s][1];
      z[s][1] = d[s].b2 * v - d[s].a2 * y;
      v = y;
    }
    if (static_cast<int>(i) >= skip) ms += v * v;
  }
  return 10 * std::log10(2 * ms / static_cast<double>(x.size() - skip)) + 120.0;
}

}  // namespace

TEST_CASE("A-weighting design vs IEC 61672-1 table (class 1, and |err| <= 0.8 dB up to 12.5 kHz)") {
  const AWeightDesign d = design_a_weighting(kFs);
  std::printf("  f_nominal   design[dB]  IEC[dB]  error[dB]\n");
  for (const IecRow& r : kIec) {
    const double h = cascade_response_db(d.data(), d.size(), r.exact, kFs);
    const double err = h - r.a_db;
    std::printf("  %8.1f  %10.2f  %7.1f  %+8.2f\n", r.nominal, h, r.a_db, err);
    CHECK(err <= r.tol_plus && err >= -r.tol_minus);
    if (r.nominal <= 12500) CHECK(std::fabs(err) <= 0.8);
  }
  CHECK_NEAR(cascade_response_db(d.data(), d.size(), 1000.0, kFs), 0.0, 1e-9);
}

TEST_CASE("A-weighting time-domain (float implementation) matches IEC table") {
  const AWeightDesign d = design_a_weighting(kFs);
  for (const IecRow& r : kIec) {
    AudioDsp dsp;
    const double amp = std::pow(10.0, -26.0 / 20.0);  // 94 dB SPL
    const SecondLevels lv = run_sine(dsp, r.exact, amp, 3);
    const double rel = lv.laeq_1s - 94.0;
    CHECK(rel - r.a_db <= r.tol_plus && rel - r.a_db >= -r.tol_minus);
    // Float filter must reproduce the double-precision design (DC blocker adds <= 0.05 dB at 31.5 Hz).
    CHECK_NEAR(rel, cascade_response_db(d.data(), d.size(), r.exact, kFs), 0.1);
  }
}

TEST_CASE("1 kHz sine at -26 dBFS reads 94.0 dB; calibration offset; low level") {
  {
    AudioDsp dsp;
    CHECK_NEAR(run_sine(dsp, 1000, std::pow(10.0, -26.0 / 20.0), 3).laeq_1s, 94.0, 0.05);
  }
  {
    DspConfig c;
    c.mic_offset_db = 2.5;
    AudioDsp dsp(c);
    CHECK_NEAR(run_sine(dsp, 1000, std::pow(10.0, -26.0 / 20.0), 3).laeq_1s, 96.5, 0.05);
  }
  {
    AudioDsp dsp;  // 30 dB SPL = -90 dBFS: still accurate in single precision
    CHECK_NEAR(run_sine(dsp, 1000, std::pow(10.0, -90.0 / 20.0), 3).laeq_1s, 30.0, 0.1);
  }
}

TEST_CASE("I2S 32-bit frame path: 24-bit extraction, 1 s blocking, clipping detection") {
  AudioDsp dsp;
  const double amp = std::pow(10.0, -26.0 / 20.0);
  std::vector<int32_t> frames(512);
  double phase = 0;
  int seconds = 0;
  SecondLevels lv{};
  for (int n = 0; n < 300; ++n) {  // 300 * 512 = 3.2 s
    for (int32_t& f : frames) {
      const int32_t s24 = static_cast<int32_t>(std::lround(amp * 8388607.0 * std::sin(phase)));
      f = static_cast<int32_t>(static_cast<uint32_t>(s24) << 8) | 0x5A;  // low byte is junk on the wire
      phase = std::fmod(phase + 2 * kPi * 1000 / kFs, 2 * kPi);
    }
    if (dsp.process_i2s_frames(frames.data(), frames.size())) {
      lv = dsp.take_second();
      ++seconds;
    }
  }
  CHECK(seconds == 3);
  CHECK(lv.seq == 2);
  CHECK(lv.valid);
  CHECK_NEAR(lv.laeq_1s, 94.0, 0.05);
  CHECK(lv.clipped_samples == 0);
  CHECK_NEAR(lv.peak_dbfs, -26.0, 0.05);

  AudioDsp loud;
  const SecondLevels clip = run_sine(loud, 1000, 1.2 /* beyond full scale */, 1);
  CHECK(clip.clipped_samples > 0);
  std::vector<int32_t> fs_frames(48000);
  for (std::size_t i = 0; i < fs_frames.size(); ++i) fs_frames[i] = (i % 48 < 24) ? INT32_MAX : INT32_MIN;
  AudioDsp sq;
  CHECK(sq.process_i2s_frames(fs_frames.data(), fs_frames.size()));
  CHECK(sq.take_second().clipped_samples == 48000);
}

TEST_CASE("Float A-weighted chain agrees with double reference on low-level noise") {
  std::mt19937 rng(42);
  std::normal_distribution<float> g(0.0f, 1.0f);
  for (double rms_dbfs : {-30.0, -80.0, -95.0}) {
    const float sigma = static_cast<float>(std::pow(10.0, rms_dbfs / 20.0));
    std::vector<float> x(48000 * 3);
    for (float& v : x) v = sigma * g(rng) + 0.002f;  // + DC offset as on a real INMP441
    AudioDsp dsp;
    SecondLevels lv{};
    double e = 0;
    for (std::size_t i = 0; i < x.size(); i += 480) {
      if (dsp.process_samples(&x[i], 480)) {
        lv = dsp.take_second();
        if (lv.seq >= 1) e += std::pow(10.0, lv.laeq_1s / 10.0);
      }
    }
    const double float_db = 10 * std::log10(e / 2);
    CHECK_NEAR(float_db, reference_laeq(x, 48000), 0.2);
  }
}

TEST_CASE("Energetic averaging, LAmax and LA90 over a minute") {
  const float half[] = {60, 70};
  CHECK_NEAR(energetic_mean_db(half, 2), 10 * std::log10((1e6 + 1e7) / 2), 1e-6);  // 67.40 dB

  MinuteAudioStats st;
  st.reset();
  SecondLevels s{};
  s.valid = true;
  for (uint32_t i = 1; i <= 60; ++i) {
    const uint32_t ts = 1800000000u - 60 + i;  // minute (1799999940, 1800000000]
    CHECK(!st.belongs_elsewhere(ts));
    s.laeq_1s = i <= 30 ? 60.0f : 70.0f;
    s.clipped_samples = (i == 17) ? 3 : 0;
    st.add(ts, s);
  }
  CHECK(st.complete_at(1800000000u));
  MinuteAudio m = st.summarize();
  CHECK_NEAR(m.laeq_60s, 67.40, 0.01);
  CHECK_NEAR(m.lamax_60s, 70.0, 1e-6);
  CHECK_NEAR(m.la90_60s, 60.0, 1e-6);
  CHECK(m.seconds == 60);
  CHECK(m.clipped);
  CHECK(st.belongs_elsewhere(1800000001u));

  float ramp[60];
  for (int i = 0; i < 60; ++i) ramp[i] = static_cast<float>(60 - i);  // 1..60 in reverse order
  CHECK_NEAR(exceedance_level_db(ramp, 60, 90.0), 7.0, 1e-6);   // exceeded/equalled by 54 of 60
  CHECK_NEAR(exceedance_level_db(ramp, 60, 10.0), 55.0, 1e-6);  // LA10
  const float with_gap[] = {NAN, 40, NAN, 50};
  CHECK_NEAR(energetic_mean_db(with_gap, 4), 10 * std::log10((1e4 + 1e5) / 2), 1e-6);
  CHECK(std::isnan(energetic_mean_db(with_gap, 1)));

  st.reset();  // invalid (no-audio) seconds give empty levels
  SecondLevels none{};
  none.valid = false;
  st.add(120, none);
  m = st.summarize();
  CHECK(std::isnan(m.laeq_60s) && std::isnan(m.lamax_60s) && std::isnan(m.la90_60s));
  CHECK(MinuteAudioStats::minute_end_for(61) == 120 && MinuteAudioStats::minute_end_for(120) == 120);
}

TEST_CASE("Octave band design: 0 dB at mid-band, -3 dB at band edges, selectivity") {
  for (int b = 0; b < kNumOctaveBands; ++b) {
    const OctaveDesign d = design_octave_band(b, kFs);
    const double fm = octave_midband_hz(b);
    CHECK_NEAR(cascade_response_db(d.data(), d.size(), fm, kFs), 0.0, 1e-9);
    CHECK_NEAR(cascade_response_db(d.data(), d.size(), fm * std::pow(10.0, 0.15), kFs), -3.01, 0.05);
    CHECK_NEAR(cascade_response_db(d.data(), d.size(), fm * std::pow(10.0, -0.15), kFs), -3.01, 0.05);
    // One octave outside the mid-band: >= 18 dB down (6th-order Butterworth: ~19.6 dB analog).
    CHECK(cascade_response_db(d.data(), d.size(), fm * 2, kFs) < -18.0);
    if (b > 0) CHECK(cascade_response_db(d.data(), d.size(), fm / 2, kFs) < -18.0);
  }
}

TEST_CASE("Octave bands time-domain: 1 kHz and 63 Hz tones land in the right band") {
  DspConfig c;
  c.octave_bands = true;
  const double amp = std::pow(10.0, -26.0 / 20.0);  // 94 dB SPL unweighted
  AudioDsp dsp(c);
  SecondLevels lv = run_sine(dsp, 1000, amp, 3);
  CHECK_NEAR(lv.band_leq_1s[4], 94.0, 0.1);
  CHECK(lv.band_leq_1s[3] < 94.0 - 18 && lv.band_leq_1s[5] < 94.0 - 18);
  CHECK(lv.band_leq_1s[2] < 94.0 - 40 && lv.band_leq_1s[6] < 94.0 - 40);
  CHECK(lv.band_leq_1s[0] < 94.0 - 60);
  AudioDsp dsp63(c);
  lv = run_sine(dsp63, 63.096, amp, 3);
  CHECK_NEAR(lv.band_leq_1s[0], 94.0, 0.1);
  CHECK(lv.band_leq_1s[1] < 94.0 - 18 && lv.band_leq_1s[7] < 94.0 - 60);
  CHECK(!std::isnan(lv.laeq_1s));
  AudioDsp no_bands;
  CHECK(std::isnan(run_sine(no_bands, 1000, amp, 1).band_leq_1s[0]));
}
