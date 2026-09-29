"""Phase 12 contracts (docs/PRODUCTION.md): engine targets name collision for their importers, static
parts merge per material (draw calls), moving groups keep their pivot, normal-mapped primitives get
tangents, LOD files keep LOD0's atlas. The Godot test runs only when SW_GODOT points at a Godot 4 binary."""

import json
import os
import struct

import numpy as np
import pytest

from shapewright.assemble import build
from shapewright.export.gltf import write_glb
from shapewright.export.targets import TARGETS, draw_calls, rigid_groups
from shapewright.export.verify import roundtrip
from shapewright.surface import build_surface
from shapewright.validate.run import run_validation

CHEST = """
profile: {profile}
materials:
  oak: {{archetype: wood, color: "#8a5a36"}}
  iron: {{archetype: metal, color: "#9aa0a8"}}
collision: {{mode: {collision}}}
parts:
  body: {{shape: {{type: chamfer_box, size: [0.8, 0.4, 0.5], chamfer: 0.02}}, anchor: bottom, material: oak}}
  band: {{shape: {{type: box, size: [0.82, 0.05, 0.52]}}, position: [0, 0.2, 0], material: iron, array: {{count: 2, offset: [0, 0.1, 0]}}}}
  lid: {{shape: {{type: chamfer_box, size: [0.8, 0.12, 0.5], chamfer: 0.02}}, anchor: bottom, position: [0, 0.4, 0], material: oak,
         pivot: bottom_back}}
  lid_band: {{shape: {{type: box, size: [0.82, 0.04, 0.52]}}, position: [0, 0.46, 0], material: iron, parent: lid}}
"""


def glb(path):
    blob = path.read_bytes()
    n = struct.unpack("<I", blob[12:16])[0]
    return json.loads(blob[20:20 + n])


def chest(make_asset, profile="godot", collision="hull", name="chest"):
    return build(make_asset(CHEST.format(profile=profile, collision=collision), name))


@pytest.mark.parametrize("target,expect", [("godot", "chest_00-convcolonly"), ("unreal", "UCX_chest_00"),
                                           ("unity", "chest_00_collider"), ("generic", "COL_chest_00")])
def test_collision_names_follow_each_engine(target, expect):
    assert TARGETS[target].collision_name("chest", 0) == expect


def test_static_parts_merge_per_material_and_moving_groups_keep_their_pivot(make_asset, tmp_path):
    a = chest(make_asset)
    s = build_surface(a)
    groups = rigid_groups(a)
    assert set(groups) == {"", "lid"} and {p.name for p in groups["lid"]} == {"lid", "lid_band"}
    out = tmp_path / "c.glb"
    write_glb(a, s, out)
    g = glb(out)
    visual = [n for n in g["nodes"] if "mesh" in n and not n["name"].endswith("colonly")]
    assert sorted(n["name"] for n in visual) == ["chest_static", "lid"]
    assert sum(len(g["meshes"][n["mesh"]]["primitives"]) for n in visual) == draw_calls(a, s) == 4
    lid = next(n for n in visual if n["name"] == "lid")
    assert np.allclose(lid["translation"], a.part("lid").pivot)  # the hinge
    ranges = [r for n in visual for r in n["extras"]["merged_parts"]]
    assert sum(r["index_count"] for r in ranges) == 3 * a.n_tris
    assert roundtrip(a, out) == []


def test_generic_target_keeps_part_nodes(make_asset, tmp_path):
    a = chest(make_asset, profile="desktop_indie", name="plain")
    out = tmp_path / "p.glb"
    write_glb(a, build_surface(a), out)
    names = {n["name"] for n in glb(out)["nodes"]}
    assert {"body", "band_0", "band_1", "lid", "lid_band"} <= names and "COL_plain_00" in names


def test_collision_modes_and_proxy_warning(make_asset, tmp_path):
    for mode, count in (("single_hull", 1), ("single_box", 1), ("hull", 5)):
        a = chest(make_asset, collision=mode, name=f"c_{mode}")
        out = tmp_path / f"{mode}.glb"
        write_glb(a, build_surface(a), out)
        assert sum(n["name"].endswith("-convcolonly") for n in glb(out)["nodes"]) == count
    many = make_asset("materials: {m: {color: '#888888'}}\ncollision: {mode: box}\nparts:\n  p: {shape: {type: box, size: [0.1, 0.1, 0.1]}, "
                      "material: m, array: {count: 40, offset: [0.1, 0, 0]}}\n", "many")
    a = build(many)
    assert "COLLISION_PROXIES" in {i["code"] for i in run_validation(a, build_surface(a))["issues"]}


def test_normal_mapped_primitives_get_unit_tangents(tmp_path):
    from shapewright.importer import import_file
    from test_import import fixture_glb

    src = fixture_glb(tmp_path / "n.glb")
    import_file(src, tmp_path / "n", "n")
    y = tmp_path / "n" / "asset.yaml"
    from PIL import Image

    Image.new("RGB", (4, 4), (128, 128, 255)).save(tmp_path / "n" / "source" / "textures" / "flat_normal.png")
    y.write_text(y.read_text().replace("textures:", "textures:\n      normal: source/textures/flat_normal.png", 1))
    a = build(tmp_path / "n")
    out = tmp_path / "n.glb"
    write_glb(a, build_surface(a), out)
    blob = out.read_bytes()
    n = struct.unpack("<I", blob[12:16])[0]
    g = json.loads(blob[20:20 + n])
    prim = g["meshes"][0]["primitives"][0]
    acc = g["accessors"][prim["attributes"]["TANGENT"]]
    bv = g["bufferViews"][acc["bufferView"]]
    off = 20 + n + 8 + bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    t = np.frombuffer(blob[off:off + acc["count"] * 16], dtype=np.float32).reshape(-1, 4)
    assert np.allclose(np.linalg.norm(t[:, :3], axis=1), 1, atol=1e-4) and set(np.unique(t[:, 3])) <= {-1.0, 1.0}


def test_lod_files_keep_the_atlas_and_report_silhouettes(make_asset, tmp_path):
    from shapewright.export.lod import write_lods

    a = build(make_asset("profile: unreal\nmaterials: {m: {archetype: stone, color: '#8b8f94'}}\nparts:\n  r: {shape: {type: icosphere, "
                         "radius: 0.3, subdivisions: 3}, material: m}\n", "rock"))
    s = build_surface(a)
    rep = write_lods(a, s, tmp_path / "rock.glb", [0.5, 0.2])
    assert [r["lod"] for r in rep] == [1, 2] and rep[0]["triangles"] < a.n_tris and rep[0]["silhouette_iou"] > 0.9
    g = glb(tmp_path / "rock_LOD1.glb")
    assert len(g["images"]) == 2  # the LOD0 atlas travels with the LOD


@pytest.mark.skipif(not os.environ.get("SW_GODOT"), reason="set SW_GODOT to a Godot 4 binary to run the engine import check")
def test_godot_imports_convex_bodies_and_merged_meshes(make_asset, tmp_path):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "engine"))
    from godot_check import check

    a = chest(make_asset)
    out = tmp_path / "chest.glb"
    write_glb(a, build_surface(a), out)
    r = check([out], os.environ["SW_GODOT"])[str(out)]
    assert r["meshes"] == 2 and r["surfaces"] == 4 and r["bodies"] == 5 and set(r["shapes"]) == {"ConvexPolygonShape3D"}
    assert abs(r["min_y"]) < 1e-4
