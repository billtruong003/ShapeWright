"""Component and family contracts: reuse without knowledge of internals."""

import pytest

from shapewright.assemble import ROOT, build
from shapewright.cli import main
from shapewright.report import SourceError

INSTANCE = """
materials: {{wood: {{}}, dark: {{}}}}
parts:
  top:
    component: plank_top
    with: {{{with_}}}
    materials: {{top: wood, under: dark}}
    anchor: top
    position: [0, 0.75, 0]
  leg:
    shape: {{type: box, size: [0.08, 0.7, 0.08]}}
    anchor: bottom
    position: [0.4, 0, 0.2]
    mirror: [x, z]
    material: dark
"""


def test_component_expands_to_prefixed_parts_with_mapped_materials(make_asset):
    a = build(make_asset(INSTANCE.format(with_="length: 1.0, width: 0.5, planks: 4")))
    names = {p.name for p in a.parts}
    assert {"top_plank_0", "top_plank_3", "top_batten_left", "top_batten_right"} <= names
    assert {p.material for p in a.parts if p.component == "top"} == {"wood", "dark"}
    assert abs(a.bounds()[1][1] - 0.75) < 1e-6  # the group is placed by its anchor


@pytest.mark.parametrize("with_,code", [("lenght: 1.0", "COMPONENT_PRIVATE"), ("plank_w: 0.1", "COMPONENT_PRIVATE")])
def test_only_public_component_params_are_settable(make_asset, with_, code):
    with pytest.raises(SourceError) as e:
        build(make_asset(INSTANCE.format(with_=with_)))
    issue = next(i for i in e.value.issues if i.code == code)
    assert issue.hint


def test_component_parts_cannot_reach_outside(tmp_path):
    d = tmp_path / "a"
    (d / "components").mkdir(parents=True)
    (d / "components" / "leaky.yaml").write_text("""
component: leaky
params: {s: 0.1}
parts:
  p: {shape: {type: box, size: [s, s, s]}, attach: {to: outside_part, at: top}}
""")
    (d / "asset.yaml").write_text("""
parts:
  outside_part: {shape: {type: box, size: [0.2, 0.2, 0.2]}, anchor: bottom}
  x: {component: leaky, anchor: bottom}
""")
    with pytest.raises(SourceError) as e:
        build(d)
    assert any(i.code == "SRC_REF" and "same component" in i.message for i in e.value.issues)


def test_disabled_component_instance(make_asset):
    a = build(make_asset(INSTANCE.format(with_="length: 1.0").replace("    anchor: top\n", "    enabled: false\n    anchor: top\n", 1)))
    assert "top" in a.disabled and not any(p.component for p in a.parts)


CHAIR = ROOT / "assets" / "tavern_chair"


@pytest.mark.parametrize("body,expected", [
    ("params: {slat_gap: 0.2}", "FAMILY_PRIVATE"),                       # private param
    ("parts: {top_rail: null}", "FAMILY_PRIVATE"),                       # structural override
])
def test_family_interface_refuses_private_overrides(make_asset, body, expected):
    with pytest.raises(SourceError) as e:
        build(make_asset(f"extends: {CHAIR}\nasset: {{name: v}}\n{body}\n"))
    assert e.value.issues[0].code == expected and e.value.issues[0].hint


def test_family_checks_are_added_not_replaced(make_asset):
    a = build(make_asset(f"extends: {CHAIR}\nasset: {{name: v}}\nchecks: [{{expr: asset.width, max: 1.0}}]\n"))
    exprs = [c["expr"] for c in a.checks]
    assert "seat.max.y" in exprs and "asset.width" in exprs


def test_base_without_interface_is_flagged(make_asset, tmp_path):
    base = make_asset("parts: {a: {shape: {type: box, size: [0.2, 0.2, 0.2]}, anchor: bottom}}\n", "base")
    child = make_asset(f"extends: {base}\nparts: {{a: {{anchor: bottom}}}}\n", "child")
    a = build(child)
    assert any(i.code == "FAMILY_NO_INTERFACE" for i in a.issues)


def test_family_command_validates_all_members(capsys):
    assert main(["family", "tavern_chair"]) == 0
    out = capsys.readouterr().out
    assert "tavern_chair" in out and "tavern_stool" in out and "interface:" in out


def test_component_instances_can_be_mirrored_and_arrayed(make_asset):
    a = build(make_asset(INSTANCE.format(with_="length: 0.6, width: 0.3, planks: 2")
                         .replace("    position: [0, 0.75, 0]\n", "    position: [0.5, 0.75, 0]\n    mirror: x\n", 1)))
    left = [p for p in a.parts if p.component == "top_left"]
    right = [p for p in a.parts if p.component == "top_right"]
    assert left and right and len(left) == len(right)
    assert {p.name for p in right} >= {"top_right_plank_0", "top_right_batten_left"}
    assert abs(sum(p.mesh.center()[0] for p in left) + sum(p.mesh.center()[0] for p in right)) < 1e-9  # mirror image
    arr = build(make_asset(INSTANCE.format(with_="length: 0.4, width: 0.3, planks: 2, batten_from_end: 0.1")
                           .replace("    position: [0, 0.75, 0]\n", "    position: [0, 0.75, 0]\n    array: {count: 3, offset: [0.5, 0, 0]}\n", 1), "arr"))
    assert {p.component for p in arr.parts if p.component} == {"top_0", "top_1", "top_2"}
