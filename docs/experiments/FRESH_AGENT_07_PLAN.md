# FRESH_AGENT_07 plan: import, modify and repair real assets (Phase 11 gate)

## Question

Phase 11 gate: can a fresh agent import **external** game assets and modify them meaningfully,
without framework-level code changes? Predictions I1–I6 are in [../IMPORT.md](../IMPORT.md) and
were written before implementation.

## Inputs

Two CC0 1.0 Khronos glTF sample models, placed in the clone's `incoming/` folder:
- **SheenChair.glb** (Wayfair): 39,936 triangles, 4 materials with textures, KHR sheen and variants extensions.
- **Lantern.glb** (Microsoft): 5,394 triangles, one 2048² PBR set, 25.7 units tall, with degenerate faces.

## Prompt (task part, verbatim)

> Two assets from an outside artist are in `incoming/` at the repository root: `SheenChair.glb`
> (a velvet loveseat) and `Lantern.glb` (an old street lantern). Bring both into this project as
> game-ready props for a desktop game:
>
> 1. **Loveseat:** give its parts meaningful names; reduce it to at most 8,000 triangles without
>    breaking its textures; replace its thin metal legs with chunkier turned wooden legs; add simple
>    collision; and make a second variant with a different fabric colour.
> 2. **Lantern:** it must be a realistic real-world size (a street lantern is about 2.5 m tall); fix
>    any technical problems; and make the post 20% taller than the original proportions.
>
> Inspect your results, fix what you find, and export validated GLBs of the loveseat, its variant
> and the lantern.

Same isolation and report request as before (including framework changes and command timings).

## Metrics

Tasks completed out of 7, framework changes (**the gate: 0**), texture fidelity after decimation and
export (checked independently by sampling the exported textures), time and tokens, discovery path
for `authored`, `clean` and `decimate`, and failures by class.
