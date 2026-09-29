# Performance and resource safety (Phase 10)

## Question

Does the pipeline stay practical for **mid-poly assets up to ~50k triangles** in a cloud-agent
loop, where one iteration is edit → build → review sheet → validate, and a session runs many
iterations? This is a performance target, not a claim about artistic complexity.

## Benchmark (tools/perf/scaling.py)

- **Asset:** one synthetic but representative asset family, generated at 1k / 5k / 10k / 25k /
  50k triangles by scaling segment counts and a module array. It includes booleans (subtract), lathe,
  helix tube, spheres, arrays and two textured archetypes.
- **Isolation:** each size runs in a fresh process, so peak RSS is per size.
- **Stages:** build, UV (surface), validate (including the texture bake), render (one 512 px
  view, clay and textured), review sheet, GLB export, Khronos validation, re-import check, and
  `sw import` + rebuild of the exported file.

All numbers are measured on this container (see "Environment"). Nothing here is extrapolated.

## Predictions (written before the first measurement)

| # | Prediction |
|---|---|
| P1 | The CPU rasterizer (a Python loop per triangle per view) dominates. The review sheet (8 views + UV) takes > 60 s at 50k. |
| P2 | Validation is second: UV overlap coverage and the mesh-integrity union-find are Python loops per triangle. |
| P3 | Bake: the sharp-edge detection (a Python loop per face) takes seconds at 50k. |
| P4 | Build (including Manifold booleans) stays < 5 s at 50k. |
| P5 | xatlas UV unwrap stays in the low seconds. |
| P6 | Export, Khronos and import each take < 5 s. |
| P7 | Peak memory stays < 1.5 GB. |

## Environment

A cloud container with 4 vCPUs (x86_64) and 15 GB RAM, Python 3.11, numpy 2, manifold3d 3.5.4,
xatlas, and Node 22 for the Khronos validator. All stages are single-threaded except the Manifold
and xatlas internals.

## Results

Raw data: [perf/scaling_before.json](perf/scaling_before.json), [perf/scaling_after.json](perf/scaling_after.json),
[perf/scaling_dense_after.json](perf/scaling_dense_after.json). "Loop" = build + UV + validate
(including the bake) + review sheet: one agent iteration.

**Many-part asset (booleans, lathe, helix tubes, spheres, arrays, two textured materials)**

| Tris | Parts | Loop before → after | Sheet | Validate | 512 px view | UV | Build | Export + Khronos + import | Peak RSS |
|---|---|---|---|---|---|---|---|---|---|
| 968 | 9 | 3.8 → **3.0 s** | 2.15 → 1.65 | 0.91 → 0.53 | 0.96 → 0.70 | 0.36 | 0.46 | 0.3 s | 293 MB |
| 4,964 | 25 | 10.7 → **5.5 s** | 5.16 → 1.82 | 4.14 → 2.23 | 0.64 → 0.41 | 0.99 | 0.46 | 0.6 s | 316 MB |
| 10,040 | 9 | 12.3 → **4.2 s** | 8.19 → 1.98 | 2.69 → 0.88 | 1.56 → 1.02 | 0.95 | 0.42 | 0.4 s | 307 MB |
| 25,036 | 33 | 26.0 → **8.5 s** | 15.4 → 2.82 | 7.96 → 2.97 | 2.31 → 0.43 | 2.20 | 0.47 | 1.0 s | 399 MB |
| 50,028 | 65 | 43.9 → **12.8 s** | 28.0 → 4.12 | 11.2 → 4.02 | 3.73 → 0.55 | 4.16 | 0.49 | 2.3 s | 537 MB |

**One dense part (a noised 256-segment sphere, a subtract and a trim), after**

| Tris | Loop | Build | UV | Validate | Sheet | Export + Khronos + import | Peak RSS |
|---|---|---|---|---|---|---|---|
| 950 | 3.3 s | 0.06 | 0.17 | 0.57 | 2.51 | 0.3 s | 276 MB |
| 10,002 | 5.0 s | 0.42 | 0.53 | 0.85 | 3.16 | 0.3 s | 283 MB |
| 25,008 | 7.5 s | 1.58 | 1.55 | 1.19 | 3.18 | 0.4 s | 312 MB |
| 47,548 | 12.2 s | 3.31 | 3.27 | 1.39 | 4.21 | 0.5 s | 350 MB |

Before the fixes, the dense 48k part took **28.6 s in UV alone** and **failed validation** (two needle
triangles from the boolean).

All sizes PASS, with Khronos 0 errors at every size and GLB export deterministic.

## Predictions vs outcome

| # | Prediction | Outcome |
|---|---|---|
| P1 | rasterizer dominates; sheet > 60 s at 50k | ✔ dominated, but 28 s rather than 60 |
| P2 | validation second (UV coverage, union-find) | ✔ second, but through the **texture bake** (rasterize UV, dilate, noise), not the union-find |
| P3 | bake sharp-edge loop costs seconds | ✔ ~1 s at 50k (small next to rasterize/dilate) |
| P4 | build < 5 s | ✔ 0.5 s; 3.3 s for the dense boolean |
| P5 | xatlas low seconds | ✘ **28.6 s for one dense 48k part**: xatlas grows huge charts on smooth dense surfaces |
| P6 | export/Khronos/import < 5 s | ✔ ≤ 2.3 s combined |
| P7 | peak memory < 1.5 GB | ✔ ≤ 540 MB at 50k. A 4096² texture bake is the outlier: **3 GB, 44 s** |

## What changed (each measured, and verified equivalent where equivalence is claimed)

| Bottleneck (profiled) | Change | Equivalence |
|---|---|---|
| per-triangle Python loops in the renderer, UV coverage and bake rasterizer | `raster.fragments`: small triangles batched by box size, large ones on their exact box; depth resolved by a stable sort (largest key, earlier triangle on ties) | **bit-identical**: sheets, renders, bakes and metrics hashed on six assets before/after; property test against the old loop on random triangles with ties and degenerates |
| per-segment wireframe drawing | vectorized samples; blending in rounds with per-segment deduplication | bit-identical (property test vs the old loop) |
| full-image texture dilation, twice | candidate-only dilation, base + ORM in one pass | bit-identical (test) |
| dict-based sharp-edge detection | sort-based edge grouping | bit-identical bakes |
| xatlas on dense smooth parts | parts > 4,000 triangles cap chart area at part area / 128 (28.6 → 3.3 s) | UVs of dense parts change; no benchmark part is that dense, so every existing layout is untouched |
| needle triangles from dense booleans (a validation **error**) | collapse the shortest edge of faces below the validator's degenerate threshold, then weld; a no-op when there are none | one benchmark changed: potted_cactus 1,792 → 1,790 tris (its two needles) |

Tried and **reverted**: rewriting value noise (no measurable gain; per-texel material evaluation
is the bake's intrinsic cost).

## Resource safety (10.4)

An adversarial suite (`tests/test_performance.py`) runs every case in a fresh build. Before this
phase, several cases did the heavy work first and only then failed:
- `arc` with 1e8 segments ran out of memory after 63 s;
- a 1e6-turn helix took 24 s and 2.4 GB before being rejected;
- subdivide/repeat/combine explosions computed millions of triangles (up to 1 GB) and were then rejected;
- `budget.texture_size: 100000` was accepted, ran into the 120 s timeout and used 4.9 GB.

Now every case is rejected with `SRC_LIMIT` **before** the work, in < 1 s and < 100 MB:

| Guard | Where |
|---|---|
| predicted triangle count (subdivide 4^n, repeat ×n, combine Σ, lathe/revolve/tube) vs the per-part limit | ops/shapes before generating |
| point count of arc/helix/line vs `max_points` (2,048) | before generating |
| nesting depth of geometry expressions (24); RecursionError reported as `SRC_LIMIT` | build_geometry |
| `budget.texture_size`, `uv.resolution` ≤ 4096; `texel_density` ≤ 8192 px/m | source |
| existing: 200k triangles per asset, 100k per part, 1,024 instances, 128 per array, 256 segments, 64 ops/part, 120 s per command | unchanged |

`LimitError` from any generator or op is now reported as `SRC_LIMIT` with the source path,
instead of a generic `OP_FAILED`.

## Diagnostic vs production rendering (10.3)

The deterministic CPU renderer is kept: it is bit-exact and fast enough (≈0.5 s per 512 px view
and ≈4 s per full review sheet at 50k). A GPU or browser backend is not justified by these
numbers. The renderer seam in docs/SURFACES.md stays available for a PBR preview backend
(Phase 15).

## Limits that remain (honest)

- A **4096² bake** takes 44 s and 3 GB. It is allowed, but it is the heaviest single operation. Iterate
  at ≤ 2048 and raise the texture size for the final export.
- UV unwrap is ~3–4 s at 50k in both families, now the largest single stage in the loop.
- Measurements come from one container type. Every `sw` command now prints its elapsed time, so
  agents see their own costs.

## Gate evidence from a real agent loop (FRESH_AGENT_06)

A fresh agent built a 43,928-triangle, 403-part fountain with a 2048² texture: 4 revisions, no limit
errors, no framework changes. It exposed a cost the synthetic benchmark missed. Assembly validation
scales with **part pairs**, and 403 parts took 7.1 s, now 2.0 s. It also found the double validation
in export. After both fixes: review 24.3 → 20.8 s, export 26 → 20.5 s, with identical reports and
GLBs. Record: [experiments/FRESH_AGENT_06.md](experiments/FRESH_AGENT_06.md).

**Phase 10 gate: PASS**, with one caveat: at ~20 s per review, agents ration iterations on mid-poly
assets. The remaining time is the 2048 bake, UV and the sheet.
