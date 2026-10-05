# Phase 20a: golden geometry across Linux and Windows, CI green

**Verdict: PASS for the supported platforms (Linux and Windows).**

macOS is out of scope by the owner's decision on 2026-10-05: there is no Mac to debug on, and the work should focus on the logic, not on operating systems. The known macOS difference is recorded below; macOS is not in CI.

## What shipped

| change | class | why it is generic |
|---|---|---|
| `tests/golden.py`: each asset has an exact hash per platform plus a tolerant signature (triangles, bounds, area, volume). The hash is compared on the platform that recorded it; the signature is compared everywhere. | VALIDATION GAP (test infrastructure) | Booleans and decimation can differ in the last bits between platforms while the shape is the same. |
| `update_golden.py` merges platform hashes when the geometry is unchanged up to noise, and starts a new signature on a real change. The old flat file migrates as Linux hashes. | — | — |
| `jitter` is a function of position (a seeded smooth field), not of vertex order | BUG | Wear landed on different vertices when vertex order changed. A field of position does not depend on order; coincident vertices get identical offsets. Every jittered asset's wear pattern changed once (same amplitude); before/after in `phase20a/evidence/jitter_before_after.png`. |
| `house_footing` mortar bed | — | A footing face needed it after the jitter change (seam check). |
| `extends` paths across drives (Windows) | BUG | `os.path.relpath` fails between drives; variants on another drive now store an absolute path. |
| CI: lint job (ruff rule set pinned to `E4, E7, E9, F` in pyproject) + tests on ubuntu-latest and windows-latest | BUG (tooling) | A newer ruff enabled more default rules, so CI stopped at lint and pytest never ran. |

## Evidence

- **Linux (this container):** 433 passed, 2 skipped; ruff clean.
- **CI on the previous commit of this branch:** lint ✓, ubuntu ✓, windows ✓.
- **Windows (local, owner's machine):** the baseline failure that started this phase (2 golden hashes) is now handled by the per-platform hash plus the signature.

## Gate

| gate item | result |
|---|---|
| `ruff check .` passes with the current ruff | **met** (rule set pinned) |
| full suite passes on Windows | **met** (CI windows-latest) |
| CI green on ubuntu and windows | **met** (macOS removed from the gate by the owner) |
| float noise passes the signature, a 2 mm move does not | **met** (`tests/test_golden.py`) |

## Known: macOS (not supported, not tested)

- **What differs.** On macOS arm64 (GitHub runner), `chamfer_box` parts got a different hull triangulation. The same part has a different hash and a slightly different volume, for example `tavern_chair.front_leg` 0.0021135 vs 0.0021309 m³ on Linux. The evidence is `phase20a/evidence/parts_{ubuntu,windows,macos}.txt`.
- **Likely cause.** The convex hull library makes different choices for coplanar points on arm64.
- **What would fix it.** Build `chamfer_box` explicitly instead of through a hull. That would also make the shape independent of any hull library. It is a candidate for a later phase if macOS support is ever needed.
