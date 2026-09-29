# Vision

## The question

*What should a 3D creation environment look like if autonomous coding agents,
rather than humans with a mouse and keyboard, were its primary users?*

## What Shapewright is

An open-source **modelling environment plus machine-operable abstractions**
covering validation, inspection and iteration. The repository is the product. An
agent that clones it can find out what it can do (`AGENTS.md`, `sw caps`),
express an asset as a semantic source file, check it deterministically, look at
it, critique it, revise it, and export files that game engines and DCC tools
open without conversion.

## What it is not

| Not | Why not |
|---|---|
| A text-to-3D demo | One-shot generation has no revision loop; the defining capability here is self-correction. |
| A Blender wrapper or MCP adapter | Remote-controlling human software makes the agent operate a UI through a keyhole. State is hidden in a scene, not in a diffable source. |
| A browser mesh editor | The UI is not the product. Every capability is a library call and a CLI command first. |
| A procedural primitive generator | Primitives are vocabulary. The product is the loop: represent, validate, inspect, critique, revise, export. |
| A Blender clone | Feature parity is a non-goal. We add capabilities when an agent-native abstraction exists for them. |

## Principles

1. **Source over state.** The editable asset is a text source (params, parts,
   ops, constraints). Meshes, renders and exports are reproducible build
   products. Version control, diffs, review, rollback and inheritance come for free.
2. **Semantics survive.** Parts have names and those names go everywhere:
   validation messages, render legends, design checks, export node names.
   "The backrest is too narrow" maps to `back_slat` / `slat_width`, never to
   vertex 1342.
3. **Highest reliable abstraction first.** Parameters, then placement
   constraints (anchors/attach), then modifiers, then new generators. Descend
   only when needed, and when you do, extend the framework so the next asset
   doesn't have to.
4. **Deterministic validation and perceptual judgement are separate.**
   Computable facts (closed meshes, budgets, UV overlap, grounding, floating
   parts, design-intent checks) are validated by code with stable codes.
   Aesthetic judgement is left to the agent's vision. The tooling supplies
   evidence (orthographic views with scale bars, part colouring, silhouettes,
   diffs) and a checklist; it never fakes a "beauty score".
5. **Reports are context-efficient.** One summary line per asset, one line per
   issue, codes plus hints, and full JSON only on request. One contact-sheet
   image per review instead of ten screenshots.
6. **Reproducible pixels.** Same source, same image, byte for byte. Iterations
   are comparable because the cameras are derived from the geometry, not from
   viewport state.
7. **Data, not programs, from the agent.** Asset sources are declarative and
   evaluated by a restricted expression language with resource limits. Code
   extensions (new shapes, ops, validators) are framework contributions that
   get reviewed and tested like any code.
8. **Open standards out.** glTF 2.0 / GLB is the exchange format. Metadata rides
   in glTF `extras`, so any engine or DCC can read the result.
9. **One developer, one agent, one machine.** No services, databases or GPUs
   are needed to run the whole loop. It runs in CI, in cloud sandboxes and on laptops.
10. **The capability map is not a checklist.** A narrow, complete loop beats a
    broad, disconnected feature list. See `ROADMAP.md`.

## The long-term picture

Today the loop works for single low-poly props. The same foundations were
chosen with these cases in mind:

- **Asset packs:** "Create a medieval tavern prop pack." Shared style and
  production profiles, `extends` families, cross-asset checks (table height vs
  chair seat height), contact sheets per pack.
- **Pack-level edits:** "Make everything 20% chunkier." That's a parameter
  sweep across sources, not re-modelling.
- **Kitbashing and components:** reusable part libraries with attachment
  semantics.
- **Scenes:** layouts of assets with the same semantic addressing.
- **Import and repair:** existing GLB/OBJ assets pass through the same validators
  and renders.
- **Richer inspection:** reference-image comparison, style-consistency checks
  across a pack, learned critics as optional validators.

The measure of success is not "can it make a chair". It is whether an agent
using it increasingly behaves like a careful modeller, technical artist and
asset-production engineer, and whether the work stays inspectable,
diffable and correct.
