"""Every validator must detect a deliberately injected defect (and not fire on clean input)."""

import numpy as np
import pytest

from shapewright.assemble import build
from shapewright.report import SourceError
from shapewright.surface import build_surface
from shapewright.validate.run import run_validation

GOOD = """
shapewright: 0.1
asset: {name: t}
profile: mobile_mid
budget: {triangles: 500}
params: {w: 0.4, h: 0.45}
materials: {wood: {base_color: "#8a5a36"}}
parts:
  top:
    shape: {type: chamfer_box, size: [w, 0.05, w], chamfer: 0.01}
    anchor: top
    position: [0, h, 0]
    material: wood
  leg:
    shape: {type: box, size: [0.05, h - 0.05, 0.05]}
    anchor: bottom
    position: [w / 2 - 0.05, 0, w / 2 - 0.05]
    mirror: [x, z]
    material: wood
checks:
  - {expr: top.max.y, min: 0.44, max: 0.46}
"""


def codes(path):
    a = build(path)
    r = run_validation(a, build_surface(a))
    return r, {i["code"] for i in r["issues"]}


def test_clean_asset_passes(make_asset):
    r, c = codes(make_asset(GOOD))
    assert r["status"] == "PASS", r["issues"]
    assert r["metrics"]["uv_overlap"] == 0


@pytest.mark.parametrize("edit,code", [
    (("position: [0, h, 0]", "position: [0, h + 0.1, 0]"), "ASM_FLOATING_PARTS"),
    (("anchor: bottom\n    position: [w / 2 - 0.05, 0,", "anchor: bottom\n    position: [w / 2 - 0.05, -0.05,"), "ASM_BELOW_GROUND"),
    (("triangles: 500", "triangles: 50"), "BUDGET_TRIANGLES"),
    (("min: 0.44, max: 0.46", "min: 0.5"), "CHECK_FAILED"),
    (("    material: wood\n  leg:", "\n  leg:"), "MAT_UNASSIGNED"),
])
def test_injected_defects_are_reported(make_asset, edit, code):
    text = GOOD.replace(*edit)
    _, c = codes(make_asset(text))
    assert code in c


def test_floating_message_names_the_gap_and_tag_near_parts_warns(make_asset):
    # FRESH_AGENT_09: an agent silenced ASM_FLOATING_PARTS by tagging a mounted sign floating_ok
    lifted = GOOD.replace("position: [0, h, 0]", "position: [0, h + 0.004, 0]")
    r, c = codes(make_asset(lifted))
    issue = next(i for i in r["issues"] if i["code"] == "ASM_FLOATING_PARTS")
    assert "0.004 m from leg" in str(issue) and "floating_ok is only for" in str(issue)
    tagged = lifted.replace("    anchor: top\n", "    anchor: top\n    tags: [floating_ok]\n", 1)
    _, c = codes(make_asset(tagged))
    assert "ASM_FLOATING_PARTS" not in c and "ASM_FLOATING_TAGGED_NEAR" in c
    _, c = codes(make_asset(GOOD.replace("    anchor: top\n", "    anchor: top\n    tags: [floating_ok]\n", 1)))
    assert "ASM_FLOATING_TAG_UNUSED" in c
    far = GOOD.replace("position: [0, h, 0]", "position: [0, h + 1.0, 0]").replace("    anchor: top\n", "    anchor: top\n    tags: [floating_ok]\n", 1)
    _, c = codes(make_asset(far))
    assert "ASM_FLOATING_TAGGED_NEAR" not in c


def test_hidden_part_detected(make_asset):
    text = GOOD.replace("checks:", """  inner:
    shape: {type: box, size: [0.1, 0.02, 0.1]}
    position: [0, h - 0.025, 0]
    material: wood
checks:""")
    _, c = codes(make_asset(text))
    assert "ASM_HIDDEN_PART" in c


def test_part_behind_glass_is_not_hidden(make_asset):
    """A candle inside a lantern's glass is visible: see-through (alpha BLEND) parts don't hide others."""
    text = GOOD.replace('materials: {wood: {base_color: "#8a5a36"}}',
                        'materials: {wood: {base_color: "#8a5a36"}, glass: {base_color: "#ffffff80", alpha_mode: BLEND}}')
    text = text.replace("checks:", """  glass:
    shape: {type: box, size: [0.2, 0.2, 0.2]}
    anchor: bottom
    position: [0, h, 0]
    material: glass
  candle:
    shape: {type: box, size: [0.04, 0.1, 0.04]}
    anchor: bottom
    position: [0, h + 0.02, 0]
    material: wood
checks:""")
    _, c = codes(make_asset(text))
    assert "ASM_HIDDEN_PART" not in c


def test_geometry_defects(make_asset):
    a = build(make_asset(GOOD))
    s = build_surface(a)
    a.parts[0].mesh.F = a.parts[0].mesh.F[1:]  # punch a hole
    a.parts[1].mesh.F = a.parts[1].mesh.F[:, ::-1].copy()  # turn inside out
    c = {i["code"] for i in run_validation(a, s)["issues"]}
    assert {"GEO_OPEN_EDGES", "GEO_INVERTED"} <= c


def test_uv_overlap_detected(make_asset):
    a = build(make_asset(GOOD))
    s = build_surface(a)
    for sp in s.parts.values():
        sp.corner_uv = np.tile(np.array([[0.1, 0.1], [0.9, 0.1], [0.5, 0.9]]), (len(sp.corner_uv), 1, 1))
    c = {i["code"] for i in run_validation(a, s)["issues"]}
    assert "UV_OVERLAP" in c


@pytest.mark.parametrize("edit,code", [
    (("type: chamfer_box", "type: chamfer_bx"), "SRC_SCHEMA"),
    (("material: wood\n  leg", "material: oak\n  leg"), "SRC_REF"),
    (("position: [0, h, 0]", "attach: {to: leg, at: top}"), None),
    (("params: {w: 0.4, h: 0.45}", "params: {w: h, h: w}"), "SRC_CYCLE"),
    (("params: {w: 0.4, h: 0.45}", "params: {w: 0.4, h: __import__('os')}"), "SRC_EXPR"),
])
def test_source_errors_are_structured(make_asset, edit, code):
    text = GOOD.replace(*edit)
    try:
        build(make_asset(text))
    except SourceError as e:
        got = {i.code for i in e.issues}
        assert code is None or code in got, got
        assert all(i.where for i in e.issues)
        return
    assert code is None


def test_attach_cycle(make_asset):
    text = GOOD.replace("position: [0, h, 0]", "attach: {to: leg, at: top}").replace(
        "position: [w / 2 - 0.05, 0, w / 2 - 0.05]", "attach: {to: top, at: bottom}")
    with pytest.raises(SourceError) as e:
        build(make_asset(text))
    assert any(i.code == "SRC_CYCLE" for i in e.value.issues)


def test_typo_gets_suggestion(make_asset):
    with pytest.raises(SourceError) as e:
        build(make_asset(GOOD.replace("anchor: top", "anchr: top")))
    assert any("anchor" in i.hint for i in e.value.issues)


def test_yaml_parse_error_is_reported(make_asset):
    with pytest.raises(SourceError) as e:
        build(make_asset("parts: [unclosed"))
    assert e.value.issues[0].code == "SRC_PARSE"


def test_yaml_flow_comma_trap_gets_a_hint(make_asset):
    with pytest.raises(SourceError) as e:
        build(make_asset("parts:\n  a: {shape: {type: box, size: [0.1, 0.1, 0.1]}, doc: legs, rails: dark}\n"))
    issue = next(i for i in e.value.issues if i.code == "SRC_SCHEMA")
    assert "rails" in issue.message and "quote" in issue.hint


def test_expressions_split_by_yaml_commas_are_rejoined(make_asset):
    # Phase 14: the flow-list comma trap cost 15 failed builds across FA-05..09
    text = GOOD.replace("position: [0, h, 0]", "position: [0, max(h, min(0.3, 0.2)), 0]").replace(
        "shape: {type: chamfer_box, size: [w, 0.05, w], chamfer: 0.01}",
        "shape: {type: chamfer_box, size: [w, 0.05, w], chamfer: max(0.005, min(0.01, 0.02))}")
    r, _ = codes(make_asset(text))
    assert r["status"] == "PASS", r["issues"]
    a = build(make_asset(text))
    top = next(p for p in a.parts if p.name == "top")
    assert abs(top.mesh.bounds()[1][1] - 0.45) < 1e-6
