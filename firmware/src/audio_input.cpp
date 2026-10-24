// The ONLY file allowed to read I2S (tools/check_no_raw_audio.py rule R1). The sample buffer is a
// static scratch area that is overwritten by every i2s_read() and only ever handed to the DSP.
#include "audio_input.h"

#include <Arduino.h>
#include <atomic>
#include <driver/i2s.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

#include "dwell_config.h"

namespace dwell_audio {
namespace {

constexpr i2s_port_t kPort = I2S_NUM_0;
constexpr size_t kBlockFrames = 256;  // 5.3 ms at 48 kHz
constexpr int kQueueDepth = 16;       // seconds of levels buffered for the main loop

QueueHandle_t g_queue = nullptr;
dwell::AudioDsp* g_dsp = nullptr;
std::atomic<float> g_offset{0.0f};
std::atomic<uint32_t> g_dropped{0};

void audio_task(void*) {
  static int32_t i2s_frames[kBlockFrames];  // scratch: overwritten each block, never leaves this task
  for (;;) {
    size_t nbytes = 0;
    if (i2s_read(kPort, i2s_frames, sizeof(i2s_frames), &nbytes, portMAX_DELAY) != ESP_OK) continue;
    if (g_dsp->process_i2s_frames(i2s_frames, nbytes / sizeof(int32_t))) {
      const dwell::SecondLevels levels = g_dsp->take_second();
      if (xQueueSend(g_queue, &levels, 0) != pdTRUE) g_dropped.fetch_add(1);
      const float off = g_offset.load();
      if (off != static_cast<float>(g_dsp->mic_offset_db())) g_dsp->set_mic_offset_db(off);
    }
  }
}

}  // namespace

bool begin(float mic_offset_db, bool octave_bands) {
  dwell::DspConfig cfg;
  cfg.sample_rate = DWELL_SAMPLE_RATE;
  cfg.mic_offset_db = mic_offset_db;
  cfg.octave_bands = octave_bands;
  g_offset.store(mic_offset_db);
  g_dsp = new dwell::AudioDsp(cfg);
  g_queue = xQueueCreate(kQueueDepth, sizeof(dwell::SecondLevels));
  if (!g_dsp || !g_queue) return false;

  i2s_config_t ic = {};
  ic.mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_RX);
  ic.sample_rate = DWELL_SAMPLE_RATE;
  ic.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;  // INMP441: 24 data bits in a 32-bit slot
  ic.channel_format = DWELL_I2S_RIGHT_CHANNEL ? I2S_CHANNEL_FMT_ONLY_RIGHT : I2S_CHANNEL_FMT_ONLY_LEFT;
  ic.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  ic.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  ic.dma_buf_count = 8;
  ic.dma_buf_len = kBlockFrames;
  ic.use_apll = true;  // accurate 48 kHz clock -> exact 1-s blocks
  if (i2s_driver_install(kPort, &ic, 0, nullptr) != ESP_OK) return false;

  i2s_pin_config_t pins = {};
  pins.mck_io_num = I2S_PIN_NO_CHANGE;
  pins.bck_io_num = DWELL_PIN_I2S_SCK;
  pins.ws_io_num = DWELL_PIN_I2S_WS;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num = DWELL_PIN_I2S_SD;
  if (i2s_set_pin(kPort, &pins) != ESP_OK) return false;
  i2s_zero_dma_buffer(kPort);

  return xTaskCreatePinnedToCore(audio_task, "audio", 4096, nullptr, configMAX_PRIORITIES - 2, nullptr, 1) ==
         pdPASS;
}

bool receive(dwell::SecondLevels* out) { return g_queue && xQueueReceive(g_queue, out, 0) == pdTRUE; }

void set_mic_offset_db(float offset_db) { g_offset.store(offset_db); }

uint32_t dropped_seconds() { return g_dropped.load(); }

}  // namespace dwell_audio
