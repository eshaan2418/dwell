// INMP441 I2S capture task. Raw frames stay inside audio_input.cpp; only SecondLevels leave it.
#pragma once

#include "audio_dsp.h"

namespace dwell_audio {

// Installs the I2S driver (48 kHz, 32-bit slots, mono) and starts the capture/DSP task on core 1.
bool begin(float mic_offset_db, bool octave_bands);
// Non-blocking: pops the next completed second of levels, if any.
bool receive(dwell::SecondLevels* out);
// Applied by the audio task at the next second boundary.
void set_mic_offset_db(float offset_db);
// Seconds lost because the main loop did not drain the queue in time.
uint32_t dropped_seconds();

}  // namespace dwell_audio
