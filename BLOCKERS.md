# BLOCKERS

| ID | Date | Blocker | Fallback | Impact on claims |
|---|---|---|---|---|
| B-001 | 2026-10-24 | No volunteer units, no sensor kits, no walkthrough videos yet (human-only steps). | Synthetic apartments + simulated sensors (rung 3); all real-data milestones prepared and marked `awaiting-human`. | No real-world accuracy claim can be made yet; every number is labelled `synthetic`. |
| B-002 | 2026-10-24 | No CUDA GPU (Apple M5 Pro, MPS only): gsplat / COLMAP dense MVS need CUDA. | COLMAP sparse (CPU) + known-object scale + floor-plan (2.5D) extraction; manual floor-plan entry. | Reconstruction fidelity claims limited to 2.5D geometry (windows, rooms). |
| B-003 | 2026-10-24 | No Android SDK / Java runtime. | Web app (PWA) for capture + viewer (D-011). | No native AR metric scale; capture uses known-object scale. |
| B-004 | 2026-10-24 | MEMS mic self-noise (~33 dBA) is above typical quiet-bedroom night levels. | Report censoring fraction; compare predictions with floor added energetically; recommend a class-2 meter for a calibration subset. | Night-noise accuracy in quiet rooms is bounded by the floor; claims restricted to rooms above floor. |
| B-005 | 2026-10-24 | Real units would be measured from ~Nov 2026: no summer data for months. | Heat model validated on synthetic + shoulder/winter dynamics on real data when available. | Summer peak-temperature claim on real data deferred (`awaiting-human`). |
