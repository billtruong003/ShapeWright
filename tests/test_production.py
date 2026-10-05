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
    for mode, count in (("single_hull", 2), ("single_box", 2), ("hull", 5)):  # single modes: one per rigid group (static + lid)
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


def test_collision_follows_moving_groups_and_is_named_after_its_mesh(make_asset, tmp_path):
    """FRESH_AGENT_08: the lid had no collision of its own, and Unreal matches UCX_<mesh>_NN to a mesh by name."""
    a = chest(make_asset, collision="single_box", name="c2")
    s = build_surface(a)
    out = tmp_path / "g.glb"
    write_glb(a, s, out)
    g = glb(out)
    lid = next(n for n in g["nodes"] if n["name"] == "lid")
    kids = [g["nodes"][i]["name"] for i in lid.get("children", [])]
    assert kids == ["lid_00-convcolonly"]  # Godot: under the lid node, so it moves with the lid
    a._export_target = "unreal"
    write_glb(a, s, tmp_path / "u.glb")
    names = {n["name"] for n in glb(tmp_path / "u.glb")["nodes"]}
    assert {"UCX_c2_static_00", "UCX_lid_00"} <= names


def test_export_target_override(make_asset, tmp_path):
    from shapewright.export.targets import export_settings

    a = chest(make_asset, name="c3")
    assert export_settings(a)["target"].name == "godot" and export_settings(a)["lods"] == []
    s = export_settings(a, "unreal")
    assert s["target"].name == "unreal" and s["merge"] == "by_material" and s["lods"] == [0.5]


def test_strut_depth_axis_is_consistent(make_asset):
    a = build(make_asset("materials: {m: {color: '#888888'}}\nparts:\n"
                         "  f: {shape: {type: strut, from: [0, 0, 0], to: [0, 0.5, 0.1], size: [0.02, 0.06], depth_axis: z}, material: m}\n"
                         "  s: {shape: {type: strut, from: [1, 0, 0], to: [1.1, 0.5, 0], size: [0.02, 0.06], depth_axis: z}, material: m}\n", "legs"))
    sz = [p.mesh.size() for p in a.parts]
    assert sz[1][2] == pytest.approx(0.06, abs=1e-6)  # depth along z for the leg leaning in x
    assert sz[0][2] > 0.05  # and (mostly) along z for the one leaning in z


def test_pivot_at_a_point_in_asset_coordinates(make_asset):
    # FA-10 A: a hinge on a computed axis needed hand-derived -1..1 coefficients
    base = CHEST.format(profile="godot", collision="hull")
    a = build(make_asset(base.replace("pivot: bottom_back}", "pivot: {at: [0, 0.4 + 0.01, -0.5 / 2]}}"), "hinge"))
    assert np.allclose(a.part("lid").pivot, [0, 0.41, -0.25])
    b = build(make_asset(base.replace("pivot: bottom_back", "pivot: [0, -1, -0.5 * 2]"), "hinge2"))
    assert np.allclose(b.part("lid").pivot, chest(make_asset, name="c3").part("lid").pivot)


@pytest.mark.skipif(not os.environ.get("SW_GODOT"), reason="set SW_GODOT to a Godot 4 binary to run the engine import check")
@pytest.mark.parametrize("name", ["barrel", "house_cottage", "ornate_fountain"])
def test_godot_imports_the_example_assets(name, tmp_path):
    # release smoke test (track E4): what CI's `godot` job runs, with Godot 4.3 headless
    import sys
    from pathlib import Path

    from shapewright.assemble import ROOT

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "engine"))
    from godot_check import check

    a = build(ROOT / "assets" / name)
    a._export_target = "godot"
    out = tmp_path / f"{name}_godot.glb"
    write_glb(a, build_surface(a), out)
    r = check([out], os.environ["SW_GODOT"])[str(out)]
    assert "error" not in r, r
    assert r["meshes"] >= 1 and r["materials"]
    if name != "barrel":  # the textured assets: their baked atlas resolved in the engine
        assert any(m.get("albedo_texture") for m in r["materials"].values())
    assert r["bodies"] >= 1 and set(r["shapes"]) <= {"ConvexPolygonShape3D", "BoxShape3D", "ConcavePolygonShape3D"}
    assert abs(r["min_y"]) < 1e-3
