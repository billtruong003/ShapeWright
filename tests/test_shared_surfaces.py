"""Phase 21: shared surfaces (pack trim sheet, ...)."""

import json
import struct

import numpy as np
import pytest

from shapewright.assemble import build
from shapewright.bake import textures_for
from shapewright.export.gltf import write_glb
from shapewright.surface import build_surface
from shapewright.validate.run import run_validation

PACK = """shapewright: 0.1
pack: kit
doc: test kit
params: {bay: 2.0}
atlas: {size: 512, density: 64}
materials:
  wood:  {archetype: wood, color: "#8a5a36"}
  stone: {archetype: stone, color: "#8c857a"}
"""


@pytest.fixture
def kit(tmp_path):
    (tmp_path / "packs").mkdir()
    (tmp_path / "packs" / "kit.yaml").write_text(PACK)
    out = {}
    for name, parts in (("beam", "  b: {shape: {type: box, size: [bay, 0.2, 0.2]}, material: wood, anchor: bottom}\n"),
                        ("block", "  s: {shape: {type: box, size: [0.5, 0.5, 0.5]}, material: stone, anchor: bottom}\n"
                                  "  w: {shape: {type: box, size: [0.6, 0.1, 0.6]}, material: wood, anchor: bottom, position: [0, 0.5, 0]}\n")):
        d = tmp_path / "assets" / name
        d.mkdir(parents=True)
        (d / "asset.yaml").write_text(f"shapewright: 0.1\npack: ../../packs/kit.yaml\nasset: {{name: {name}, placement: free}}\nparts:\n{parts}")
        out[name] = build(d)
    return out


def test_members_map_onto_their_material_strip(kit):
    a = kit["beam"]
    s = build_surface(a)
    assert s.uv_method == "trim" and s.uv_resolution == 512
    uv = s.parts["b"].corner_uv
    # wood is the first of 2 strips: v in [0, 0.5], away from the strip edges by the padding
    assert uv[..., 1].min() > 0 and uv[..., 1].max() < 0.5
    # U at 64 px/m on a 512 px sheet: the 2 m beam spans 2 * 64 / 512 = 0.25 texture widths, inside one width
    top = a.parts[0].mesh.face_normals()[0][:, 1] > 0.99  # one planar group: the top of the beam
    span = uv[top][..., 0].max() - uv[top][..., 0].min()
    assert span == pytest.approx(0.25, abs=0.01) and 0 <= uv[top][..., 0].min() and uv[top][..., 0].max() <= 1
    b = build_surface(kit["block"]).parts["s"].corner_uv
    assert b[..., 1].min() > 0.5  # stone: the second strip


def test_every_member_shares_one_sheet_and_exports_it_identically(kit, tmp_path):
    sa, sb = build_surface(kit["beam"]), build_surface(kit["block"])
    ta, tb = textures_for(kit["beam"], sa), textures_for(kit["block"], sb)
    assert ta is tb and ta.trim["strips"] == ["wood", "stone"]
    imgs = []
    for name, s in (("beam", sa), ("block", sb)):
        out = tmp_path / f"{name}.glb"
        write_glb(kit[name], s, out)
        data = out.read_bytes()
        n = struct.unpack("<I", data[12:16])[0]
        doc = json.loads(data[20:20 + n])
        assert doc["samplers"][0]["wrapS"] == 10497  # repeat along U
        imgs.append([i["name"] for i in doc["images"]])
    assert imgs[0] == imgs[1] and imgs[0][0].startswith("kit_trim_")


def test_trim_members_validate_without_overlap_errors(kit):
    a = kit["block"]
    rep = run_validation(a, build_surface(a))
    codes = {i["code"] for i in rep["issues"]}
    assert not {"UV_OVERLAP", "UV_OUT_OF_BOUNDS", "UV_LOCK_STALE"} & codes
    assert rep["metrics"]["texel_density_px_m"] == pytest.approx(64) and rep["metrics"]["trim_sheet"] == "kit"


def test_a_face_taller_than_its_strip_is_scaled_and_reported(tmp_path, kit):
    d = tmp_path / "assets" / "tall"
    d.mkdir(parents=True)
    (d / "asset.yaml").write_text("shapewright: 0.1\npack: ../../packs/kit.yaml\nasset: {name: tall, placement: free}\nparts:\n"
                                  "  t: {shape: {type: box, size: [10, 10, 0.2]}, material: wood, anchor: bottom}\n")
    a = build(d)
    s = build_surface(a)
    assert s.trim_density["t"] < 64
    uv = s.parts["t"].corner_uv
    assert uv[..., 1].max() < 0.5  # still inside the wood strip
    rep = run_validation(a, s)
    assert any(i["code"] == "UV_TEXEL_DENSITY" and "trim strip" in i["msg"] for i in rep["issues"])
    assert np.isfinite(uv).all()


# ---------------------------------------------------------------- F2: vertex-colour materials

STOOL = """shapewright: 0.1
asset: {name: NAME}
profile: mobile_mid
materials:
  paint: {archetype: vertex, color: "#c98b4a", bottom_shade: 0.4}
EXTRA
parts:
  seat: {shape: {type: box, size: [0.36, 0.05, 0.36]}, material: paint, anchor: top, position: [0, 0.45, 0]}
  leg:  {shape: {type: box, size: [0.05, 0.4, 0.05]}, material: MAT, anchor: bottom, position: [0.13, 0, 0.13], mirror: x}
"""


def _stool(tmp_path, name, extra="", mat="paint"):
    d = tmp_path / name
    d.mkdir()
    (d / "asset.yaml").write_text(STOOL.replace("NAME", name).replace("EXTRA", extra).replace("MAT", mat))
    return build(d)


def test_vertex_colour_material_exports_colours_and_no_texture(tmp_path):
    a = _stool(tmp_path, "stool")
    s = build_surface(a)
    assert textures_for(a, s) is None
    leg = s.parts["leg_left"]
    c, y = leg.colors[:, :3], leg.positions[:, 1]
    assert c[np.argmin(y)].sum() < c[np.argmax(y)].sum()  # the bottom of the part is shaded
    out = tmp_path / "s.glb"
    write_glb(a, s, out)
    data = out.read_bytes()
    doc = json.loads(data[20:20 + struct.unpack("<I", data[12:16])[0]])
    assert not doc.get("images") and all("COLOR_0" in p["attributes"] for m in doc["meshes"] for p in m["primitives"])
    assert doc["materials"][0]["pbrMetallicRoughness"]["baseColorFactor"][:3] == [1.0, 1.0, 1.0]
    rep = run_validation(a, s)
    assert rep["metrics"]["vertex_colour_materials"] == 1 and "VERTEX_COLOR_MIXED" not in {i["code"] for i in rep["issues"]}


def test_vertex_colours_next_to_textured_materials_are_flagged(tmp_path):
    a = _stool(tmp_path, "mixed", extra="  oak: {archetype: wood, color: '#8a5a34'}", mat="oak")
    rep = run_validation(a, build_surface(a))
    assert "VERTEX_COLOR_MIXED" in {i["code"] for i in rep["issues"]}


# ---------------------------------------------------------------- F3: weld with a tolerance, duplicate surfaces


def test_clean_welds_within_a_distance_and_drops_the_copy(tmp_path):
    import trimesh

    box = trimesh.creation.box((0.4, 0.4, 0.4))
    copy = box.copy()
    copy.vertices += 0.0002  # an unwelded copy 0.2 mm off: what a careless export leaves
    both = trimesh.util.concatenate([box, copy])
    d = tmp_path / "imp"
    d.mkdir()
    both.export(d / "dup.glb")
    src = ("shapewright: 0.1\nasset: {name: imp}\nmaterials: {m: {base_color: '#888888'}}\nparts:\n"
           "  b: {shape: {type: mesh_file, path: dup.glb}, material: m, tags: [open_ok], OPS}\n")
    (d / "asset.yaml").write_text(src.replace(", OPS", ""))
    a = build(d)
    rep = run_validation(a, build_surface(a))
    assert a.n_tris == 24
    (d / "asset.yaml").write_text(src.replace("OPS", "ops: [{type: clean, weld_distance: 0.0005}]"))
    a = build(d)
    assert a.n_tris == 12
    rep2 = run_validation(a, build_surface(a))
    assert "GEO_DUPLICATE_SURFACE" not in {i["code"] for i in rep2["issues"]}
    assert rep  # the unwelded file built


def test_an_unwelded_copy_is_reported(tmp_path):
    import trimesh

    box = trimesh.creation.box((0.4, 0.4, 0.4))
    both = trimesh.util.concatenate([box, box.copy()])  # identical positions, separate vertices
    d = tmp_path / "imp2"
    d.mkdir()
    both.export(d / "dup.glb")
    (d / "asset.yaml").write_text("shapewright: 0.1\nasset: {name: imp2}\nmaterials: {m: {base_color: '#888888'}}\nparts:\n"
                                  "  b: {shape: {type: mesh_file, path: dup.glb}, material: m}\n")
    a = build(d)
    hits = [i for i in run_validation(a, build_surface(a))["issues"] if i["code"] in ("GEO_DUPLICATE_SURFACE", "GEO_DUPLICATE_FACES")]
    assert hits


# ---------------------------------------------------------------- F5: multi-hull collision


def test_hulls_keep_a_doorway_open_and_block_the_walls(tmp_path):
    from shapewright.export.collision import decompose, segment_clear

    d = tmp_path / "gate"
    d.mkdir()
    (d / "asset.yaml").write_text(
        "shapewright: 0.1\nasset: {name: gate, placement: free}\nmaterials: {m: {base_color: '#888888'}}\nparts:\n"
        "  left:  {shape: {type: box, size: [1.0, 2.4, 0.2]}, material: m, anchor: bottom, position: [-1.0, 0, 0]}\n"
        "  right: {shape: {type: box, size: [1.0, 2.4, 0.2]}, material: m, anchor: bottom, position: [1.0, 0, 0]}\n"
        "  head:  {shape: {type: box, size: [3.0, 0.4, 0.2]}, material: m, anchor: bottom, position: [0, 2.4, 0]}\n")
    a = build(d)
    hulls = decompose(a.parts, max_hulls=1)  # asking for one hull must still not fill the doorway
    assert 1 < len(hulls) <= 3
    assert segment_clear(hulls, [0, 1.0, -1], [0, 1.0, 1])  # walk through the doorway
    assert not segment_clear(hulls, [-1.0, 1.0, -1], [-1.0, 1.0, 1])  # the wall blocks


# ---------------------------------------------------------------- F6: lightmap UVs


def test_lightmap_uvs_are_unique_and_exported_as_texcoord_1(tmp_path):
    a = _stool(tmp_path, "lm", extra="  oak: {archetype: wood, color: '#8a5a34'}", mat="oak")
    a.uv = dict(a.uv or {}, lightmap=True, lightmap_resolution=512)
    s = build_surface(a)
    assert all(sp.corner_uv1 is not None for sp in s.parts.values())
    rep = run_validation(a, s)
    codes = {i["code"] for i in rep["issues"]}
    assert not codes & {"LIGHTMAP_UV_OVERLAP", "LIGHTMAP_UV_MISSING"}
    assert rep["metrics"]["lightmap_uv_overlap"] <= 0.002 and rep["metrics"]["lightmap_uv_utilization"] > 0.2
    out = tmp_path / "lm.glb"
    write_glb(a, s, out)
    data = out.read_bytes()
    doc = json.loads(data[20:20 + struct.unpack("<I", data[12:16])[0]])
    assert all("TEXCOORD_1" in p["attributes"] for m in doc["meshes"] for p in m["primitives"])


def test_unreal_profile_turns_lightmaps_on():
    from pathlib import Path

    from shapewright.surface import lightmap_enabled

    a = build(Path(__file__).resolve().parents[1] / "assets" / "park_bench_unreal")
    assert lightmap_enabled(a)
    s = build_surface(a)
    assert {i["code"] for i in run_validation(a, s)["issues"]}.isdisjoint({"LIGHTMAP_UV_OVERLAP", "LIGHTMAP_UV_MISSING"})
