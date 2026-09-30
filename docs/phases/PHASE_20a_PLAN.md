# Phase 20a plan: cross-OS golden geometry and a green CI

Added to the queue by the owner on 2026-09-30, before 20b. The baseline could not be run as the handoff assumed.

## Failing case (recorded)

On a fresh Windows 11 clone (Python 3.11.9, numpy 2.4.6, manifold3d 3.5.4, trimesh 5.1.0):

- **pytest:** 2 failed, 426 passed, 2 skipped. Both failures are `test_geometry_matches_golden`, for `battle_axe` and `ornate_fountain`. Both assets use booleans; the fountain also uses `decimate`. Each builds with the same hash on repeated runs here, but a different one from the golden recorded in the Linux container.
- **ruff:** 127 errors with ruff 0.16.9, because its default rule set grew. The code passes the rules it was written against (`E4, E7, E9, F`).
- **CI on main is red for the same reason.** The pytest step has never run in CI.

## Goal

- The golden test tells cross-OS float drift apart from a real geometry change.
- It still catches small changes wherever an exact hash exists.
- CI runs the suite on Linux, Windows and macOS.

## Scope

- **`tests/golden.py`:**
  - each asset has `hash: {<platform>: hash}` and `sig: {tris, bounds, area, volume}`;
  - the signature is compared with tolerances on every OS;
  - the hash is compared on the OS that recorded it.
- **`update_golden.py`:**
  - geometry unchanged up to noise → add this OS's hash;
  - a real change → a new signature, and only this OS's hash is kept.
- **Migration:** the old flat file is read as Linux hashes.
- **`geometry_signature()`** in `shapewright/mesh.py`.
- **CI:**
  - a lint job;
  - a test matrix (ubuntu, windows, macos);
  - `[tool.ruff.lint] select` pinned.
- `.venv/` added to `.gitignore`.

## Out of scope

- Making booleans bit-identical across OSes.
- Pinning dependency versions.

## Gate

1. `ruff check .` passes with the current ruff.
2. The full suite passes on Windows locally.
3. CI is green on ubuntu, windows and macos.
4. A regression test shows that float noise passes the signature and a 2 mm move does not.

## Risks and predictions

- **Tolerances.** A 0.1 mm bound or 0.1 % area/volume tolerance may be too tight if a boolean triangulates differently on macOS.
- **Prediction.** Triangle counts are equal across OSes, and area and volume differ below 1e-6 relative. If CI shows otherwise, the tolerance is reported and the gate discussed, not quietly widened.

## Class

- **Golden test:** VALIDATION GAP (test infrastructure). It is generic: any boolean or simplification output can differ in the last bits across platforms.
- **ruff pin:** BUG (tooling).
