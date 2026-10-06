# Phase 25b: toon showcase (presentation)

Branch `phase/25b-toon`. Asked by the owner after tracks F and G: show the finished assets in toon shading with an
outline that stays continuous at hard edges and split normals and that wraps the silhouette, plus an honest
statement of what the framework is good and bad at.

**Verdict: PASS.** Toon shading exists in both renderers:
- **CPU renderer:** cel shading with post-process outlines, for images.
- **Workbench 3D view:** three.js toon materials with an inverted-hull outline pushed along smoothed normals, for live viewing (rigged characters included).

Both outlines are closed around the silhouette and do not tear at hard corners. The README and the docs now say plainly that human characters are a weak point and that low-poly props, kits and re-texturing are the strength.

## What shipped

| piece | where | how the outline stays continuous |
|---|---|---|
| mode `toon` (CPU) | `render/views.py` (`_toon_light`, `_toon_outline`) | outlines are found on the rendered buffers, per pixel: silhouette (coverage edge), depth steps, creases over 60°; they do not depend on the mesh's vertex splits, so hard edges cannot break them; drawn 3 px at 2× supersampling |
| toon + outline (three.js) | `workbench/viewer.js` (`toonMaterial`, `outlineHull`), mode "toon + outline" | an inverted hull (back faces only) pushed along **smoothed** normals: every vertex at one position gets the area-weighted average normal of all faces around that position, so the separate vertices of a hard edge or a UV seam move together and the hull stays closed; the push scales with view depth for an even width on screen; on skinned meshes the hull is a SkinnedMesh bound to the same skeleton |
| `tools/site/toon_showcase.py` | `docs/images/toon_showcase.png` | 12 finished assets: 3 houses, 5 props, 3 creatures, a wheelbarrow |
| MCP `render` mode `toon` | `mcp_server.py` | |
| docs | README "Where it is strong, and where it is not"; website Presentation (toon) and Characters (people are a weak point) | |

Found on the way (BUG): the workbench's "material colours" view built a material array for meshes without
material groups, which three.js draws as nothing. The toon view hit the same thing first; both now return one
material per mesh unless the mesh has groups.

## Gates

| gate | measured | met |
|---|---|---|
| the outline wraps the silhouette, no gaps at sharp corners (CPU) | `tests/test_toon.py`: ≥ 97 % of silhouette border pixels have outline within 2 px, on the crate (hard box edges) and the fox (organic, decals) | yes |
| toon bands, not smooth shading | fewer distinct tones than the `material` mode (test) | yes |
| the outline stays closed at hard edges in three.js | headless Chromium: the crate's hull is closed at every box corner; the fox's hull is closed at rest and mid-walk (`phase25b/evidence/workbench_toon_*.png`) | yes |
| showcase of finished products | `docs/images/toon_showcase.png` (README, website) | yes |
| strengths and weaknesses documented | README, website pages | yes |

## Limits

- **Patchy bands on organic forms:** the cel bands follow the decimated normals, so the slime and the fox's sides show some uneven band edges. Smoothing the organic normals before shading would help.
- **Inner lines in three.js:** the inverted hull draws the silhouette and outer contours only. The creases inside the form (window frames, planks) come from the CPU mode's post-process. A screen-space edge pass in three.js would add them live; it was not needed for the showcase.
