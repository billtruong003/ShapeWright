# Roadmap

Each stage has a success criterion that is *demonstrated*, not just implemented.
Stages overlap in practice; the order reflects dependencies.

## Stage 0: Research ✅
Prior art, libraries, licences, risks → `RESEARCH.md`. Capability taxonomy →
`MODELING_CAPABILITY_MAP.md`.
**Done when:** every core dependency is chosen with a reason and a licence
check. *(Met.)*

## Stage 1: Architecture ✅
Representation, kernel, semantics, validation layers, inspection, iteration,
export, security, extension seams → `ARCHITECTURE.md`, `ASSET_FORMAT.md`.
**Done when:** the design questions in ARCHITECTURE §2–§20 have written answers.
*(Met.)*

## Stage 2: Vertical slice ✅ (v0.1, this commit)
One complete loop: source → geometry → validation → renders → revision →
comparison → GLB export.
**Done when:**
- ✅ a chair can be modelled, critiqued from renders, revised and exported
  without touching vertices (`assets/tavern_chair/history/`: 2 iterations with
  critiques);
- ✅ the GLB passes the Khronos glTF-Validator with 0 errors and round-trips;
- ✅ outputs are deterministic (byte-identical GLB, golden geometry hashes);
- ✅ 7 benchmarks with different challenges pass (`sw bench`): chair (hard-surface
  assembly), stool (inheritance), table (pack consistency), barrel (lathe,
  rings), crate (multi-axis mirrors, variants), rock (organic, seeded),
  street lamp (sweep, booleans, emissive).

## Stage 2.5: Architecture hardening ✅
Prompted by DESIGN_REVIEW.md. No new modelling features; the foundations were
made to grow: mesh attribute contract, backend boundary, recursive geometry
expressions, `measure` relationships, geometry sources (`mesh_file`, import),
stable UV regions with a lock, components/`enabled`/family interfaces.
**Done when:** every change has a contract test (not only example outputs); all
benchmarks pass; golden changes are explained (chair/stool/table: see
HARDENING.md). *(Met: 163 tests.)* Fresh-agent results are in HARDENING.md.

## Phase 5: Agent-native spatial modelling language ✅ (gate passed)
Research ([research/SPATIAL_RELATIONSHIPS.md](research/SPATIAL_RELATIONSHIPS.md)), a relationship-heavy
fresh-agent benchmark with predictions written first, independent perturbation testing, and fixes at the
layer that failed. Result: [experiments/FRESH_AGENT_02.md](experiments/FRESH_AGENT_02.md).

## Phase 6: Reuse, components and asset families ✅ (gate passed with caveats)
A fresh agent built a coherent six-asset pack with four reused components. It exposed a concept collapse
(`extends` used as set membership), fixed by first-class **packs**, plus a real bug and missing
pack-review tooling (both adopted from the agent). Record: [experiments/FRESH_AGENT_03.md](experiments/FRESH_AGENT_03.md).

## Phase 7: Surface architecture ✅ (design gate)
[SURFACES.md](SURFACES.md): semantic material archetypes evaluated in object space and baked into the
atlas; lifecycle states (DERIVED/VALID/REGION_KEPT/RELAYOUT/INVALID); texel density per pack; renderer
backend seam; baking split into core and optional; validation; glTF mapping; security; layout; migration.

## Stage 3: Prototype: a fresh agent succeeds unassisted
- Run the README task ("tavern chair, < 700 tris, mobile") with a *fresh* agent
  that has only the repository. Record the transcript and friction points, and
  fix documentation and error messages until it succeeds without hints.
- Add two benchmarks that stress missing abstractions: a **modular wall kit
  piece** (grid dimensions, typed sockets, openings via cross-part booleans) and
  an **imported asset repair** (GLB in → validate → fix → out).
- Selectors v1 (`faces: {normal: +y}` on a part) plus `bevel` on selected edges of
  convex parts.
- `enabled:` expressions per part (structural variants).
- Turntable strip view; measurement overlay; human-scale reference in ortho views.

**Success:** 3 of 3 fresh-agent runs (different prompts) end with an exported,
validated asset and a critique history, with no human edits.

## Stage 4: MVP: asset packs
- Components (reusable sub-assemblies) with namespaced params.
- Curves (`curves:` data) with `sweep`/`loft`/`follow_curve`.
- Vertex colours and palette validation (one-material stylized props).
- LOD generation with silhouette-IoU verification against LOD0.
- Lightmap UVs (UV1), shared-UV instancing, shared-mesh export.
- Pack manifest, pack contact sheet at common scale, cross-asset checks.
- Reference images in sources, rendered next to matching views.
- MCP adapter and a read-only browser workbench, both thin.

**Success:** "Create a 6-piece medieval tavern prop pack for mobile" produces
6 validated GLBs with LODs whose pack sheet shows consistent scale, chamfer
language and palette, judged consistent by a human reviewer.

## Stage 5: Production foundation
- Import (GLB/OBJ/STL/PLY) with sandboxed parsing, and repair ops.
- Texture layer: procedural textures into UV0, baking (AO, curvature, ID) by CPU ray casting.
- Rigid animation clips on named parts (doors, lids, wheels); pivot validation.
- Engine smoke tests in CI (headless Blender and Godot import).
- Plugin packages (entry points) for community generator and validator packs.
- Performance: vectorized rasterizer or optional GPU backend for 50k+ tris.

**Success:** a third-party generator pack installs with pip and appears in `sw caps`;
an imported asset from an external pack is repaired and re-exported with
validation passing.

## Stage 6: Long-term research
Agent-native sculpting (deformation volumes, SDF blends), constraint solving
for kits and assemblies, image-guided parameter fitting to concept art,
learned style critics as optional validators, scenes and layout (the "fishing
village" scenario), terrain and foliage subsystems, skinning.

**Success criterion (north star):** *"Create a stylized fishing village asset
pack for a cozy mobile game"* runs end to end, with a pack-level review the
agent can defend with evidence.

## Principles for scheduling
- A capability enters a stage only with a benchmark that needs it.
- Each new capability ships with an example, tests, a line in `sw caps` and a
  validator if it can produce a new class of defect.
- Keep the loop runnable by one developer on one machine.
