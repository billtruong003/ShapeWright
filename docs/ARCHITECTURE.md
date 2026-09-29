# Architecture

This document records the design decisions, the alternatives considered and
why they lost. It answers the design-phase questions in order: product,
representation, geometry, semantics, procedural model, modifiers, surfaces,
scene, validation, inspection, iteration, export, extensibility, onboarding,
headless operation, security, testing, performance and future-proofing.

## 1. System overview

```
                           AGENTS.md  ·  sw caps  (discovery)
                                         │
 user request ──► agent ──edits──► asset.yaml  (source of truth: params, parts, ops, checks)
                   ▲                     │ load · extends · schema · safe expressions · limits
                   │                     ▼
                   │              ┌──────────────┐   registry of shapes/ops (typed specs)
                   │              │   ASSEMBLE   │◄─ trimesh (hulls) · Manifold (booleans)
                   │              └──────┬───────┘
                   │         Asset IR: named part instances (world meshes), sockets,
                   │                   materials, profile, style, checks
                   │                     ▼
                   │              ┌──────────────┐
                   │              │   SURFACE    │  normals (flat/smooth/auto) · UV atlas (xatlas)
                   │              └──────┬───────┘
                   │     ┌───────────────┼──────────────────┬───────────────┐
                   │     ▼               ▼                  ▼               ▼
                   │ ┌─────────┐   ┌───────────┐     ┌────────────┐   ┌──────────┐
                   │ │VALIDATE │   │  RENDER   │     │  HISTORY   │   │  EXPORT  │
                   │ │ layers  │   │ CPU raster│     │ snapshots  │   │ GLB      │
                   │ └────┬────┘   └─────┬─────┘     │ compare    │   │ Khronos  │
                   │      │              │           └─────┬──────┘   │ roundtrip│
                   │  report.json    sheet.png         diff.png +     └────┬─────┘
                   │  (codes+hints)  (views+legend)    metrics             │
                   └──────┴──── critique ───┴──────────────┘         game-ready .glb
```

Every box is a plain Python module with a function-level API. The CLI (`sw`)
is a thin wrapper, and any future UI or MCP server would call the same
functions. Nothing lives only in the interface.

## 2. Product definition

A headless, deterministic toolchain plus a representation. The unit of work is
an **asset source**. The loop is **edit source → build → validate → render →
critique → edit**. The product boundary is the repository: code, docs,
profiles, styles, benchmarks and history conventions.

## 3. Core representation: what does the agent manipulate?

**Decision: a declarative, semantic, parametric source (YAML) that compiles to
meshes.** This is a hybrid of *editable source + generated mesh*.

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Raw meshes (OBJ/GLB as source) | universal | agents cannot reason about vertex arrays; no semantics; edits are destructive; huge diffs | output only |
| Procedural code (Python scripts, OpenSCAD/CadQuery style) | unlimited expressiveness; agents write code well | arbitrary code execution in the loop; every asset is a one-off program; hard to validate statically; semantics are conventions only | the extension layer, not the asset layer |
| Node / modifier graph (Houdini / Geometry Nodes style) | non-destructive, composable | graphs are verbose to serialize and hard for agents to read and diff; they solve a GUI problem | ordered op lists per part capture most of the value |
| Custom DSL | concise | new syntax to learn; needs a parser, tooling and error messages | not worth it yet; YAML plus expressions covers v0 |
| **Declarative data + safe expressions** | readable, diffable, commentable; statically checkable against typed specs; safe to evaluate; semantics are structural (part names, params); agents write YAML reliably | less expressive than code | **chosen**, with code-level extension points for what data cannot express |

A source has: `params` (named numbers and expressions), `materials`, `parts`
(each part = `shape` + ordered `ops` + placement + replication + material
+ shading), `sockets`, `checks` (design intent), and references to a
production `profile` and a `style`. See `ASSET_FORMAT.md`.

**What is source and what is artifact:**

| Kind | Examples | Git |
|---|---|---|
| Source | `asset.yaml`, profiles, styles | committed |
| History | `history/NNN/{source.yaml, resolved.yaml, summary.json}` | committed (small text) |
| Deliverable | `export/<name>.glb`, `export/<name>.report.json` | committed for finished assets |
| Reproducible build products | `.build/` renders, sheets, reports, compare images | ignored |

Renders are never stored in history. They are regenerated from snapshot sources
because rendering is deterministic, which keeps repository growth bounded.

## 4. Geometry system

**Decision: an indexed triangle mesh (`Mesh(V, F)`) as the single kernel type,
with established libraries for the hard algorithms.**

- **Why triangles, not B-rep/NURBS (OpenCascade, build123d):** the target is
  game assets, where the final representation is triangles anyway. B-rep
  kernels are large (OCCT is LGPL, heavy native dependency) and push CAD
  semantics (fillets as exact surfaces) that game pipelines tessellate
  immediately. CAD-like ideas are still adopted at the *source* level:
  parameters, dimensional checks, profiles, extrude/revolve/sweep.
- **Why not SDF/voxels as the core:** great for organic blending and booleans,
  but they lose crisp low-poly topology, need remeshing, and make UVs and
  triangle budgets hard to control. They are planned as an *op family*
  (sculpt-like fields producing meshes), not as the kernel.
- **Libraries (all permissive):** Manifold (booleans, robust extrusion and
  revolution, exact contact distance, plane trimming), trimesh (convex hulls,
  subdivision, smoothing, re-import), xatlas (UV charting and packing),
  fast-simplification (quadric decimation), numpy/scipy. Custom code is
  limited to agent-specific pieces: generators with controlled low-poly
  topology (chamfer_box, lathe, tube), deformers, the assembler, validators and
  the renderer.
- **Invariants:** generators return closed, outward-wound, welded meshes.
  Every part is a closed shell, and parts may interpenetrate (the standard
  low-poly prop construction). Booleans require closed inputs and produce
  closed outputs.

## 5. Semantic model

**Parts are the unit of meaning.** A part has a name, a doc string, tags,
a material, an optional semantic parent and an optional pivot. Replication
creates *instances* with predictable names (`front_leg_left`, `back_slat_1`,
`post_front_left`) and records how they were derived (`extras.instance`).

Placement is **semantic, not numeric**:
- **Anchors** are points on a part's bounding box addressed by composable
  tokens (`bottom_front_left` = [-1,-1,+1] in normalized box coordinates).
- **attach** puts this part's anchor on another part's anchor plus an offset.
  Attachments form a dependency graph that is topologically sorted, with cycles
  and unknown references reported with suggestions.
- **mirror** across a world-axis plane (optionally offset) and **array** (linear
  or radial) generate instances.

Semantics survive to export: node names, hierarchy (`parent`), `extras.part`,
socket nodes (`SOCKET_*`) and asset-level metadata (params, source hash,
profile, style, validation status).

*Deliberately not (yet):* a general constraint solver. Anchors plus
expressions cover "legs under seat corners" and "rail follows the post
lean" declaratively and deterministically. A solver (for example for "door fits
opening" in modular kits) is on the roadmap once benchmarks demand it. The
`checks` layer already verifies relationships even where it doesn't enforce them.

## 6. Procedural model

- **Parameters** with ranges, docs and `vary` bounds. Expressions derive
  dimensions from other parameters (`post_z: -seat_depth / 2 + leg_inset + leg / 2`).
- **Seeds** everywhere randomness appears (`jitter`, `noise`, `random_hull`,
  variants). Same seed, same geometry.
- **Families:** `extends: ../tavern_chair` deep-merges a base source. `null`
  deletes inherited entries. `tavern_stool` is 30 lines on top of the chair.
- **Variants:** `sw variants crate --count 5 --seed 3` samples `vary` ranges
  into child sources that extend the base.
- **Generators** are registered functions with typed parameter specs, which is
  the reusable procedural vocabulary. Community generator packs slot in here.

## 7. Modifiers: is a modifier system justified?

**Yes, as an ordered op list per part, not as a free-form graph.** Most
DCC modifier stacks are linear per object, and a linear list is trivially
readable, diffable and reorderable by an agent. Ops run in *part-local space*
(the part is centred on its bounding box first), so deformers such as taper,
bend and shear use normalized coordinates that don't depend on placement.
Booleans take nested shape definitions as tools. Cross-part booleans and
graph-shaped dependencies are deferred until a benchmark needs them. When they
come, they will reference other parts by name, which keeps the source semantic.

## 8. Surface system: UVs, normals, materials

- **Normals:** per part `flat`, `smooth` or `auto` (auto-smooth by angle,
  defaulting from the style). This is computed per corner, which is the glTF
  equivalent of hard/soft edges and smoothing groups.
- **UVs:** one atlas for the whole asset (UV0) via xatlas, with padding and
  resolution from the profile. This is the game-ready default: one texture set
  and one material draw for the asset if desired. Validators check bounds,
  overlap (rasterized coverage), texel-density spread and utilization.
  Deliberate overlap (mirrored or stacked islands to save texture space) is a
  roadmap option (`uv.share_instances`).
- **Materials:** named PBR parameter sets (base colour in sRGB hex, metallic,
  roughness, emissive, alpha mode, double-sided), exported as glTF PBR
  materials. There are no textures in v0. Baking and texturing are later layers
  that consume UV0.
- The renderer and exporter consume **the same surface buffers**, so what the
  agent inspects is what ships.

## 9. Scene system

v0 scene = one asset: a root node, part instances, sockets and collision proxies.
The IR (`Asset` → `Part`s with names, parents, pivots) is already a scene graph.
Multi-asset scenes and packs will reference assets by path, re-using transforms
and anchors. Instancing is recorded in metadata today (`extras.instance`) and
can later be exported as shared glTF meshes.

## 10. Validation system

Layered and deterministic, with every layer always running, so an agent sees
all problems in one pass (see `VALIDATION.md`):

```
source → geometry → assembly → budget → intent → surface → style → export
```

Validators are registered functions (`@validator(name, layer, doc, codes)`)
returning `Issue(code, severity, message, where, hint)`. `where` is a part
name or source path. `hint` names what to change. Severities: error (a defect
that blocks export), warning (probably wrong), info (context).

Two layers encode *meaning*, not just mesh hygiene:
- **assembly:** parts must physically connect (Manifold `min_gap` between
  bounding-box-overlapping pairs, graph search from grounded parts), the asset
  rests on y=0 with the origin under the grounded footprint, and no part is
  hidden inside others (wasted triangles).
- **intent:** the asset's own `checks:`, which are design requirements as tests
  (`seat.max.y in [0.42, 0.50]`, `plank.max.y - 0.46 ≈ chair seat + 0.3`).

**Perceptual quality is not scored.** `sw review` renders evidence and prints the
style checklist. The agent judges proportions, silhouette and style. This
avoids arbitrary numeric proxies for beauty while still making the critique
concrete: parts are named and sizes are available.

## 11. Visual inspection

**Decision: a deterministic CPU rasterizer (numpy + Pillow), not a browser, GPU
or Blender.**

| Option | Headless in a sandbox | Deterministic | Deps | Verdict |
|---|---|---|---|---|
| Blender (Cycles/EEVEE) | needs Blender install; EEVEE needs GPU/EGL | mostly | 300+ MB, GPL tool | too heavy for the core |
| three.js in headless Chromium | yes (Chromium is common in sandboxes) | GPU/driver dependent; SwiftShader differs from hardware | Node + browser | good for a human viewer, not for reference images |
| pyrender / OpenGL (EGL/OSMesa) | needs system GL libraries | driver dependent | native | fragile in containers |
| **numpy z-buffer rasterizer** | always | **byte-identical** | none beyond Pillow | **chosen** for inspection |

The renderer is small (about 250 lines) and deliberately non-photoreal. It is
tuned for *legibility to a vision model*: neutral clay with camera-relative
lighting, dark outlines at silhouettes, part boundaries and creases, magenta
back faces (flipped or holed geometry shows up at once), orthographic views
with metric scale bars and ground lines, and part-colour legends.

**Cameras** are derived from the asset bounding box: orthographic front, back,
left, right, top and bottom; 30° perspective 3/4 views at ±35° and ±145°
azimuth; and a low eye-level view. `compare` frames both iterations with their
union bounding box, so pixels are directly comparable (silhouette IoU,
added/removed masks).

**Modes** were chosen for diagnostic value, not DCC parity: `clay` (form),
`parts` (semantics), `material`, `wire` (density and topology), `normals`
(orientation), `silhouette` (readability), and a UV view with overlaps in
red. X-ray, depth and AO were considered and left out: they add pixels
without adding findings at this asset scale.

The default **contact sheet** (8 tiles, about 250 KB) is the single image an
agent looks at per review, which keeps the context cost low.

A browser workbench (three.js viewer of the exported GLB plus the report) is a
*roadmap item for humans*. It will consume the same files and add no logic.

## 12. Iteration and reversibility

- `sw snapshot` stores the source as written (comments kept), a flattened copy
  and a summary (status, metrics, params, note, critique). If nothing changed,
  nothing is recorded.
- `sw log` shows the story, `sw compare A B` gives an image plus metrics
  (param diffs, per-part size changes in %, silhouette IoU per view, status and
  triangles), and `sw restore N` rolls back and backs up the current source.
- Git remains the long-term history. Snapshots are the fine-grained,
  agent-facing layer inside a task.

## 13. Export

**GLB first, and only GLB in v0.** It is an open standard (Khronos) with a
reference validator, supported natively by Godot, Unity (glTFast), Unreal
(Interchange), Blender, three.js and Babylon. It uses the same axis convention
as the modelling space (Y-up, metres, front +Z), so there is no conversion step
where bugs could hide. The writer is hand-written (about 200 lines), so output
is byte-deterministic and every node name and extras field is under our
control. Export runs validation first (it refuses on errors unless `--force`),
then the Khronos glTF-Validator (optional Node tool) and a re-import round-trip
(part names, triangle count, bounds).

OBJ/STL/PLY are trivial via trimesh when needed. USD is the next strategic
format (scene composition, `usdz` for AR). FBX is intentionally out of scope:
it is proprietary, has no permissive writer, and engines accept glTF.

## 14. Extensibility

| Add | Where | Mechanism |
|---|---|---|
| shape (generator) | `shapewright/ops/shapes.py` or a new module | `@shape(name, doc, [Param...], example=...)` |
| op (modifier) | `shapewright/ops/modifiers.py` | `@op(...)` |
| validator | `shapewright/validate/checks.py` | `@validator(name, layer, doc, codes)` |
| view / mode | `shapewright/render/views.py` | `VIEWS` / `MODES` tables |
| profile / style | `profiles/*.yaml`, `styles/*.yaml` | data only |
| exporter | `shapewright/export/` | function over `(Asset, Surface)` |

Registries feed `sw caps`, schema checking, error suggestions and the test
suite (every shape and op must ship an `example`, which is automatically tested
for closedness, orientation and determinism). Adding a capability makes it
discoverable, validated and tested automatically. Third-party plugin loading
(entry points) is deferred until there are third parties, and the registry
design already supports it.

## 15. Agent onboarding

`AGENTS.md` (vendor-neutral; `CLAUDE.md` points to it) is the manual: the loop,
the rules, error recovery and a repository map. `sw caps` is the generated,
always-current vocabulary. `assets/` are worked examples, and `tavern_chair`
contains a recorded critique loop. Error messages carry hints and "did you
mean" suggestions, so documentation reaches the agent at the moment it is
needed.

## 16. Headless and cloud operation

Pure-Python wheels only (numpy, scipy, trimesh, manifold3d, xatlas, Pillow,
PyYAML, fast-simplification). No GPU, display, Blender or services. The Node
glTF validator is optional. It runs from a clone via `./sw` without installation.

## 17. Security and trust boundary

```
trusted:   framework code, registered shapes/ops/validators, profiles, styles   (reviewed like any code)
untrusted: asset sources written by agents in the loop, imported files (future)
```

- Sources are parsed with `yaml.safe_load` (no object construction).
- Expressions are evaluated by an AST whitelist: numbers, names, arithmetic,
  comparisons, conditionals, whitelisted math functions and attribute reads on
  read-only namespaces. There are no calls outside the whitelist, no attribute
  access on Python objects, no strings, lambdas or comprehensions, and exponent
  and size limits apply.
- **Resource limits** (`limits.py`): triangles per part and total, parts,
  instances, segments, array counts, ops per part, subdivision depth,
  expression size, `extends` depth, source size, render size, and a wall-clock
  timeout in the CLI.
- Sources never execute code, and generators are chosen by name from the
  registry. When agents need new geometry logic they write framework code,
  which passes through the normal code-review and test path (and where CI
  applies). This is the tradeoff: flexibility comes through reviewed extension,
  not through runtime `exec`.
- Future importers must treat files as hostile: size caps, parse in a
  subprocess, and never follow external URIs in glTF.

## 18. Testing strategy

- **Contract tests over the registry:** every shape example must be closed,
  outward and deterministic, and every op example must keep the surface closed.
- **Defect-injection tests:** each validator must fire on a deliberately
  broken asset (floating part, below ground, budget, open mesh, inverted, UV
  overlap, hidden part, schema errors, cycles, unsafe expressions).
- **Golden geometry:** a hash of every benchmark's geometry (rounded) in
  `tests/golden.json`. A refactor cannot silently change modelling behaviour.
  Intentional changes regenerate the golden file (`python tests/update_golden.py`)
  and show up in review.
- **Determinism:** GLB bytes are identical across builds, and there is a
  re-import round-trip.
- **CLI tests:** exit codes, render, snapshot, compare and restore cycle.

## 19. Performance (measured)

On one CPU core, with warm imports:

| asset | tris | build | surface (UV) | validate | render 512² | sheet (8 tiles) | GLB |
|---|---|---|---|---|---|---|---|
| tavern_chair | 484 | 37 ms | 42 ms | 62 ms | 0.99 s | 1.4 s | 4 ms |
| street_lamp | 306 | 28 ms | 38 ms | 36 ms | 0.32 s | 1.0 s | 3 ms |
| dense sphere | 20,480 | 12 ms | 1.9 s | 1.8 s | 3.1 s | n/a | n/a |

Rendering dominates, because the rasterizer loops over triangles in Python. It
is fine for props (a full review cycle takes about 2 s). For 50k+ triangle
assets, the known fixes are: vectorize by triangle-size buckets, render at
lower supersampling, or add an optional `moderngl`/EGL backend behind the same
interface (with pixel-level non-determinism accepted for that backend only).
UV unwrap and pairwise contact tests are the next costs, since contact is
O(n²) in parts with bounding-box pruning.

## 20. Decisions that keep the future open

| Future capability | What in v0 keeps it possible |
|---|---|
| Asset packs, pack-wide edits | named params, `extends`, profiles and styles as shared files, `sw bench` |
| Kitbashing / components | parts are self-contained (shape + ops + material); anchors and sockets define attachment semantics |
| Modular kits, grid snapping | anchors in normalized box coordinates, sockets as named transforms; a grid/snap layer can generate `position`s |
| Constraint solving | placement already resolves through a dependency graph, so a solver can replace the resolver for chosen parts |
| Texturing, baking | a single UV0 atlas with padding and texel-density checks; materials are named slots |
| LODs | `decimate` op and quadric simplification are already in the stack; export can emit `<part>_LOD1` nodes |
| Rigging / animation | parts have pivots and semantic parents (node transforms), so skinning attributes can be added per part mesh |
| Morph targets | the surface stage produces per-part vertex buffers, and glTF morph targets attach there |
| Organic / sculpt-like | ops operate on closed meshes, so field-based ops (SDF sculpt, deformation volumes) can be added as op families |
| Scenes | the IR is a scene graph, so scenes compose assets by reference |
| Import / repair | validators and renderer take an `Asset` of meshes; an importer builds that from GLB |
| Other agents / MCP | everything is a library call with JSON-able results; the CLI is a thin wrapper, and an MCP server would be another |
