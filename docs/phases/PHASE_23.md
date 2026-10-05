# Phase 23: character surface (track G, G2)

Branch `phase/22-organic` (stacked; G1 and G2 share the kernel). Plan: docs/REMAINING_WORK.md §9 (G2).

**Verdict: PARTIAL.** Painted regions, procedural decals and the reference image on the review sheet shipped and
work on all three creatures. The fox now reads as a fox in a hoodie with a face, and the face reads from the front
at 256 px. The gate's rubric against the owner's concept could not be scored, because the concept image is not in the
repository. Toon presets were not built.

## What shipped

| piece | where | notes |
|---|---|---|
| `rest` vertex attribute | `mesh.py` schema | the position where the generator made the vertex; transforms keep it, so painting follows the part when it moves or is mirrored |
| painted regions (`paint: true`, default) | `organic.paint_spec`, `organic.region_materials`, `bake.py` | per texel, the material of the item whose own surface is there; carved surfaces take the subtraction's material (else the part's); the part exports as ONE material (one draw call) |
| decals `eye`, `disc`, `smile` | `organic.decal_masks`, `bake.py` | projected along `toward` near `at`, only on surfaces facing it; anti-aliased over one texel; `mirror: x`; glossy (roughness 0.3) |
| `reference: concept/x.png` | `source.py`, `render/views.py` | the sheet shows the concept beside the textured front view |
| `MAT_UNUSED` | `checks.py` | knows painted materials are used |

Found on the way:
- **Carved surfaces mislabelled.** Region lookup by nearest |distance| ignored subtractions: the mushroom's eyes, inside the carved hollow under the cap, were painted cap red. A union item's surface now only counts where no later subtraction removed it.
- **Decals over geometry for small details.** As geometry, spots and eyes were a few triangles wide (sharp pyramids). As decals they are crisp at any budget. The mushroom now uses decals for spots and face; its triangle count is spent on the forms.

## Gates

| gate | target | measured | met |
|---|---|---|---|
| region edges independent of triangles | — | crisp at 3–4 k triangles (`phase23/evidence/creatures_painted.png`; jagged in `phase22/evidence/creatures.png`) | yes |
| the face reads from the front at 256 px | — | `phase23/evidence/fox_front_256.png`: eyes with highlights, nose, smile | yes |
| reference next to the matching view | — | `phase23/evidence/fox_sheet_with_reference.png` (a placeholder concept) | yes |
| fox vs the concept, rubric (silhouette, proportions, palette, face, details) | scored with evidence | **not scored**: the concept image is not in the repository | **no** |
| toon presets | — | not built: flat materials plus an engine's toon shader cover it for now | **no** |
| one draw call per painted part | — | fox, slime, mushroom: 1 material each (were 4, 3, 4) | yes |

Tests: `tests/test_organic.py`:
- `test_regions_and_decals_are_painted_per_texel`: one material in the file, decal and region texels in the atlas, the decal visible in the front render;
- `test_reference_image_goes_on_the_sheet`.

## Not done

- **Rubric:** the owner adds `concept/fox.png` to `assets/chibi_fox` and sets `reference:`; then the rubric can be scored. 0.25 points are left for it.
- **Toon presets** (ramp-shaded base colours, outline hints in extras).
- **Image decals** (a PNG projected like the procedural ones). The procedural kinds cover eyes, spots and mouths.
- **Soft region blending:** edges are crisp at texel resolution, with no gradient option yet.
