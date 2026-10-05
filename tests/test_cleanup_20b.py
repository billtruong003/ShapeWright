"""Phase 20b: cleanup of known defects (docs/REMAINING_WORK.md track A)."""

import json
import struct

from shapewright import paths
from shapewright.assemble import ROOT, build
from shapewright.cli import main
from shapewright.report import SourceError
from shapewright.validate.run import format_text, run_validation
from shapewright.surface import build_surface
from shapewright.validate.seams import coplanar_pairs


def _asset(tmp_path, parts: str, name="t", extra=""):
    d = tmp_path / name
    d.mkdir()
    (d / "asset.yaml").write_text(f"shapewright: 0.1\nasset: {{name: {name}}}\nmaterials: {{m: {{base_color: '#888888'}}}}\n{extra}parts:\n{parts}")
    return d


def _glb_nodes(path):
    data = path.read_bytes()
    n = struct.unpack("<I", data[12:16])[0]
    return [x.get("name", "") for x in json.loads(data[20:20 + n])["nodes"]]


# A1: z-fighting on the ground plane faces down into the floor; it is not reported
def test_coplanar_faces_lying_on_the_ground_are_hidden_by_the_floor(tmp_path):
    d = _asset(tmp_path, """  a: {shape: {type: box, size: [0.4, 0.5, 0.4]}, material: m, anchor: bottom, position: [0, 0, 0]}
  b: {shape: {type: box, size: [0.2, 0.8, 0.2]}, material: m, anchor: bottom, position: [0.25, 0, 0]}
""")
    rows = coplanar_pairs(build(d).parts)
    assert rows and rows[0]["same_facing_m2"] == 0 and rows[0]["same_facing_hidden_m2"] > 0


def test_seam_issue_says_where_the_shared_surface_is(tmp_path):
    d = _asset(tmp_path, """  wall: {shape: {type: box, size: [1.0, 1.0, 0.2]}, material: m, anchor: bottom, position: [0, 0.1, 0]}
  plinth: {shape: {type: box, size: [0.3, 0.4, 0.2]}, material: m, anchor: bottom_left, position: [-0.5, 0.1, -0.1]}
""")
    a = build(d)
    hit = [i for i in run_validation(a, build_surface(a))["issues"] if i["code"] == "SEAM_COPLANAR_OVERLAP"][0]
    assert "near (" in hit["msg"] and hit["data"]["at"] and hit["data"]["normal"]


def test_benchmark_assets_are_seam_clean():
    flagged = {}
    for p in sorted((ROOT / "assets").glob("*/asset.yaml")):
        rows = [r for r in coplanar_pairs(build(p).parts) if r["same_facing_m2"] >= 5e-5]
        if rows:
            flagged[p.parent.name] = len(rows)
    assert not flagged, flagged


# A2
def test_tavern_chair_param_range_agrees_with_its_check(capsys):
    assert main(["validate", "tavern_chair", "--set", "seat_height=0.42"]) == 0


# A3
def test_preview_export_has_no_collision_and_the_same_visible_meshes(tmp_path):
    full, prev = tmp_path / "full.glb", tmp_path / "prev.glb"
    assert main(["export", "storage_chest", "--out", str(full)]) == 0
    assert main(["export", "storage_chest", "--preview", "--out", str(prev)]) == 0
    a, b = _glb_nodes(full), _glb_nodes(prev)
    col = [n for n in a if n.startswith(("COL_", "UCX_")) or n.endswith(("colonly",))]
    assert col and not [n for n in b if n in col]
    assert [n for n in a if n not in col] == b


# A5
def test_library_examples_write_build_products_into_the_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["init", "."]) == 0
    monkeypatch.setenv("SW_PROJECT", str(tmp_path))
    lib = ROOT / "assets" / "barrel"
    before = sorted(p.name for p in lib.iterdir())
    assert paths.out_dir(lib) == tmp_path / ".build" / "library" / "barrel"
    assert main(["review", "barrel"]) == 0
    assert main(["export", "barrel", "--preview"]) == 0
    assert (tmp_path / ".build" / "library" / "barrel" / ".build" / "sheet.png").is_file()
    assert (tmp_path / ".build" / "library" / "barrel" / "export" / "barrel_preview.glb").is_file()
    assert sorted(p.name for p in lib.iterdir()) == before
    own = tmp_path / "assets" / "mine"
    assert paths.out_dir(own) == own.resolve()


# A6
def test_hidden_info_line_names_the_codes(tmp_path):
    d = _asset(tmp_path, """  wall: {shape: {type: box, size: [1.0, 1.0, 0.2]}, material: m, anchor: bottom, position: [0, 0, 0]}
  sign: {shape: {type: box, size: [0.4, 0.2, 0.03]}, material: m, anchor: back, position: [0, 0.6, 0.1]}
""")
    a = build(d)
    text = format_text(run_validation(a, build_surface(a)))
    assert "info items hidden: " in text and "ASM_CONTACT_ONLY" in text.splitlines()[-1]


# A8
def test_source_errors_carry_the_file_and_line(tmp_path):
    d = _asset(tmp_path, """  a:
    shape: {type: box, size: [1, 1, 1]}
    material: m
  b:
    shape: {type: box, size: [1, 1, 1]}
    material: m
    positon: [0, 1, 0]
  rung:
    shape: {type: cylinder, radius: hh, height: 1}
    material: m
    array: {count: 3, offset: [1, 0, 0]}
""")
    try:
        build(d)
        raise AssertionError("expected a source error")
    except SourceError as e:
        by = {i.where: i for i in e.issues}
    assert by["parts.b.positon"].src == "t/asset.yaml:11"
    assert "t/asset.yaml:11 parts.b.positon" in by["parts.b.positon"].line()
    radius = [i for w, i in by.items() if w.endswith("shape.radius")][0]
    assert radius.src == "t/asset.yaml:13"
    assert by["parts.b.positon"].to_dict()["src"] == "t/asset.yaml:11"


def test_source_errors_in_a_variant_point_into_the_variant_file(tmp_path):
    _asset(tmp_path, """  a: {shape: {type: box, size: [1, 1, 1]}, material: m}
  b: {shape: {type: box, size: [1, 1, 1]}, material: m, position: [2, 0, 0]}
""", name="base")
    v = tmp_path / "v"
    v.mkdir()
    (v / "asset.yaml").write_text("shapewright: 0.1\nextends: ../base\nasset: {name: v}\nparts:\n  b:\n    positon: [3, 0, 0]\n")
    try:
        build(v)
        raise AssertionError("expected a source error")
    except SourceError as e:
        hit = [i for i in e.issues if i.where == "parts.b.positon"]
    assert hit and hit[0].src == "v/asset.yaml:6"
