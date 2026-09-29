"""Pack review (`sw pack`) and nested-expression translate (found while building the blacksmith pack)."""

from shapewright.assemble import build
from shapewright.cli import main
from shapewright.pack import pack_report, run_pack

BOX = "parts:\n  a:\n    shape: {type: box, size: [0.2, 0.2, 0.2]}\n    anchor: bottom\n    material: m\n"


def test_combine_item_translate_is_kept(make_asset):
    p = make_asset("parts:\n  a:\n    shape: {type: combine, items: [{type: box, size: [0.2, 0.2, 0.2]}, "
                   "{type: box, size: [0.1, 0.1, 0.1], translate: [0.5, 0, 0]}]}\n    anchor: bottom\n")
    a = build(p)
    assert abs(a.parts[0].mesh.size()[0] - 0.65) < 1e-6  # -0.1 .. 0.5 + 0.05: the offset survived


def test_boolean_tool_translate_is_kept(make_asset):
    p = make_asset("parts:\n  a:\n    shape: {type: boolean, operation: union, base: {type: box, size: [0.2, 0.2, 0.2]}, "
                   "tools: [{type: box, size: [0.1, 0.1, 0.1], translate: [0, 0.12, 0]}]}\n    anchor: bottom\n")
    assert abs(build(p).parts[0].mesh.size()[1] - 0.27) < 1e-6


def test_pack_reports_material_drift_and_writes_sheet(make_asset, tmp_path, capsys):
    a = make_asset(BOX + "materials: {m: {base_color: '#ff0000'}}\n", "a")
    b = make_asset(BOX + "materials: {m: {base_color: '#00ff00'}}\n", "b")
    _, _, _, rep = run_pack([a, b])
    assert any(f["code"] == "PACK_MATERIAL_DRIFT" for f in rep["findings"])
    out = tmp_path / "pack.png"
    assert main(["pack", str(a), str(b), "--out", str(out), "--size", "96"]) == 0
    assert out.exists()
    assert main(["pack", str(a)]) == 2  # a pack needs two assets


def test_pack_consistent_materials_have_no_drift(make_asset):
    a = make_asset(BOX + "materials: {m: {base_color: '#ff0000'}}\n", "a")
    b = make_asset(BOX + "materials: {m: {base_color: '#ff0000'}}\n", "b")
    assets = [build(a), build(b)]
    rep = pack_report(assets, [{"status": "PASS", "metrics": {}, "issues": []}] * 2)
    assert not any(f["code"] == "PACK_MATERIAL_DRIFT" for f in rep["findings"])
