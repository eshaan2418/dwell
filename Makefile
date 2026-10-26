# Dwell — see README.md. All experiment outputs go to results/ with provenance (core/provenance.py).
PY ?= .venv/bin/python
export PYTHONHASHSEED := 0
export MPLBACKEND := Agg
export OMP_NUM_THREADS := 2
WORLD ?= world_v1
UNIT ?=

.PHONY: help setup models geo test lint typecheck ci firmware firmware-build privacy-scan check-numbers synth predict-synth \
        train m1 m3 m4 m5-m8 sobol bench figures predict demo app ingest ingest-colocation validate freeze-test-units \
        study-analysis reproduce-quick reproduce-full paper recon clean-cache docker

help:
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

setup: ## create .venv and install pinned deps (uv)
	uv venv --python 3.12 .venv && uv pip install --python $(PY) -r requirements.lock && uv pip install --python $(PY) -e . --no-deps

models: ## download the redaction face model (OpenCV zoo YuNet, ~230 KB)
	@test -f data/models/face_detection_yunet_2023mar.onnx || (mkdir -p data/models && curl -sL -o data/models/face_detection_yunet_2023mar.onnx https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx)

geo: ## download Toronto open-data layers (3D massing, TTC GTFS, traffic counts) into data/geo/cache
	$(PY) -m bench.fetch_geo

test: models ## unit + golden tests (synthetic fixtures)
	$(PY) -m pytest -q tests firmware/tools

lint: ## ruff + clang-format (firmware)
	$(PY) -m ruff check .
	$(MAKE) -C firmware lint

typecheck: ## mypy
	$(PY) -m bench.mypy_ratchet

firmware: ## host DSP tests + no-raw-audio checker + lint
	$(MAKE) -C firmware host-test check-privacy lint

firmware-build: ## ESP32 build (needs PlatformIO: uv tool install platformio)
	$(MAKE) -C firmware build

privacy-scan: ## scan git history + tree for addresses, raw media, secrets, large files
	$(PY) -m bench.privacy_scan

check-numbers: ## every number in README/paper/bullets must trace to results/
	$(PY) -m bench.check_numbers

ci: lint typecheck test firmware privacy-scan check-numbers app ## everything CI runs

synth: ## build synthetic world + simulated deployments (cached)
	$(PY) -m bench.synth_dataset --name $(WORLD)

predict-synth: synth ## physics predictions for all synthetic units (cached)
	$(PY) -m bench.predict_synth --name $(WORLD)

train: predict-synth ## train hidden-property + hybrid models on the synthetic train split
	$(PY) -m bench.train_models

m1: ## M1 target-derivation calibration/validation
	$(PY) -m bench.m1_target_derivation

m3: ## M3 scan-geometry experiments (synthetic point clouds)
	$(PY) -m bench.m3_recon

m4: ## M4 orientation/horizon experiments
	$(PY) -m bench.m4_locate

m5-m8: predict-synth ## M5-M8 method comparison on synthetic data
	$(PY) -m bench.m8_hybrid

sobol: train ## M8 Sobol sensitivity over test units
	$(PY) -m bench.m8_sobol

figures: ## regenerate all figures from results/
	$(PY) -m bench.figures

bench: m1 m3 m4 m5-m8 sobol figures ## all experiments

predict: train ## report bundle for one unit: make predict UNIT=<synthetic unit id | real pseudonym>
	$(PY) -m bench.make_report --unit $(UNIT)

demo: train ## end-to-end demo: reports for two synthetic test units -> app build + bundle check
	$(PY) -m bench.demo
	cd app && npm ci --silent && npm run build --silent
	node app/scripts/check_bundle.mjs app/public/reports

app: ## app typecheck/tests/build
	cd app && npm ci --silent && npm run lint && npm test && npm run build

ingest-colocation: ## per-kit calibration from data/private/raw/colocation
	$(PY) -m ingest.cli colocation

ingest: ## ingest one real unit's SD logs: make ingest UNIT=U03
	$(PY) -m ingest.cli unit --unit $(UNIT)

validate: ## evaluate predictions vs real sensor targets (needs consented real units)
	$(PY) -m bench.validate_real

freeze-test-units: ## freeze real test units (run once when >=3 units exist)
	$(PY) -m bench.freeze_real_test_units

study-analysis: ## M11 analysis (real data if present; else exits)
	$(PY) -m study.analysis

recon: ## walkthrough video -> 2.5D unit geometry: make recon UNIT=U03
	$(PY) -m recon.cli --unit $(UNIT)

reproduce-quick: ## < 1 h: synthetic world (reduced) + all experiments + figures + checks
	DWELL_QUICK=1 $(MAKE) synth predict-synth m1 m5-m8 train sobol m3 m4 figures check-numbers WORLD=$(WORLD)

reproduce-full: ## full pipeline incl. demo and study dry-run
	$(MAKE) bench demo
	$(PY) -m study.analysis --dry-run

paper: figures check-numbers ## render paper/paper.md from template + results
	$(PY) -m bench.render_docs

docker: ## build the reproducibility image
	docker build -t dwell:latest .

clean-cache:
	rm -rf data/synthetic/cache
