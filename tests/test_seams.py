"""Phase 20: seam validation. The cases are the MODULAR_HOUSE_PACK_01 findings, reduced to their geometry."""

import numpy as np
import pytest

from shapewright.assemble import build
from shapewright.surface import build_surface
from shapewright.validate.run import run_validation
from shapewright.validate.seams import coplanar_pairs


def _asset(tmp_path, parts: str, name="t"):
    d = tmp_path / name
    d.mkdir()
    (d / "asset.yaml").write_text(f"shapewright: 0.1\nasset: {{name: {name}}}\nmaterials: {{m: {{base_color: '#888888'}}}}\nparts:\n{parts}")
    a = build(d)
    return a, run_validation(a, build_surface(a))


def _codes(report):
    return [i["code"] for i in report["issues"]]


# MHP-01: both X-brace diagonals on the same depth -> their faces coincide where they cross
X_BRACE = """  a: {shape: {type: box, size: [1.6, 0.12, 0.1]}, material: m, rotate: [0, 0, 35], position: [0, 0.6, 0]}
  b: {shape: {type: box, size: [1.6, 0.12, 0.1]}, material: m, rotate: [0, 0, -35], position: [0, 0.6, 0]}
  foot: {shape: {type: box, size: [1.6, 0.1, 0.3]}, material: m, anchor: bottom, position: [0, 0, 0]}
"""


def test_crossing_timbers_on_the_same_depth_z_fight(tmp_path):
    a, rep = _asset(tmp_path, X_BRACE)
    hits = [i for i in rep["issues"] if i["code"] == "SEAM_COPLANAR_OVERLAP"]
    assert hits and hits[0]["severity"] == "warning" and set(hits[0]["data"]["parts"]) == {"a", "b"}
    assert rep["metrics"]["seam_zfight_pairs"] == 1


def test_the_fix_depth_ranks_clears_it(tmp_path):
    ranked = X_BRACE.replace("rotate: [0, 0, -35], position: [0, 0.6, 0]", "rotate: [0, 0, -35], position: [0, 0.6, -0.012]")
    a, rep = _asset(tmp_path, ranked)
    assert "SEAM_COPLANAR_OVERLAP" not in _codes(rep)


def test_overlap_buried_inside_a_third_part_is_not_reported(tmp_path):
    # MHP-01: plank ends that both stop inside a beam share a plane, but nobody can see it
    buried = """  p1: {shape: {type: box, size: [1.0, 0.05, 0.2]}, material: m, anchor: right, position: [0.05, 0.5, 0]}
  p2: {shape: {type: box, size: [1.0, 0.05, 0.2]}, material: m, anchor: left, position: [-0.05, 0.5, 0]}
  beam: {shape: {type: box, size: [0.3, 0.3, 0.4]}, material: m, anchor: bottom, position: [0, 0.35, 0]}
  post: {shape: {type: box, size: [0.2, 0.35, 0.2]}, material: m, anchor: bottom, position: [0, 0, 0]}
"""
    a, rep = _asset(tmp_path, buried)
    rows = coplanar_pairs(a.parts)
    assert any(r["same_facing_hidden_m2"] > 0 for r in rows)  # found, and classified as hidden
    assert "SEAM_COPLANAR_OVERLAP" not in _codes(rep)


def test_face_to_face_contact_is_not_z_fighting_but_is_noted_as_contact_only(tmp_path):
    # MHP-01 stress test: the awning met the wall only face to face (a hairline in renders)
    touching = """  wall: {shape: {type: box, size: [1.0, 1.0, 0.2]}, material: m, anchor: bottom, position: [0, 0, 0]}
  sign: {shape: {type: box, size: [0.4, 0.2, 0.03]}, material: m, anchor: back, position: [0, 0.6, 0.1]}
"""
    a, rep = _asset(tmp_path, touching)
    assert "SEAM_COPLANAR_OVERLAP" not in _codes(rep)
    contact = [i for i in rep["issues"] if i["code"] == "ASM_CONTACT_ONLY"]
    assert contact and "sign" in contact[0]["data"]["parts"]
    embedded = touching.replace("position: [0, 0.6, 0.1]", "position: [0, 0.6, 0.097]")
    a, rep = _asset(tmp_path, embedded, name="t2")
    assert "ASM_CONTACT_ONLY" not in _codes(rep)


def test_flush_coplanar_faces_of_two_parts_z_fight(tmp_path):
    # the kind found in existing benchmark assets (stone_doorway wall/plinth, staircase stringer/newel)
    flush = """  wall: {shape: {type: box, size: [1.0, 1.0, 0.2]}, material: m, anchor: bottom, position: [0, 0, 0]}
  plinth: {shape: {type: box, size: [0.3, 0.4, 0.2]}, material: m, anchor: bottom_left, position: [-0.5, 0, -0.1]}
"""
    a, rep = _asset(tmp_path, flush)
    assert "SEAM_COPLANAR_OVERLAP" in _codes(rep)


def test_jitter_that_inverts_thin_geometry_is_reported(tmp_path):
    # MHP-01: a 1 mm shingle wedge turned inside out under 6 mm of wear jitter (magenta patches); every layer passed.
    # Since Phase 20a jitter is a field of position, so whether a given slab crosses depends on the seed (seed 2 does)
    thin = """  shingle: {shape: {type: box, size: [0.3, 0.001, 0.2]}, material: m, ops: [{type: jitter, amount: 0.006, seed: 2}], anchor: bottom, position: [0, 0, 0]}
"""
    a, rep = _asset(tmp_path, thin)
    hit = [i for i in rep["issues"] if i["code"] == "OP_FACES_INVERTED"]
    assert hit and hit[0]["severity"] == "warning" and "jitter" in hit[0]["msg"]
    thick = thin.replace("size: [0.3, 0.001, 0.2]", "size: [0.3, 0.04, 0.2]")
    a, rep = _asset(tmp_path, thick, name="t2")
    assert "OP_FACES_INVERTED" not in _codes(rep)


@pytest.mark.parametrize("name", ["house_cottage", "house_workshop"])
def test_the_final_kit_houses_are_seam_clean(name):
    from shapewright.assemble import ROOT

    a = build(ROOT / "assets" / name)
    rows = coplanar_pairs(a.parts)
    assert not [r for r in rows if r["same_facing_m2"] >= 5e-5]
    assert np.isfinite(sum(r["back_to_back_m2"] for r in rows))


def test_the_reported_spot_is_a_visible_one(tmp_path):
    # Phase 18b: the first overlap sample was a hidden one (on the ground), so `near (...)` pointed at the floor
    a, rep = _asset(tmp_path, """  wall: {shape: {type: box, size: [1.0, 1.2, 0.2]}, material: m, anchor: bottom, position: [0, 0, 0]}
  plinth: {shape: {type: box, size: [0.3, 0.4, 0.2]}, material: m, anchor: bottom_left, position: [-0.5, 0, -0.1]}
""")
    hit = [i for i in rep["issues"] if i["code"] == "SEAM_COPLANAR_OVERLAP"][0]
    assert hit["data"]["normal"] == [-1.0, 0.0, 0.0] and "facing -x" in hit["msg"]
