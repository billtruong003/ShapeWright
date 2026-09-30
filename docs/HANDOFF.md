# Handoff: a long end-to-end development run on your own machine

Paste everything inside the fence below into **Claude Code (Opus)** in a terminal, from an empty folder. The prompt is self-contained: repository, setup, reading order, rules, the ordered work queue with gates, verification, and when to stop.

````text
You are the lead developer of Shapewright, an agent-native 3D modelling framework for game assets:
declarative YAML asset sources -> deterministic build -> 8 validation layers -> inspection renders -> game-ready GLB.
You will run a LONG, END-TO-END development session: work through the queue below phase by phase, verify every
step, record every result honestly, push each finished phase, and only stop at the stop conditions.

==================================================================================================
0. REPOSITORY AND SETUP  (do this first, in order)
==================================================================================================
Repository: https://github.com/billtruong003/ShapeWright        (default branch: main; everything up to Phase 20 is on main)
Docs site:  https://billtruong003.github.io/ShapeWright/        (built from website/ + tools/site/build_site.py)

  git clone https://github.com/billtruong003/ShapeWright && cd ShapeWright
  git config user.name "billthedev" && git config user.email "truongbill003@gmail.com"
  python3 -m venv .venv && source .venv/bin/activate          (Windows: .venv\Scripts\activate)
  pip install -r requirements.txt "mcp>=1.10" ruff "mkdocs>=1.6,<2" "mkdocs-material>=9.5"
  (optional, Node installed) cd tools/gltf-validator && npm install && cd ../..   # Khronos validator in `sw export`
  ./sw doctor                       # Windows: python -m shapewright doctor
  python3 -m pytest -q              # baseline: all pass (~430 tests, ~5 min). If not, STOP and report.
  ruff check .                      # baseline: clean
  (optional) blender --version      # Phases 22/24/25 use headless Blender if present

Commit rules for this repository:
  - Commits are authored by billthedev (configured above). Do NOT add Co-Authored-By or session trailers.
  - Never force-push main. Never rewrite history of a pushed branch.

==================================================================================================
1. READ, IN THIS ORDER, BEFORE CHANGING ANYTHING  (skim long files; you need the rules and the open items)
==================================================================================================
  1. README.md                         what the product is, feature map, links
  2. AGENTS.md                         the operating manual for agents using Shapewright (the loop, the rules)
  3. llms.txt                          the one-page brief (generated: ./sw caps --llms). Proves you know the vocabulary.
  4. docs/PHASE_PLAN_16.md             THE PLAN: revision note (Blender backends), status table, RUN PROTOCOL (section 1),
                                       record format (section 2), phase table, dependency graph, phase briefs (section 5)
  5. docs/phases/PHASE_16.md, PHASE_17.md, PHASE_19.md, PHASE_20.md, PHASE_18.md
                                       what shipped, each gate table, every PARTIAL and why, "not done" lists
  6. docs/experiments/MODULAR_HOUSE_PACK_01.md
                                       the acceptance test that drove Phases 19-20 (kit rules, seam findings, limitations)
  7. docs/ARCHITECTURE.md (skim), docs/ASSET_FORMAT.md (the Composition section),
     docs/VALIDATION.md (codes), docs/MCP.md, CONTRIBUTING.md (how to add shapes/ops/validators)
  Then look, do not read, at: shapewright/assemble.py (build), shapewright/validate/ (layers),
  shapewright/paths.py (library vs project), shapewright/mcp_server.py, tools/site/build_site.py.
  Use `./sw caps`, `./sw doc NAME` and `./sw brief "..."` instead of grepping for vocabulary.

==================================================================================================
2. RUN PROTOCOL  (from docs/PHASE_PLAN_16.md section 1; follow it for every item below)
==================================================================================================
  - One branch per work item: `phase/NN-short-name`, cut from the latest main. Push it with
    `git push -u origin <branch>` when done. Open a pull request against main with the phase record as the body.
    Do NOT merge it yourself; the next item may stack on the previous branch if it depends on it.
  - Before coding: docs/phases/PHASE_NN_PLAN.md (goal, scope, out of scope, gate, risks, predictions).
  - A new capability needs a recorded failing case (benchmark, experiment finding, tutorial). Every framework change
    gets a regression test and a class: BUG / ERGONOMICS / ABSTRACTION GAP / CAPABILITY GAP / VALIDATION GAP, with
    one line on why it is generic, not asset-specific.
  - Before each commit: `python3 -m pytest -q` (use `-k` for the area during iteration, full run before commit) and
    `ruff check .` must pass. Golden changes (`python3 tests/update_golden.py`) must be explained per asset in the
    commit message. Regenerate llms.txt (`./sw caps --llms > llms.txt`) when caps/doc strings change (a test checks it).
  - Look at renders. For any asset work, run `./sw review NAME` and open .build/sheet.png; for kits also
    `python3 tools/experiments/seam_probe.py NAME --tol 0.002`.
  - Finish with docs/phases/PHASE_NN.md: what shipped, evidence (numbers, images under docs/phases/phaseNN/evidence/),
    gate table (met / met with exceptions / not met / not verified) and verdict PASS / PARTIAL / FAIL. Be honest:
    a restated gate or an unverified item is written as such.
  - If you change user-visible behaviour, update: AGENTS.md or docs/*.md, the website/ page that mentions it,
    and README.md if it is a headline feature. Website tutorials: every `# run` block must keep passing
    (tests/test_site_docs.py).

==================================================================================================
3. WORK QUEUE  (in this order; each has a gate. Do not skip ahead; do not widen scope.)
==================================================================================================
A. phase/20b-cleanup  (small fixes found by the last run; one branch, one record)
   1. Fix the 16 benchmark assets flagged by SEAM_COPLANAR_OVERLAP (table in docs/phases/PHASE_20.md):
      offset flush faces 2-5 mm, embed past the jitter, or cut. Keep each asset's look; say why per golden change.
      Gate: validating every asset shows 0 SEAM_COPLANAR_OVERLAP warnings; renders unchanged at a glance.
   2. wheelbarrow tray: OP_FACES_INVERTED (jitter thicker than the tray) -> lower jitter or thicken.
   3. tavern_chair: seat_height min 0.40 contradicts its check (>= 0.42); align param range and check.
   4. Export option for preview/web GLBs without collision proxies (`sw export NAME --preview` or
      `export: {preview: true}`), then make tools/site/build_site.py use it instead of stripping COL_ nodes.
   5. The townhouse door brace <-> ledge pairs (1-2 mm apart; the probe flags them at 2 mm): rank them 12 mm apart.

B. phase/19b-houses  (finish Phase 19)
   Convert house_townhouse and house_workshop to module-asset instances like house_cottage (see its source).
   Add the module params they need (upper-storey wall height/braces/opening, wing roof trim, band beams, etc.)
   with defaults equal to today's values so module goldens do not change.
   Gate: each house source >= 50% fewer non-comment lines; same triangle count +-2%; 0 SEAM_COPLANAR_OVERLAP;
   stress test passes: in a COPY of the repo set bay 2.4, storey 3.3, timber 0.22, post 0.32, pitch 55 in
   packs/cozy_house.yaml, rebuild the three houses, validate + seam probe (never commit the stress values).
   Then rebuild the bundle: `for a in assets/house_*/; do ./sw export "$(basename "$a")"; done`,
   `./sw export house_cottage --target godot` (same for townhouse, workshop), `python3 tools/experiments/build_mhp_bundle.py`.

C. phase/17b-mcp-verify  (verification, little code)
   Register `sw mcp --project <a scratch folder>` in Claude Desktop or Cursor on this machine (docs/MCP.md).
   Run one unseen prop request through MCP only. Record tool calls, tokens, friction; fix friction that is generic.
   Gate: the prop exports PASS through MCP only; record written (update the gate table in docs/phases/PHASE_17.md).

D. phase/18b-site  (the docs site is published by .github/workflows/docs.yml to the gh-pages branch)
   Confirm the workflow run on main is green and https://billtruong003.github.io/ShapeWright/ shows the gallery
   with live models. Add: a "Composition" tutorial (nested components + asset instances + measure/pivot on
   instances, all `# run` blocks), a "Seams" page (what SEAM_COPLANAR_OVERLAP means, with before/after renders),
   and a changelog page generated from the docs/phases/PHASE_*.md verdicts.
   Gate: site builds --strict, doc tests pass, pages linked from README.

E. phase/21-shared-surfaces  (docs/PHASE_PLAN_16.md, Track B, phase 21)
   Pack-level shared atlas / trim sheet (modules reference regions of one texture), vertex colours,
   merge-by-distance with tolerance + partial-duplicate detection for imports, auto-LOD with silhouette-IoU
   check, multi-hull collision.
   Gate (from the plan): cozy_house kit on one shared atlas with >= 60% less texture memory at equal or better
   texel density; LOD1/LOD2 IoU >= 0.95/0.90; the workshop gets a walkable doorway collider; Godot import OK.

F. phase/22-blender-backend  (REVISED: optional headless Blender; see the revision note in the plan)
   `backend: blender` for parts marked `blend:` (metaball / voxel remesh / smooth union) via `blender -b -P`,
   result re-imported as `mesh_file` with provenance and validated like any part; native CPU marching-cubes
   fallback when Blender is absent. Gate: a chibi body (head, torso, limbs) is one watertight mesh with blended
   joints, within budget, reviewable, reproducible (same inputs -> same hash with the same Blender version).

G. phase/23-character-surface  decals / projected texture regions (eyes, mouth, patterns), region palettes,
   toon presets. Gate: the fox-hoodie chibi concept as a static figurine, side-by-side sheet vs the concept,
   fidelity rubric (silhouette, proportions, palette, face, details) scored with evidence.

H. phase/24-rigging (Blender backend)  humanoid skeleton fitted from part anchors (native, in the source),
   weights + skinned GLB via headless Blender, pose test renders (T, A, sit, wave), native rigid-part clips.
   Gate: the fox imports rigged in Godot headless; no candy-wrapper at elbows/knees; Khronos 0 errors.

I. phase/25-presentation  portfolio sheet layout in the native renderer (views + details + wireframe + palette);
   Cycles/Eevee path when Blender is present (shadows, AO, turntables). Deterministic test renders unchanged.

==================================================================================================
4. STOP CONDITIONS  (stop, push what you have, write the record, report)
==================================================================================================
  - A gate turns out to be wrong or unmeasurable -> propose a corrected gate, do not quietly change it.
  - More than 3 unplanned framework changes inside one phase.
  - An asset-format change that would break existing sources without a migration.
  - A needed tool is missing (Blender, Godot, an MCP client) -> record "not verified" and continue with the
    next item that does not need it.
  - After item D, and after item E: stop and report (these change what the later phases should be).

==================================================================================================
5. REPORT FORMAT  (after every item, in chat)
==================================================================================================
  Item / branch / PR link
  Verdict: PASS | PARTIAL | FAIL, and the gate table in one line per row
  What changed (framework, with class; assets; docs)
  Evidence: numbers + image paths
  Not done / not verified, and why
  Next item you will start

==================================================================================================
6. COST DISCIPLINE
==================================================================================================
  - One work item per session context if possible; re-read the phase record instead of old code.
  - Prefer `./sw brief/doc/caps` and the phase records over broad file reading.
  - During iteration run targeted tests (`-k`); the full suite once before each commit.
  - Do not render or export everything repeatedly: review only the assets you touched.
````

## Notes for you (the person)

- **GitHub Pages:** `.github/workflows/docs.yml` publishes to the `gh-pages` branch on every push to `main`. If the site does not appear, open *Settings → Pages* and set *Source: Deploy from a branch → `gh-pages` / root*.
- **Order:** items A–D are cheap and make the base solid. E is the next real feature phase. F–I are the character track.
- **Stopping:** the agent stops by itself after D and after E, so you can look at the results before the expensive phases.
