"""Tests for check_no_raw_audio.py: real firmware passes; synthetic leaks fail.

Run: python -m pytest firmware/tools/test_check_no_raw_audio.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_no_raw_audio as chk  # noqa: E402

FIRMWARE = Path(__file__).resolve().parent.parent
AUDIO = "src/audio_input.cpp"
# Anchor inside the real capture task, right after the I2S read.
ANCHOR = "    if (g_dsp->process_i2s_frames(i2s_frames, nbytes / sizeof(int32_t))) {\n"


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A copy of the real firmware sources that tests can mutate."""
    dst = tmp_path / "firmware"
    shutil.copytree(
        FIRMWARE, dst, ignore=shutil.ignore_patterns(".pio", "build", "__pycache__", ".pytest_cache")
    )
    return dst


def inject(root: Path, rel: str, snippet: str, anchor: str = ANCHOR) -> None:
    p = root / rel
    src = p.read_text()
    assert anchor in src, f"anchor not found in {rel}"
    p.write_text(src.replace(anchor, snippet + anchor, 1))


def rules(root: Path) -> set[str]:
    return {v.rule for v in chk.check(root)[0]}


def test_real_firmware_passes() -> None:
    violations, n = chk.check(FIRMWARE)
    assert violations == [], "\n".join(map(str, violations))
    assert n > 10
    assert chk.main(["--root", str(FIRMWARE)]) == 0


def test_real_capture_path_is_detected() -> None:
    """Guard against a vacuous pass: the checker must see the real I2S read and its buffer."""
    code = chk.strip_comments_and_strings((FIRMWARE / AUDIO).read_text())
    assert [buf.strip() for _, _, buf in chk.find_i2s_calls(code)] == ["i2s_frames"]


@pytest.mark.parametrize(
    "snippet",
    [
        "    Serial.write(reinterpret_cast<uint8_t*>(i2s_frames), nbytes);\n",
        '    Serial.printf("%ld\\n", (long)i2s_frames[0]);\n',
        '    { File f = SD.open("/a.bin", FILE_WRITE); f.write((const uint8_t*)i2s_frames, nbytes); }\n',
        "    { HTTPClient http; http.POST((uint8_t*)i2s_frames, nbytes); }\n",
        "    xQueueSend(g_queue, i2s_frames, 0);\n",
        "    upload_samples(i2s_frames, nbytes);\n",  # any non-DSP consumer
        # aliasing and copies are tracked
        "    { const int32_t* p = i2s_frames; Serial.write((const uint8_t*)p, 4); }\n",
        "    { int32_t first = i2s_frames[0]; Serial.println(first); }\n",
        "    { static int32_t copy[256]; memcpy(copy, i2s_frames, nbytes); stash(copy); }\n",
    ],
)
def test_leaks_from_i2s_buffer_fail(tree: Path, snippet: str) -> None:
    inject(tree, AUDIO, snippet)
    assert "R2" in rules(tree)
    assert chk.main(["--root", str(tree)]) == 1


def test_returning_buffer_fails(tree: Path) -> None:
    p = tree / AUDIO
    p.write_text(
        p.read_text() + "\nint32_t* leak() {\n  static int32_t b[8];\n  size_t n;\n"
        "  i2s_read(I2S_NUM_0, b, sizeof(b), &n, 0);\n  return b;\n}\n"
    )
    assert "R2" in rules(tree)


def test_i2s_read_outside_capture_file_fails(tree: Path) -> None:
    p = tree / "src/logger.cpp"
    p.write_text(
        p.read_text() + "\nvoid sneaky() {\n  int32_t buf[64];\n  size_t n = 0;\n"
        "  i2s_read(I2S_NUM_0, buf, sizeof(buf), &n, 0);\n}\n"
    )
    assert "R1" in rules(tree)


def test_io_in_dsp_module_fails(tree: Path) -> None:
    p = tree / "lib/dwell_core/audio_dsp.cpp"
    p.write_text("#include <cstdio>\n" + p.read_text())
    assert "R3" in rules(tree)
    p.write_text(
        p.read_text().replace(
            "void AudioDsp::push(float x) {\n", 'void AudioDsp::push(float x) {\n  printf("%f", x);\n'
        )
    )
    assert "R3" in rules(tree)


def test_logger_accepting_samples_fails(tree: Path) -> None:
    inject(
        tree,
        "lib/dwell_core/log_sink.h",
        "  virtual void log(const int32_t* samples, size_t n) = 0;\n",
        anchor="  virtual void log(const EventRecord& r) = 0;\n",
    )
    assert "R4" in rules(tree)


@pytest.mark.parametrize(
    "rel,content",
    [
        (
            "src/wav.cpp",
            'void hdr(File& f) { f.write((const uint8_t*)"RIFF", 4); f.write((const uint8_t*)"WAVE", 4); }\n',
        ),
        ("src/rec.cpp", 'const char* kPath = "/rec_0001.wav";\n'),
        ("src/up.cpp", 'void go(HTTPClient& h) { h.addHeader("Content-Type", "audio/L16"); }\n'),
        ("tools/dump.py", "import wave\nw = wave.open('x', 'wb')\n"),
        ("src/pcm.h", "void write_pcm(const int16_t* s, int n);\n"),
    ],
)
def test_wav_or_pcm_writer_fails(tree: Path, rel: str, content: str) -> None:
    (tree / rel).write_text(content)
    assert "R5" in rules(tree)


def test_comments_and_strings_are_not_code() -> None:
    code = chk.strip_comments_and_strings(
        'int a; // i2s_read(x, buf)\n/* Serial */ const char* s = "i2s_read(";\n'
    )
    assert "i2s_read" not in code and "Serial" not in code
    assert code.count("\n") == 2
