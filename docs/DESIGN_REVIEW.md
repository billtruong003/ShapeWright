# Design review #1 (after the v0.1 vertical slice)

This is the architectural critique written right after v0.1 shipped. It is kept
as a **permanent record**. Findings are phrased as they were found, including
the uncomfortable ones. Later sections record what the hardening phase
changed. The original findings are not edited to look better in hindsight.

**Summary verdict at the time:** the architecture was adequate for the v0.1
goal (low-poly props built from primitives). It had three structural limits
that would block growth early if left alone:

1. `Mesh(V, F)` has no attribute channels.
2. UVs are re-unwrapped from scratch on every build.
3. There is no real escape hatch for free-form geometry.

---

## 1. Why YAML instead of a DSL, code or a graph?

The asset source is the **trust boundary** between the agent and the system,
and it should be data:
- **Safe:** nothing executes; expressions go through an AST whitelist.
- **Checkable before execution:** every field is checked against a typed
  registry spec, with "did you mean" suggestions.
- **Diffable and readable**, and agents write YAML reliably.

The alternatives:
- **Code (CadQuery-style Python):** more powerful, but every asset becomes its
  own program, needs a sandbox, and cannot be checked before it runs.
- **Graph:** a GUI-shaped form; verbose to serialize and diff.
- **Custom DSL:** a parser, tooling and error messages to build, plus a syntax
  agents have never seen.

YAML was chosen because it is **the cheapest thing that is safe enough**, not
because it is the best representation. The sensible upgrade is "code that
emits data": generators or agents write Python that *outputs* YAML, and the
YAML remains the validated contract.

## 2. Where YAML breaks

These were hit while building the benchmarks:
- **Geometric relationships have to be derived by hand.** Making the crest rail
  follow the post lean required `post_z - lean * rail_y / back_height` and
  `rotate: [-lean_deg, 0, 0]`. Replace `shear` with `bend` and the formulas
  become wrong without any warning. Anchors live on the bounding box, not on
  the real surface. **This is the first thing that will break at scale.**
- **No loops, conditionals or functions.** There is no `enabled: expr`, no
  reusable component, and no "N steps of increasing height". `array` only
  repeats a fixed offset.
- **A flat params namespace.** A 50–100 part asset means hundreds of
  ungrouped parameter names.
- **Lists are replaced wholesale under `extends`.** Changing one op in the base
  requires rewriting the whole `ops` list.
- **Errors point at paths** (`parts.seat.shape.size[0]`), not line numbers.
- **YAML traps:** `no` parses as `false`, and parameter names that collide with
  YAML keywords are a hazard.

Points 2 and 3 are solvable with components and `enabled:`. Point 1 needs
surface-aware anchors or a real constraint layer. **It is the biggest
architectural risk in the format.**

## 3. Is the CPU rasterizer technical debt?

Yes, but bounded debt:
- **Measured limits:** the chair (484 tris) renders in about 1 s; a 20k-triangle
  sphere takes about 3 s. The cause is a per-triangle Python loop.
- **Not supported:** texture sampling, alpha/transparency, shadows, AO.
- **It becomes real debt** with textures (bake/paint), assets over 50k tris, or
  material previews.
- **What saves it:** the interface is one function
  `render(asset, surface, view, mode, ...)` that consumes surface buffers, so a
  backend can be swapped (moderngl/EGL, headless three.js). Keep the CPU path as
  the *reference* backend for determinism tests and diffs; use GPU as an
  optional backend for speed or quality.
- **Current code debt:** `views.py` mixes camera, shading, outlines and
  annotation. Split it before adding modes.

## 4. Does the mesh representation support curves and organic modelling later?

- **Curves: yes.** Curves are source-level data sampled to polylines at build
  time (`tube` already works that way). The kernel does not need a curve type.
- **Organic: partially.** Noise, subdivide and smooth exist. There is no remesh
  and no SDF. The rock benchmark has only 112 tris because noise barely deforms
  a sparse hull. Additive sculpting needs remeshing (Manifold `level_set`
  offers an SDF→mesh path).
- **The real problem: `Mesh` only has `V` and `F`.** There is nowhere for face
  tags, vertex colours, skin weights or per-face material ids. Selectors,
  per-face materials, vertex colours, rigging and morph targets all need
  attributes, and every op must carry them through (booleans must interpolate,
  decimation must preserve). **This kernel change should happen early, before
  the op count grows.**

## 5. Is the modifier architecture really composable?

Only at level 1: a linear op list inside one part. It is **not closed under
composition**:
- A boolean tool is a bare `shape` with no `ops` of its own. You cannot
  subtract a tapered block.
- `mirror` and `array` are assembly steps, not ops. You cannot mirror inside a
  part and then boolean.
- A part cannot be used as the input to another part's op. There are no
  cross-part booleans.
- There are no op macros or reusable op groups.
- Ops use bbox-normalized coordinates. That makes them independent of where the
  part is placed, but reordering ops changes their meaning (taper-then-bend is
  not bend-then-taper), and the bbox changes after each op.

Fix direction: make the shape definition recursive, so `{shape, ops}` is valid
everywhere a shape is accepted (including boolean tools), and give mirror and
array an op form. This does not break the current format.

## 6. Does stool-from-chair inheritance scale to asset families?

No. The stool itself exposes the problems:
- **A parameter reused for the wrong meaning.** The stool sets
  `back_height: seat_height - seat_thickness + 0.02` to turn backrest posts
  into ordinary legs.
- **Knowledge of the base's internals.** The stool overrides `rear_leg`'s
  `ops`, `rotate` and `anchor`, so it knows too much about how the base is
  built. When the base's structure changes, the variant breaks silently.
- **No public interface.** Every param and every part of the base can be
  overridden. There is no version and no contract.

Deep merge works for *parameter variants* (which `sw variants` already does
correctly). It does not work for *families with structural differences*.
Scaling needs: public params and optional parts (`enabled:`) declared by the
base, variants that only set params, components instead of part overrides, and
contract tests that every family member still validates when the base changes
(`sw bench` only partly covers this).

## 7. How do semantic parts survive booleans and merges?

- **Booleans are intra-part only**, so the result stays in its part and the
  name is not lost. If a boolean splits a part into several pieces,
  `GEO_PART_FRAGMENTED` warns (one name, several pieces = semantic ambiguity).
- **Cross-part booleans and merging: not supported.** Export always keeps one
  node per part.
- **Direction:** Manifold tracks an `originalID` per triangle, which can become
  a face tag for provenance ("this triangle came from `window_cutter`"). That
  again needs the attribute channels from §4. When merging for draw-call
  optimization, semantics should move into face attributes and `extras`, not
  disappear.

## 8. How does UV unwrapping keep correspondence with semantic parts?

- **The mapping is correct today.** Part meshes are concatenated and unwrapped
  once by xatlas. xatlas preserves face order, so slicing by each part's
  `n_tris` matches. Charts never span two parts, because parts share no
  vertices. Texel density is measured per part.
- **The big problem: UVs are not stable between builds.** A small parameter
  change re-packs the whole atlas and moves every chart. Any texture painted or
  baked earlier is invalidated. With no textures yet this is invisible, but
  **it blocks texturing**.
- **Needed:** fixed UV regions per part (or packing in a fixed part order), UV
  locking, shared UVs for instances, seam control.

## 9. What happens with an imported GLB that has no semantic metadata?

Nothing: import was not implemented. Proposed design:
1. `sw import file.glb` writes an `asset.yaml` with one part per node (node name
   or `mesh_03`) using `shape: {type: mesh_file, path, node}`.
2. Merged nodes are split into connected components (`piece_N`).
3. Render in `parts` mode (one colour per piece, with legend). The agent looks
   at the image and renames pieces to `seat`, `leg`, ... This is the "semantics
   by eye" step, and the existing renderer is good at it.
4. Validators need a policy for open meshes (`closed: false`), because imported
   assets are often not watertight.

Imported assets have no params, so they cannot be edited parametrically, only
through ops, transforms and part replacement.

## 10. What is the escape hatch when primitives are not enough?

It was weak:
- **Available:** `extrude` with any polygon, `lathe`/`revolve` with any profile,
  `tube` along any path, plus booleans. That combination covers a lot.
- **Last resort:** write a new `@shape` in Python. That is framework code and
  needs review.
- **Missing:**
  - `mesh_file`: reference an OBJ/GLB as a part. An agent can run any script
    in its own process and write a file, while the source stays data. The part
    becomes "baked" (not parametric) but still goes through validators and the
    renderer.
  - inline `mesh` (vertices/faces, size-limited) for small shapes.

## 11. Can the geometry backend change without rewriting asset sources?

- **Same-paradigm library swap** (another boolean library for Manifold): the
  source is unchanged, because it references shape/op names and params, not
  the backend. About four functions in `modifiers.py` change, plus golden hashes.
- **Paradigm swap** (to B-rep or SDF): the source is **not** portable.
  - `jitter`, `noise` and `decimate` are vertex operations with no B-rep meaning.
  - Triangle budgets depend on generator topology (`chamfer_box` = 44 tris),
    which is an implicit contract with the backend.
- **The real weakness:** there is no backend interface layer. Ops call trimesh
  and Manifold directly. A thin layer (`boolean`, `hull`, `remesh`, `ray_cast`)
  plus a "topology contract" test per generator would make a backend change
  show exactly what differs.

## Priority order recorded at the time

1. Attribute channels for `Mesh` (face tags, provenance, colour). Foundation for §4, §7, §8.
2. Recursive shape definitions (`{shape, ops}` everywhere a shape is accepted, including boolean tools) (§5).
3. `mesh_file` and an import skeleton (§9, §10).
4. UVs that are stable between builds (§8).
5. `enabled:`, components and a family interface (§2, §6).

---

## Hardening phase outcome

What the hardening phase changed is recorded in [HARDENING.md](HARDENING.md),
together with what it did **not** solve. Findings above that remain open are
listed there explicitly.
