# Dwell firmware: host tests, lint, privacy check, PlatformIO build.
#   make -C firmware host-test | lint | check-privacy | build | all
REPO      := $(abspath $(CURDIR)/..)
CXX       ?= c++
CXXFLAGS  ?= -std=c++17 -O2 -Wall -Wextra -Werror -pedantic
PYTHON    ?= $(firstword $(wildcard $(REPO)/.venv/bin/python) python3)
CLANG_FORMAT ?= $(firstword $(wildcard $(REPO)/.venv/bin/clang-format) clang-format)
PIO       ?= $(firstword $(wildcard $(HOME)/.local/bin/pio) $(wildcard $(REPO)/.venv/bin/pio) pio)

CORE_SRC  := $(wildcard lib/dwell_core/*.cpp)
TEST_SRC  := $(wildcard test_host/*.cpp)
FMT_FILES := $(wildcard src/*.cpp src/*.h include/*.h lib/dwell_core/*.cpp lib/dwell_core/*.h test_host/*.cpp test_host/*.h)

.PHONY: all host-test lint format check-privacy build clean

all: lint host-test check-privacy build

build/host_tests: $(CORE_SRC) $(TEST_SRC) $(wildcard lib/dwell_core/*.h test_host/*.h)
	@mkdir -p build
	$(CXX) $(CXXFLAGS) -Ilib/dwell_core $(CORE_SRC) $(TEST_SRC) -o $@

host-test: build/host_tests
	./build/host_tests

lint:
	$(CLANG_FORMAT) --dry-run --Werror $(FMT_FILES)

format:
	$(CLANG_FORMAT) -i $(FMT_FILES)

# Static no-raw-audio check on the real sources, plus the checker's own tests (if pytest is available).
check-privacy:
	$(PYTHON) tools/check_no_raw_audio.py --root .
	@if $(PYTHON) -c "import pytest" 2>/dev/null; then \
	  $(PYTHON) -m pytest -q -p no:cacheprovider tools/test_check_no_raw_audio.py; \
	else echo "pytest not installed: skipped tools/test_check_no_raw_audio.py"; fi

build:
	$(PIO) run -d .

clean:
	rm -rf build .pio
