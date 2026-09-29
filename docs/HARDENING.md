# Architecture hardening phase: outcome

Scope: answer [DESIGN_REVIEW.md](DESIGN_REVIEW.md) structurally, with **no new
modelling features**. Each area records the problem, the alternatives, the
direction chosen, migration impact, compatibility, the contract tests, and
what is still open. Details live in the linked documents.

| Area | Doc | Contract tests |
|---|---|---|
| Mesh attributes and provenance | [MESH_MODEL.md](MESH_MODEL.md) | `tests/test_mesh_contract.py` (every registered op) |
| Geometry backend boundary | [BACKEND.md](BACKEND.md) | `tests/test_architecture.py` |
| Recursive geometry composition | [ASSET_FORMAT.md](ASSET_FORMAT.md#geometry-expressions-recursive) | `test_mesh_contract` (boolean provenance), `test_shapes_ops` (every generator example) |
| Attachments / relationships | [RELATIONSHIPS.md](RELATIONSHIPS.md) | `tests/test_relationships.py` |
| Geometry sources | [ASSET_FORMAT.md](ASSET_FORMAT.md#baked-and-imported-geometry) | `tests/test_sources.py` |
| Stable UVs | [UV.md](UV.md) | `tests/test_uv.py` |
| Components and families | [FAMILIES.md](FAMILIES.md) | `tests/test_components.py` |

Test count went from 84 to 163. `sw bench` reports 8/8 PASS.

## 1. Mesh attributes and provenance

- **Problem:** `Mesh(V, F)` could carry nothing; every future feature would have
  required rewriting every op.
- **Alternatives:** free-form dicts (no contract), trimesh visuals (library
  coupling), half-edge rewrite (too big).
- **Chosen:** a closed typed schema (`origin`, `material`, `region`, `color`,
  `uv`) over vertex/face/corner domains. Every op declares a topology class
  whose attribute policy is fixed (preserve / interpolate / inherit / transfer /
  invalidate). Derived data (normals, tangents) is never stored.
- **Migration:** none for sources. Ops were rewritten to use `with_positions`,
  `remapped` or backend functions. **All v0.1 benchmark geometry stayed
  byte-identical** through this refactor (golden hashes unchanged), which was
  the acceptance criterion.
- **Open:** selector syntax over regions; corner attributes through booleans
  (deliberately invalidated); Manifold merges coplanar provenance (documented,
  visible in `--mode provenance`).

## 2. Backend boundary

- **Problem:** ops imported trimesh/Manifold directly; there was no statement of
  what is contract.
- **Chosen:** one module (`backend.py`, ~20 functions) with stated policies,
  enforced by a test that fails on direct imports elsewhere. On its first run
  it found a real leak (scipy in the exporter). Generator triangle counts are
  pinned as a *source-level* contract.
- **Honest limit:** the source is portable across same-paradigm libraries, not
  across paradigms (B-rep/SDF). `jitter`/`noise`/`decimate` and UV charts are
  inherently triangle-topology semantics. BACKEND.md lists which is which.

## 3. Recursive geometry composition

- **Problem:** boolean tools could not have ops; mirror/array existed only at
  part level; composition was not closed.
- **Alternatives:** node graph (rejected in v0.1 for diffability), special-case
  fields per op (the thing to avoid).
- **Chosen:** a *geometry expression* `{type, params, ops, material, rotate,
  translate}` accepted everywhere geometry is expected, plus `boolean` and
  `combine` generators and `mirror`/`repeat` ops. `boolean(base = modified,
  tool = modified)` and `mirror(modified)` need no special cases.
- **Compatibility:** v0.1 sources are valid expressions. The old
  `shape`/`position`/`rotate` op parameters still work (history snapshots from
  v0.1 rebuild unchanged).
- **Open:** **cross-part geometry references** (subtract part A from part B)
  remain unsupported. The obstacle is ordering: a part's placement depends on
  its geometry's bounding box, and a cross-part boolean needs the other part's
  *placed* geometry expressed in this part's local frame before this part is
  placed. It is solvable (place first, then boolean in world space, then
  re-derive local space), but it changes the build order contract and no
  benchmark required it yet.

## 4. Attachments, anchors and constraints

- **Problem:** relationships were hand-derived arithmetic (the chair's lean maths).
- **Alternatives:** CAD solver (opaque failures), surface anchors (too narrow),
  local frames (don't cover dependent geometry).
- **Chosen:** `measure:` queries on already-built parts: `section`, `gap`,
  `bounds`, `anchor`, `ray`. They are deterministic, ordered, compose with
  expressions, and name the part and plane when they fail.
- **Migration:** the chair's rail, slats and both stretchers now use queries.
  Geometry changed intentionally (stretchers now embed 1.5 cm into the legs
  instead of overlapping by up to 4 cm, about 20% shorter; silhouettes IoU ≥
  0.988 vs iteration 2). Golden hashes regenerated for chair and stool.
- **Evidence:** the chair stays valid under lean 0 to 0.15, splay 6°, width,
  depth and leg changes, and with no back (6 perturbation tests).
- **Open:** orientation still authored (`rotate: -atan2(lean, back_height)`); no
  simultaneous constraints; `attach` anchors remain bbox-based.

## 5. Geometry sources

- **Problem:** imported or externally generated geometry had no place, so the
  only escape hatch was framework code.
- **Chosen:** `mesh_file` is an ordinary geometry expression with sandboxed paths
  (inside the asset directory; GLB/OBJ/STL/PLY only; size and triangle limits;
  files are never executed; `generated_by` is recorded, not run). It carries
  authored UVs and colours as attributes and participates in ops, booleans
  (if closed), measure, validation, UV regions and export. `sw import` creates
  addressable structure (per node, or per connected piece with `--split`),
  skips engine collision proxies, tags open meshes `open_ok`, and leaves the
  naming to the agent after a `parts` render.
- **Evidence:** export → import round-trip of the chair keeps part names,
  triangle count, bounds and UVs; native parts can attach to and boolean with
  imported ones.
- **Open:** sockets/empties in imported files are not imported yet; glTF
  materials are replaced by one neutral material.

## 6. Stable UVs

- **Problem:** one global unwrap per build meant any edit moved all charts.
- **Chosen:** part-owned regions (charts computed per owner from its own
  geometry, deterministic), area-proportional shelf packing, a committed
  `uv.lock.yaml`, `share_instances`, `seams: regions`, and authored UVs kept.
- **Evidence:** with a lock, widening the back slats changes exactly the two
  slats' UVs, inside their rectangles. Adding a part is reported as a stale lock.
- **Costs:** lower atlas utilization (chair median texel density ~283 → ~250
  px/m at 512²).
- **Open:** chart identity *within* a part across its own geometry edits (needs
  chart transfer by projection); lock does not rebalance density automatically.

## 7. Components and families

- **Problem:** `extends` coupled variants to base internals (the stool).
- **Chosen:** components (public `params`, `private` values, internal-only
  references, material slot mapping, group placement), `enabled:` on parts and
  instances, `when:` on checks, and family `interface:` enforced on `extends`
  (variants set public params only; their checks are *added*), plus `sw family`.
- **Migration:** the stool is 4 public params. The table uses the `plank_top`
  component, and the new `tavern_bench` reuses it. Golden hashes regenerated for
  the table (its parts are now `top_plank_*`, `top_batten_*`).
- **Open:** components cannot be mirrored/arrayed or nested; interfaces are not
  versioned.

## Findings from DESIGN_REVIEW that remain open

| Review item | Status |
|---|---|
| §2 YAML: loops/functions | partially (components, `enabled`); no loops |
| §2 YAML: flat namespace | partially (components scope their params) |
| §2 YAML: list replacement under extends | avoided by interfaces (variants no longer patch lists) |
| §2 YAML: errors without line numbers | **open** |
| §2 YAML traps | a new instance confirmed during migration (commas inside `atan2(a, b)` split flow lists); the error message now detects it |
| §3 CPU rasterizer debt | **unchanged** (not in scope) |
| §4 organic modelling (remesh/SDF) | **unchanged**; the attribute contract reserves the `resample` class for it |
| §5 cross-part booleans | **open** (see §3 above) |

## Fresh-agent experiment

*Filled in from the observed run; see the section below.*
