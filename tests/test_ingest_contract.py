"""Contract test: lines produced by the real firmware formatter parse into the expected frames."""

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from ingest.logs import clean_minute, parse_lines

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "firmware" / "lib" / "dwell_core"


@pytest.fixture(scope="module")
def lines(tmp_path_factory):
    cxx = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
    if cxx is None:
        pytest.skip("no C++ compiler")
    exe = tmp_path_factory.mktemp("emit") / "emit"
    srcs = [str(ROOT / "tests" / "contract" / "emit_lines.cpp")] + [str(p) for p in CORE.glob("*.cpp")]
    subprocess.run([cxx, "-std=c++17", "-O1", f"-I{CORE}", *srcs, "-o", str(exe)], check=True)
    return subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout.splitlines()


def test_firmware_lines_parse(lines):
    log = parse_lines(lines)
    assert log.kit_id == "K07"
    assert float(log.header["mic_offset_db"]) == 0.5
    assert len(log.minute) == 180
    assert len(log.second) == 180 * 60
    assert np.isnan(log.minute["temp_c"].iloc[10])
    assert np.isnan(log.minute["batt_v"]).all()
    assert log.minute["flags"].iloc[20] == 0x08
    assert log.minute["lux"].iloc[0] == pytest.approx(1234.5)
    assert len(log.events) == 1


def test_clean_drops_flagged_and_regularises(lines):
    d = clean_minute(parse_lines(lines).minute)
    assert len(d) == 180
    assert np.isnan(d["temp_c"].iloc[20])  # climate-error flag
    assert d.index.freqstr in ("min", "T") or (d.index[1] - d.index[0]).seconds == 60
