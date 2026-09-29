"""Phase 9 vocabulary, added from FRESH_AGENT_05 evidence (docs/experiments/FRESH_AGENT_05.md):
point generators, rounded tube corners, strut + origin: keep, rotate_about: anchor, per-instance
arrays, extrude chamfer, cut-split reporting, chart-aware UV regions, wood grain axis."""

import numpy as np
import pytest

from shapewright.assemble import build
from shapewright.expr import FUNCTIONS
from shapewright.report import SourceError
from shapewright.surface import build_surface
from shapewright.validate.run import run_validation

HEAD = "profile: desktop_indie\nmaterials: {m: {color: '#888888'}}\nparts:\n"


def asset(make_asset, parts: str, name="t", extra=""):
    return build(make_asset(HEAD + parts + extra, name))


def codes(a):
    return {i["code"] for i in run_validation(a, build_surface(a))["issues"]}


def test_arc_generator_builds_a_round_arch(make_asset):
    a = asset(make_asset, """
  arch: {shape: {type: extrude, depth: 0.2, polygon: [[0.5, 0], [0.7, 0], {arc: {center: [0, 0], radius: 0.7, from: 0, to: 180, segments: 12}},
          [-0.5, 0], {arc: {center: [0, 0], radius: 0.5, from: 180, to: 0, segments: 12}}]}, anchor: bottom, material: m}
""")
    lo, hi = a.part("arch").bounds
    assert np.allclose(hi - lo, [1.4, 0.7, 0.2], atol=1e-6)
    assert a.part("arch").mesh.volume() == pytest.approx(np.pi * (0.7**2 - 0.5**2) / 2 * 0.2, rel=0.03)


def test_helix_and_rounded_corners_in_tube_paths(make_asset):
    a = asset(make_asset, """
  coil: {shape: {type: tube, radius: 0.01, path: [{helix: {radius: 0.1, pitch: 0.03, turns: 3, axis: y}}]}, material: m}
  pipe: {shape: {type: tube, radius: 0.02, sides: 8, corner_radius: 0.1, corner_segments: 6, path: [[0, 0, 0], [0, 0.5, 0], [0.5, 0.5, 0]]},
         origin: keep, position: [1, 0, 0], material: m}
""")
    lo, hi = a.part("coil").bounds
    assert hi[1] - lo[1] == pytest.approx(0.09 + 0.02, abs=0.01)
    assert hi[0] - lo[0] == pytest.approx(0.22, abs=0.01)
    V = a.part("pipe").mesh.V - [1, 0, 0]
    corner = np.array([0, 0.5, 0])
    assert np.linalg.norm(V - corner, axis=1).min() > 0.02  # the sharp corner is gone
    lo, hi = a.part("pipe").bounds
    assert np.allclose(lo, [1 - 0.02, 0, -0.02], atol=0.005) and np.allclose(hi, [1.5, 0.52, 0.02], atol=0.005)  # kept coordinates


def test_strut_runs_between_measured_points(make_asset):
    a = asset(make_asset, """
  left: {shape: {type: box, size: [0.1, 1, 0.1]}, anchor: bottom, position: [-0.5, 0, 0], material: m}
  right: {shape: {type: box, size: [0.1, 1, 0.1]}, anchor: bottom, position: [0.5, 0, 0], material: m}
  brace:
    measure: {l: {bounds: left}, r: {bounds: right}}
    shape: {type: strut, from: [l.max.x, 0.1, 0], to: [r.min.x, 0.9, 0], size: [0.06, 0.05]}
    material: m
""")
    b = a.part("brace").mesh
    d = np.array([0.9, 0.8, 0]) / np.linalg.norm([0.9, 0.8, 0])
    t = (b.V - [-0.45, 0.1, 0]) @ d
    assert t.min() == pytest.approx(0, abs=1e-6) and t.max() == pytest.approx(np.hypot(0.9, 0.8), abs=1e-6)
    assert b.V[:, 2].max() == pytest.approx(0.025, abs=1e-6)  # depth lies along z (the wall normal)
    assert "ASM_FLOATING_PARTS" not in codes(a)


def test_rotate_about_anchor_keeps_the_base_in_place(make_asset):
    a = asset(make_asset, """
  leaf: {shape: {type: box, size: [0.02, 0.3, 0.1]}, anchor: bottom, rotate_about: anchor, rotate: [0, 0, 40], position: [0, 0.2, 0], material: m}
  plain: {shape: {type: box, size: [0.02, 0.3, 0.1]}, anchor: bottom, rotate: [0, 0, 40], position: [1, 0.2, 0], material: m}
""")
    lv = a.part("leaf").mesh.V
    base = lv[np.argsort(lv[:, 1])[:4]].mean(0)  # the four lowest corners: the old bottom face
    assert np.allclose(base, [0, 0.2, 0], atol=0.02)
    assert a.part("plain").bounds[0][1] == pytest.approx(0.2)  # default: the rotated bbox bottom is placed


def test_array_each_skip_start_and_nesting(make_asset):
    a = asset(make_asset, """
  leaf:
    shape: {type: box, size: [0.02, 0.2, 0.06]}
    anchor: bottom
    position: [0.05, 0, 0]
    material: m
    array: {count: 6, radial: y, start: 15, each: {rotate: [0, 0, "-20 - 30 * i / (n - 1)"], scale: [1, "0.8 + 0.4 * rand(i)", 1]}, skip: [3]}
  shingle:
    shape: {type: box, size: [0.2, 0.02, 0.1]}
    position: [2, 0, 0]
    material: m
    array: [{count: 4, offset: [0.2, 0, 0]}, {count: 3, offset: [0, 0.05, 0.08], each: {translate: ["(i % 2) * 0.1", 0, 0]}}]
""")
    names = sorted(p.name for p in a.parts if p.base == "leaf")
    assert names == ["leaf_0", "leaf_1", "leaf_2", "leaf_4", "leaf_5"]
    tilts = [a.part(f"leaf_{i}").bounds[1][1] for i in (0, 5)]
    assert tilts[0] != pytest.approx(tilts[1], abs=1e-3)  # instances differ
    sh = [p for p in a.parts if p.base == "shingle"]
    assert len(sh) == 12 and a.part("shingle_0_1") is not None
    x0 = a.part("shingle_0_0").bounds[0][0]
    assert a.part("shingle_0_1").bounds[0][0] == pytest.approx(x0 + 0.1)  # odd rows offset by half a shingle
    assert a.part("shingle_0_2").bounds[0][0] == pytest.approx(x0)
    assert FUNCTIONS["rand"](3) == FUNCTIONS["rand"](3) and 0 <= FUNCTIONS["rand"](3) < 1


def test_extrude_chamfer_on_convex_outlines(make_asset):
    a = asset(make_asset, """
  stone: {shape: {type: extrude, depth: 0.3, chamfer: 0.02, polygon: [[-0.1, 0], [0.1, 0], [0.14, 0.2], [-0.14, 0.2]]}, material: m}
""")
    lo, hi = a.part("stone").bounds
    assert np.allclose(hi - lo, [0.28, 0.2, 0.3], atol=1e-6)
    assert a.part("stone").mesh.n_tris > 12
    with pytest.raises(SourceError) as e:
        asset(make_asset, "  l: {shape: {type: extrude, depth: 0.1, chamfer: 0.01, polygon: [[0, 0], [1, 0], [1, 1], [0.5, 0.2], [0, 1]]}, material: m}\n", "bad")
    assert any("convex" in i.message for i in e.value.issues)


def test_cut_split_is_reported_but_intended_pieces_are_not(make_asset):
    a = asset(make_asset, """
  board: {shape: {type: box, size: [1, 0.1, 0.2], ops: [{type: subtract, shape: {type: box, size: [0.05, 0.5, 0.5]}}]}, material: m}
  pegs: {shape: {type: combine, items: [{type: box, size: [0.05, 0.05, 0.05]}, {type: box, size: [0.05, 0.05, 0.05], translate: [0.2, 0, 0]}]},
         position: [0, 0.3, 0], material: m}
""")
    issues = run_validation(a, build_surface(a))["issues"]
    split = [i for i in issues if i["code"] == "GEO_CUT_SPLIT"]
    assert len(split) == 1 and "board" in split[0]["where"]
    assert all(i["severity"] == "info" for i in issues if i["code"] == "GEO_PART_FRAGMENTED")


def test_ring_parts_get_the_same_texel_density(make_asset):
    a = asset(make_asset, """
  drum: {shape: {type: cylinder, radius: 0.3, height: 0.6, segments: 16}, anchor: bottom, material: m}
  hoop: {shape: {type: ring, radius: 0.31, thickness: 0.02, height: 0.04, segments: 16}, position: [0, 0.3, 0], material: m}
""")
    assert "UV_TEXEL_DENSITY" not in codes(a)


def test_wood_grain_axis(make_asset):
    from shapewright.bake import bake

    def grain(axis):
        p = make_asset("profile: desktop_indie\nmaterials: {oak: {archetype: wood, grain_strength: 0.9, grain_scale: 0.01, "
                       f"grain_axis: {axis}}}}}\nparts:\n  top: {{shape: {{type: box, size: [0.6, 0.05, 0.3]}}, material: oak}}\n", axis)
        a = build(p)
        return bake(a, build_surface(a)).base

    assert not np.array_equal(grain("auto"), grain("y"))
    with pytest.raises(SourceError):
        grain("diagonal")


def test_point_generator_errors_are_explained(make_asset):
    with pytest.raises(SourceError) as e:
        asset(make_asset, "  a: {shape: {type: tube, radius: 0.01, path: [[0, 0, 0], {arcc: {radius: 1}}]}, material: m}\n")
    assert any("arc" in (i.hint or "") for i in e.value.issues)
