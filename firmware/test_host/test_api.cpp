// No-raw-audio guarantee, compile-time part: the DSP's public outputs are level structs, and the
// logger interface (LogSink) cannot be called with sample pointers / arrays / byte buffers.
#include <array>
#include <cstdint>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

#include "audio_dsp.h"
#include "harness.h"
#include "level_stats.h"
#include "log_sink.h"

using namespace dwell;

namespace {

template <typename T, typename = void>
struct can_log : std::false_type {};
template <typename T>
struct can_log<T, std::void_t<decltype(std::declval<LogSink&>().log(std::declval<T>()))>> : std::true_type {};

// Plain level structs: trivially copyable, no pointers possible, too small to smuggle a sample block
// (one 1-ms block at 48 kHz would already be 192 bytes).
template <typename T>
constexpr bool is_small_level_struct = std::is_trivially_copyable_v<T> && std::is_standard_layout_v<T> &&
                                       !std::is_pointer_v<T> && sizeof(T) <= 128;

// Logger accepts exactly the record types...
static_assert(can_log<const MinuteRecord&>::value);
static_assert(can_log<const SecondRecord&>::value);
static_assert(can_log<const OctaveRecord&>::value);
static_assert(can_log<const EventRecord&>::value);
// ...and nothing that could carry raw audio.
static_assert(!can_log<const int32_t*>::value);
static_assert(!can_log<int32_t*>::value);
static_assert(!can_log<const int16_t*>::value);
static_assert(!can_log<const float*>::value);
static_assert(!can_log<const double*>::value);
static_assert(!can_log<const uint8_t*>::value);
static_assert(!can_log<const void*>::value);
static_assert(!can_log<const char*>::value);
static_assert(!can_log<std::string>::value);
static_assert(!can_log<std::vector<int32_t>>::value);
static_assert(!can_log<std::vector<float>>::value);
static_assert(!can_log<std::array<int32_t, 512>>::value);
static_assert(!can_log<std::array<float, 512>>::value);
static_assert(!can_log<std::pair<const int32_t*, std::size_t>>::value);
static_assert(!can_log<float>::value);                // no implicit conversions from bare numbers
static_assert(!can_log<const SecondLevels&>::value);  // DSP output must be mapped to a record first

// Records and DSP outputs are small value types.
static_assert(is_small_level_struct<MinuteRecord>);
static_assert(is_small_level_struct<SecondRecord>);
static_assert(is_small_level_struct<OctaveRecord>);
static_assert(is_small_level_struct<EventRecord>);
static_assert(is_small_level_struct<SecondLevels>);
static_assert(is_small_level_struct<MinuteAudio>);

// The DSP's public output functions return levels (by value), never pointers/references to buffers.
static_assert(std::is_same_v<decltype(std::declval<AudioDsp&>().take_second()), SecondLevels>);
static_assert(std::is_same_v<decltype(std::declval<const AudioDsp&>().ms_to_db(0.0)), double>);
static_assert(std::is_same_v<decltype(std::declval<AudioDsp&>().process_i2s_frames(nullptr, 0)), bool>);
static_assert(std::is_same_v<decltype(std::declval<AudioDsp&>().process_samples(nullptr, 0)), bool>);
static_assert(std::is_same_v<decltype(std::declval<const MinuteAudioStats&>().summarize()), MinuteAudio>);
// Sample input is read-only: the DSP cannot be used as a place to stash/forward buffers.
static_assert(
    !std::is_invocable_v<decltype(&AudioDsp::process_i2s_frames), AudioDsp&, int32_t**, std::size_t>);

// The SecondLevels fields are all scalar levels/counters.
static_assert(std::is_same_v<decltype(SecondLevels::laeq_1s), float>);
static_assert(std::is_same_v<decltype(SecondLevels::band_leq_1s), float[kNumOctaveBands]>);

// A recording sink used to check run-time behaviour of the interface.
struct CountingSink : LogSink {
  int n = 0;
  void log(const MinuteRecord&) override { ++n; }
  void log(const SecondRecord&) override { ++n; }
  void log(const OctaveRecord&) override { ++n; }
  void log(const EventRecord&) override { ++n; }
};

}  // namespace

TEST_CASE("API: logger accepts only level/record structs (static_asserts compiled)") {
  CountingSink sink;
  LogSink& s = sink;
  s.log(SecondRecord{1, 40.0f});
  s.log(make_event(1, "BOOT", "test"));
  CHECK(sink.n == 2);
}
