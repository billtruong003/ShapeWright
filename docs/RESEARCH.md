# Research notes

How this was researched: runtime dependencies were installed and exercised
hands-on in a headless Linux container. Their APIs were probed, the behaviour
relied on was covered by tests, and licences were read from the installed
package metadata. Other projects are assessed from their documentation and
published papers, as known at the time of writing (2026). **Licences marked
"(verify)" must be re-checked before adoption.**

## 1. Existing projects investigated

### Code-first / programmatic modelling
| Project | What it teaches | Adopted | Rejected |
|---|---|---|---|
| OpenSCAD (GPL-2) | CSG trees in a tiny language; parametric modules; plain-text sources in git | source-as-truth, parameters, CSG as vocabulary | its own language (agents know YAML/Python better); CSG-only thinking; slow CGAL booleans (it moved to Manifold for this reason) |
| CadQuery / build123d (Apache-2.0, on OpenCascade) | sketch → extrude/revolve/loft; selectors (`faces(">Z")`) | profile modelling, **selectors** as the agent-native replacement for picking (roadmap) | B-rep kernel (heavy LGPL native dependency, CAD semantics, tessellation step); arbitrary Python as the asset format |
| JSCAD (MIT) | browser CSG | — | JS kernel with weaker robustness than Manifold |
| Houdini SOPs / PDG, Blender Geometry Nodes | non-destructive procedural graphs, attributes, instancing, seeded variation | seeds, instancing metadata, attribute thinking (per-part metadata to extras) | node graphs as the source (GUI-shaped, verbose to serialize and diff) |
| CityEngine CGA, L-systems, shape grammars | rule-based buildings and foliage | roadmap generator family | not a core abstraction for props |

### Agent / AI 3D work
| Project | What it teaches | Adopted | Rejected |
|---|---|---|---|
| Blender MCP adapters (BlenderMCP etc.) | agents can drive DCCs through tool calls | — | opaque scene state, GUI-first tool, no diffable source, heavy install; the "AI awkwardly controlling human software" pattern |
| SceneCraft, 3D-GPT, LL3M-style "LLM writes Blender Python" work | code generation plus **visual feedback loops** improve results; agents benefit from rendering their own output | the render → critique → revise loop; part-level inspection | unrestricted Python as the asset; Blender dependency |
| CADCodeVerify / CAD-Recode / Text2CAD | visual verification of generated CAD code; question-driven self-critique | review checklists (`styles/*.review`), specific critique format | — |
| BlenderGym-type benchmarks | VLM agents are weak at fine geometric edits through GUIs/APIs and better with structured targets | semantic parameters and checks instead of raw edits | — |
| Neural text/image-to-3D (Shap-E, TRELLIS, Hunyuan3D, MeshGPT, LLaMA-Mesh…) | fast plausible shapes; poor topology, UVs and editability | nothing in core; possible future *reference* or *blockout* source via import | one-shot generation as the product |

### Game-asset validation
| Source | Checks adopted |
|---|---|
| Blender 3D-Print Toolbox, mesh-analysis tools | non-manifold, degenerate, intersecting, thin features, overhangs → geometry layer, style thin-feature |
| Engine import pipelines (Unity AssetPostprocessor, Unreal Data Validation, Godot import hints) | naming conventions (UCX_, -colonly), pivots, scale units, material count, LODs |
| Khronos glTF-Validator (Apache-2.0) | used directly for the export layer |
| Studio outsourcing checklists (common practice) | triangle budgets per platform, texel density consistency, UV overlap/padding, grounded origin, no hidden faces |

## 2. Geometry libraries evaluated

| Library | Licence | Used for | Notes |
|---|---|---|---|
| **Manifold** (`manifold3d` 3.x) | Apache-2.0 (from metadata) | booleans, cross-section extrude and revolve, plane trim, **min_gap** contact distance | guaranteed-manifold output, fast; float32 internally (fine at prop scale) |
| **trimesh** 4–5 | MIT (from metadata) | convex hull (qhull via scipy), subdivide, Taubin smoothing, re-import | used selectively; our kernel type is our own `Mesh` |
| **xatlas** (python binding) | MIT (from metadata) | UV charting and packing | deterministic across runs (tested); preserves face order |
| **fast-simplification** | MIT (from metadata) | quadric decimation | wraps Fast-Quadric-Mesh-Simplification |
| numpy / scipy | BSD (from metadata) | everything numeric, qhull | — |
| libigl | MPL-2.0 (verify) | many research algorithms | pybind wheels are large; not needed yet |
| CGAL | GPL/LGPL mix (verify) | exact booleans and remeshing | licence incompatible with a permissive core |
| PyMeshLab | GPL-3.0 (verify) | remeshing and repair | **rejected for core** (copyleft); optional external tool at most |
| Open3D | MIT (verify) | point clouds, visualization | heavy; not needed |
| OpenCascade (OCCT) | LGPL-2.1 with exception (verify) | B-rep | kernel choice rejected (ARCHITECTURE §4) |
| meshoptimizer | MIT (verify) | vertex cache/fetch optimization, simplification | good future export optimization step |
| Instant Meshes / QuadriFlow | BSD-3 / MIT (verify) | quad remeshing | research items |
| MikkTSpace | zlib (verify) | tangents | when normal maps arrive |

## 3. Rendering frameworks evaluated

| Option | Verdict |
|---|---|
| **Custom numpy rasterizer** | chosen for inspection: deterministic, headless, zero system dependencies (ARCHITECTURE §11) |
| three.js (MIT) in headless Chromium (Playwright) | good for a human workbench; not reference-grade deterministic (GPU/SwiftShader differences) |
| pyrender / moderngl (MIT) via EGL/OSMesa | fast; needs system GL, driver-dependent pixels; possible optional backend for big meshes |
| Blender Cycles/EEVEE (GPL tool) | photoreal, heavy; not needed for critique |
| Filament, bgfx | native builds, overkill |

## 4. Validation tools

Khronos glTF-Validator (Apache-2.0, npm `gltf-validator`, optional Node tool in
`tools/`) and the trimesh re-import round-trip are adopted. gltf-transform
(MIT, verify) is planned for texture compression and meshopt in export.

## 5. Ideas worth adopting (and where they went)

- Source-as-truth with reproducible build products (OpenSCAD, build systems) → asset.yaml + `.build/`
- Selectors instead of picking (CadQuery) → roadmap (MODELING_CAPABILITY_MAP §2)
- Seeds for all randomness (Houdini) → `seed`, `vary`, `sw variants`
- Visual self-verification loops (SceneCraft, CADCodeVerify) → `sw review`, critique format, `sw compare`
- Engine naming conventions carried as data → profiles (`collision_naming`)
- Design intent as executable checks (tests for geometry) → `checks:`
- Golden-file regression tests for procedural geometry → `tests/golden.json`

## 6. Ideas deliberately rejected

| Idea | Why |
|---|---|
| Agent-written Python/JS as the asset format | security boundary, static validation, and every asset becoming a one-off program |
| Node-graph source | GUI-shaped; poor diffs; linear op lists cover the observed needs |
| B-rep/NURBS kernel | wrong output domain (game triangles), heavy LGPL dependency |
| Photoreal or GPU rendering in the loop | non-determinism and sandbox fragility; photorealism is not needed for critique |
| A numeric "quality score" | conflates perceptual judgement with metrics; separate layers are more honest and more actionable |
| Microservices, databases, job queues | nothing needs them at this scale (single process, files, git) |
| MCP as the primary interface | an adapter, not a foundation; Python API and CLI first |

## 7. Licences

Project licence: **Apache-2.0** (patent grant, permissive, compatible with all
runtime dependencies).

| Runtime dependency | Licence (from installed metadata) |
|---|---|
| numpy | BSD-3-Clause (plus 0BSD, MIT, Zlib, CC0 for bundled parts) |
| scipy | BSD-3-Clause |
| trimesh | MIT |
| manifold3d | Apache-2.0 |
| xatlas (python) | MIT |
| Pillow | MIT-CMU (HPND) |
| PyYAML | MIT |
| fast-simplification | MIT |
| gltf-validator (optional, Node) | Apache-2.0 |

Policy: no GPL/LGPL/AGPL runtime dependencies in the core. Copyleft tools may
be used only as optional, separately installed external executables.

## 8. Technical risks

| Risk | Mitigation |
|---|---|
| Expressiveness ceiling of declarative sources for complex organic or hard-surface shapes | extension points (new shapes/ops), selectors and components on the roadmap; watch benchmark friction |
| Agents misjudging images (perceptual critique quality varies by model) | orthographic views with scale bars, numeric `sw stats`, `checks:` to lock in intent, compare diffs |
| CPU rendering speed on dense meshes | measured (~3 s for 20k tris); optional GPU backend behind the same interface if needed |
| Float differences across platforms breaking golden hashes | rounding in hashes; hashes cover geometry, not UVs; regenerate intentionally |
| xatlas and Manifold wheel availability on exotic platforms | `sw doctor`; UV method falls back to `none` with a warning |
| Contact test cost O(n²) in parts | bounding-box pruning; fine to ~200 parts |

## 9. Unresolved questions

1. What is the best agent-native abstraction for **general bevels and face-level
   edits**: selectors by normal/region, or named regions defined at the
   generator level?
2. Should components (sub-assemblies) have their own **namespaced params**,
   or share the asset's namespace with prefixes?
3. How far can **explicit constraints** go before a solver is needed, and can
   solver failures be explained well enough for agents?
4. How to encode **style** beyond prose plus a few heuristics: reference
   packs, statistics extracted from example assets, learned critics?
5. What does **sculpting** look like for agents: deformation volumes, SDF
   blends, or image-guided parameter fitting?
6. When should a **browser workbench** come in, and should it allow edits
   (writing back to the YAML) or stay read-only?
