# Phase plan 16+: from tool to platform

This is the layout for the next long run of phases. It builds on `docs/ROADMAP.md` (Stages 3–6) and the evidence recorded in `docs/experiments/` so far, including MODULAR_HOUSE_PACK_01.

Every phase follows the same run protocol (§1) and the same record format (§2). Phases are grouped into four tracks (§3); dependencies are in §4, and a ready-to-paste brief per phase in §5.


> **Revision (after the Blender MCP comparison).** Shapewright's advantage is a reproducible, diffable,
> validated, headless source of truth for game asset *sets*; it should not re-implement Blender.
> Phases 22, 24 and 25 therefore become **optional Blender backends** (headless `blender -b` driven
> from the asset source, results re-imported and validated), not native kernels. Phase 23 stays native.
> The phase numbers are kept so references stay valid.
>
> **Revision 2 (2026-10-05): no Blender at all.** The character track is native (SDF + marching cubes, bone-heat
> weights with scipy, skinned glTF from the existing exporter), so the user never opens or installs Blender: they
> prompt, look at review sheets and the three.js workbench viewer, and comment. Phases 22 and 24 below are native;
> the Blender render path (25b) moved to the backlog. The task-level plan is docs/REMAINING_WORK.md (tracks W and G).

## Status (updated at the end of the cloud run)

| phase | branch | verdict | record |
|---|---|---|---|
| MHP-01 (acceptance test) | `test/modular-house-pack` | PARTIAL | docs/experiments/MODULAR_HOUSE_PACK_01.md |
| 16 packaging + AI docs | `phase/16-packaging` | PASS (Docker not built) | docs/phases/PHASE_16.md |
| 17 MCP server | `phase/17-mcp` | PARTIAL (no agent MCP client run) | docs/phases/PHASE_17.md |
| 19 composition | `phase/19-composition` | PARTIAL (1 of 3 houses converted; closed by 19b) | docs/phases/PHASE_19.md |
| 20 seam validation | `phase/20-seams` | PASS (gate restated) | docs/phases/PHASE_20.md |
| 18 docs site | `phase/18-docs-site` | PARTIAL (deploy not run) | docs/phases/PHASE_18.md |
| 20a golden across Linux/Windows, CI | `phase/20a-cross-os-golden` | PASS (macOS out of scope) | docs/phases/PHASE_20a.md |
| 20b cleanup (track A) | `phase/20b-cleanup` | PASS | docs/phases/PHASE_20b.md |
| 19b kit complete (track B) | `phase/19b-houses` | PASS (closes 19's PARTIAL) | docs/phases/PHASE_19b.md |
| 25a presentation renders (track R) | `phase/25a-render` | PARTIAL (25 s, not 10 s; owner review pending) | docs/phases/PHASE_25a.md |
| 15b web workbench, three.js (track W) | `phase/15b-web-viewer` | PASS with exceptions (Windows/Edge/Firefox not verified) | docs/phases/PHASE_15b.md |
| 17b MCP verification (track C) | `phase/17b-mcp-verify` | PARTIAL (C2 done; C1, C3 need the owner) | docs/phases/PHASE_17b.md |
| 18b docs site completion (track D) | `phase/18b-site` | PASS (closes 18's open gate) | docs/phases/PHASE_18b.md |
| Release 1.0.0 (track E) | `release/1.0` | PASS (PyPI waits for the owner) | docs/phases/RELEASE_1.0.md |
| 21 shared surfaces (track F) | `phase/21-shared-surfaces` | PASS with exceptions (module texel density lower, 218 hulls; M2 re-run left) | docs/phases/PHASE_21.md |
| G0 spike, native organic mesh (track G) | `phase/22-organic` | GO (3 plan changes; concept image not in the repo) | docs/phases/G0_SPIKE.md |
| 22 native organic kernel (G1) | `phase/22-organic` | PASS (a shape, not part groups; regions jagged until 23) | docs/phases/PHASE_22.md |
| 23 character surface (G2) | `phase/22-organic` | PARTIAL (painted regions, decals, reference sheet; rubric needs the concept image) | docs/phases/PHASE_23.md |
| 24 native rigging + clips (G4, G5) | `phase/22-organic` | PASS (Godot: skeleton, skin, clips; Khronos 0/0) | docs/phases/PHASE_24.md |
| 24b character review modes (G3) | `phase/22-organic` | PASS (CPU sheet, workbench skeleton/weights/clips, MCP review) | docs/phases/PHASE_24b.md |
| M2 kit gates re-run (F7) | `phase/22-organic` | PASS (all 10; gate 9 by FRESH_AGENT_13) | docs/experiments/MODULAR_HOUSE_PACK_02.md |

The branches are **stacked**: each one contains the ones above it, so `phase/18-docs-site` has everything.
All of them were fast-forwarded into `main` on 2026-09-30; the branches stay for review.

---

## 1. Run protocol (every phase)

1. **Branch.** Cut `phase/NN-short-name` from the latest `main`. Never work on `main`, and never merge automatically.
2. **Plan first.** Write `docs/phases/PHASE_NN_PLAN.md` before any code. It holds the goal, scope, out-of-scope list, gate and risks.
3. **Evidence before capability.** A new capability needs a recorded failing case: a benchmark, an experiment finding or a user task that needs it. Without one, it waits.
4. **Every change ships with four things:**
   - a regression test;
   - an example asset or doc snippet;
   - a line in `sw caps` / `sw doc`;
   - a validator, if the change can produce a new class of defect.
5. **Classify every framework change:** BUG, ERGONOMICS, ABSTRACTION GAP, CAPABILITY GAP or VALIDATION GAP, with a one-line reason why it is generic.
6. **Checks stay green:** `pytest`, `ruff`, `sw bench`, the golden test, and the Khronos validator on exports. A golden change must be explained in the commit message.
7. **Acceptance test.** Close the phase with a real task: a fresh agent where possible, otherwise the author acting as a user. It is recorded like MODULAR_HOUSE_PACK_01.
8. **Stop and report.** End with PASS / PARTIAL / FAIL against the gate, push the branch, and leave it for review.
9. **Stop conditions (mid-phase).** Stop and report instead of pushing on when any of these happen:
   - the gate turns out to be wrong;
   - more than 3 framework changes are unplanned;
   - a change would break the asset format for existing assets without a migration.

## 2. Record format (every phase)

```
docs/phases/PHASE_NN_PLAN.md       written before work: goal, scope, gate, risks, predictions
docs/phases/PHASE_NN.md            written at the end: what shipped, evidence, gate table, verdict
docs/phases/phaseNN/evidence/      renders, probe output, transcripts, metrics.json
docs/experiments/<TEST>.md         the acceptance test record (if it ran)
```

The gate table in `PHASE_NN.md` has one row per gate item, each with a result (met / met with exceptions / not met / not verified) and a link to its evidence.

---

## 3. Tracks and phases

### Track A: reach (other people and other agents can use it)

| # | phase | scope | gate |
|---|---|---|---|
| **16** | **Packaging + AI docs** | `pip install shapewright` (pyproject, entry point `sw`, optional extras); Docker image; `llms.txt` (one-page agent brief); `.claude/skills/shapewright/SKILL.md`; rewritten README ("first asset in 5 minutes") | a clean container runs `pip install`, `sw doctor`, and `sw brief` → `export` on a new request with no repo clone; a fresh agent given only `llms.txt` exports a valid asset |
| **17** | **MCP server** | `sw mcp` (stdio + streamable HTTP): tools build, stats, validate, render (returns images), review, export, set, snapshot/compare, caps/doc; a sandbox with an asset root and no arbitrary paths; config snippets for Claude Code, Claude Desktop, Cursor and ChatGPT connectors | the same task completes through MCP only (no shell) in 2 clients; tool schemas pass MCP inspector; path-escape tests are refused |
| **18** | **Docs site + gallery** | MkDocs Material on GitHub Pages: quickstart per platform (Claude Code cloud / local / Desktop+MCP / ChatGPT / Cursor); 6 use-case tutorials using existing assets; gallery with `<model-viewer>` GLBs; reference pages generated from `sw caps --json` | the site builds in CI, and every code block in tutorials runs in CI (doc tests); every gallery item links to its source |

### Track B: close the evidenced gaps (from MHP-01, FA-03 and FA-09)

| # | phase | scope | gate |
|---|---|---|---|
| **19** | **Composition** | nested components (with a depth limit and cycle detection); asset-as-instance (`asset: house_wall_window` inside another asset); cross-instance `measure` (an instance's anchors/bounds are queryable); pivot on component instances | MHP-01 rebuilt: houses instance module assets; the house sources are ≥ 50 % shorter; hand-derived offsets drop to 0; all goldens unchanged or explained |
| **20** | **Seam validation** | promote `seam_probe` to a validation layer: cross-part coplanar overlap (visibility-tested), contact-only (touching without embedding), thin-feature inversion after jitter, near-float (1–5 mm); new `sw doc` codes; a `seams` render mode overlay | the 26 recorded MHP cases are re-created as fixtures, and every one is flagged; 0 false positives on all existing assets (or each one explained) |
| **21** | **Shared surfaces + runtime** | a pack-level trim sheet / shared atlas (modules reference regions of one texture); vertex colours; merge-by-distance with tolerance, and partial-overlap duplicate detection for imports; automatic LODs with silhouette-IoU check; collision decomposition (multi-hull) | the cozy_house kit uses 1 shared atlas: total texture memory ≥ 60 % smaller at equal or better texel density; LOD1/2 IoU ≥ 0.95/0.9; the workshop gets a walkable doorway collider |

### Track C: new domain (characters and organic forms)

| # | phase | scope | gate |
|---|---|---|---|
| **22** | **Organic modelling (native)** | parts marked `blend:` become SDF primitives combined by smooth union, meshed by marching cubes on the CPU, decimated and UV'd with xatlas, then validated like any part; no Blender | a chibi body (head, torso, limbs) is one watertight mesh with blended joints; the remesh has no slivers; triangle budget respected |
| **23** | **Surface detail for characters** | decals / projected texture regions (eyes, mouth, patterns); a per-region palette; toon/flat shading presets | the fox-hoodie concept as a static figurine: judged ≥ 80 % faithful on silhouette and palette by side-by-side review; the face is readable from the front at 256 px |
| **24** | **Rigging (native)** | skeleton template fitted from part anchors; bone-heat weights solved with scipy sparse; skinned GLB from the existing exporter; weight validators; pose test renders; rigid-part clips (doors, lids, wheels) | the fox character imports rigged into Godot and Unity (by convention) and plays a T-pose → idle test with no candy-wrapper artefacts at elbows/knees; Khronos 0 errors |

### Track D: visual quality

| # | phase | scope | gate |
|---|---|---|---|
| **25** | **Presentation renderer** | portfolio sheet layout (views + details + wireframe + palette) in the native renderer (shadows, AO, turntables: track R); a Blender path is backlog only | the sheet for 3 existing assets is comparable to a concept sheet layout; the deterministic mode is kept for tests |

---

## 4. Order and dependencies

```
16 Packaging ──► 17 MCP ──► 18 Docs site
                    │
19 Composition ─────┼──► 21 Shared surfaces
20 Seam validation ─┘
                         22 Organic ──► 23 Char. surface ──► 24 Rigging
25 Presentation renderer (independent; best before 18's gallery is final)
```

**Recommended order:** 16 → 17 → 19 → 20 → 18 → 21 → 22 → 23 → 24, with 25 slotted before the final gallery.

**Why this order:**
- 16–17 make every later acceptance test runnable by more agents.
- 19–20 fix the proven gaps before new domains add more.
- 18 waits for 19 so the tutorials show the composed kit.
- 22 → 24 is the character track, where each phase needs the one before it.

**Milestones:**

| milestone | after phase | what it proves |
|---|---|---|
| **M1: usable anywhere** | 18 | install, MCP, docs; any agent can drive it |
| **M2: kit-grade** | 21 | MHP-02 re-run is a strong PASS (all 10 gates) |
| **M3: character-grade** | 24 | the fox concept as a rigged game character |
| **North star** | — | "stylized fishing village pack for a cozy mobile game" end to end (ROADMAP Stage 6) |

---

## 5. Phase briefs (paste one per run)

Each brief is self-contained. Prepend the run protocol (§1).

**16. Packaging + AI docs.**
- *Goal:* Shapewright installs and onboards without cloning.
- *Build:*
  - pyproject with an `sw` entry point, extras `[validate]` and `[workbench]`, and a Dockerfile;
  - `llms.txt` of at most 400 lines, generated from `sw caps --json` plus the AGENTS.md essentials;
  - a Claude Code skill;
  - a README rewrite.
- *Acceptance:* a fresh agent in a clean container with only `pip install` and `llms.txt` exports a validated asset for an unseen prop request. Record the cost against FA-10.

**17. MCP server.**
- *Goal:* any MCP client can run the full loop.
- *Build:*
  - an `sw mcp` server whose tools map 1:1 to CLI commands;
  - render returns PNG content;
  - asset-root sandboxing;
  - structured errors with `sw doc` hints;
  - client config docs.
- *Acceptance:* the same unseen prop through (a) Claude Code over MCP only and (b) one other MCP client. Compare tool calls and tokens with the CLI run.

**18. Docs site + gallery.**
- *Goal:* a public site that teaches by use case.
- *Build:*
  - MkDocs Material;
  - quickstarts per platform;
  - 6 tutorials (prop, kit, variants family, import+repair, VR budget, CI pipeline) using existing assets;
  - a gallery with GLB viewer;
  - reference pages generated from caps.
- *Acceptance:* the site builds in CI, doc tests pass, and a reader following one tutorial reproduces the published GLB byte-identically.

**19. Composition.**
- *Goal:* kits compose without verbosity.
- *Build:*
  - nested components;
  - assets as instances;
  - cross-instance measure;
  - pivot on instances.
- *Acceptance:* redo MODULAR_HOUSE_PACK as MHP-02 on this branch:
  - the houses instance module assets;
  - measure the source-length reduction;
  - hand offsets must be 0;
  - the stress test is re-run.

**20. Seam validation.**
- *Goal:* the validator catches what MHP-01 caught by hand.
- *Build:*
  - a seam layer (coplanar overlap, contact-only, jitter inversion, near-float);
  - fixtures from the 26 recorded cases;
  - a seams overlay render.
- *Acceptance:* every fixture is flagged, there are 0 unexplained false positives across `sw bench`, and it runs in under 10 % extra validation time on the townhouse.

**21. Shared surfaces + runtime.**
- *Goal:* a kit ships like a real game kit.
- *Build:*
  - a pack trim sheet / shared atlas;
  - vertex colours;
  - tolerance merge-by-distance and partial-duplicate detection;
  - auto-LOD with an IoU check;
  - multi-hull collision.
- *Acceptance:* the cozy_house kit on one shared atlas, with LODs and walkable collision, imported in Godot. Report texture memory before and after.

**22. Organic modelling.**
- *Goal:* blended, watertight organic forms.
- *Build:*
  - an SDF primitives + smooth-union layer (CPU, marching cubes / dual contouring);
  - remesh;
  - symmetry;
  - shell.
- *Acceptance:*
  - a chibi base body and 2 creatures (a slime and a mushroom character) are each one watertight mesh;
  - the budget is met;
  - the render review passes;
  - it records where parts-based modelling was still better.

**23. Character surface detail.**
- *Goal:* faces and patterns without hand painting.
- *Build:*
  - projected decals;
  - region palettes;
  - toon presets.
- *Acceptance:* the fox-hoodie concept figurine, with a side-by-side sheet against the concept and a fidelity rubric (silhouette, proportions, palette, face, details) scored with evidence.

**24. Rigging.**
- *Goal:* characters that animate.
- *Build:*
  - a humanoid skeleton fitted from anchors;
  - auto-weights;
  - skinned GLB;
  - pose tests;
  - rigid clips.
- *Acceptance:* the fox character rigged, imported in Godot headless with the skeleton intact, and a pose sheet (T, A, sit, wave) without deformation defects.

**25. Presentation renderer.**
- *Goal:* portfolio-grade sheets.
- *Build:*
  - shadow/AO/rim lighting;
  - turntable output;
  - a concept-sheet layout;
- *Acceptance:* sheets for the cottage, the treasure chest and the fox, reviewed against a reference sheet; the deterministic test renders are unchanged.

---

## 6. Sizing (rough)

Sizes are relative to Phase 12 (= M).

| phase | size | risk |
|---|---|---|
| 16 Packaging + AI docs | S | low |
| 17 MCP | M | low–medium (client differences) |
| 18 Docs site | M | low |
| 19 Composition | L | medium (asset-format change, golden churn) |
| 20 Seam validation | M | low (probe exists) |
| 21 Shared surfaces | L | medium (UV architecture) |
| 22 Organic | XL | high (new geometry kernel path) |
| 23 Character surface | M | medium |
| 24 Rigging | XL | high (weights quality) |
| 25 Presentation | M | low |
