"""Spatial relationships must survive edits the author did not anticipate.

In v0.1 the chair's rail/slat/stretcher placement was hand-derived arithmetic
that silently broke when lean, splay or construction changed. With `measure:`
queries, relationships follow the real geometry. These tests perturb the chair
through its public interface and assert structural validity, not pixels.
"""

import numpy as np
import pytest

from shapewright.assemble import ROOT, build
from shapewright.report import SourceError
from shapewright.surface import build_surface
from shapewright.validate.run import run_validation

CHAIR = ROOT / "assets" / "tavern_chair"


def variant(make_asset, **params):
    body = "\n".join(f"  {k}: {v}" for k, v in params.items())
    return make_asset(f"shapewright: 0.1\nextends: {CHAIR}\nasset: {{name: v}}\nparams:\n{body}\n")


@pytest.mark.parametrize("params", [
    {"lean": 0.0}, {"lean": 0.15}, {"rear_splay": 6}, {"leg": 0.095, "seat_width": 0.58},
    {"seat_depth": 0.34, "lean": 0.12}, {"has_back": "false"},
])
def test_chair_stays_structurally_valid_under_interface_changes(make_asset, params):
    a = build(variant(make_asset, **params))
    r = run_validation(a, build_surface(a))
    errors = [i for i in r["issues"] if i["severity"] == "error"]
    assert not errors, errors


@pytest.mark.parametrize("lean", [0.0, 0.08, 0.16])
def test_rail_follows_the_post(make_asset, lean):
    a = build(variant(make_asset, lean=lean))
    rail, post = a.part("top_rail"), a.part("rear_leg_right")
    y = rail.mesh.center()[1]
    from shapewright import backend

    pts = backend.section_points(post.mesh, 1, y)
    post_z = (pts[:, 2].min() + pts[:, 2].max()) / 2
    assert abs(rail.mesh.center()[2] - post_z) < 0.01


def test_stretcher_length_tracks_leg_gap(make_asset):
    narrow = build(variant(make_asset, seat_width=0.40)).part("front_stretcher").mesh.size()[0]
    wide = build(variant(make_asset, seat_width=0.58)).part("front_stretcher").mesh.size()[0]
    assert np.isclose(wide - narrow, 0.18, atol=0.02)


def test_failed_query_names_part_and_plane(make_asset):
    text = (CHAIR / "asset.yaml").read_text().replace("at: rail_y}", "at: rail_y + 1}")
    p = make_asset(text)
    with pytest.raises(SourceError) as e:
        build(p)
    issue = next(i for i in e.value.issues if i.code == "MEASURE_FAILED")
    assert "rear_leg_right" in issue.message and "misses" in issue.message


def test_reference_to_disabled_part_is_explained(make_asset):
    text = (CHAIR / "asset.yaml").read_text().replace("  front_leg:\n", "  front_leg:\n    enabled: false\n")
    with pytest.raises(SourceError) as e:
        build(make_asset(text))
    msgs = [i for i in e.value.issues if i.code == "SRC_REF"]
    assert msgs and all("disabled" in i.message for i in msgs)
    assert any("enabled" in i.hint for i in msgs)


def test_stool_is_a_pure_parameter_variant():
    a = build(ROOT / "assets" / "tavern_stool")
    assert {"top_rail", "back_slat"} <= set(a.disabled)
    assert a.bounds()[1][1] < 0.5


def test_measure_on_an_unknown_part_is_a_readable_error(make_asset):
    # FA-10 B: measuring 'leg_right_front' (the instance is leg_front_right) crashed with an AttributeError
    from shapewright.assemble import build
    from shapewright.report import SourceError

    text = """shapewright: 0.1
asset: {name: t}
materials: {m: {color: "#888888"}}
parts:
  leg: {shape: {type: box, size: [0.05, 0.4, 0.05]}, anchor: bottom, position: [0.2, 0, 0.2], mirror: [x, z], material: m}
  top:
    measure: {s: {section: leg_right_front, axis: y, at: 0.2}}
    shape: {type: box, size: [0.5, 0.04, 0.5]}
    position: [0, 0.42, s.center.z]
    material: m
"""
    with pytest.raises(SourceError) as e:
        build(make_asset(text))
    issue = next(i for i in e.value.issues if i.code == "MEASURE_FAILED")
    assert "leg_right_front" in issue.message and "leg_front_right" in issue.message
