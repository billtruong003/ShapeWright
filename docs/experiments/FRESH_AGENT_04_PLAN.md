# FRESH_AGENT_04 plan: textured asset, request to GLB (written before the run)

## Question

Phase 8 gate: can a fresh agent go from a request to a **textured** GLB
(geometry → UV → material → texture → render → critique → revise → validation → export)
with no human material editing? More precisely:

1. **Discovery:** does it find material archetypes from the repository alone? The prompt
   names no archetype, param or command.
2. **Abstraction:** are the semantic params enough to express what the request asks for
   (wood grain, worn metal, painted detail), or does the agent escape to hand-made images,
   extra geometry or framework code?
3. **Inspection:** does it look at texture-specific views, and can it critique and revise
   in terms of material params?
4. **Production:** does the result validate (`TEX_*`/`PBR_*`), export Khronos-clean, and
   stay within a mobile texture budget?

## Benchmark

A stylized treasure chest for a mobile game. It has three distinct surface types (wooden
planks, iron bands/corners, a painted or brass lock plate), a wear requirement and a
texture budget. It has none of the relationship or reuse difficulty of FA-02/03, so
failures can be attributed to the surface system.

## Prompt (task part, verbatim)

> Use this repository to create a game-ready textured prop: "A stylized treasure chest for a
> mobile game. Wooden plank body and lid with visible wood grain, dark iron bands and corner
> guards with worn, scuffed edges, and a lock plate that reads clearly at thumbnail size.
> It should look well used, not brand new. Under 1,500 triangles, one texture set no larger
> than 1024×1024. The surface detail must be in the textures, not flat colours."
> Inspect the textured result, critique it, improve it, and export a validated GLB.

Same isolation as FA-02/03: fresh clone, `docs/experiments/` and `docs/research/` removed,
the node gltf-validator installed, and the same experiment-report request.

## Metrics

FA-02 metrics (time, tool calls, tokens, iterations, snapshots, validation failures,
parameterization ratio) plus:
- how archetypes were discovered (which doc or command, and after how many calls);
- material definitions: archetypes used, params set vs defaults, `use:` instances, layers;
- **escape profile for surfaces**: hand-made image files, geometry added to fake surface
  detail, framework changes;
- texture inspection: which render modes and commands were used (`textured`, `albedo`,
  `roughness`, `texel`, `sw materials`);
- material-param edits across iterations and whether critiques name params;
- final atlas size, achieved px/m, `TEX_*`/`PBR_*` issues, Khronos result, determinism;
- framework modifications (tracked in every experiment since FA-03).

## Predictions

| # | Prediction | Failure class if it happens |
|---|---|---|
| T1 | Finds archetypes through AGENTS.md/ASSET_FORMAT within the first ~10 calls and uses `wood` + `metal` (and probably `painted` or `metal` for the lock) | DISCOVERY if not |
| T2 | Does **not** hand-author image files; if it does, it is for the lock plate emblem (no archetype for motifs) | ABSTRACTION (no decal/motif concept) |
| T3 | Hits or notices `TEX_DENSITY_BELOW_TARGET` or the atlas-size trade-off and handles it by lowering `texel_density` or raising `budget.texture_size` to 1024 | API ERGONOMICS if it can't tell which knob to use |
| T4 | Grain direction looks wrong on at least one part (for example lid planks or curved lid), and there is no param to set the grain axis | CAPABILITY (grain follows the principal axis only) |
| T5 | Critiques name params (`edge_wear`, `grain_scale`) at least once | AGENT REASONING if critiques stay vague ("looks good") |
| T6 | Plank-to-plank variation is wanted; the agent creates `use:` instances or seeds, or accepts uniformity | ABSTRACTION if it can't vary parts sharing a material |
| T7 | Does not run `sw uv lock` before texturing | DISCOVERY (low impact: procedural textures are always DERIVED) |
| T8 | Exports a Khronos-clean textured GLB within 1024², ≤ 1,500 tris | CAPABILITY if not |
| T9 | 0–1 framework modifications | if more than 1: classify each |
