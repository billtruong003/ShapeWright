# Surface, material and texture architecture (Phase 7 design)

Status: **design, written before implementation.** Phase 8 implements the
smallest complete subset (marked **P8** below).

Inputs from earlier phases:
- *FA-01*: the first agent needed a third material only to make a surface read
  differently (end grain vs bark). Colour variation had to be spent as draw
  calls.
- *FA-03*: across a pack, texel density spread 2.5× because every asset has its
  own atlas at a fixed resolution; thin rings and tubes pack loosely into UV
  regions.
- *FA-02*: the UV lock goes stale whenever an array count changes, because owners
  are instance names.

## 1. The fundamental question

*What should an editable surface look like when its primary editor is an
autonomous coding agent?*

Agents cannot paint and should not edit pixels. They are good at:
- naming intent ("dark stylized oak, subtle grain, moderate edge wear");
- changing a number and looking at the result;
- reading a report.

So the editable thing must be a **recipe with semantic parameters**, evaluated
deterministically into textures, and inspected through renders. Pixels are a
build artifact, as meshes are. Hand-authored and externally generated images
remain first-class *inputs*, but they are the exception with a clear
lifecycle, not the default.

### Alternatives considered

| Representation | For agents | Verdict |
|---|---|---|
| Traditional shader node graph (Blender, MaterialX, Substance Designer) | expressive, but graphs are verbose to write and diff; the vocabulary is low-level (noise → colour ramp → mix); agents would rebuild "wood" every time | rejected as the *authoring* layer; MaterialX is a possible **export** target later |
| Raw PBR factors only (today) | trivially editable, but no variation inside a material; every visual distinction costs a material slot (FA-01) | kept as the degenerate case (`archetype: flat`) |
| Image textures only (painted/generated) | an agent can't revise "reduce grain strength"; UV changes invalidate them | first-class input, not the default |
| **Material archetypes with semantic parameters**, evaluated procedurally in object space and baked into the atlas | "make the wood warmer" is one parameter; deterministic; survives UV changes (re-bake); reusable across a pack | **chosen** |

## 2. Surface data model

```
Material (named, reusable)
  archetype        registered generator: flat | wood | metal | stone | painted | ... (P8: flat, wood, metal, stone, painted)
  semantic params  archetype-specific, human-meaningful: color, grain_strength, grain_scale, edge_wear, roughness, ...
  layers           optional list of surface sources blended on top (P8: image, vertex_color, edge/cavity masks)
  pbr overrides    metallic, roughness, emissive, alpha_mode, double_sided (as today)
  use              optional: another material this one is an instance of (overrides params only)

Surface source (a layer)
  procedural       archetype evaluation (object-space noise/grain; deterministic, seeded)
  image            file in the asset/pack directory (authored or externally generated), projected
                   (triplanar/box in object space) or sampled through authored UVs (mesh_file parts)
  vertex_color     the mesh `color` attribute
  mask             derived from geometry: edge (convexity), cavity, ao (optional), height, region, part
  constant         flat colour/value
```

Assignment is unchanged: part `material:`, per-expression `material:` (face
attribute), pack materials. A **material instance** (`use: oak`) changes
semantic params without redefining the recipe, the same way a variant changes
public params.

Example (illustrative, to be finalised in Phase 8):

```yaml
materials:
  oak_dark:
    archetype: wood
    color: "#6b4428"          # base tone (sRGB)
    grain_strength: 0.35      # 0 = flat colour, 1 = strong contrast
    grain_scale: 0.12         # metres per grain band
    edge_wear: 0.4            # lightens convex edges (reads as handled wood)
    roughness: 0.85
  oak_light: {use: oak_dark, color: "#9a6a40", grain_strength: 0.25}
```

Semantic edits map to parameters: "warmer" is a hue shift of `color`; "less
grain" is `grain_strength`; "lighter edges" is `edge_wear` / `edge_color`;
"rougher" is `roughness`. The vocabulary is **per archetype, typed and
documented** (`sw doc wood`), exactly like shapes. Archetypes are registered
functions, so the registry, schema checking, suggestions and contract tests
apply unchanged.

## 3. Texture lifecycle and UV relationship

Key insight: **procedural surfaces are evaluated in object space and baked into
UVs at build time**, so they do not depend on UV stability at all. Every build
re-bakes them into the current UV layout. UV stability matters only for content
that cannot be regenerated: authored or externally generated images mapped
through UVs, and expensive bakes someone chose to commit.

States (per part × texture channel), reported by validation:

| State | Meaning | Typical cause | Action |
|---|---|---|---|
| **DERIVED** | regenerated from source every build | procedural archetypes, masks, vertex colour | none (always valid) |
| **VALID** | authored content whose UV region and charts are unchanged | image on a locked part that did not change | none |
| **REGION_KEPT** | the part changed, its locked region did not; charts inside were regenerated | dimensions changed | authored content for *this part only* must be redone or re-projected |
| **RELAYOUT** | regions moved (lock stale or missing) | part added or removed, count change without shared owners | re-lock; authored content for moved parts is invalid |
| **INVALID** | content references UVs that no longer exist | topology change on a mesh_file part with authored UVs; path missing | re-author, or switch to projected mapping |

Rules that reduce the non-DERIVED cases:
- **Default to object-space projection** for images too (triplanar/box, baked
  into the atlas). Only `mesh_file` parts with authored UVs use UV-sampled images.
- **Arrays default to shared UV owners for locking purposes**
  (`uv.share_instances` recommended in docs; the lock treats a change in instance
  count of a shared owner as non-structural). This fixes the FA-02 finding.
- **Append-only lock allocation** (future): a new part gets a free region instead
  of forcing a full relayout.

## 4. Texel density and pack consistency

Texture **resolution follows surface area** so that texel density is set per pack,
not per asset: `resolution = pow2(ceil(sqrt(total_region_area) × target_px_per_m / utilization))`,
clamped by the profile's `texture_size`. The pack (or profile) declares
`texel_density`. This fixes the FA-03 spread (2.5×) by construction; the
validator reports the remaining spread. **P8.**

## 5. Rendering requirements and abstraction

| Need | Backend |
|---|---|
| geometry, silhouettes, regression diffs (today) | **CPU diagnostic** (numpy): deterministic, byte-identical |
| material appearance for agent critique: albedo, variation, seams, stretching, texel density, colour balance | **CPU diagnostic + textured mode** (P8): per-pixel UV interpolation, bilinear sampling, simple lit shading (lambert + roughness-scaled specular). Deterministic. Not PBR-accurate |
| PBR-plausible preview (metal vs dielectric, reflections) | optional **browser backend** (three.js in headless Chromium via Playwright; Chromium is already in the environment); tolerance-based diffs instead of byte equality |
| marketing-quality renders | out of scope (Blender if a user wants it) |

Interface (P8 introduces the seam; only the CPU backend is implemented):
`render(asset, surface, textures, view, mode, size, ...) -> Image`. New inspection
modes: `textured` (lit), `albedo` (unlit base colour: colour balance), `roughness`,
`metallic`, `texel` (checker at the target density: stretching and density),
`seams` (UV chart borders overlaid). A `material_sheet` shows each material on a
reference shape (sphere + chamfer box) under the same lights.

## 6. Baking architecture

| Bake | Where | Why |
|---|---|---|
| procedural archetype → atlas (base colour, roughness, metallic) | **core (P8)** | the main mechanism |
| edge / convexity mask (from mesh dihedral angles per vertex/face) | **core (P8)** | cheap, deterministic, drives "edge wear" |
| material ID, part ID, position, region masks | **core** | cheap, from attributes |
| ambient occlusion | **optional** (P8+): per-vertex rays through the backend, interpolated; texel-level AO needs a BVH (Embree/trimesh optional) | expensive; low-poly stylized often skips it |
| curvature (smooth), thickness | optional | needs rays or remeshing |
| high-to-low normal baking | **extension** (Phase 9+) | needs a high-poly source per part (`high:` expression), a cage and tangent space (MikkTSpace); valuable for mid-poly, heavy |

Baked outputs are **artifacts** in `.build/textures/` (regenerated) unless
explicitly committed (for expensive bakes), in which case they follow the
lifecycle states above.

## 7. Validation strategy

Deterministic (errors/warnings):
- missing/invalid image paths (sandboxed like `mesh_file`), unsupported formats (PNG/JPEG only);
- resolution over budget; non-power-of-two when the profile requires it;
- unknown archetype or parameter (with suggestions); parameter ranges;
- material referenced but undefined; material defined but unused;
- texel density vs pack/profile target, and spread across parts and across a pack;
- PBR plausibility: base colour outside ~[30, 240] sRGB for dielectrics; metallic neither ~0 nor ~1
  on large areas; emissive without purpose (warnings);
- lifecycle states (section 3) for authored content;
- texture memory estimate vs the profile (for example mobile: total MB).

Perceptual (agent, from renders): colour balance, repetition, seams, stretching,
material mismatch across a pack, whether wear reads, style fit.

## 8. Import / export mapping

| Shapewright | glTF 2.0 export |
|---|---|
| baked base colour (sRGB) | `baseColorTexture` (+ `baseColorFactor` = 1) |
| baked roughness + metallic | `metallicRoughnessTexture` (G = roughness, B = metallic) |
| normal (future bakes) | `normalTexture` (tangent space; engines generate MikkTSpace; export `TANGENT` later) |
| AO (optional) | `occlusionTexture` (R) |
| emissive | `emissiveTexture` / `emissiveFactor` |
| UV0 atlas | `TEXCOORD_0` |
| semantic recipe | `extras.shapewright.material` (archetype + params) so tools can re-derive |
| textures | embedded PNG in the GLB buffer (P8); KTX2/Basis via external `toktx` later |

Import (`sw import`): glTF materials become `archetype: flat` materials with the
factors; images are copied to `textures/` and referenced as `image` layers sampled
through the part's authored UVs.

## 9. Technology candidates

| Need | Candidate | Licence | Decision |
|---|---|---|---|
| image I/O | Pillow | MIT-CMU | **use** (already a dependency) |
| procedural noise | own numpy value/gradient noise (seeded) | — | **use**: deterministic, no dependency |
| atlas baking | own: rasterize each face into UV space, evaluate at interpolated 3D positions | — | **use**: reuses the rasterizer |
| GPU / browser preview | three.js + Playwright (Chromium present) / moderngl | MIT | later, optional |
| texture compression | Basis Universal / `toktx` (KTX2) | Apache-2.0 | later, optional external tool |
| node-graph interchange | MaterialX | Apache-2.0 | later, export only |
| AI texture generation | any external tool | varies | never in core; outputs are files with `generated_by` provenance |

## 10. Security

Image inputs follow the `mesh_file` trust boundary: paths inside the asset or pack
directory; PNG/JPEG only; byte and pixel limits (Pillow's decompression-bomb
guard plus our own `max_texture_size`); never execute or fetch anything.
Generated textures are recorded, not produced, by the core. Resolution is capped
by the profile and `LIMITS` so a typo cannot allocate gigabytes.

## 11. File layout

```
materials/NAME.yaml            reusable material library (optional; packs may also define materials)
packs/NAME.yaml                pack palette and texel density target
assets/X/asset.yaml            assignments, local materials and instances (use:)
assets/X/textures/*.png        authored or externally generated inputs (committed)
assets/X/.build/textures/      baked outputs (reproducible, ignored)
assets/X/export/X.glb          textures embedded
```

## 12. Migration

- Existing materials are `archetype: flat` implicitly. **No asset changes**; exports
  stay texture-free unless a material uses a non-flat archetype or a layer.
- `texel_density` in profiles already exists and becomes the resolution driver.
- The UV lock format stays; shared owners are recommended for arrays.
- The renderer gains a backend seam without changing existing modes (goldens and
  diagnostic renders unchanged).

## 13. Phase 8 scope (the smallest complete loop)

1. Archetypes: `flat`, `wood`, `metal`, `stone`, `painted` with semantic params
   and an `edge_wear` mask; material instances (`use:`).
2. Object-space evaluation baked into the UV0 atlas (base colour + ORM);
   resolution from texel density; deterministic.
3. `image` layer (triplanar projected) for authored or external images, sandboxed.
4. CPU renderer: `textured`, `albedo`, `texel`, `seams` modes; `sw materials` sheet.
5. GLB export with embedded textures and recipe extras; Khronos-valid.
6. Validation: the deterministic checks in section 7 that apply to this scope.
7. A fresh agent textures an asset end to end (FRESH_AGENT_04).

Out of Phase 8: normal-map baking, AO by default, KTX2, a browser backend,
MaterialX export, texture painting.
