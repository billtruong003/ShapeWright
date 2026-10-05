# Remaining work: complete task list, plan and progress

Status measured on `main` @ `6094518` (2026-10-05): CI green on Linux and Windows, 433 tests pass, docs site auto-deploys.
This file is **the work queue** for long runs: do the tasks in order, tick them here in the same commit that finishes
them, and update the progress table at the end.

## 1. Progress

Progress is counted in effort points. One point is about one medium agent session (one small phase).

**What is counted.** The figures below count **every** open item found by a full sweep of the repository on 2026-10-05:
- every phase record's "not done", "not verified" and "left for later" lists;
- the ROADMAP stages and HARDENING's open items;
- MODULAR_HOUSE_PACK_01's limitations;
- the Phase 13–18 open gates.

Nothing is left out. The earlier figures (87 % and 83 %) counted fewer items, which is why these are lower.

| scope | done | remaining | **progress** |
|---|---|---|---|
| **v1.0** (tracks A, B, R, C, D, E): prop and kit framework, polished, verified, released | 42 | 10.75 | **≈ 80 %** |
| **v1.0 + Phase 21** (track F: shared atlas, LOD on kits, collision, lightmap UVs) | 42 | 14.75 | **≈ 74 %** |
| **planned roadmap** (+ track G: character track and the Blender render path) | 42 | 25.75 | **≈ 62 %** |
| **everything ever listed** (+ track H: the long-term backlog, not scheduled) | 42 | ≈ 35.75 | **≈ 54 %** |

## 2. Master checklist (every remaining task)

`who`: **agent** means an agent can do it alone; **owner** needs you (a desktop app, a token, Docker, your eyes).
Tick `[x]` here in the commit that finishes a task.

| ✓ | ID | task | pts | depends | who |
|---|---|---|---|---|---|
| [ ] | A1 | Fix z-fighting in 15 benchmark assets (78 pairs) | 0.6 | — | agent |
| [ ] | A2 | tavern_chair `seat_height` min 0.40 → 0.42 (agree with its check) | 0.05 | — | agent |
| [ ] | A3 | `sw export --preview`: GLB without collision proxies; site uses it | 0.3 | — | agent |
| [ ] | A4 | Townhouse door brace ↔ ledges: 12 mm depth rank | 0.05 | — | agent |
| [ ] | A5 | Library examples never write into the library (`.build`/`export` go to the project) | 0.3 | — | agent |
| [ ] | A6 | "N info hidden" lists the hidden codes | 0.05 | — | agent |
| [ ] | A7 | `sw.cmd` launcher for Windows clones (same as `./sw`) | 0.05 | — | agent |
| [ ] | A8 | YAML schema errors carry the source line number (HARDENING: open since v0.1) | 0.1 | — | agent |
| [ ] | B1 | `house_townhouse` from module assets (309 → ≤ 150 lines) | 0.8 | A1, A4 | agent |
| [ ] | B2 | `house_workshop` from module assets (437 → ≤ 220 lines) | 0.8 | B1 | agent |
| [ ] | B3 | Stress test of the 3 houses (pack values changed in a copy) | 0.1 | B2 | agent |
| [ ] | B4 | Rebuild `modular_house_pack/` bundle + metrics | 0.2 | B3 | agent |
| [ ] | B5 | `asset:` instances import the instanced asset's sockets | 0.1 | — | agent |
| [ ] | B6 | Window-size family in the kit (`house_wall_window` `win_size` small/standard/tall) | 0.5 | B1 | agent |
| [ ] | R1 | `beauty` render mode: 3-point light, shadow map, AO, contact shadow, tone map, 4× AA | 1.0 | — | agent |
| [ ] | R2 | Turntable GIF/MP4 (`--turntable N`) | 0.25 | R1 | agent |
| [ ] | R3 | Presentation sheet (`sw sheet --present`): views, details, wireframe, silhouette, palette | 0.5 | R1 | agent |
| [ ] | R4 | Regenerate README, gallery, home hero and bundle renders in beauty mode | 0.15 | R1–R3, B4 | agent |
| [ ] | R5 | MCP `render` accepts `beauty`; docs page; llms.txt | 0.1 | R1 | agent |
| [ ] | R6 | Human-scale silhouette + dimension overlay in orthographic review views (ROADMAP Stage 3) | 0.25 | — | agent |
| [ ] | C1 | MCP through a real desktop client (Claude Desktop or Cursor), one unseen prop, Windows launch documented | 0.5 | A5 | **owner** + agent |
| [ ] | C2 | MCP Inspector run on the tool schemas (Phase 17 gate) | 0.25 | — | agent (needs Node) |
| [ ] | C3 | Another vendor's agent (Codex CLI or ChatGPT via MCP) does one prop (closes Phase 13's open gate) | 0.5 | C1 | **owner** + agent |
| [ ] | D1 | Tutorial: composition (nested components, `asset:`, measure/pivot on instances) | 0.3 | B1 | agent |
| [ ] | D2 | Concept page: seams (codes, fixes, before/after renders) | 0.2 | A1 | agent |
| [ ] | D3 | Changelog page generated from the phase records | 0.2 | — | agent |
| [ ] | D4 | Windows notes in every quickstart | 0.1 | A7 | agent |
| [ ] | D5 | README badges (CI, docs) + changelog link | 0.05 | D3 | agent |
| [ ] | D6 | Doc test: a tutorial's exported GLB is byte-identical to the published one (Phase 18 gate) | 0.25 | — | agent |
| [ ] | D7 | Docs use beauty renders (after R4) | 0.15 | R4 | agent |
| [ ] | E1 | Version 1.0.0; package vs format version documented | 0.1 | all of A–D | agent |
| [ ] | E2 | `CHANGELOG.md` | 0.1 | D3 | agent |
| [ ] | E3 | Docker image build + run + `mcp` (closes Phase 16's open gate) | 0.3 | — | **owner** (Docker) |
| [ ] | E4 | Godot headless import smoke test in CI (ROADMAP Stage 5) | 0.5 | — | agent |
| [ ] | E5 | Fresh-agent acceptance on the release (FRESH_AGENT_12: a prop + a mini kit) | 0.5 | E1 | agent |
| [ ] | E6 | Tag `v1.0.0`, GitHub release with wheel + bundle zip | 0.25 | E1–E5 | agent (owner approves) |
| [ ] | E7 | PyPI upload | 0.25 | E6 | **owner** (token) |
| [ ] | F1 | Pack atlas / trim sheet (≥ 60 % less texture memory for the kit) | 1.2 | v1.0 | agent |
| [ ] | F2 | Vertex-colour / palette material path for one-material stylized props (COLOR_0 already exported; add an archetype and palette validation) | 0.4 | — | agent |
| [ ] | F3 | Merge-by-distance with tolerance + partial-duplicate detection for imports | 0.4 | — | agent |
| [ ] | F4 | LODs on the kit and the houses (LOD + IoU already exist in export/lod.py: apply, set thresholds, report) | 0.3 | F1 | agent |
| [ ] | F5 | Multi-hull collision; a walkable doorway in the workshop | 0.7 | — | agent |
| [ ] | F6 | Lightmap UVs (UV1, non-overlapping) for Unity/Unreal static lighting (ROADMAP Stage 4) | 1.0 | — | agent |
| [ ] | G1 | Phase 22: Blender backend for organic forms (+ CPU marching-cubes fallback) | 4 | v1.0 | agent (Blender) |
| [ ] | G2 | Phase 23: character surface (decals, region palettes, toon), reference images in sources (ROADMAP Stage 4) | 2 | G1 | agent |
| [ ] | G3 | Phase 24: rigging (skeleton from anchors, weights via Blender, rigid clips for doors/lids/wheels) | 4 | G1 | agent (Blender, Godot) |
| [ ] | G4 | Phase 25b: Blender render path (Cycles/Eevee) for the presentation sheet | 1 | R3, G1 | agent (Blender) |
| [ ] | H* | Long-term backlog (§11): plugins, loft, selectors/bevel, cross-part booleans, YAML loops, cost gate, workbench user test, near-float, macOS, interiors, north-star village | ≈ 10 | — | later |

Done so far (42 points):

| work | points |
|---|---|
| Stages 0–2.5 (research, architecture, vertical slice, hardening) | 4 |
| Phases 5–15 (spatial language, reuse, surfaces, breadth, performance, import, production, cross-agent, cost, workbench) | 22 |
| MODULAR_HOUSE_PACK_01 (26 modules, 3 houses, metrics, bundle) | 3 |
| Phase 16 packaging | 1 |
| Phase 17 MCP | 2 |
| Phase 18 docs site | 2 |
| Phase 19 composition | 3 |
| Phase 20 seams | 2 |
| Phase 20a cross-OS goldens and CI | 1 |
| docs and README polish | 2 |

## 2b. Rules for every task

These are the same rules as docs/PHASE_PLAN_16.md section 1 and docs/HANDOFF.md.

- **Branching.**
  - Use one branch per track: `phase/20b-cleanup`, `phase/19b-houses`, and so on, cut from the latest `main`.
  - Open a PR. CI (lint, ubuntu, windows) must be green before merge.
  - The owner merges, or the agent fast-forwards `main` when the owner has said so.
- **Commits.** Author billthedev, with no Co-Authored-By or session trailers. Every golden change is explained per asset in the commit message: `python3 tests/update_golden.py`.
- **Checks before each commit:**
  - `ruff check .`;
  - `python3 -m pytest -q` (use `-k` while iterating);
  - `./sw caps --llms > llms.txt` when caps or doc strings change.
- **Look at what you change.**
  - Run `./sw review NAME` and open `.build/sheet.png`.
  - For assets also run `python3 tools/experiments/seam_probe.py NAME --tol 0.002`.
- **Record.** Each track ends with `docs/phases/PHASE_<id>.md` containing: what shipped, evidence, a gate table, and a PASS / PARTIAL / FAIL verdict.
- **Supported platforms:** Linux and Windows. macOS is out of scope (docs/phases/PHASE_20a.md).

---

## 3. Track A: cleanup of known defects (`phase/20b-cleanup`), 1.5 points

**A1. Fix the z-fighting in 15 benchmark assets** (78 pairs; `SEAM_COPLANAR_OVERLAP` on current main).

How:
1. List the pairs:

   ```bash
   python3 -c "import sys;sys.path.insert(0,'.');from shapewright.assemble import build;from shapewright.validate.seams import coplanar_pairs;[print(r) for r in coplanar_pairs(build('assets/NAME').parts) if r['same_facing_m2']>=5e-5]"
   ```

2. For each pair, find the shared plane with `./sw render NAME --part P --view ...`. Then pick the fix:
   - **flush faces of two parts** (e.g. a leg flush with a rail): inset the smaller part 2–3 mm, or extend it 3 mm *into* the other;
   - **coincident ends** (a stringer end against a newel face): end one part inside the other (embed ≥ jitter + 1 mm);
   - **an attachment lying on a surface** (a hinge on a lid): lift it 1–2 mm, or embed it 1 mm.
3. Prefer changing a param or an anchor offset over adding a new part. Keep the look.

| asset | pairs | example pair | likely fix |
|---|---|---|---|
| ornate_fountain | 19 | bed_n ↔ plinth_n tops | lower the bed tops 2 mm, or raise the plinths |
| wooden_staircase (and its 3 variants: long_shallow, short_wide, steep_narrow) | 6 each | stringer ↔ newel_bottom, riser_0 ↔ newel | inset the stringers 3 mm from the newel face (one change in the base fixes all 4) |
| park_bench, park_bench_unreal | 6 each | rear_leg ↔ seat_rail, back_post | rails 3 mm narrower than the legs |
| roof_section | 8 | wall_plate ↔ rafter_n | rafters notch 5 mm into the plate (offset) |
| mine_cart | 4 | wheel ↔ axle | axle ends 3 mm proud of the hubs |
| pipe_assembly | 2 | stand_post ↔ stand_foot | embed the post 5 mm into the foot |
| stone_doorway | 2 | wall ↔ plinth fronts (1,396 cm²) | plinths 5 mm proud of the wall |
| storage_chest, storage_chest_unreal | 2 each | lid ↔ hinge | lift the hinges 1.5 mm |
| tavern_table | 2 | stretcher ↔ cross_stretcher | cross stretcher 3 mm narrower |
| well_winch | 1 | crank ↔ grip | embed the grip 3 mm |

Gate: the seam check prints 0 flagged assets; each asset's sheet looks the same at a glance (attach before/after for 3 of them); goldens updated and explained.

**A2. Make `tavern_chair` agree with itself.**
- Today `seat_height` has `min: 0.40`, but its check requires ≥ 0.42.
- Change the param `min` to 0.42 (the check is the design intent).
- Gate: `./sw validate tavern_chair --set seat_height=0.42` passes.

**A3. Add a preview export without collision proxies.**
1. Add `sw export NAME --preview` (and `export: {preview: true}` in the source). It writes `export/NAME_preview.glb` without `COL_`/`UCX_`/`-colonly` nodes and without LOD files.
2. `tools/site/build_site.py` uses the preview export; delete `_strip_collision`.
3. Add a test: the preview GLB has no collision nodes and the same visible meshes.

Gate: the gallery still renders the real models; Khronos 0 errors on the preview files.

**A4. Townhouse door: rank the brace and ledges.**
- The probe flags `door_brace ↔ door_ledge_0/1` (2.36 cm² at 1–2 mm).
- In `components/house_door.yaml`, rank the brace 12 mm behind the ledges, the same depth-rank rule as the walls.
- Gate: `seam_probe house_townhouse --tol 0.002` gives 0 pairs.

**A5. Stop library examples writing build files into the library.**
- `sw review/render/export` on a *library* asset writes `.build/` and `export/` next to it. In a pip install that is site-packages.
- Fix: write build products of library assets to `<project>/.build/library/<name>/`.
- Test with a read-only library folder (`chmod -w`, or a temp copy).
- Gate: `review`, `render` and `export` of `barrel` work with the library read-only, and the MCP `review(barrel)` still returns its image.

**A6. Small ergonomics from FA-11.** The "N info items hidden" line lists the codes it hides (e.g. `(2 info hidden: UV_UNLOCKED, ASM_CONTACT_ONLY; --verbose)`).

**A7. Windows launcher.**
- Add `sw.cmd` next to `sw`: `@python -m shapewright %*` with the repo on `PYTHONPATH`, as `sw` does.
- Test on Windows CI: `sw.cmd doctor` exits 0.

**A8. Line numbers in source errors.**
- Load YAML with a loader that records the line of every mapping key (a `SafeLoader` subclass storing `node.start_mark.line`).
- `Ctx.error(where=...)` maps `parts.leg.shape.size[0]` to `asset.yaml:42`.
- The text output shows `asset.yaml:42 parts.leg...`.
- Test: a typo on a known line reports that line.

Record: `docs/phases/PHASE_20b.md`.

---

## 4. Track B: finish the kit (`phase/19b-houses`), 2.5 points

**B1. Rebuild `house_townhouse` from module assets.**
- Today it has 309 non-comment lines and 1 module instance. The target is ≤ 150 lines.
- Steps:
  1. Map each section of its source to a module: footing, corner, floor, beam, wall_* (ground and upper), roof_section, roof_end, gable, ridge, chimney, steps.
  2. Where a module lacks a parameter the townhouse needs, add a module param with a default equal to today's value, so module goldens do not change. For example:
     - `house_wall_upper`: `braces`, `opening`, `seed`;
     - `house_beam`: `length` for the floor band;
     - `house_chimney`: already has `height` and `shoulder`;
     - the gable facing the street: `rotate` on the instance.
  3. Rewrite the house with `asset:` instances and grid arithmetic, like `house_cottage`.
- Gate:
  - same triangle count ±2 %;
  - 0 seam pairs;
  - `./sw validate` PASS or WARN (texel only);
  - side-by-side render before/after.

**B2. Rebuild `house_workshop` the same way.**
- Today it has 437 non-comment lines. The target is ≤ 220.
- The wing shares the main block's grid line: place shared posts and walls once (see MODULAR_HOUSE_PACK_01 §14).
- The wing roof dies into the main wall: either a `house_roof_section` param `trim` / `length`, or a measured length.

**B3. Stress test.**
1. In a temp copy of the repo, set `bay 2.4, storey 3.3, timber 0.22, post 0.32, pitch 55` in `packs/cozy_house.yaml`.
2. Rebuild the 3 houses: validate plus seam probe.
3. Never commit those values.

Gate: 0 coordinate edits needed, 0 seam pairs.

**B4. Rebuild the deliverable bundle.**
1. `for a in assets/house_*/; do ./sw export "$(basename "$a")"; done`
2. `./sw export house_{cottage,townhouse,workshop} --target godot`
3. `python3 tools/experiments/build_mhp_bundle.py`
4. Update the metrics in `modular_house_pack/README.md` and the MODULAR_HOUSE_PACK_01 addendum (source lengths, parameterization).

**B5. Import an instanced asset's sockets.**
- Today an `asset:` instance drops the sockets of the asset it places.
- Import them as `<instance>_<socket>`, transformed with the instance and replicated with array and mirror.
- Test with the cottage's `entrance` socket placed through a wrapper asset.

**B6. Window-size family.**
- MODULAR_HOUSE_PACK_01 §16 reported "one window size".
- Add pack params `win_w_small`, `win_h_tall` and a `house_wall_window` param `size: 0 small | 1 standard | 2 tall` that picks the opening, frame and shutter sizes.
- Use the small size on the townhouse upper floor and the tall size on the workshop's tavern front.
- Gate: all three sizes validate, seam-clean, shutters measured (no offsets).

Record: `docs/phases/PHASE_19b.md`. This also closes Phase 19's PARTIAL.

---

## 5. Track C: verify MCP with real clients and another vendor (`phase/17b-mcp-verify`), 1.25 points

1. On the owner's machine, register the server in Claude Desktop or Cursor: `pip install -e ".[mcp]"`, then `sw mcp --project <scratch folder>` (docs/MCP.md).
2. Run an unseen request through MCP tools only, for example *"a stylized wooden signpost with two arrow signs, mobile, under 800 tris, export for Godot"*.
3. Record tool calls, tokens or time, whether the model looked at the returned sheet, and every friction point.
4. Fix generic friction (tool descriptions, error messages) with tests.
5. On Windows, check that `sw mcp` starts from the Claude Desktop config: the command may need the full path to `sw.exe` or `python -m shapewright mcp`. Document this in docs/MCP.md.

Gate: the asset exports PASS through MCP only. The gate table in docs/phases/PHASE_17.md is updated to PASS or PARTIAL with the reason.

**C2. MCP Inspector.**
- Run `npx @modelcontextprotocol/inspector sw mcp --project <dir>`, list the tools and call `guide`, `brief`, `review`.
- Record schema warnings and fix them.

**C3. Another vendor's agent** (closes Phase 13's open gate "a run by another vendor's agent").
- Use Codex CLI (config in docs/MCP.md) or ChatGPT with a connector to an HTTPS tunnel of `sw mcp --transport streamable-http`.
- Give it the same unseen prop.
- Record it as `docs/experiments/FRESH_AGENT_13.md`: calls, success, friction, whether it looked at the sheet.

---

## 6. Track D: docs site completion (`phase/18b-site`), 1.25 points

**D1. Composition tutorial.** Add `website/use-cases/composition.md`: a nested component, an `asset:` instance with `with:`, `measure:` and `pivot:` on an instance. Every block is `# run`, built in a fresh project (tests/test_site_docs.py runs it).

**D2. Seams page.** Add `website/concepts/seams.md`: what `SEAM_COPLANAR_OVERLAP`, `ASM_CONTACT_ONLY` and `OP_FACES_INVERTED` mean, the three fixes, before/after renders from A1.

**D3. Changelog.** `tools/site/build_site.py` generates `website/changelog.md` from the verdict lines and gate tables of `docs/phases/PHASE_*.md`.

**D4. Windows notes in the quickstarts.**
- On Windows, `./sw` is `sw` after `pip install -e .`, or `python -m shapewright`.
- venv activation is different.
- The Node validator is optional.

**D5. README badges** (CI, docs) and a link to the changelog.

**D6. Reproducibility test** (Phase 18 gate, "a reader reproduces the published GLB").
- A test exports the prop tutorial's asset twice in fresh projects and compares the GLB bytes with each other.
- On Linux it also compares them with a committed reference hash.

**D7. Beauty renders in the docs.** After R4, home, gallery, tutorials and README use the beauty renders; the site rebuilds.

Gate: `mkdocs build --strict` passes, the doc tests pass, the docs workflow is green, and the new pages are linked from the nav and the README.

---

## 6b. Track R: presentation renders (`phase/25a-render`), 2.25 points

The native renderer is built for *inspection*: Lambert key + fill, specular, outlines, 2× supersampling, deterministic. It has no shadows, no ambient occlusion and no presentation layout. README, docs and portfolio images need more. This track is native: no GPU, no Blender. The deterministic inspection modes must stay **byte-identical**, so all existing render tests stay unchanged.

**R1. A `beauty` render mode** (`sw render NAME --mode beauty`):
- three-point lighting: key, fill, and rim for silhouette separation;
- **shadows** from a shadow map of the key light;
- **ambient occlusion**: screen-space, or per vertex from the baked ORM occlusion when present;
- **a ground contact shadow** under floor props;
- tone mapping and a soft background gradient;
- 4× supersampling.

Gate:
- a test that the inspection modes are unchanged (hash of `clay` and `textured` renders);
- `beauty` is deterministic: same bytes twice;
- under 10 s for a 33k-tri house at 1024 px.

**R2. Turntable output.** `sw render NAME --turntable 24 --mode beauty` writes a GIF, plus an MP4 when `imageio-ffmpeg` is installed. Frames are deterministic.

**R3. Presentation sheet.** `sw sheet NAME --present` lays the asset out like a concept-art sheet:
- front / side / back / 3/4 in beauty mode;
- detail close-ups of 4 named parts, chosen automatically (largest or most complex) or from `present: {details: [...]}`;
- a wireframe row and a silhouette row;
- the palette swatches from its materials;
- triangle and material counts in the footer.

**R4. Use them everywhere.**
- `tools/site/build_site.py`: gallery posters and the home hero in beauty mode, plus one turntable GIF.
- README images regenerated (`docs/images/readme_*.png`).
- `modular_house_pack/renders/` gets beauty versions.

**R5. MCP and docs.**
- MCP `render` accepts `mode: beauty`.
- A docs page "Presentation renders" with examples.
- llms.txt regenerated.

**R6. Scale reference in review views** (ROADMAP Stage 3).
- In orthographic `review` and `render` views, add an optional 1.75 m human silhouette next to the asset (`--scale-ref`), plus dimension lines for overall width, height and depth.
- Off by default in deterministic test renders.

Gate for the track: side-by-side before/after for 4 assets in the record (a prop, a textured chest, a house, the fountain). The owner judges them better at a glance. Determinism and the speed budget hold.

Record: `docs/phases/PHASE_25a.md`.

---

## 7. Track E: release v1.0 (`release/1.0`), 2 points

1. **Version.**
   - `pyproject.toml` version `1.0.0`.
   - The `shapewright: 0.1` format version stays (sources are compatible). Document the difference between package version and format version in ASSET_FORMAT.
2. **`CHANGELOG.md`** at the repo root, generated from the same data as D3.
3. **Docker.** On a machine with Docker:
   - `docker build -t shapewright .`
   - `docker run --rm -v "$PWD:/work" shapewright brief "a barrel"`
   - `docker run --rm -i shapewright mcp` answering `initialize`
   - Record it in docs/phases/PHASE_16.md, which closes its "not verified" item.
4. **Fresh-agent acceptance on the release.**
   - In a clean venv: `pip install git+https://github.com/billtruong003/ShapeWright@v1.0.0`.
   - A fresh agent gets only `llms.txt` and two unseen requests: a prop, and a 3-module mini kit that uses `asset:` instances.
   - Record it as `docs/experiments/FRESH_AGENT_12.md`.
5a. **Godot smoke test in CI** (ROADMAP Stage 5; Phase 12 verified Godot only by hand).
   - A CI job (ubuntu) downloads Godot 4.3 headless and imports the cottage, the barrel and the fountain `_godot.glb`.
   - It asserts the node count, the materials and that the collision bodies exist.
   - Cache the Godot download.
5. **Tag and GitHub release.**
   - `git tag v1.0.0 && git push origin v1.0.0`.
   - Create a GitHub release with the wheel (`pip wheel --no-deps -w dist .`), the `modular_house_pack` zip, and the changelog.
6. **(Owner decision) PyPI.**
   - `python -m build && twine upload dist/*` needs the owner's PyPI token. The project name `shapewright` must be free.
   - Without PyPI, the git install stays the documented way.

Gate: the tag exists, the release has assets, the fresh agent succeeds on both requests, Docker is verified, and CI is green on the tag.

**At this point v1.0 is done (100 % of the v1.0 scope).**

---

## 8. Track F: Phase 21, shared surfaces and runtime (`phase/21-shared-surfaces`), 4 points

This is the plan's brief in docs/PHASE_PLAN_16.md §5, broken into tasks.

1. **F1. Pack atlas / trim sheet.**
   - Add `packs/NAME.yaml: atlas: {size: 2048, materials: [timber, plaster, ...]}`.
   - Bake one texture per pack; modules map their parts' UVs into its material regions. That means a trim sheet: each material owns a region; parts tile within it along their long axis.
   - Export references the shared image.
   - Gate:
     - total texture memory of the 26 modules plus 3 houses drops ≥ 60 %;
     - texel density is equal or better;
     - the review sheets show no seams.
2. **F2. Vertex colours.** Add a material `archetype: vertex` (colour per part or region, no texture) for mobile and low profiles. Export `COLOR_0`. Godot import OK.
3. **F3. Merge by distance.**
   - Add `{type: clean, weld: 0.0005}` with a tolerance.
   - Add partial-duplicate detection for imports (the `GEO_DUPLICATE_FACES` family with a tolerance).
   - Tests with fixture meshes.
4. **F4. Auto-LOD.**
   - Add `export: {lods: [0.5, 0.25]}` using UV-preserving decimate.
   - Verify silhouette IoU against LOD0 from 6 views: ≥ 0.95 for LOD1, ≥ 0.90 for LOD2. Report it in the export report.
5. **F5. Multi-hull collision.**
   - Add `collision: {mode: hulls, max: 8}` (convex decomposition by parts or by an approximate VHACD-like split).
   - The workshop gets a walkable doorway.
   - Godot import check: a collider count, and a ray through the door passes.

6. **F6. Lightmap UVs** (ROADMAP Stage 4).
   - A second UV set (`TEXCOORD_1`), non-overlapping and with padding, via xatlas.
   - Enabled per profile (`unity`, `unreal`) or with `uv: {lightmap: true}`.
   - Validator: overlap 0, texel ratio within 2× across parts.
   - Gate: imported in Godot, UV1 present; Unity and Unreal by convention.

Record: `docs/phases/PHASE_21.md`. Milestone **M2, kit-grade**: re-run the MODULAR_HOUSE_PACK gates and aim for a strong PASS.

---

## 9. Track G: character track (optional, after v1.0), 11 points

The revision note at the top of docs/PHASE_PLAN_16.md applies: Blender is an optional headless backend, and Shapewright stays the source of truth.

| phase | tasks (summary) | gate |
|---|---|---|
| 22 Blender backend for organic forms (4, G1) | `blend:` groups → `blender -b -P` smooth union / voxel remesh → `mesh_file` with provenance; CPU marching-cubes fallback; reproducibility hash per Blender version | chibi body is one watertight mesh with blended joints, within budget |
| 23 Character surface (2, G2) | projected decals (eyes, mouth), region palettes, toon presets; **reference images in sources** shown next to matching views (ROADMAP Stage 4) | fox-hoodie figurine vs the concept, rubric scored |
| 24 Rigging (4, G3) | skeleton from anchors (native), weights and a skinned GLB via Blender, pose renders, rigid clips (doors, lids, wheels) | rigged fox in Godot, no deformation artefacts |
| 25b Blender render path (1, G4) | Cycles/Eevee renders of the same sheet layout when Blender is present (the native beauty mode from Track R stays the default) | the same 4 assets rendered both ways; native output unchanged |

---

## 10. Order and milestones

```
20b cleanup (A) ──► 19b houses (B) ──► 25a render (R) ──► 18b site (D) ──► release v1.0 (E) ──► 21 (F) ──► 22 ► 23 ► 24, 25b (G)
      └── 17b MCP verify (C): when the owner has a desktop client ready; C3 after C1
```

| milestone | after | v1.0 progress | full planned roadmap (A–G) |
|---|---|---|---|
| today | — | 80 % | 62 % |
| defects cleared | A | 82 % | 64 % |
| kit complete (3 houses from modules, window family, bundle rebuilt) | B | 87 % | 68 % |
| presentation renders | R | 91 % | 71 % |
| MCP verified, other vendor tried | C | 94 % | 73 % |
| docs complete (beauty renders, changelog, Windows notes) | D | 96 % | 75 % |
| **v1.0 released** | E | **100 %** | 78 % |
| kit-grade runtime (M2) | F | — | 84 % |
| characters (M3) | G | — | 100 % (planned roadmap) |

Track H (backlog) is outside these figures; counting it as well, the project is ≈ 54 % of everything ever listed.

## 11. Track H: long-term backlog (not scheduled, ≈ 10 points)

Every item comes from a recorded source. Pick one up only with a recorded failing case (the run protocol).

| item | source | note |
|---|---|---|
| Plugin packages (entry points) for third-party shapes, ops and validators | ROADMAP Stage 5 | `[project.entry-points."shapewright.plugins"]`; listed by `sw caps` |
| Curves: `loft` between profiles, `follow_curve` | ROADMAP Stage 4 | `tube` covers sweeps today |
| Selectors (`faces: {normal: +y}`) + `bevel` on selected edges | ROADMAP Stage 3, DESIGN_REVIEW | chamfer_box covers boxes today |
| Cross-part booleans (cut a window through several parts) | HARDENING (open) | components cut inside themselves today |
| YAML loops/functions (beyond arrays, components, `enabled`) | HARDENING (partial) | arrays with `each` cover most cases |
| Phase 14 cost gate (total agent cost down 30 % on held-out tasks) | ROADMAP Phase 14 ✗ | re-measure after v1.0 with `tools/experiments/cost_breakdown.py` |
| Workbench tried by people | Phase 15 | needs human testers |
| Near-float check (1–5 mm off a second surface) | PHASE_20 not done | no real case since |
| macOS support | PHASE_20a | build `chamfer_box` explicitly (no hull); needs a Mac |
| Kit interiors: interior walls, stairs, upper floor openings | MODULAR_HOUSE_PACK_01 §16 | the next kit test |
| Detail-density balance across a kit (18.6× spread) | MODULAR_HOUSE_PACK_01 §8 | a `sw pack` density warning, then rebalance |
| MCP over HTTP with built-in auth | docs/MCP.md | a reverse proxy covers it today |
| North star: "a stylized fishing village pack for a cozy mobile game" end to end | ROADMAP Stage 6 | the final acceptance test |
