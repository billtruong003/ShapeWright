# FA13 report: cozy_house kit, new bakery and shared foundation module

Total wall-clock time: about 17 minutes (17:51 to 18:08 UTC), including about 3 minutes of pytest.
Nothing under `shapewright/` was modified. Nothing was committed.

## Task 1: `house_bakery` (SUCCESS)

**Time:** about 7 minutes.

**What it is:** two storeys, 3 x 2 bays, ridge along x. The ground-floor front has a shopfront hatch (left bay), a door with steps (middle) and a tall window (right). The upper front has 3 `house_wall_upper` bays. The back has windows on both floors. The right side has small windows downstairs and upper-wall windows upstairs. The left gable is plain and carries the oven chimney. Floor band and top band, gables, verges and ridge are included, plus `entrance` and `shop_counter` sockets. It uses only existing module assets, placed with the same grid arithmetic as the demo houses: the plan and roof follow the cottage, and the second storey follows the workshop's main block.

**Final validate:**
```
PASS house_bakery  tris 35038/50000  parts 628  size 7.360x9.622x5.541 m  materials 7  uv_overlap 0.0  texel 128.0 px/m (median part)
layers: source=PASS geometry=PASS assembly=PASS budget=PASS intent=PASS surface=PASS style=PASS
```

**Export:** `assets/house_bakery/export/house_bakery.glb` (5.37 MB, 2 meshes, 7 materials, export=PASS). `EXP_VALIDATOR_UNAVAILABLE` appears only as an info item: the optional Khronos validator is not installed.

**Visual fix after looking at the renders:** in the `front` render, the open shop hatch showed the back wall's window straight through it. It read as a second window frame set inside the shopfront. I replaced that one back bay with `house_wall_plain`. I did this with `skip: [0]` on the `ground_back` array plus a new `ground_back_oven` part. I then checked the front, front_right and back_left renders and found nothing else wrong.

**Commands:**
- `./sw validate house_bakery`
- `./sw render house_bakery --mode textured --view front_right`, then the same with `--view front --size 900` and `--view back_left --size 900`
- `./sw render house_wall_shopfront --mode textured --view front_right`, to understand what the hatch looks like on its own
- `./sw export house_bakery`

## Task 2: shared `house_foundation` module (SUCCESS, with one cosmetic caveat)

**Time:** about 10 minutes, including verification and tests.

**The new module:** `assets/house_foundation/asset.yaml` holds footings (front/back and sides), corner nodes (front/back and sides), the ground deck and the steps.
- Params: `nx`, `nz` and `door_bay`. Steps sit at `x0 + (door_bay + 0.5) * bay`.
- Origin is the plan centre at ground level, the same as the houses.
- Its own validate result is PASS: 7164 triangles, 146 parts.
- It has no sockets on purpose. An instanced asset's sockets are copied into the house as `foundation_entrance`, which duplicated the house's own `entrance` socket in my first attempt.

**House changes:** in `house_cottage` and `house_townhouse`, six instance lines each (footing_fb, footing_side, node_fb, node_side, deck/deck_ground, steps) became this single line:
```
foundation: {asset: house_foundation, with: {nx: nx, nz: nz, door_bay: 1}, position: [0, 0, 0]}
```

**Final validate (identical to the baseline before the edit):**
```
PASS house_cottage  tris 24856/30000  parts 390  size 7.365x6.622x5.541 m  materials 7  uv_overlap 0.0  texel 128.0 px/m (median part)
layers: source=PASS geometry=PASS assembly=PASS budget=PASS intent=PASS surface=PASS style=PASS
PASS house_townhouse  tris 33598/45000  parts 595  size 5.505x9.522x7.396 m  materials 7  uv_overlap 0.0  texel 128.0 px/m (median part)
layers: source=PASS geometry=PASS assembly=PASS budget=PASS intent=PASS surface=PASS style=PASS
```

**How I checked that nothing changed:**
- **Per-part stats:** I saved `sw stats --json` before and after and mapped `foundation_*` back to the old names. All 390 cottage parts and all 595 townhouse parts have identical tris, size, centre and material. Bounds and sockets are identical too, once the module's socket was removed.
- **Per-part geometry hashes:** I built the HEAD version of the cottage under a temporary name, then deleted it. All 390 per-part geometry hashes are identical.
- **Renders:** I diffed the `front_right` textured renders before and after, and put the crops side by side. They look the same. The pixel diff is not zero, though: the maximum channel difference is 14 out of 255, on about 9k pixels, limited to the footing, post and step parts. See the caveat below.
- **Tests:** `tests/test_assets.py`, `test_pack.py`, `test_seams.py` and `test_composition.py` all pass: 188 passed. That is after running `python3 tests/update_golden.py` (see below).

**Caveat (framework behaviour, cannot be fixed without a framework change):** nested asset instances are always named `<instance>_<part>`, so the foundation parts are now `foundation_footing_fb_...`. The trim sheet's per-part texture offset is seeded from the part name: `shapewright/trim.py:91`, `seed = zlib.crc32(f"{part.base}:{gi}")`. The stone and timber texture therefore slides slightly along its strip on those 146 parts. Geometry is bit-identical, and the change cannot be seen at normal viewing size. Making it pixel-identical would need a framework change: either an instance option that keeps the child part names, or a texture seed that does not depend on the instance prefix. I did not make that change.

**Golden hashes:** the whole-asset golden hash is taken over the parts in build order. The steps and ground deck now come earlier in that order, so the cottage and townhouse hashes changed even though every part is identical. The signature check passes. `python3 tests/update_golden.py` reported "changed 2 (house_cottage, house_townhouse), new 2 (house_bakery, house_foundation), unchanged 79".

**Commands:**
- `./sw validate` (before and after)
- `./sw stats --json` (before and after)
- `./sw render ... --mode textured --view front_right` (before and after)
- a short Python script with PIL to diff the renders
- a short Python script with `shapewright.assemble.build` to compare per-part hashes
- `python3 tests/update_golden.py`
- `python3 -m pytest -q tests/test_assets.py tests/test_pack.py tests/test_seams.py tests/test_composition.py`

## Files created or changed
- created `assets/house_bakery/asset.yaml`, plus `assets/house_bakery/export/` (GLB and report)
- created `assets/house_foundation/asset.yaml`
- changed `assets/house_cottage/asset.yaml`
- changed `assets/house_townhouse/asset.yaml`
- changed `tests/golden.json`: new hashes for cottage and townhouse, new records for bakery and foundation
- changed nothing in `shapewright/`. `.build/` render output is git-ignored.

## What was confusing or slow
- **`modular_house_pack/README.md` is out of date.** Its "Known limitations" section says "Houses cannot place the module assets ... components cannot nest". All three demo houses do exactly that via `asset:` instances (Phase 19, documented in `docs/ASSET_FORMAT.md`, "Composition"). I trusted the asset files and ASSET_FORMAT over the README. The same README also says "No LODs", but the houses declare `lods: [0.5, 0.25]`.
- **Comments contradict code.** The townhouse header comment says the left wall uses `rotate -90`, but both the cottage and the townhouse use `rotate: [0, 90, 0]` on both side walls. The workshop uses -90 on the left. It makes no visible difference with symmetric plain walls, but it is confusing when copying a pattern. I followed the documented rule (-90) in the bakery.
- **Sockets propagate silently.** A nested asset instance's sockets are copied into the parent with a prefix. This is not mentioned in the "Asset instances" section of ASSET_FORMAT.md, and I found it only by diffing `sw stats --json`.
- **Instance prefixes change textures and the golden hash.** Neither effect is mentioned in the docs. A pure refactor therefore shows up as "geometry changed below the signature tolerance" in `test_assets.py`. The message suggests running `update_golden.py`, which works but does not explain that part order alone causes it.
- **`uv.lock.yaml` goes stale without a warning.** The cottage and townhouse locks are keyed by the old part names. Because the pack uses the shared trim sheet (`atlas:` in the pack), the lock is never read, so no `UV_LOCK_STALE` warning appears. The lock files are dead weight for trim-sheet assets. I left them alone because re-locking would only churn a large generated file.
- **Speed.** Every validate or render of a house takes 20 to 30 seconds, which is the main cost of iterating. `sw brief` was not needed: the three demo houses were enough to copy from.

## Possible framework issues (not changed)
1. The trim-sheet texture offset depends on the full part name, including the instance prefix (`trim.py:91`). Wrapping parts in a sub-assembly changes their texture.
2. The golden whole-asset hash depends on part order, so reordering identical parts counts as a geometry change.
3. A stale `uv.lock.yaml` is silently ignored under trim-sheet texturing. This is arguably by design, but undocumented.
None of these blocked either task.

## Rating
**8 / 10** for ease of understanding and editing the kit. The grid conventions in the pack file header and the three demo houses make new houses quick to assemble. Points off for the stale kit README, the inconsistent rotation comments, and the undocumented side effects of nesting (socket copying, texture offsets).
