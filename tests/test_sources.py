"""Geometry sources beyond native generators: mesh_file and `sw import`."""

import shutil

import numpy as np
import pytest
import yaml

from shapewright.assemble import ROOT, build
from shapewright.export.gltf import write_glb
from shapewright.importer import import_file
from shapewright.report import SourceError
from shapewright.surface import build_surface
from shapewright.validate.run import run_validation

FIXTURE = ROOT / "tests" / "fixtures" / "source" / "example.obj"


def test_export_import_roundtrip_keeps_names_geometry_and_uvs(tmp_path):
    chair = build(ROOT / "assets" / "tavern_chair")
    glb = tmp_path / "chair.glb"
    write_glb(chair, build_surface(chair), glb)
    res = import_file(glb, tmp_path / "imp", "imp")
    assert len(res["skipped_collision"]) == 0 or all(n.startswith("UCX_") for n in res["skipped_collision"])
    a = build(tmp_path / "imp")
    assert {p.name for p in a.parts} == {p.name for p in chair.parts}
    assert a.n_tris == chair.n_tris
    assert np.allclose(a.bounds(), chair.bounds(), atol=1e-4)
    assert all("uv" in p.mesh.cattr for p in a.parts), "authored UVs must survive import"
    r = run_validation(a, build_surface(a))
    assert r["status"] != "FAIL", [i for i in r["issues"] if i["severity"] == "error"]
    assert all(p.source == "file" for p in a.parts)


def test_split_gives_addressable_pieces(tmp_path):
    two = tmp_path / "two.obj"
    lines = FIXTURE.read_text().splitlines()
    verts = [ln for ln in lines if ln.startswith("v ")]
    faces = [ln for ln in lines if ln.startswith("f ")]
    moved = ["v " + " ".join(str(float(x) + (0.5 if i == 0 else 0)) for i, x in enumerate(v.split()[1:])) for v in verts]
    shifted = ["f " + " ".join(str(int(i) + 8) for i in f.split()[1:]) for f in faces]
    two.write_text("\n".join(verts + moved + faces + shifted) + "\n")
    res = import_file(two, tmp_path / "pieces", "pieces", split=True)
    assert [r["part"] for r in res["parts"]] == ["two_obj_01", "two_obj_02"]  # pieces keep their node's name (Phase 11)
    a = build(tmp_path / "pieces")
    assert len(a.parts) == 2 and np.isclose(a.bounds()[1][0] - a.bounds()[0][0], 0.7)


def _asset_with_file(tmp_path, shape_extra="", extra_parts=""):
    d = tmp_path / "a"
    (d / "source").mkdir(parents=True)
    shutil.copy(FIXTURE, d / "source" / "cube.obj")
    (d / "asset.yaml").write_text(f"""
materials: {{m: {{}}}}
parts:
  body:
    shape: {{type: mesh_file, path: source/cube.obj{shape_extra}}}
    anchor: bottom
    material: m
{extra_parts}""")
    return d


@pytest.mark.parametrize("path", ["../cube.obj", "/etc/passwd.obj", "source/cube.gltf", "source/missing.obj"])
def test_mesh_file_paths_are_sandboxed(tmp_path, path):
    d = _asset_with_file(tmp_path)
    (d / "asset.yaml").write_text((d / "asset.yaml").read_text().replace("source/cube.obj", path))
    with pytest.raises(SourceError) as e:
        build(d)
    assert e.value.issues[0].code == "OP_FAILED"


def test_native_parts_compose_with_imported_geometry(tmp_path):
    extra = """  handle:
    measure: {top: {bounds: body}}
    shape: {type: torus, radius: 0.05, tube: 0.01, rotate: [90, 0, 0]}
    anchor: bottom
    position: [0, top.max.y - 0.01, 0]
    material: m
"""
    d = _asset_with_file(tmp_path, ", ops: [{type: subtract, shape: {type: cylinder, radius: 0.03, height: 0.5}}]", extra)
    a = build(d)
    r = run_validation(a, build_surface(a))
    assert r["status"] != "FAIL", r["issues"]
    body = a.part("body")
    assert "file:source/cube.obj" in set(body.mesh.label_values("origin"))
    assert any(o.endswith("ops[0].shape") for o in body.mesh.label_values("origin"))


def test_open_imported_surface_policy(tmp_path):
    d = _asset_with_file(tmp_path)
    obj = d / "source" / "cube.obj"
    obj.write_text("\n".join(ln for ln in obj.read_text().splitlines() if ln != "f 1 3 2") + "\n")
    a = build(d)
    codes = {(i["code"], i["severity"]) for i in run_validation(a, build_surface(a))["issues"]}
    assert ("GEO_OPEN_EDGES", "error") in codes
    src = yaml.safe_load((d / "asset.yaml").read_text())
    src["parts"]["body"]["tags"] = ["open_ok"]
    (d / "asset.yaml").write_text(yaml.safe_dump(src))
    a = build(d)
    codes = {(i["code"], i["severity"]) for i in run_validation(a, build_surface(a))["issues"]}
    assert ("GEO_OPEN_EDGES", "warning") in codes
