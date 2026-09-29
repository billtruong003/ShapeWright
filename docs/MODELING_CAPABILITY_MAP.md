# Modelling capability map

A taxonomy of modern 3D creation capabilities: what they are, how an agent
would use them natively, how they would be implemented, and where they sit in
Shapewright's plan. **This is a map, not a checklist.** It exists so early
decisions don't block important futures (see §B and §C at the end).

**Priority:** `NOW` = implemented in v0.1 · `NEAR` = next stages (prototype/MVP) ·
`LONG` = production foundation and later · `RESEARCH` = open question ·
`OUT` = out of scope, with the reason given.
**Imp.** (importance for agent-made game assets): H / M / L.

Column guide: *Agent-native* = how an agent expresses it (not how a human clicks it).
*Impl.* = implementation family / library. *Arch.* = architectural impact.


## Status changes from the architecture-hardening phase

See docs/HARDENING.md. Rows below keep their original text; these entries override them.

| Capability | Was | Now | How |
|---|---|---|---|
| Per-face attributes, provenance, regions | — | NOW | typed attribute contract (docs/MESH_MODEL.md) |
| Named regions within parts (§6) | LONG | NOW (data), NEAR (selector syntax) | `region` face attribute, `--mode regions` |
| Per-face materials within a part (§11) | NEAR | NOW | `material:` on geometry expressions → glTF primitive per material |
| Vertex colours (§11) | NEAR | PARTIAL | attribute, import and export (`COLOR_0`) work; no authoring syntax yet |
| CSG with modified tools; mirror within a part (§1, §4) | NEAR | NOW | recursive geometry expressions, `boolean`/`combine` shapes, `mirror`/`repeat` ops |
| Spatial relations from real geometry (§17) | — | NOW | `measure:` queries (section, gap, bounds, anchor, ray) |
| Enforced constraints / solver (§17) | RESEARCH | RESEARCH (deliberately) | see docs/RELATIONSHIPS.md |
| Reusable components (§5) | NEAR | NOW | `components/*.yaml` with public/private params |
| Structural variation / optional parts (§24) | NEAR | NOW | `enabled:` + checks with `when:` |
| Family interfaces (§24) | — | NOW | `interface:` + `sw family` |
| Import GLB/OBJ/STL/PLY (§31) | NEAR | NOW (skeleton) | `mesh_file`, `sw import --split` |
| Stable UVs, shared instance UVs, seams (§10) | NEAR | NOW (region-level) | part-owned regions, `uv.lock.yaml`, `share_instances`, `seams: regions` |
| Chart identity across geometry edits (§10) | — | RESEARCH | would need chart transfer by projection |
| Cross-part booleans (§1) | NEAR | NEAR | blocked by placement↔geometry ordering; see HARDENING.md |

---

## 1. Geometry creation

| Capability | Imp. | Priority | Agent-native interaction | Impl. | Depends on | Arch. |
|---|---|---|---|---|---|---|
| Box / plane | H | NOW (box) · NEAR (plane: open surfaces) | `shape: {type: box, size: [...]}` | custom / trimesh | kernel | open surfaces need per-part `closed: false` so validators don't flag cards |
| Chamfered box (the low-poly workhorse) | H | NOW | `chamfer_box` with `chamfer` in metres | hull of 3 boxes (trimesh/qhull) | — | fixed 44-tri topology keeps budgets predictable |
| Cylinder / cone / frustum | H | NOW | `cylinder` with `radius_top`, `segments`, `chamfer` | lathe | lathe | segment count is the budget lever |
| Sphere (UV) / icosphere / capsule | M | NOW | `sphere`, `icosphere`, `capsule` | lathe / trimesh | — | icosphere is the organic base |
| Torus / ring | M | NOW | `torus`, `ring` | custom / Manifold revolve | — | — |
| Custom parametric primitives (wedge, arch, stairs, gear…) | M | NEAR | new `@shape` with typed params | Python generator | registry | one decorated function each; community packs |
| Polygon creation (explicit verts/faces) | L | NEAR | `shape: {type: mesh, vertices, faces}` (escape hatch, size-capped) | custom | limits | must be validated like any input; discouraged in docs |
| Curves / splines as first-class objects | M | NEAR | `curves:` section, named, referenced by tube/sweep/loft | Catmull-Rom/Bezier sampling | §23 | curves become shared named data (like params) |
| Extrusion (2D profile) | H | NOW | `extrude` with `polygon`, `holes`, `scale_top` | Manifold CrossSection | — | 2D sketch layer (§20) builds on this |
| Inset / bevel / chamfer on arbitrary meshes | H | NEAR (chamfer on convex parts via hull) · LONG (general) | op `bevel {width, segments, angle}` | Manifold minkowski (convex) / custom edge bevel | topology tags | general bevel needs edge selection → §2 selectors |
| Bridge / fill / append | L | LONG | ops over named regions | custom | selectors | only once region naming exists |
| Sweep (profile along path) | H | NOW (regular polygon) · NEAR (arbitrary profile) | `tube {path, radius, sides}`; `sweep {profile, path}` | custom frames (parallel transport) | curves | — |
| Revolve / lathe | H | NOW | `lathe` (open profile), `revolve` (closed outline) | custom / Manifold | — | — |
| Loft / skinning between profiles | M | NEAR | `loft {sections: [{profile, y}], segments}` | custom ring stitching | curves | same ring-stitching core as lathe/tube |
| Surface generation (patches, NURBS) | L | OUT (for now) | — | would need a B-rep kernel | — | triangle kernel chosen; see ARCHITECTURE §4 |
| Profile modelling (2D sketch → solid) | H | NEAR | `sketch` data (lines/arcs/fillets) → extrude/revolve | Manifold CrossSection offset/boolean | 2D ops | a 2D layer mirrors the 3D registry |
| CSG union / subtract / intersect | H | NOW (within part) · NEAR (across parts by name) | `ops: [{type: subtract, shape: ...}]`; later `{type: subtract, part: window_cutter}` | Manifold | closed inputs | cross-part booleans need a dependency graph (placement already has one) |
| Shell / solidify | M | NEAR | op `shell {thickness, open: top}` | Manifold offset (via SDF level set) or inward offset | closed meshes | mugs, buckets, boxes with lids |
| Slice / clip / cut / projection | M | NOW (`flat_bottom`) · NEAR (`slice {plane}`, `split`) | op with a plane given by axis + fraction/anchor | Manifold trim/split_by_plane | — | split produces new named parts: the naming convention needed |

**Shared abstractions:** (a) *profiles* (2D point lists) feed extrude, lathe,
revolve, sweep and loft; (b) *ring stitching* is the core of lathe, tube, loft
and cylinder; (c) *solids + booleans* via one robust library (Manifold);
(d) *typed parameters* in the registry.

## 2. Mesh editing

| Capability | Imp. | Priority | Agent-native interaction | Impl. | Depends on | Arch. |
|---|---|---|---|---|---|---|
| Vertex / edge / face manipulation | M | LONG | **selectors, not indices**: `select: {part: seat, faces: top}`, `{normal: +y}`, `{region: front_half}` | custom selector engine | face tagging | raw indices are unstable across rebuilds; selectors are the agent-native equivalent of picking |
| Face extrude / inset | M | LONG | op `extrude_faces {select, distance}` | custom | selectors | — |
| Edge loops / loop cuts / rings | L | LONG | op `loop_cut {axis, at: [0.3, 0.7]}` (positional, not interactive) | half-edge structure | quad topology | mostly relevant for deformation and subdivision |
| Dissolve / delete / merge / weld / split / detach | M | NEAR (weld = `merged`; split by plane) | ops over selectors | trimesh / custom | selectors | detach creates new named parts |
| Triangulate | H | NOW (the kernel is triangles) | implicit | — | — | quads are not preserved; see §9 |
| Quadrangulate | L | RESEARCH | op | instant-meshes-like | — | matters for subdivision workflows, not game export |
| Flip / reverse normals | M | NOW (automatic outward orientation) | automatic; validator `GEO_INVERTED` | — | — | agents never need to flip by hand |
| Relax / smooth / flatten | M | NOW (`smooth`) · NEAR (`flatten {select}`) | ops | trimesh smoothing | selectors | — |
| Align / snap | H | NOW (anchors/attach) · NEAR (grid snap) | `attach`, anchors, `snap: 0.05` | assembler | — | semantic snapping replaces interactive snapping |
| Shrinkwrap / project onto surface | M | LONG | op `project {onto: part, direction}` | ray casting (Manifold ray_cast / trimesh) | cross-part refs | decals, straps, vines |

**Principle:** direct component editing is where human DCC interaction lives.
Agents get *selectors* (semantic, stable queries) plus ops. They are
implemented only when a benchmark needs them.

## 3. Transform system

| Capability | Imp. | Priority | Agent-native interaction | Impl. | Depends on | Arch. |
|---|---|---|---|---|---|---|
| Translate / rotate / scale | H | NOW | `position`, `rotate` (deg XYZ), ops `scale/rotate/translate` | 4×4 matrices | — | mirror → negative determinant handled (winding flip) |
| Local / world / parent space | H | NOW (local = part space for ops; world for placement) · NEAR (parent-relative placement) | explicit per field | — | — | documented per field in ASSET_FORMAT |
| Applied (frozen) transforms | H | NOW | meshes are baked in world space; node transforms only for pivots | exporter | — | engines get clean identity/pivot transforms |
| Transform inheritance | M | NOW (export hierarchy via `parent`) | `parent: seat` | exporter | — | — |
| Pivots / origins | H | NOW | asset origin at the ground under the footprint (validated); per-part `pivot: anchor` | exporter | anchors | hinges and wheels need part pivots → rigging-ready |
| Bounding boxes / centres | H | NOW | anchors, metrics (`part.size.x`) | assembler | — | — |
| Alignment / snapping | H | NOW (anchors) | `attach: {to, at, offset}` | assembler | — | — |
| Coordinate systems / handedness | H | NOW | one convention = glTF (Y-up, RH, front +Z) | — | — | zero conversions internally; engine conversions only at import side |
| Units | H | NOW | metres everywhere; `ASM_SCALE_SUSPICIOUS` catches cm/mm mistakes | — | — | — |

## 4. Modifier / non-destructive modelling

| Modifier | Imp. | Priority | Agent-native | Impl. | Arch. |
|---|---|---|---|---|---|
| Bevel (general) | H | NEAR/LONG | op | see §1 | edge selection |
| Mirror | H | NOW (part-level instances; plane offset) · NEAR (mirror-merge within a part) | `mirror: x`, `{axis, at}` | assembler | instance naming `_left/_right` |
| Array / radial array | H | NOW | `array: {count, offset}` / `{radial: y}` | assembler | instance naming `_0.._n` |
| Subdivision | M | NOW (midpoint) · NEAR (Loop/Catmull-Clark) | `subdivide` | trimesh | — |
| Solidify | M | NEAR | `shell` | Manifold | — |
| Decimate | H | NOW | `decimate {ratio}` | fast-simplification | LOD basis |
| Triangulate | — | implicit | — | — | — |
| Remesh | M | LONG | `remesh {edge_length}` | Manifold refine / isotropic remesh (PyMeshLab is GPL: avoid) | licensing |
| Boolean | H | NOW | `subtract/union/intersect` | Manifold | — |
| Lattice / FFD | M | NEAR | `lattice {points: [...]}` (coarse control grid values) | custom trilinear | — |
| Twist / bend / taper / shear | H | NOW | ops | custom | normalized part space |
| Noise displacement | M | NOW | `noise {amount, frequency, seed}` | custom seeded waves | — |
| Curve deformation | M | NEAR | `follow_curve {curve}` | custom | curves |
| Shrinkwrap | M | LONG | `project` | ray cast | cross-part |
| Weighted normals | M | NEAR | `shading: weighted` | custom (face-area weighting) | surface stage |
| Geometry optimization (weld, cleanup) | H | NOW (automatic weld/compact) | implicit | kernel | — |

**Decision:** an ordered op list per part (a linear modifier stack), recorded
in source and therefore non-destructive and diffable. A general node graph is
not adopted (see ARCHITECTURE §7).

## 5. Procedural modelling

| Capability | Imp. | Priority | Agent-native | Impl. | Arch. |
|---|---|---|---|---|---|
| Parametric generators | H | NOW | params + expressions | expr evaluator | the heart of the format |
| Reusable procedural components (sub-assemblies) | H | NEAR | `components/*.yaml` with params, instantiated via `use: chair_leg` | assembler namespaces | name prefixing, param scoping |
| Dependency graphs | H | NOW (params, attach) | implicit from references | topo sort | cycles reported |
| Instancing | M | NOW (instances recorded) · NEAR (shared glTF meshes) | `array`, `mirror`, future `instance_of` | exporter | UV sharing decision (§11) |
| Random seeds / controlled variation | H | NOW | `seed`, `vary`, `sw variants` | numpy default_rng | determinism |
| Reusable profiles / curves | M | NEAR | named `profiles:` / `curves:` sections | source schema | shared data |
| Rule-based geometry (L-systems, shape grammars) | M | RESEARCH | `grammar:` rules for buildings and foliage | custom | would be a generator family |
| Composable generators / node-like systems | M | NEAR (components) · RESEARCH (graphs) | nesting of components | assembler | — |
| Generator libraries / packs | M | LONG | pip-installable plugin packages registering shapes/ops | entry points | registry already supports it |
| Parameter constraints | M | NOW (min/max warn, checks) · NEAR (hard constraints, solver) | `min/max`, `checks` | — | — |

## 6. Semantic geometry

| Capability | Imp. | Priority | Agent-native | Arch. |
|---|---|---|---|---|
| Semantic part graph / scene tree | H | NOW | `parts:` names, `parent`, instance naming | names survive to export |
| Named regions within parts (faces) | M | LONG | `regions: {seat_top: {normal: +y}}` | face tags stored alongside meshes |
| Named parameter groups | M | NEAR | `params` with `group:` | doc/UX only |
| Attachment relationships | H | NOW | `attach` graph | enables kitbash, modular kits |
| Semantic tags | M | NOW | `tags` | queryable by validators (`floating_ok`, `thin_ok`) |
| Semantics surviving export | H | NOW | node names + `extras.part/instance/tags/doc` | readable by engines and re-import |

## 7. Topology

| Check / capability | Imp. | Priority | Impl. |
|---|---|---|---|
| Manifold / non-manifold edges, open edges, holes | H | NOW | edge incidence counting |
| Duplicate vertices | H | NOW (welded automatically) | `Mesh.merged` |
| Duplicate / degenerate faces | H | NOW | sorted-index uniqueness, area threshold |
| Inconsistent winding, inverted normals | H | NOW | directed-edge counts, signed volume |
| Disconnected islands / fragmentation | M | NOW | union-find |
| Long thin triangles / quality | M | NOW (info) | radius-ratio quality |
| Self-intersection within a part | M | NEAR | Manifold round-trip status / triangle-triangle tests |
| Ngons / poles / quad flow | L | OUT for triangle kernel (RESEARCH for subdivision workflows) | — |
| Topology density and distribution | M | NEAR | triangles per m² of surface per part vs asset median → "overdetailed part" info |

## 8. Retopology

| Capability | Imp. | Priority | Notes |
|---|---|---|---|
| Triangle reduction | H | NOW (`decimate`) | quadric error metrics |
| Automatic retopology / quad remeshing | L | RESEARCH | Instant Meshes (BSD) or QuadriFlow (MIT) as optional tools |
| Surface projection / topology transfer | L | LONG | ray casting |
| Topology-aware optimization | M | LONG | combine density metrics with silhouette error |

## 9. Normals and shading geometry

| Capability | Imp. | Priority | Agent-native | Impl. |
|---|---|---|---|---|
| Face / vertex normals | H | NOW | automatic | surface stage |
| Smoothing groups / hard edges / split normals | H | NOW | `shading: flat/smooth/auto`, `smooth_angle` | per-corner normals |
| Weighted normals | M | NEAR | `shading: weighted` | area/angle weighting |
| Tangent generation (MikkTSpace) | M | NEAR (when normal maps arrive) | automatic on export | mikktspace port (zlib licence) |
| Normal validation | H | NOW | `NRM_FLIPPED`, magenta back faces in renders | — |

## 10. UV and surface mapping

| Capability | Imp. | Priority | Agent-native | Impl. | Deterministic? |
|---|---|---|---|---|---|
| UV creation, automatic unwrap and packing | H | NOW | `uv: {method: auto}` | xatlas | yes (tested) |
| Seam definition | M | NEAR | seams from `shading` hard edges and part boundaries; explicit `seams: {select}` later | xatlas chart options | yes |
| Planar / box / cylindrical / spherical projection | M | NEAR | `uv: {method: box}` per part | custom | yes |
| Island transform / packing / padding | H | NOW (padding from profile) | profile `uv.padding_px` | xatlas | yes |
| Overlap / out-of-bounds detection | H | NOW | validator | rasterized coverage | yes |
| Texel density & normalization | H | NOW (measure) · NEAR (per-part weighting) | metrics, `UV_TEXEL_DENSITY` | — | yes |
| Mirrored / stacked / intentional overlap | M | NEAR | `uv: {share_instances: true}` | instance-aware unwrap | yes |
| Texture atlasing across assets | M | LONG | pack-level atlas | xatlas multi-mesh | yes |
| Lightmap UVs (UV1) | M | NEAR | `uv: {lightmap: true}` | second xatlas pass, no overlap | yes |
| UDIM | L | OUT (film workflow) | — | — | — |

*Artistic judgement* remains in seam placement for hand-painted textures and in
texel-density priorities (faces seen up close). Both are expressible as data
later (seam selectors, density weights).

## 11. Materials

| Capability | Imp. | Priority | Notes |
|---|---|---|---|
| Material slots / assignments | H | NOW | per part; budget-checked |
| PBR (base colour, metallic, roughness, emissive, alpha, double-sided) | H | NOW | glTF PBR, sRGB→linear |
| Vertex colours | M | NEAR | per-part colour or gradient → `COLOR_0`; big win for flat-shaded low-poly (one material) |
| Per-face materials within a part | M | NEAR | face material ids from selectors |
| Procedural materials / shader metadata | L | LONG | extras; engine-side graphs are out of scope |
| Palette-driven stylized shading | M | NEAR | style `palette` → validator for off-palette colours |

## 12. Texture pipeline

| Capability | Imp. | Priority | Notes |
|---|---|---|---|
| Texture assignment / image textures | M | NEAR | `base_color_texture:` path in material; embedded in GLB |
| Procedural textures (noise, wood grain, gradients) | M | LONG | numpy generators writing PNGs into UV0 space, deterministic |
| Texture generation by image models | M | RESEARCH | an *optional external tool* behind an interface; never in the core loop's determinism path |
| Painting interfaces | L | OUT | human workflow; agents paint via procedural or baked textures |
| Atlases, resolution budgets | M | NEAR | profile `texture_size` already present |
| Compression (KTX2/Basis) | M | LONG | via `gltf-transform` (MIT) CLI in export |

## 13. Baking

| Capability | Imp. | Priority | Notes |
|---|---|---|---|
| AO, curvature, thickness, position, material-ID maps | M | LONG | CPU ray casting against the asset (Manifold/trimesh rays) into UV0 space; the renderer's rasterizer already rasterizes UV space |
| High-to-low normal baking | M | LONG | needs a high-poly source (subdivided/sculpted variant of the same part), so the source format needs `high:` variants per part |
| Lightmaps | L | LONG | UV1 first |

**Decision:** baking is an *extension layer* (it consumes Asset + Surface and
writes textures), not core. Its main dependency (a clean, non-overlapping UV0)
exists already.

## 14. Scene architecture

| Capability | Imp. | Priority | Notes |
|---|---|---|---|
| Objects, hierarchy, parenting | H | NOW (within asset) | parts, `parent` |
| Collections / groups / layers | L | NEAR | tags suffice for now |
| Instances / references / linked assets | M | LONG | scene files referencing assets by path, transforms per placement |
| Modular assemblies / multi-asset scenes | M | LONG | scene source format mirroring asset format (`placements:` with attach) |

## 15. Modular modelling and sockets

| Capability | Imp. | Priority | Notes |
|---|---|---|---|
| Standard dimensions / grid alignment | H | NEAR | profile `grid: 0.5`, validator: bounds multiples of grid for `kind: module/*` |
| Snap points / attachment points / sockets | H | NOW (sockets) | `SOCKET_<name>` nodes; kits need typed sockets (`type: wall_edge`) |
| Modular kits (walls, floors, doors, trims, pipes) | M | LONG | depends on components + grid + typed sockets |

## 16. Instancing

Recorded now (`extras.instance`, per-instance meshes). NEAR: export shared
meshes with node transforms for arrays (memory, batching), with UVs shared
intentionally. LONG: scatter/placement generators with engine-friendly instance
lists (`EXT_mesh_gpu_instancing`).

## 17. Spatial constraints

| Capability | Imp. | Priority | Notes |
|---|---|---|---|
| Attachment (anchor-to-anchor + offset) | H | NOW | resolves in dependency order |
| Verified relations (A above B, gap < x) | H | NOW | `checks:` expressions |
| Enforced relations / solver (fit door to opening, wheel to axle) | M | RESEARCH | a small constraint solver on part transforms and params; risk of opaque failures, so it must explain unsatisfiable sets |

## 18. Hard-surface

Booleans, chamfers, cut-outs, symmetry, arrays, radial patterns and precise
dimensions are NOW. Panel lines and inset surfaces are NEAR (via
`subtract` with thin tools; general inset needs selectors). Mechanical
components (bolts, hinges, gears) are NEAR as generator packs.

## 19. CAD-like capabilities

| Capability | Priority | Notes |
|---|---|---|
| Exact dimensions, parametric relationships | NOW | params + expressions + checks |
| Profiles/sketches → extrude/revolve | NOW (polygons) · NEAR (sketch entities with arcs/fillets) | |
| Lofts | NEAR | |
| Fillets (true rounds) | NEAR (via chamfer segments on convex parts) · OUT (exact B-rep fillets) | triangle kernel |
| Geometric constraints (parallel, tangent) | RESEARCH | 2D sketch solver |

## 20. Organic and sculpt-like modelling

**Agent-native sculpting is not a brush.** Candidates, all as op families on
closed meshes:

| Approach | Priority | Notes |
|---|---|---|
| Seeded noise / inflate / smooth / subdivide | NOW | rocks, blobs |
| Deformation volumes ("push region R by d along n") | RESEARCH | `deform: {region: sphere(c, r), offset: [...], falloff: smooth}` is a semantic analogue of a brush stroke |
| SDF / field modelling (smooth unions, blends) | RESEARCH | Manifold `level_set` can mesh SDFs; enables organic blends between parts |
| Voxel workflows, remeshing | LONG | via level sets |
| Image-guided edits (match silhouette to reference) | RESEARCH | optimize params to minimize silhouette difference against a reference image, using the same renderer |
| Learned deformation / shape priors | RESEARCH | optional external tools |

## 21. Curves and splines

Bezier, B-spline and Catmull-Rom as named `curves:` data (NEAR), sampled to
polylines with explicit sample counts (a budget lever). Consumers: `tube`
(NOW, polyline), `sweep`, `loft`, `follow_curve`, cables, pipes, rails, roads,
branches. Curves are data, so agents can edit control points by name.

## 22. Terrain (LONG, separate subsystem)

Heightfield generator (grid + noise + erosion passes), masks as images, terrain
LOD by quadtree, road/river carving by curves, biome placement. Shares the
renderer (top ortho view is a map) and exporter. Not a prop-kernel concern.

## 23. Foliage (LONG)

Branching generators (space colonization / L-systems as generator family), leaf
cards (needs open surfaces and alpha materials), clustering, wind metadata in
vertex colours, LODs with billboard fallback.

## 24. Asset variants, families, kitbashing

| Capability | Priority | Notes |
|---|---|---|
| Seeded variation of params | NOW | `vary` + `sw variants` |
| Structural variation (optional parts) | NEAR | `enabled: expression` per part |
| Families (base → variants) | NOW | `extends` with deletions |
| Kitbashing from component libraries | LONG | components + typed sockets + material harmonization |
| Detail levels per variant | NEAR | LODs |

## 25. Art direction, references, style

| Capability | Priority | Notes |
|---|---|---|
| Natural-language style documents | NOW | `styles/*.yaml` description + review questions printed by `sw review` |
| Measurable style heuristics | NOW (min feature size, part/material counts) · NEAR (bevel ratio, palette adherence, detail density) | warnings only |
| Reference images (geometry / style / scale / material refs) | NEAR | `references:` in source with a role per image; `sw review` puts the reference next to the same-view render |
| Reference-silhouette matching | RESEARCH | silhouette IoU vs ortho reference; param optimization |
| Pack style consistency ("does this chair belong with this table?") | NEAR | multi-asset contact sheet at a common scale plus metric comparisons (density, chamfer ratio, palette) |
| Learned style embeddings | RESEARCH | optional external critic; never a hard gate |

## 26. Closed-loop modelling and validation

NOW: review → critique → snapshot → compare → restore, layered validation, and
design-intent checks. NEAR: `sw loop-report` summarizing iteration trajectories
(metrics over iterations) and automated stop-rule hints (no improvement between
snapshots). RESEARCH: automated critics (vision model prompts as optional
validators with structured output).

## 27. Visual inspection

NOW: 11 deterministic cameras; clay, parts, material, wire, normals and
silhouette modes; UV view; part focus and isolation; contact sheets; compare
with silhouette diff. NEAR: turntable strip (8 azimuths in one image),
human-scale reference figure in ortho views, measurement overlays between named
parts (`--measure seat.top leg.bottom`), and a pack sheet. Deliberately not:
photoreal rendering in the loop.

## 28. LOD, optimization, collision

| Capability | Imp. | Priority | Notes |
|---|---|---|---|
| LOD generation (LOD1/LOD2 by ratio, silhouette-preserving) | H | NEAR | per part decimate plus silhouette IoU check vs LOD0 from the same cameras |
| Platform profiles | H | NOW | profiles/*.yaml |
| Draw-call / material / texture budgets | H | NOW (materials) · NEAR (textures) | |
| Mesh merging for export (one mesh per material) | M | NEAR | export option; semantics kept in extras |
| Collision: box / hull / compound / single box | H | NOW | `collision.mode`; UCX or Godot naming |
| Walkable collision, triggers | L | LONG | |

## 29. Rigging, skinning, morphs, animation (LONG)

| Capability | Notes |
|---|---|
| Rigid part animation (doors, lids, wheels) | *first step*: per-part pivots (NOW) + glTF node animation clips (`animations:` with keyframes on named parts). Mechanical rigs come nearly free from the semantic hierarchy. |
| Skeletons, bind pose, skin weights | per-part vertex buffers in the surface stage get `JOINTS_0/WEIGHTS_0`; weights from part membership (rigid skinning) first, then distance-based smooth weights |
| Weight validation (normalization, influences ≤ 4, bone limits) | validators in a `rig` layer; profile `constraints.max_bones` already reserved |
| Blend shapes / morph targets | per-part `morphs:` defined as op lists applied to the same topology, exported as glTF morph targets |
| Humanoid rigs, IK | OUT for the prop domain; interoperate via engines |

## 30. Scenes, packs, engines

| Capability | Priority | Notes |
|---|---|---|
| Asset packs with shared scale/style | NEAR | pack manifest (`pack.yaml`), `sw bench` per pack, pack sheet |
| Scene generation (layout, placement, navigation) | LONG | scene source format; reuse validators (floating, penetration, scale) |
| Engine compatibility: Godot, Unity (glTFast), Unreal (Interchange), Blender | NOW (glTF) · NEAR (import smoke tests in CI where engines are available headless: Blender, Godot) | naming conventions via profiles |

## 31. Import / export / interop

| Format | Priority | Notes |
|---|---|---|
| GLB export | NOW | deterministic, Khronos-validated |
| glTF (JSON + bin) | NEAR | trivial variant |
| OBJ / STL / PLY export | NEAR | via trimesh, loses semantics (documented) |
| USD / USDA / USDZ | LONG | strategic for scenes/AR; `usd-core` (Apache-2.0-style licence) |
| FBX | OUT | proprietary SDK; engines accept glTF |
| Import GLB/OBJ/STL/PLY → Asset (validate, render, repair) | NEAR | parts from nodes; sandboxed parsing; size limits |

## 32. Agent interfaces

| Interface | Priority | Notes |
|---|---|---|
| Python API | NOW | every command is a function |
| CLI (`sw`) | NOW | compact text, `--json`, exit codes |
| Capability manifest | NOW | `sw caps --json` generated from registries |
| MCP server | NEAR | thin adapter over the same functions; not required |
| Browser workbench for humans | NEAR | static three.js viewer of export + report + sheets; no hidden logic |

## 33. Metadata, catalog, multi-asset reasoning

| Capability | Priority | Notes |
|---|---|---|
| Asset metadata (kind, tags, description, dimensions, triangles, profile, style, validation state, source hash, params) | NOW | in the source (`asset:`) and exported in the root node's `extras.shapewright` |
| Shared dimensional context (chair seat vs table height vs door vs character) | NOW (cross-asset `checks:` with literal values) · NEAR (a `scale_reference.yaml` of named standard dimensions importable as params) | human scale is the hub of pack consistency |
| Asset catalog / discovery by tag, kind, style, dimensions | LONG | `sw catalog` scanning `assets/*/asset.yaml`; no database needed until thousands of assets |
| Learning from existing packs (extract dimensions, density, chamfer language) | RESEARCH | importer + statistics over parts; seeds style heuristics |

---

## A. Shared abstractions (what unlocks most of the map)

1. **Semantic parts + anchors**: placement, symmetry, sockets, modular kits,
   kitbashing, rigid animation and scenes all reuse them.
2. **Profiles and ring stitching**: extrude, lathe, revolve, sweep, loft and
   tubes, and later terrain strips.
3. **Robust solids (Manifold)**: booleans, shells, trims, contact tests,
   level sets for SDF/organic work.
4. **Typed registry**: shapes, ops, validators, and later exporters and
   importers; it drives docs, schema checks and tests.
5. **One surface stage**: normals, UV0/UV1, vertex colours, skin weights and
   morphs all attach to per-part vertex buffers consumed by both renderer and
   exporter.
6. **Deterministic cameras and rasterizer**: inspection, comparison, LOD
   silhouette checks, UV rasterization (overlap, baking later).
7. **Selectors (future)**: the agent-native replacement for picking; required
   by general bevel, face ops, per-face materials, seams and regions.

## B. Futures that bad early decisions would have blocked (and what was done)

| Risk | Avoided by |
|---|---|
| Unnamed geometry blocks semantic edits, sockets and rigs | parts are named at the source level and names survive export |
| A non-glTF axis convention creates conversion bugs everywhere | glTF convention internally |
| Code-as-asset needs sandboxing for every asset and makes static validation impossible | declarative source; code only in reviewed extensions |
| Storing renders in history bloats the repo | deterministic re-rendering from snapshot sources |
| Per-part UV islands with no atlas block texturing and baking | single asset-wide UV0 atlas with padding and texel checks |
| Baked world meshes without pivots block animation | optional per-part pivots already exported as node transforms |
| GPU/browser-only rendering fails in sandboxes and CI | CPU rasterizer; a browser viewer is optional |
| A custom boolean or UV algorithm becomes a maintenance sink | Manifold and xatlas |
| Copyleft dependencies (GPL: PyMeshLab, CGAL parts; LGPL: OCCT) limit redistribution | permissive-only runtime dependencies (RESEARCH.md) |

## C. MVP prioritization summary

| Category | What | Why there | Key dependency | Major risk |
|---|---|---|---|---|
| **CORE NOW** (done) | source format, params, parts, anchors, mirror/array, primitives, profile shapes, deformers, booleans, normals, UV atlas, layered validation, CPU renders, history, GLB export | the minimum closed loop for low-poly props | Manifold, xatlas | expressiveness ceiling of declarative data → mitigated by extension points |
| **NEAR** | selectors, components, curves/loft/sweep, cross-part booleans, vertex colours, LODs, lightmap UVs, reference images, pack sheets, import, MCP adapter, human viewer | the second benchmark wave (modular kit, foliage card, imported asset repair) needs them | registry, surface stage | scope creep; each item needs a benchmark that needs it |
| **LONG** | texturing and baking, rigid animation, skinning, scenes, terrain, foliage generators, USD | valuable but each is a subsystem | UV0, pivots, scene IR | building before demand; keep them as extensions |
| **RESEARCH** | agent-native sculpting (deformation volumes, SDF), constraint solving, image-guided param fitting, learned critics, quad remeshing | unclear best abstraction | renderer, Manifold level sets | opaque failures that agents can't debug |
| **OUT** | exact B-rep/NURBS surfaces, FBX, UDIM, brush-based painting UIs, engine-level profiling | wrong domain or licence, or a human-interaction workflow | — | — |
