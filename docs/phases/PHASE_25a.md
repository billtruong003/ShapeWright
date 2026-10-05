# Phase 25a: presentation renders (track R)

Branch `phase/25a-render`, stacked on `phase/19b-houses`. Plan: docs/REMAINING_WORK.md §6b (R1–R6).

**Verdict: PARTIAL.** Everything shipped and is deterministic, and the images look much better (evidence below).
Two gates are not met: the speed budget (25 s instead of 10 s for a 33k-triangle house at 1024 px) and the owner's
judgement, which has not been given yet.

## What shipped

| task | result |
|---|---|
| R1 `beauty` mode | `shapewright/render/beauty.py`: key/fill/rim lights in linear space, an orthographic shadow map for the key light (3x3 PCF, normal-offset bias), screen-space AO times the baked ORM occlusion, a shadow-catcher ground with a blurred top-down contact shadow that fades out (no ground edge), ACES tone mapping, 2x2 supersampling. `sw render NAME --mode beauty`, `views.render(..., "beauty")` |
| R2 turntable | `sw render NAME --turntable N` → `renders/turntable.gif` (+ `.mp4` when `imageio-ffmpeg` is installed; not installed here, so not verified). One framing for every frame, so the asset does not jump |
| R3 presentation sheet | `sw render NAME --present [--part P ...]` → `renders/present.png`: 4 beauty views, 4 close-ups (the most detailed parts, or `--part`), wireframe, silhouette, back 3/4, palette, counts |
| R4 images | `tools/site/readme_images.py` regenerates `docs/images/readme_houses.png`, `readme_gallery.png`, `readme_turntable.gif`; docs gallery posters are beauty renders; the bundle gets `renders/<house>_<view>_beauty.png` (and the bundle script writes them from now on) |
| R5 MCP and docs | MCP `render(mode="beauty")`; `website/use-cases/presentation.md` (every block runs in the doc tests); README feature row; llms.txt regenerated |
| R6 scale reference | `--scale-ref` on orthographic side views: a 1.75 m figure beside the asset and overall width/height dimension lines; off by default |

Rasterizing for beauty uses its own depth resolve (`beauty._raster`: two scatter reductions instead of a 3-key
sort, same winner rule). The shadow map is the heaviest overdraw; this cut the cottage from 49.5 s to 25 s. The
inspection rasterizer is unchanged, so inspection renders stay byte-identical.

## Evidence

- `phase25a/evidence/{barrel,treasure_chest,house_cottage,house_townhouse}_textured_vs_beauty.png`: inspection
  `textured` (left) next to `beauty` (right)
- `treasure_chest_present.png`, `treasure_chest_turntable.gif`, `scale_ref.png` (a chair and the cottage next to the figure)
- README images: `docs/images/readme_*.png`

Timings (this container, 1024 px unless noted):

| asset | triangles | textured (inspection) | beauty |
|---|---|---|---|
| treasure_chest (512 px) | 1,464 | 1.4 s | 6.5 s |
| house_cottage | 24,856 | 11.3 s | 25.2 s |
| house_townhouse | 33,598 | 11.5 s | 25.0 s |

## Gate

| gate | result |
|---|---|
| inspection modes unchanged | **met**: their code path is untouched (beauty dispatches before it, `scale_ref` defaults off); goldens and render tests unchanged |
| `beauty` deterministic (same bytes twice) | **met** (`test_beauty_is_deterministic_and_tone_mapped`, turntable frames compared too) |
| under 10 s for a 33k-tri house at 1024 px | **not met**: 25 s. The inspection `textured` render of the same house already takes 11.5 s; the remaining time is the 2048² main raster (as in inspection), the shadow map and SSAO. A faster rasterizer is the fix and would help inspection too; recorded for later instead of widening this phase |
| before/after for 4 assets, judged better by the owner | **met with exceptions**: the 4 side-by-sides exist; the owner has not judged them yet |

## Not done

- MP4 output is not verified (`imageio-ffmpeg` is not installed here; the GIF is the deliverable).
