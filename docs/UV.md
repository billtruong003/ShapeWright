# UV architecture: stability before texturing

## Problem (v0.1)

All parts were unwrapped and packed together by xatlas on every build. Any
change (a 1 mm edit to one leg) could move every chart in the atlas. Painted
or baked textures would be invalidated by unrelated edits (DESIGN_REVIEW §8).
No textures existed yet, but this had to be solved before they do.

## Alternatives considered

| Option | Verdict |
|---|---|
| Keep global packing, store all UVs in the source | Huge, non-diffable sources; any geometry edit leaves stored UVs stale anyway |
| Global packing with a fixed seed/order | Still global: one part's chart size change shifts neighbours |
| Per-part textures (one material per part) | Explodes draw calls, contradicting mobile budgets |
| **Part-owned regions + deterministic per-part charting + a lock file** | Chosen |

## The model

- **UV owner:** each part instance, or a group of instances that share UVs
  (`uv: {share_instances: true}` on the part: mirrored and arrayed copies reuse
  one set of charts, the standard trick to save texture space).
- **Charts per owner:** xatlas runs on that owner's mesh only, so charts depend
  only on its own geometry (deterministic, tested). Authored UVs (for example
  from `mesh_file`) are kept as the charts instead of re-unwrapping.
- **Seams:** `uv: {seams: regions}` cuts charts along face-region boundaries
  (top/side/bevel/cap). This is a data-driven stand-in for hand-marked seams.
- **Regions:** each owner gets a rectangle of the atlas. Sizes follow 3D
  surface area (uniform texel density) with the chart layout's aspect, packed
  by a deterministic shelf packer with a padding gutter. Charts are fitted
  uniformly (no distortion) into their rectangle.
- **Lock file:** `sw uv ASSET lock` writes `uv.lock.yaml` (region rectangle and
  geometry hash per owner). **Commit it**, like a package lock. While the set of
  owners is unchanged, regions are taken from the lock:

| Change | Effect with a lock | Reported as |
|---|---|---|
| one part's geometry changes | only that part's charts regenerate, inside its own fixed region | `UV_REGION_REGENERATED` (info; lists the parts whose textures need redoing) |
| a part is added, removed or disabled | the layout is recomputed; everything may move | `UV_LOCK_STALE` (warning: re-lock) |
| no lock | regions follow areas; edits can move everything | `UV_UNLOCKED` (info: lock before texturing) |

Tested in `tests/test_uv.py`. With a lock, widening the back slats changes
exactly `back_slat_0` and `back_slat_1`, and their new charts stay inside their
rectangles. Without a lock, the same edit moves the seat's UVs.

## What is source and what is artifact

| | Where | Committed |
|---|---|---|
| UV intent (`share_instances`, `seams`, resolution, padding) | `asset.yaml` | yes |
| Region layout and per-owner geometry hash | `uv.lock.yaml` | yes (generated, reviewed like a lockfile) |
| Charts / per-corner UVs | regenerated each build (deterministic) | no |
| Authored UVs of imported meshes | inside the mesh file | yes (with the file) |

## Costs and limits

- **Utilization is lower** than global packing: rectangles waste space around
  charts. For the chair, the median texel density dropped from ~283 to
  ~250 px/m at 512². This is the price of locality.
- A part whose area grows a lot keeps its old rectangle, so texel density drops
  for that part until re-lock (`UV_TEXEL_DENSITY` warns at a 1.5× spread).
- **Chart identity within a part is not persistent:** if a part's geometry
  changes, its own charts are regenerated from scratch. Transferring charts
  across a geometry edit (projection onto the new surface) is future work, and
  it is what baking-heavy workflows will need.
- `uv.method: atlas` keeps the v0.1 behaviour; `none` disables UVs.
