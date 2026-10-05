# G0 spike: a native organic mesh (track G)

Plan: docs/REMAINING_WORK.md §9, G0. Script: `tools/experiments/sdf_spike.py OUT_DIR`.

**Verdict: GO for G1, with three changes to the plan (below).** A chibi fox in a hoodie built from 11 SDF primitives
is one watertight, consistently wound mesh of 6 k triangles in under 5 s. It uses no new dependency and no Blender.
It reads as a fox in a hoodie. The face and the colour boundaries are not game quality yet; G2's work is what fixes them.

The owner's fox-hoodie concept image is not in the repository, so the side-by-side comparison was not possible.
The fox was modelled from the plan's description (body, head, cheeks, ears, tail, a hood).

## What was built

- **Field.**
  - 11 primitives: 8 ellipsoids and 3 rounded cones. Arms, ears, legs and cheeks are mirrored by folding x, so each pair is written once.
  - Combined by a polynomial smooth union (radius 35 mm).
  - The hood has a smooth subtraction that opens it at the front.
- **Mesher.** Marching tetrahedra, in about 60 lines of numpy:
  - each grid cube is split into 6 tetrahedra around its main diagonal (the Kuhn split), so neighbouring cubes agree and the surface is closed without the 256-case tables of marching cubes;
  - vertices are shared by grid-edge keys;
  - triangles are oriented along the field gradient.
- **Then the existing pipeline:**
  - `backend.simplify` (fast-simplification) to the budget;
  - `collapse_needles`;
  - `backend.unwrap_charts` (xatlas).
- **Regions.** Each face takes the region of its nearest primitive: hoodie, fur, white or black. The spike writes one OBJ per region and an `asset.yaml`, so `sw validate` and `sw render` review it like any asset.

## Measurements

| measure | value |
|---|---|
| grid | 91 × 140 × 107 at 8 mm (1.36 M samples) |
| raw triangles → after decimation | 191 880 → 5 984 |
| watertight / winding consistent (whole mesh) | yes / yes |
| time: field, mesh, decimate, UV, total | 2.3 s, 1.7 s, 0.7 s, 0.3 s, **4.9 s** |
| numbers the model needed | 81, for 11 primitives (one blend radius, one subtraction) |
| height | 1.04 m |
| UV overlap | 0.0 |
| validation | 2 × `NRM_FLIPPED` after decimation; the rest are expected for the split-region spike (open edges between regions) |

Evidence: `g0/evidence/fox_sheet.png` (clay views, regions, wire, UV), `g0/evidence/fox_front_textured.png`, `g0/evidence/spike.json`.

## What looked wrong, and what it changes in G1/G2

1. **Ragged colour boundaries.** Colour per face (nearest primitive) gives jagged edges on a 6 k mesh, worst around the muzzle.
   - **Change:** regions are painted into the texture per texel (nearest primitive, with a soft blend), not by splitting faces. The mesh stays one part.
   - This belongs in G1's kernel (region masks) and G2 (palettes).
2. **The hood swallows the head.** A union of hood and head shows the bigger shape, so the face only shows where the hood is carved.
   - **Change:** smooth subtraction and ordered groups belong in G1, not later; the spike needed them.
   - Agents also need a "shell" primitive: an ellipsoid with a thickness and an opening.
3. **Two faces flip during decimation** (`NRM_FLIPPED`).
   - **Change:** G1 checks normals after decimation against the field gradient and re-decimates with a milder ratio, or collapses the folded faces, before handing the mesh on.
4. **No face.** Eyes and mouth need G2's projected decals. Without them the figure reads as a mascot, not a character.
5. **Proportions.** A chibi wants a larger head (about 45 % of the height; here 35 %). That is a parameter, not a kernel problem.

## Decisions for the plan

- **The own mesher is enough.** It meshes 1.4 M samples in 1.7 s, so scikit-image is not needed.
- **The field costs most.** Evaluating 11 primitives at 1.4 M points takes 2.3 s. G1 should evaluate per primitive only inside its bounding box (plus the blend radius); that should cut the time several-fold.
- **G1 gate.** The plan's "under 10 s each" is realistic at 8 mm.
