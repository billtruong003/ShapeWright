# FRESH_AGENT_03 plan: coherent multi-asset pack (written before the run)

## Question

Given a pack request, does a fresh agent produce a **coherent collection**
(shared scale, construction language, materials, detail density) and does it
**reuse structure** (components, families) instead of copying source blocks?
Do the current abstractions keep Component / Family / Variant / Instance
distinct?

## Current semantics (before the run)

| Concept | Intended meaning | Mechanism today |
|---|---|---|
| **Component** | encapsulated structure (a sub-assembly with public params) | `components/*.yaml`, `component:` + `with:` |
| **Family** | a base asset that exposes intent through an interface | `interface: {params}` on a base asset |
| **Variant** | a family member that sets public params only | `extends:` + params (enforced) |
| **Instance** | geometry repeated inside one asset | part-level `array`/`mirror`, `repeat`/`mirror` ops, `share_instances` UVs |

Known gaps: components can't be mirrored/arrayed or nested; **materials cannot
be shared across assets** (each asset declares its own); there is no pack-level
parameter file (shared scale); there is no pack-level review image.

## Benchmark

Stylized blacksmith workstation pack: workbench, stool, weapon rack, shelf,
tool crate, bucket. Mobile budgets. Requirements: shared scale, consistent
construction language, component reuse where natural, consistent materials,
matching detail density, all validated and exported.

## Prompt (task part, verbatim)

> Use this repository to create a coherent asset pack: "A stylized blacksmith workstation pack for a mobile
> game: a workbench, a stool, a weapon rack, a wall shelf, a tool crate and a bucket. They must look like
> one set: shared scale, the same construction language (e.g. the same plank, leg and metal-band style),
> consistent materials and matching detail density. Reuse structure where it makes sense instead of
> duplicating it. Each asset game-ready, under 1,200 triangles, clean UVs. Inspect the pack as a whole as
> well as each asset, fix problems, and export all six."

## Metrics

Per asset: the FA-02 metrics. Pack level: number of components created and their
reuse count; **duplication**, meaning identical or near-identical part
definitions across assets (normalized YAML blocks); material definitions
duplicated across assets and their drift (colour differences for the "same"
material); detail density spread (triangles per m² of surface); scale
consistency (seat/bench heights vs the existing tavern set); framework
modifications; tool calls, tokens, time.

## Predictions

| # | Prediction | Failure class if it happens |
|---|---|---|
| Q1 | The agent creates 1–3 components (plank/board, leg, metal band) and reuses them | — |
| Q2 | Materials are **copied into every asset** (no shared material mechanism) and may drift | ABSTRACTION/CAPABILITY FAILURE (no shared materials); input to Phase 7 |
| Q3 | Shared dimensions (plank thickness, leg size) are repeated as literals in each asset | ABSTRACTION FAILURE (no pack-level params) |
| Q4 | It wants to mirror/array a component instance (e.g. legs) and hits the unsupported error | CAPABILITY FAILURE (known limitation) |
| Q5 | Pack-wide inspection is ad hoc (reviewing six sheets separately) | API ERGONOMICS FAILURE (no pack sheet) |
| Q6 | Family `extends` is used little (the assets differ structurally) | — |
| Q7 | No framework modification | — |
