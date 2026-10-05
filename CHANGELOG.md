# Changelog

Newest first. Generated from the phase records by `tools/site/changelog.py`; each entry links to its record (what shipped, evidence, the gate table and what is not done).

## MODULAR_HOUSE_PACK_02: the kit gates re-run (milestone M2)

- **Verdict:** PASS (all 10; gate 9 by FRESH_AGENT_13)
- **Branch:** `phase/22-organic`
- **Record:** [docs/experiments/MODULAR_HOUSE_PACK_02.md](docs/experiments/MODULAR_HOUSE_PACK_02.md)
- The first pass left gate 9 met in part. A fresh agent then edited this kit (FRESH_AGENT_13, below), which closes gate 9. Its shared `house_foundation` module also removes the one duplication noted under gate 3.

## Phase 24b: character review modes (track G, G3)

- **Verdict:** PASS (CPU sheet, workbench skeleton/weights/clips, MCP review)
- **Branch:** `phase/22-organic`
- **Record:** [docs/phases/PHASE_24b.md](docs/phases/PHASE_24b.md)
- A person can review a character without leaving Shapewright: one CPU sheet, three new render views, and a workbench 3D view with the skeleton, joint weights and clips. Agents get the same sheet from `review`.

## Phase 24: native rigging and clips (track G, G4 and G5)

- **Verdict:** PASS (Godot: skeleton, skin, clips; Khronos 0/0)
- **Branch:** `phase/22-organic`
- **Record:** [docs/phases/PHASE_24.md](docs/phases/PHASE_24.md)
- The chibi fox is a rigged game character: 19 joints fitted from its own coordinates, bone-heat weights, three procedural clips, and a skinned GLB that the Khronos validator passes with 0 errors and 0 warnings. Godot 4.3 imports it headless with the skeleton intact and the clips playable. No standard pose or clip frame loses more than 10 % of the volume (no candy-wrapper collapse). Rigid clips (a lid, a wheel) work without a skeleton.

## Phase 23: character surface (track G, G2)

- **Verdict:** PARTIAL (painted regions, decals, reference sheet; rubric needs the concept image)
- **Branch:** `phase/22-organic`
- **Record:** [docs/phases/PHASE_23.md](docs/phases/PHASE_23.md)
- Painted regions, procedural decals and the reference image on the review sheet shipped and work on all three creatures. The fox now reads as a fox in a hoodie with a face, and the face reads from the front at 256 px. The gate's rubric against the owner's concept could not be scored, because the concept image is not in the repository. Toon presets were not built.

## Phase 22: native organic kernel (track G, G1)

- **Verdict:** PASS (a shape, not part groups; regions jagged until 23)
- **Branch:** `phase/22-organic`
- **Record:** [docs/phases/PHASE_22.md](docs/phases/PHASE_22.md)
- A new shape, `blend`, meshes SDF primitives into one closed part. The chibi fox, a slime and a mushroom creature are each one watertight, consistently wound mesh that passes all 8 validation layers within budget, builds in 0.9–3.3 s and is deterministic on Linux. Windows is checked by CI against the tolerant signature. Colour-region edges are jagged and small features are coarse at these budgets (see "What is not good yet").

## G0 spike: a native organic mesh (track G)

- **Verdict:** GO (3 plan changes; concept image not in the repo)
- **Branch:** `phase/22-organic`
- **Record:** [docs/phases/G0_SPIKE.md](docs/phases/G0_SPIKE.md)
- A chibi fox in a hoodie built from 11 SDF primitives is one watertight, consistently wound mesh of 6 k triangles in under 5 s. It uses no new dependency and no Blender. It reads as a fox in a hoodie. The face and the colour boundaries are not game quality yet; G2's work is what fixes them.

## Phase 21: shared surfaces and runtime (track F)

- **Verdict:** PASS with exceptions (module texel density lower, 218 hulls; M2 re-run left)
- **Branch:** `phase/21-shared-surfaces`
- **Record:** [docs/phases/PHASE_21.md](docs/phases/PHASE_21.md)
- All six tasks shipped with tests (`tests/test_shared_surfaces.py`). The memory (−83.8 %), LOD, doorway and lightmap gates are met. Texel density went up on the houses but down on 20 of the 26 small modules, and the workshop collider has 218 hulls, not 8 or 24.

## Release 1.0.0

- **Verdict:** PASS (PyPI waits for the owner)
- **Branch:** `release/1.0`
- **Record:** [docs/phases/RELEASE_1.0.md](docs/phases/RELEASE_1.0.md)
- v1.0 bundles tracks A, B, R, W, C2 and D (see the changelog) and was accepted by a fresh agent from the wheel alone.

## Phase 18b: docs site completion (track D)

- **Verdict:** PASS (closes 18's open gate)
- **Branch:** `phase/18b-site`
- **Record:** [docs/phases/PHASE_18b.md](docs/phases/PHASE_18b.md)
- It also closes Phase 18's untested gate ("a reader reproduces the published GLB").

## Phase 17b: verify MCP with real clients (track C)

- **Verdict:** PARTIAL (C2 done; C1, C3 need the owner)
- **Branch:** `phase/17b-mcp-verify`
- **Record:** [docs/phases/PHASE_17b.md](docs/phases/PHASE_17b.md)
- C2 (MCP Inspector) is done. C1 (a desktop client) and C3 (another vendor's agent) need the owner's machine and accounts; they are prepared, not run.

## Phase 15b: web workbench with a three.js 3D view (track W)

- **Verdict:** PASS with exceptions (Windows/Edge/Firefox not verified)
- **Branch:** `phase/15b-web-viewer`
- **Record:** [docs/phases/PHASE_15b.md](docs/phases/PHASE_15b.md)
- Everything shipped and was driven in a real browser (headless Chromium, WebGL through SwiftShader). Not verified: Windows, Edge and Firefox (no such browsers here).

## Phase 25a: presentation renders (track R)

- **Verdict:** PARTIAL (25 s, not 10 s; owner review pending)
- **Branch:** `phase/25a-render`
- **Record:** [docs/phases/PHASE_25a.md](docs/phases/PHASE_25a.md)
- Everything shipped and is deterministic, and the images look much better (evidence below). Two gates are not met: the speed budget (25 s instead of 10 s for a 33k-triangle house at 1024 px) and the owner's judgement, which has not been given yet.

## Phase 19b: finish the kit (track B)

- **Verdict:** PASS (closes 19's PARTIAL)
- **Branch:** `phase/19b-houses`
- **Record:** [docs/phases/PHASE_19b.md](docs/phases/PHASE_19b.md)
- This also closes Phase 19's PARTIAL: all three demo houses are now built only from module-asset instances.

## Phase 20b: cleanup of known defects (track A)

- **Verdict:** PASS
- **Branch:** `phase/20b-cleanup`
- **Record:** [docs/phases/PHASE_20b.md](docs/phases/PHASE_20b.md)
- Every task shipped with a regression test (`tests/test_cleanup_20b.py`). One gate was met in a different way than planned (A1, see below), and one item is not verified here (A7 runs only on Windows CI).

## Phase 20a: golden geometry across Linux and Windows, CI green

- **Verdict:** PASS (macOS out of scope)
- **Branch:** `phase/20a-cross-os-golden`
- **Record:** [docs/phases/PHASE_20a.md](docs/phases/PHASE_20a.md)

## Phase 18: docs site and gallery

- **Verdict:** PARTIAL (deploy not run)
- **Branch:** `phase/18-docs-site`
- **Record:** [docs/phases/PHASE_18.md](docs/phases/PHASE_18.md)
- - **Built and checked:** the site builds in strict mode. Every runnable tutorial block passes as a test, and the gallery renders the real models (checked in headless Chromium). - **Not verified:** deployment. `.github/workflows/docs.yml` is written but has not run; it needs GitHub Pages enabled on the repository. - **Not tested end to end:** the gate's "a reader reproduces the published GLB byte-identically". Determinism of the export is covered by the existing golden tests, not by a site test.

## Phase 20: seam validation

- **Verdict:** PASS (gate restated)
- **Branch:** `phase/20-seams`
- **Record:** [docs/phases/PHASE_20.md](docs/phases/PHASE_20.md)

## Phase 19: composition

- **Verdict:** PARTIAL (1 of 3 houses converted; closed by 19b)
- **Branch:** `phase/19-composition`
- **Record:** [docs/phases/PHASE_19.md](docs/phases/PHASE_19.md)
- Every composition capability shipped and was proven on the kit: - the cottage is now built from module assets; - its source is 76 % shorter; - hand-derived offsets are 0 across all three houses; - the stress test passes.

## Phase 17: MCP server

- **Verdict:** PARTIAL (no agent MCP client run)
- **Branch:** `phase/17-mcp`
- **Record:** [docs/phases/PHASE_17.md](docs/phases/PHASE_17.md)
- The server and the protocol are verified end to end with a scripted client over stdio and HTTP, on two SDK major versions. Two gate items were not verified here: - "the same task through MCP only in two agent clients": no desktop MCP client can run in this container, and a subagent cannot attach a new MCP server; - the MCP Inspector: it was not run.

## Phase 16: packaging + AI docs

- **Verdict:** PASS (Docker not built)
- **Branch:** `phase/16-packaging`
- **Record:** [docs/phases/PHASE_16.md](docs/phases/PHASE_16.md)
- (The Docker item, not verified at first, was verified at release 1.0: see the gate table.)

## MODULAR_HOUSE_PACK_01: a modular house kit as a real-user acceptance test

- **Verdict:** PARTIAL
- **Branch:** `test/modular-house-pack`
- **Record:** [docs/experiments/MODULAR_HOUSE_PACK_01.md](docs/experiments/MODULAR_HOUSE_PACK_01.md)
- The kit works: - 26 modules and 3 visibly different houses, all built from one pack. - 0 visible z-fighting pairs. - A 5-parameter stress test rebuilt everything with no coordinate edits. - Valid, game-ready GLBs.

## Before Phase 16 (stages 0 to 15)

The framework itself: research and architecture, the vertical slice, hardening, the spatial modelling language,
components and families, the surface system (UVs, baked textures), modelling breadth, 50k-triangle performance,
import and repair, game-ready production for Godot / Unity / Unreal, cross-agent validation, agent cost and the
human workbench. Each stage is recorded in [ROADMAP.md](docs/ROADMAP.md) and the experiments in [docs/experiments](docs/experiments).
