"""Phase 10 contracts (docs/PERFORMANCE.md): the vectorized rasterizers are bit-identical to the
per-triangle loops they replaced, and adversarial sources are rejected before any heavy work."""

import time

import numpy as np
import pytest

from shapewright.assemble import build
from shapewright.render import raster
from shapewright.report import SourceError


def _loop_rasterize(screen, key, normals, front, w, h):
    """The v0.1 reference implementation (one triangle at a time)."""
    depth = np.full((h, w), -np.inf)
    tri = np.full((h, w), -1, dtype=np.int64)
    normal = np.zeros((h, w, 3))
    for t in range(len(screen)):
        (x0, y0), (x1, y1), (x2, y2) = screen[t]
        area = raster.edge(x0, y0, x1, y1, x2, y2)
        if abs(area) < 1e-12:
            continue
        minx, maxx = max(int(np.floor(min(x0, x1, x2))), 0), min(int(np.ceil(max(x0, x1, x2))), w - 1)
        miny, maxy = max(int(np.floor(min(y0, y1, y2))), 0), min(int(np.ceil(max(y0, y1, y2))), h - 1)
        if minx > maxx or miny > maxy:
            continue
        px, py = np.meshgrid(np.arange(minx, maxx + 1) + 0.5, np.arange(miny, maxy + 1) + 0.5)
        b0 = raster.edge(x1, y1, x2, y2, px, py) / area
        b1 = raster.edge(x2, y2, x0, y0, px, py) / area
        b2 = 1.0 - b0 - b1
        inside = (b0 >= 0) & (b1 >= 0) & (b2 >= 0)
        k = b0 * key[t, 0] + b1 * key[t, 1] + b2 * key[t, 2]
        region = depth[miny:maxy + 1, minx:maxx + 1]
        win = inside & (k > region)
        region[win] = k[win]
        tri[miny:maxy + 1, minx:maxx + 1][win] = t
        n = b0[..., None] * normals[t, 0] + b1[..., None] * normals[t, 1] + b2[..., None] * normals[t, 2]
        normal[miny:maxy + 1, minx:maxx + 1][win] = n[win]
    return depth, tri, normal


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_vectorized_rasterizer_matches_the_reference_loop(seed):
    rng = np.random.default_rng(seed)
    w, h, m = 96, 80, 400
    centre = rng.uniform(-10, 100, (m, 1, 2))
    scale = np.where(rng.random((m, 1, 1)) < 0.1, 60.0, 4.0)  # mostly small, some huge (both code paths)
    screen = centre + rng.normal(0, 1, (m, 3, 2)) * scale
    screen[::37] = screen[::37, :1]  # degenerate triangles
    key = rng.uniform(0, 1, (m, 3))
    key[5:9] = key[4]  # exact depth ties: the earlier triangle must win
    screen[5:9] = screen[4]
    normals = rng.normal(0, 1, (m, 3, 3))
    front = rng.random(m) > 0.5
    buf = raster.rasterize(screen, key, normals, front, w, h)
    depth, tri, normal = _loop_rasterize(screen, key, normals, front, w, h)
    assert np.array_equal(buf.tri, tri) and np.array_equal(buf.depth, depth)
    ln = np.linalg.norm(normal, axis=2, keepdims=True)
    assert np.array_equal(buf.normal, np.where(ln > 1e-12, normal / np.maximum(ln, 1e-12), 0))


def test_draw_lines_blends_like_drawing_segments_one_by_one():
    rng = np.random.default_rng(3)
    segs = rng.uniform(-5, 70, (120, 2, 2))
    segs[10:20] = segs[9]  # overlapping identical segments blend repeatedly
    img = rng.random((64, 64, 3))
    ref = img.copy()
    for s in segs:  # reference: the v0.1 per-segment loop
        (x0, y0), (x1, y1) = s
        n = int(max(abs(x1 - x0), abs(y1 - y0))) + 2
        t = np.linspace(0, 1, n)
        xs = np.round(x0 + (x1 - x0) * t - 0.5).astype(int)
        ys = np.round(y0 + (y1 - y0) * t - 0.5).astype(int)
        ok = (xs >= 0) & (xs < 64) & (ys >= 0) & (ys < 64)
        ref[ys[ok], xs[ok]] = ref[ys[ok], xs[ok]] * 0.4 + np.array([0.1, 0.2, 0.3]) * 0.6
    raster.draw_lines(img, segs, (0.1, 0.2, 0.3), alpha=0.6)
    assert np.array_equal(img, ref)


def test_dilate_matches_full_image_rolls():
    from shapewright.bake import _dilate

    rng = np.random.default_rng(4)
    filled = rng.random((40, 50)) > 0.8
    img = rng.random((40, 50, 6)) * filled[..., None]
    ref, f = img.copy(), filled.copy()
    for _ in range(5):  # v0.1 implementation
        acc, cnt = np.zeros_like(ref), np.zeros(f.shape)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            sf = np.roll(f, (dy, dx), (0, 1))
            acc += np.roll(ref, (dy, dx), (0, 1)) * sf[..., None]
            cnt += sf
        grow = (~f) & (cnt > 0)
        ref[grow] = acc[grow] / cnt[grow][:, None]
        f |= grow
    assert np.array_equal(_dilate(img, filled, 5), ref)


ADVERSARIAL = {
    "subdivide": "{shape: {type: sphere, radius: 1, segments: 256, rings: 128, ops: [{type: subdivide, iterations: 3}]}, material: m}",
    "repeat": "{shape: {type: sphere, radius: 1, segments: 128, rings: 64, ops: [{type: repeat, count: 128, offset: [2.1, 0, 0]}]}, material: m}",
    "helix": "{shape: {type: tube, radius: 0.01, path: [{helix: {radius: 0.1, pitch: 0.01, turns: 1000000}}]}, material: m}",
    "arc": "{shape: {type: extrude, depth: 0.1, polygon: [{arc: {radius: 1, segments: 100000000}}]}, material: m}",
    "arrays": "{shape: {type: box, size: [0.1, 0.1, 0.1]}, material: m, array: [{count: 128, offset: [1, 0, 0]}, {count: 128, offset: [0, 1, 0]}]}",
    "nesting": "{shape: " + "{type: boolean, operation: union, base: " * 40 + "{type: box, size: [1, 1, 1]}"
               + ", tools: [{type: box, size: [0.5, 2, 0.5]}]}" * 40 + ", material: m}",
    "combine": "{shape: {type: combine, items: [" + ", ".join(["{type: sphere, radius: 0.1, segments: 256, rings: 128}"] * 40) + "]}, material: m}",
    "lathe": "{shape: {type: lathe, segments: 256, profile: [{line: {from: [0.1, 0], to: [0.1, 10], segments: 2000}}]}, material: m}",
}


@pytest.mark.parametrize("case", sorted(ADVERSARIAL))
def test_resource_limits_reject_before_heavy_work(make_asset, case):
    t0 = time.perf_counter()
    with pytest.raises(SourceError) as e:
        build(make_asset("materials: {m: {color: '#888888'}}\nparts:\n  a: " + ADVERSARIAL[case] + "\n", case))
    assert any(i.code == "SRC_LIMIT" for i in e.value.issues), e.value.issues
    assert time.perf_counter() - t0 < 5


@pytest.mark.parametrize("extra", ["budget: {texture_size: 100000}", "uv: {texel_density: 100000}", "uv: {resolution: 8}"])
def test_texture_settings_are_bounded(make_asset, extra):
    with pytest.raises(SourceError) as e:
        build(make_asset("materials: {m: {color: '#888888'}}\nparts:\n  a: {shape: {type: box, size: [1, 1, 1]}, material: m}\n" + extra + "\n"))
    assert any(i.code == "SRC_LIMIT" for i in e.value.issues)


def test_dense_boolean_leaves_no_degenerate_faces(make_asset):
    a = build(make_asset("materials: {m: {color: '#888888'}}\nparts:\n  a: {shape: {type: sphere, radius: 0.5, segments: 256, rings: 128, "
                         "ops: [{type: noise, amount: 0.04, frequency: 3, seed: 2}, {type: subtract, shape: {type: cylinder, radius: 0.15, "
                         "height: 1.2, segments: 24}}]}, material: m}\n"))
    _, area = a.parts[0].mesh.face_normals()
    size = np.linalg.norm(a.parts[0].mesh.size())
    assert (area >= (size * 1e-5) ** 2).all()
