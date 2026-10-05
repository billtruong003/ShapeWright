# Phase 22: native organic kernel (track G, G1)

Branch `phase/22-organic`. Plan: docs/REMAINING_WORK.md §9 (G1), after the G0 spike (docs/phases/G0_SPIKE.md).

**Verdict: PASS with one design change.** A new shape, `blend`, meshes SDF primitives into one closed part. The
chibi fox, a slime and a mushroom creature are each one watertight, consistently wound mesh that passes all 8
validation layers within budget, builds in 0.9–3.3 s and is deterministic on Linux. Windows is checked by CI against
the tolerant signature. Colour-region edges are jagged and small features are coarse at these budgets (see "What is
not good yet").

## What shipped

| piece | where | notes |
|---|---|---|
| SDF items: sphere, ellipsoid, capsule, cone (rounded), box (rounded), torus | `shapewright/organic.py` | each with `mirror`, `shell`, `rotate`, `blend`, `material` |
| ordered smooth union / subtraction / intersection | `organic.combine` | polynomial smooth min; an item's `blend` overrides the shape's `radius` |
| grid field, each item evaluated only inside its own box | `organic.grid_field` | outside its box an item counts as far away, which leaves the surface unchanged |
| marching tetrahedra | `organic.marching_tets` | the Kuhn split, so neighbouring cubes agree; triangles wound from inside to outside corners (exact: the field is linear in a tetrahedron); vertices within 1 µm welded |
| decimation to `triangles` with defect control | `organic.mesh_blend` | quadric decimation, retried at 6 ratios to avoid pinched edges and folds; Manifold's topology-safe simplification when that fits the budget; collinear needles collapsed |
| `ground: true` | | cuts the form flat at y = 0 for standing creatures |
| `GEO_BLEND_PINCHED` | `ops/organic.py` | the budget's edges are longer than a gap in the design; says where and what to do |
| organic shading default | `assemble.py` | `blend` parts shade smooth with creases above 75° (fully smooth flipped normals at knife-edge rims) |
| `backend.simplify_closed` | `backend.py` | Manifold `simplify(tolerance)` |
| three library assets | `assets/chibi_fox`, `assets/creature_slime`, `assets/creature_mushroom` | |

**Design change from the plan.** The plan had a `blend: {group: body}` key on parts, so several parts would become one mesh.
It became a shape, `{type: blend, items: [...]}`, for three reasons:
- **One result.** The result is one part, and a shape is how Shapewright makes one part from a definition.
- **The pipeline applies unchanged.** Transforms, materials, ops, measure, checks and goldens all work without special cases.
- **Clear order.** The order of subtraction is explicit in one list.

Several organic parts (a body and a separate hat) remain several `blend` parts.

## Found on the way

Each finding is recorded because G2–G5 build on this kernel.

1. **Orientation.** The spike oriented triangles by the field gradient at their centre. That fails across thin and carved shells: the far side's gradient points the other way. Winding is now exact, from the tetrahedron's own inside and outside corners.
2. **Degenerate triangles.** Dropping zero-area triangles opened holes. They come from the surface passing through a grid point. Welding the coincident vertices instead closes the mesh.
3. **Pinches.** Quadric decimation (fast-simplification) pinches narrow crevices: an eye in a socket, a thin bowl left under a cap. The retries and the topology-safe fallback cannot fix a gap narrower than the budget's edges. Two attempts to repair it automatically made it worse:
   - splitting non-manifold vertices;
   - dropping two-sided sheets.

   So the kernel reports it (`GEO_BLEND_PINCHED`, with the place), and the design changes. Both creatures needed exactly that:
   - the slime's eyes became domes instead of sockets;
   - the mushroom's hollow was carved deeper, so no thin bowl remains.
4. **Fold test.** Folds are counted by edge neighbours, not by corner normals: at a cone tip (an ear) the corner normals cancel.
5. **Shading.** Fully smooth shading gave `NRM_FLIPPED` at knife-edge rims (the cap's lip). The default is now `auto` with a 75° crease angle.

## Gates

| gate | target | measured | met |
|---|---|---|---|
| one watertight mesh | each of 3 | fox, slime, mushroom: watertight, winding consistent, every edge shared by 2 faces | yes |
| validation | no errors | all three PASS (8 layers), no warnings | yes |
| within budget | — | fox 3978 / 6000, slime 3376 / 4000, mushroom 3510 / 4000 | yes |
| no slivers | below `GEO_SLIVER_TRIS` (25 %) | 2.8 %, 3.4 %, 5.8 % | yes |
| deterministic | — | the same hash on rebuild (test); goldens recorded on Linux | yes (Windows: CI) |
| under 10 s each | < 10 s | 2.0 s, 0.9 s, 3.3 s | yes |

Evidence: `phase22/evidence/creatures.png` (material views), `fox_sheet.png`, `mushroom_sheet.png`. Tests: `tests/test_organic.py` (9).

## What is not good yet

- **Colour regions follow faces:** the fox's hoodie/fur edge is jagged. Phase 23 (G2) paints regions into the texture.
- **Small features at low budgets** (mushroom spots, slime eyes) are a few triangles wide and look faceted. Raising `triangles` helps. An adaptive decimation that keeps small features is in the backlog.
- **No face detail:** there are no eyes or mouth on the fox. Projected decals are G2.
- **Long slivers** remain on the mushroom's stem (well under the threshold).
