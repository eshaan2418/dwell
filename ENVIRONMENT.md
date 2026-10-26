# ENVIRONMENT (probed 2026-10-24)

| Item | Value |
|---|---|
| Machine | Apple M5 Pro (arm64), 18 cores, 48 GiB RAM, ~757 GiB free disk |
| OS | macOS (Darwin 27.0.0) |
| GPU | Apple integrated (Metal/MPS) — **no CUDA** |
| Python | 3.12.14 (uv-managed `.venv`), deps pinned in `requirements.lock` |
| Node | via mise (npm available) — app build |
| C/C++ | Apple clang 21 (firmware host tests), clang-format (pip wheel) |
| PlatformIO | installed with `uv tool install platformio` (espressif32 6.x, Arduino core 2.0.x); `pio run` builds `esp32dev` + `esp32dev_bme280` |
| COLMAP / GLOMAP | not installed; COLMAP 4.2.1 available via Homebrew bottle (CPU sparse only; dense MVS needs CUDA) |
| nerfstudio / gsplat | not usable (CUDA required) |
| Docker | Docker Desktop 29.7.2 (server running) |
| Android / iOS tooling | no Android SDK / Java runtime; Xcode 27.1 present (not used — PWA, D-011) |
| Network | available (PyPI, NASA POWER, ECCC, OSM) |

## Fallback rungs chosen (M0, D-003)

| Resource | Rung | Notes |
|---|---|---|
| Real sensor data | **Fallback 2** (synthetic + public data) | 0 units so far; real validation `awaiting-human` |
| Walkthrough capture | Fallback 1/2 | plain video + known-object scale; manual floor-plan entry supported |
| 3D reconstruction | Fallback 2 (2.5D floor plan + window boxes) | COLMAP sparse optional when installed |
| Building obstruction | Preferred/Fallback 1 | Toronto 3D Massing + OSM heights (`locate/`) |
| Noise sources | Preferred/Fallback 1 | Toronto traffic counts + TTC GTFS when fetched; OSM class proxies otherwise |
| ML compute | CPU | gradient boosting, small models |

## Data status counts
- Units with video: 0 · with reconstruction: 0 · with sensor data: 0 (see DATA_STATUS.md)
- Sensor hardware: firmware ready, kits not yet built (HUMAN_TODO §3)
