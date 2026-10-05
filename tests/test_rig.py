"""Phase 24: native rigging (rig.py): skeleton templates, bone-heat weights, poses, glTF skin."""

import json
import struct

import numpy as np
import pytest

from shapewright import rig as R
from shapewright.assemble import ROOT, build
from shapewright.export.gltf import write_glb
from shapewright.surface import build_surface
from shapewright.validate.run import run_validation


@pytest.fixture(scope="module")
def fox():
    a = build(ROOT / "assets" / "chibi_fox")
    return a, R.build_rig(a)


def test_fox_skeleton_mirrors_and_orders_joints(fox):
    a, rg = fox
    assert len(rg.names) == 19 and rg.parents[0] == -1
    for j, p in enumerate(rg.parents):
        assert p < j  # parents first
    left, right = rg.rest[rg.index("hand_l")], rg.rest[rg.index("hand_r")]
    assert left[0] == pytest.approx(-right[0]) and left[1:] == pytest.approx(right[1:])
    assert rg.names[rg.parents[rg.index("tail_2")]] == "tail_1"


def test_weights_are_normalised_with_at_most_four_influences(fox):
    a, rg = fox
    W = rg.weights["body"]
    assert np.allclose(W.sum(1), 1.0)
    assert ((W > 0).sum(1) <= 4).all()
    head = a.parts[0].mesh.V[:, 1] > 0.8  # the ears and the top of the hood follow the head
    assert W[head, rg.index("head")].mean() > 0.6
    feet = a.parts[0].mesh.V[:, 1] < 0.03
    assert W[feet][:, [rg.index("foot_l"), rg.index("foot_r"), rg.index("lower_leg_l"), rg.index("lower_leg_r")]].sum(1).mean() > 0.8


@pytest.mark.parametrize("pose", ["a_pose", "walk", "sit", "wave", "look"])
def test_poses_keep_the_volume(fox, pose):
    a, rg = fox
    assert R.volume_kept(a, rg, R.POSES[pose]) > 0.9  # no candy-wrapper collapse


def test_rest_pose_is_the_identity(fox):
    a, rg = fox
    assert np.allclose(R.posed(a, rg, {}).parts[0].mesh.V, a.parts[0].mesh.V)


def test_skinned_export(fox, tmp_path):
    a, rg = fox
    s = build_surface(a)
    out = tmp_path / "fox.glb"
    write_glb(a, s, out)
    data = out.read_bytes()
    n = struct.unpack("<I", data[12:16])[0]
    doc = json.loads(data[20:20 + n])
    binary = data[20 + n + 8:]
    skin = doc["skins"][0]
    assert len(skin["joints"]) == 19
    body = next(i for i, nd in enumerate(doc["nodes"]) if nd.get("skin") == 0)
    assert body in doc["scenes"][0]["nodes"]  # skinned meshes are scene roots
    prim = doc["meshes"][doc["nodes"][body]["mesh"]]["primitives"][0]
    acc = doc["accessors"][prim["attributes"]["WEIGHTS_0"]]
    view = doc["bufferViews"][acc["bufferView"]]
    w = np.frombuffer(binary[view.get("byteOffset", 0):view.get("byteOffset", 0) + view["byteLength"]], dtype=np.float32).reshape(-1, 4)
    assert np.allclose(w.sum(1), 1.0, atol=1e-5)
    ibm = doc["accessors"][skin["inverseBindMatrices"]]
    v = doc["bufferViews"][ibm["bufferView"]]
    M = np.frombuffer(binary[v["byteOffset"]:v["byteOffset"] + v["byteLength"]], dtype=np.float32).reshape(-1, 4, 4).transpose(0, 2, 1)
    assert np.allclose(M[:, :3, 3], -rg.rest, atol=1e-6)  # inverse of the rest translation


def test_template_only_rig_and_validation(tmp_path):
    d = tmp_path / "blob"
    d.mkdir()
    (d / "asset.yaml").write_text(
        "shapewright: 0.1\nasset: {name: blob, placement: floor}\nmaterials: {m: {base_color: '#888888'}}\n"
        "parts:\n  body: {material: m, origin: keep, shape: {type: blend, ground: true, triangles: 1500, items: ["
        "{sdf: ellipsoid, center: [0, 0.45, 0], radii: [0.2, 0.3, 0.15]}, {sdf: capsule, a: [0.1, 0.05, 0], b: [0.1, 0.3, 0], radius: 0.06, mirror: x}, "
        "{sdf: capsule, a: [0.18, 0.62, 0], b: [0.32, 0.35, 0], radius: 0.05, mirror: x}]}}\n"
        "rig: {template: biped}\n")
    a = build(d)
    rg = R.build_rig(a)
    assert rg is not None and "upper_leg_r" in rg.names
    rep = run_validation(a, build_surface(a))
    assert rep["metrics"]["rig_joints"] == len(rg.names)
    assert "RIG_INVALID" not in {i["code"] for i in rep["issues"]}


def test_bad_rig_is_reported(tmp_path):
    d = tmp_path / "bad"
    d.mkdir()
    (d / "asset.yaml").write_text(
        "shapewright: 0.1\nasset: {name: bad, placement: free}\nmaterials: {m: {base_color: '#888888'}}\n"
        "parts:\n  body: {material: m, shape: {type: sphere, radius: 0.2}}\n"
        "rig: {template: biped, joints: {wing_l: [0.2, 0.3, 0]}}\n")
    a = build(d)
    issues = [i for i in run_validation(a, build_surface(a))["issues"] if i["code"] == "RIG_INVALID"]
    assert issues and "parent" in issues[0]["msg"]


def _doc(path):
    data = path.read_bytes()
    n = struct.unpack("<I", data[12:16])[0]
    return json.loads(data[20:20 + n]), data[20 + n + 8:]


def _acc(doc, binary, i, width):
    a = doc["accessors"][i]
    v = doc["bufferViews"][a["bufferView"]]
    return np.frombuffer(binary[v["byteOffset"]:v["byteOffset"] + v["byteLength"]], dtype=np.float32).reshape(-1, width)


def test_procedural_clips_export_and_loop(fox, tmp_path):
    a, rg = fox
    out = tmp_path / "fox.glb"
    write_glb(a, build_surface(a), out)
    doc, binary = _doc(out)
    anims = {an["name"]: an for an in doc["animations"]}
    assert set(anims) == {"idle", "walk", "wave"}
    walk = anims["walk"]
    names = {doc["nodes"][c["target"]["node"]]["name"] for c in walk["channels"]}
    assert {"upper_leg_l", "upper_leg_r", "lower_leg_l", "hips"} <= names
    for smp in walk["samplers"]:
        out_v = _acc(doc, binary, smp["output"], 4 if doc["accessors"][smp["output"]]["type"] == "VEC4" else 3)
        assert np.allclose(out_v[0], out_v[-1], atol=1e-5)  # the clip loops
        if out_v.shape[1] == 4:
            assert np.allclose(np.linalg.norm(out_v, axis=1), 1.0, atol=1e-4)


@pytest.mark.parametrize("clip", ["idle", "walk", "wave"])
def test_clips_keep_the_volume(fox, clip):
    a, rg = fox
    p = R.clip_settings(a)[clip]
    for k in range(0, R.KEYS, 3):
        pose, off = R.clip_pose(rg, clip, p, p["seconds"] * k / R.KEYS)
        assert R.volume_kept(a, rg, pose) > 0.9


def test_rigid_clip_turns_the_lid_node(tmp_path):
    a = build(ROOT / "assets" / "storage_chest")
    out = tmp_path / "chest.glb"
    write_glb(a, build_surface(a), out)
    doc, binary = _doc(out)
    an = next(x for x in doc["animations"] if x["name"] == "open_lid")
    node = doc["nodes"][an["channels"][0]["target"]["node"]]
    assert node["name"] == "lid"
    q = _acc(doc, binary, an["samplers"][0]["output"], 4)
    assert np.allclose(q[0], [0, 0, 0, 1], atol=1e-6) and np.allclose(q[-1], q[0], atol=1e-6)  # pingpong
    mid = q[len(q) // 2]
    assert abs(2 * np.degrees(np.arccos(min(1.0, abs(mid[3]))))) == pytest.approx(100, abs=1)


def test_bad_clips_are_reported(tmp_path):
    d = tmp_path / "anim"
    d.mkdir()
    (d / "asset.yaml").write_text(
        "shapewright: 0.1\nasset: {name: anim, placement: free}\nmaterials: {m: {base_color: '#888888'}}\n"
        "parts:\n  body: {material: m, shape: {type: box, size: [0.2, 0.2, 0.2]}}\n"
        "animations: [{name: spin, part: wheel, rotate: [360, 0, 0], loop: cycle}]\n")
    codes = {i["code"] for i in run_validation(build(d), build_surface(build(d)))["issues"]}
    assert "ANIM_INVALID" in codes


def test_review_modes_density_and_weights(fox):
    from shapewright.render.views import character_sheet, render

    a, rg = fox
    s = build_surface(a)
    w = np.asarray(render(a, s, "front", "weights", 200, bone="head")).astype(int)
    red = (w[..., 0] > 180) & (w[..., 2] < 90)
    blue = (w[..., 2] > 150) & (w[..., 0] < 90)
    assert red.sum() > 50 or ((w[..., 0] > 180) & (w[..., 1] > 150) & (w[..., 2] < 90)).sum() > 50  # the head is warm
    assert blue.sum() > red.sum()  # the rest of the body is cold
    lo = blue.nonzero()[0].mean() if blue.any() else 0
    assert lo > (w.shape[0] * 0.4)  # cold pixels sit low (the body), warm high (the head)
    d = np.asarray(render(a, s, "front", "density", 160))
    assert d.std() > 10
    with pytest.raises(ValueError, match="--bone"):
        render(a, s, "front", "weights", 120, bone="wing")
    sheet = character_sheet(a, s, tile=120)
    assert sheet.size == (480, 360)  # 3 rows of 4: look x3, UV checker, UV layout, density, 3 weights, 2 poses


def test_cli_review_writes_the_character_sheet(tmp_path, capsys):
    from shapewright import cli

    rc = cli.main(["review", "chibi_fox", "--size", "160"])
    out = capsys.readouterr().out
    assert rc == 0 and "character: " in out
