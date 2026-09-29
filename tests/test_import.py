"""Phase 11 contracts (docs/IMPORT.md): imported texture sets pass through unchanged, exported UVs
follow the glTF convention (checked by reading the file ourselves, not through trimesh), repair
and decimation keep authored UVs, and the atlas ignores authored parts."""

import json
import struct

import numpy as np
import pytest
from PIL import Image

from shapewright.assemble import build
from shapewright.bake import bake
from shapewright.export.gltf import write_glb
from shapewright.importer import import_file
from shapewright.surface import build_surface
from shapewright.validate.run import run_validation

QUADRANTS = np.zeros((32, 32, 3), np.uint8)
QUADRANTS[:16, :16], QUADRANTS[:16, 16:], QUADRANTS[16:, :16], QUADRANTS[16:, 16:] = [255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 0]


def fixture_glb(path, extents=(0.4, 0.3, 0.2), sphere=False):
    """A small textured file as another tool would write it: per-side planar UVs over an asymmetric texture,
    a metallic-roughness map and a node rotation."""
    import trimesh

    base = trimesh.creation.icosphere(3, 0.2) if sphere else trimesh.creation.box(extents=list(extents))
    V = base.vertices[base.faces].reshape(-1, 3)
    F = np.arange(len(V)).reshape(-1, 3)
    n = base.face_normals.repeat(3, 0)
    uv = np.zeros((len(V), 2))
    for i in range(len(V)):
        ax = int(np.argmax(np.abs(n[i])))
        a, b = [k for k in range(3) if k != ax]
        uv[i] = [(V[i][a] + 0.25) * 1.8, (V[i][b] + 0.25) * 1.8]
    mat = trimesh.visual.material.PBRMaterial(name="Paint Mat", baseColorTexture=Image.fromarray(QUADRANTS), metallicFactor=0.0,
                                              roughnessFactor=0.7, metallicRoughnessTexture=Image.fromarray(np.full((8, 8, 3), [0, 128, 0], np.uint8)))
    mesh = trimesh.Trimesh(V, F, visual=trimesh.visual.TextureVisuals(uv=uv, material=mat), process=False)
    if sphere:
        mesh.merge_vertices()
    sc = trimesh.Scene()
    sc.add_geometry(mesh, node_name="crate_body", geom_name="crate_body", transform=trimesh.transformations.rotation_matrix(np.pi, [0, 1, 0]))
    path.write_bytes(sc.export(file_type="glb"))
    return path


def read_glb(path):
    """Minimal glTF reader (positions in world space, raw TEXCOORD_0, images) independent of trimesh."""
    from scipy.spatial.transform import Rotation

    blob = path.read_bytes()
    n = struct.unpack("<I", blob[12:16])[0]
    g = json.loads(blob[20:20 + n])
    b0 = 20 + n + 8

    def acc(i, comp):
        a = g["accessors"][i]
        bv = g["bufferViews"][a["bufferView"]]
        off = b0 + bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        return np.frombuffer(blob[off:off + a["count"] * comp * 4], dtype=np.float32).reshape(-1, comp)

    P, U, idx = [], [], []
    for node in g["nodes"]:
        if "mesh" not in node:
            continue
        if "matrix" in node:
            M = np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T  # glTF matrices are column-major
        else:
            M = np.eye(4)
            M[:3, :3] = Rotation.from_quat(node.get("rotation", [0, 0, 0, 1])).as_matrix()
            M[:3, 3] = node.get("translation", [0, 0, 0])
        for pr in g["meshes"][node["mesh"]]["primitives"]:
            if "TEXCOORD_0" in pr["attributes"]:
                P.append(acc(pr["attributes"]["POSITION"], 3) @ M[:3, :3].T + M[:3, 3])
                U.append(acc(pr["attributes"]["TEXCOORD_0"], 2))
                ia = g["accessors"][pr["indices"]]
                bv = g["bufferViews"][ia["bufferView"]]
                off = b0 + bv.get("byteOffset", 0) + ia.get("byteOffset", 0)
                dt = {5125: np.uint32, 5123: np.uint16}[ia["componentType"]]
                idx.append(np.frombuffer(blob[off:off + ia["count"] * np.dtype(dt).itemsize], dtype=dt).reshape(-1, 3) + sum(len(p) for p in P[:-1]))
    images = []
    for im in g.get("images", []):
        bv = g["bufferViews"][im["bufferView"]]
        import io

        images.append(np.asarray(Image.open(io.BytesIO(blob[b0 + bv.get("byteOffset", 0):b0 + bv.get("byteOffset", 0) + bv["byteLength"]])).convert("RGB")))
    return g, np.concatenate(P), np.concatenate(U), np.concatenate(idx), images


def imported(tmp_path, **kw):
    src = fixture_glb(tmp_path / "crate.glb", **kw)
    res = import_file(src, tmp_path / "crate", "crate")
    return res, tmp_path / "crate"


def test_import_keeps_materials_and_texture_files(tmp_path):
    res, d = imported(tmp_path)
    a = build(d)
    mat = a.materials["paint_mat"]
    assert mat["archetype"] == "authored" and set(mat["textures"]) == {"base_color", "metallic_roughness"}
    assert all((d / p).exists() for p in mat["textures"].values())
    assert a.parts[0].material == "paint_mat" and res["materials"] == {"paint_mat": ["base_color", "metallic_roughness"]}
    s = build_surface(a)
    assert bake(a, s) is None  # authored parts are never baked
    assert run_validation(a, s)["status"] != "FAIL"


def test_authored_uvs_and_textures_round_trip_exactly(tmp_path):
    from scipy.spatial import cKDTree

    _, d = imported(tmp_path)
    a = build(d)
    out = tmp_path / "out.glb"
    write_glb(a, build_surface(a), out)
    g0, P0, U0, _, img0 = read_glb(tmp_path / "crate.glb")
    g1, P1, U1, _, img1 = read_glb(out)
    dist, _ = cKDTree(np.c_[P0, U0]).query(np.c_[P1, U1])
    assert dist.max() < 1e-4  # every exported (position, uv) pair exists in the original file
    assert np.array_equal(img1[0], img0[0])  # the base colour image is unchanged
    m = g1["materials"][0]
    assert "baseColorTexture" in m["pbrMetallicRoughness"] and "metallicRoughnessTexture" in m["pbrMetallicRoughness"]


def test_exported_atlas_follows_the_gltf_uv_convention(make_asset, tmp_path):
    """Sample the exported base texture the way an engine does (v from the image's top row) and compare
    with the bake: this is the check that caught the Phase 8 v-flip bug."""
    p = make_asset("materials: {m: {archetype: painted, color: '#3f6b8a', under_color: '#e0c080', chips: 0.9, edge_wear: 1.0}}\n"
                   "parts:\n  a: {shape: {type: chamfer_box, size: [0.6, 0.3, 0.4], chamfer: 0.05}, material: m}\n")
    a = build(p)
    s = build_surface(a)
    t = bake(a, s)
    out = tmp_path / "atlas.glb"
    write_glb(a, s, out)
    g, P, U, tri, images = read_glb(out)
    img = images[g["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"]["index"]].astype(float) / 255
    h, w = img.shape[:2]
    cu = U[tri].mean(1)  # face-centre UVs in file convention
    engine = img[np.clip((cu[:, 1] * h).astype(int), 0, h - 1), np.clip((cu[:, 0] * w).astype(int), 0, w - 1)]
    r = t.resolution
    internal = t.base[np.clip(((1 - (1 - cu[:, 1])) * r).astype(int), 0, r - 1), np.clip((cu[:, 0] * r).astype(int), 0, r - 1)]
    assert np.abs(engine - internal).mean() < 0.02
    flipped = img[np.clip(((1 - cu[:, 1]) * h).astype(int), 0, h - 1), np.clip((cu[:, 0] * w).astype(int), 0, w - 1)]
    assert np.abs(flipped - internal).mean() > np.abs(engine - internal).mean()


def test_authored_uv_overlap_and_tiling_are_not_errors(tmp_path):
    _, d = imported(tmp_path)  # the fixture's planar UVs overlap and exceed 0..1 on purpose
    a = build(d)
    codes = {i["code"]: i["severity"] for i in run_validation(a, build_surface(a))["issues"]}
    assert codes.get("UV_OVERLAP") is None and "UV_OUT_OF_BOUNDS" not in codes


def test_dropping_authored_uvs_is_an_error(tmp_path):
    _, d = imported(tmp_path)
    y = d / "asset.yaml"
    y.write_text(y.read_text().replace("tags:", "ops: [{type: subtract, shape: {type: box, size: [0.1, 1, 0.1]}}]\n    tags:", 1))
    a = build(d)
    issues = run_validation(a, build_surface(a))["issues"]
    assert any(i["code"] == "TEX_AUTHORED_UV_MISSING" and i["severity"] == "error" for i in issues)


def test_authored_texture_paths_are_sandboxed(tmp_path):
    _, d = imported(tmp_path)
    y = d / "asset.yaml"
    y.write_text(y.read_text().replace("base_color: source/textures/paint_mat_base_color.png", "base_color: ../../etc/x.png"))
    a = build(d)
    assert any(i["code"] == "TEX_AUTHORED_IMAGE_INVALID" for i in run_validation(a, build_surface(a))["issues"])


def test_reassigning_a_procedural_material_bakes_the_part(tmp_path):
    _, d = imported(tmp_path)
    y = d / "asset.yaml"
    y.write_text(y.read_text().replace("material: paint_mat", "material: oak") + "  oak: {archetype: wood, color: '#8a5a36'}\n"
                 if False else y.read_text().replace("material: paint_mat", "material: oak").replace("materials:\n", "materials:\n  oak: {archetype: wood, color: '#8a5a36'}\n", 1))
    a = build(d)
    s = build_surface(a)
    assert not s.parts[a.parts[0].name].authored and bake(a, s) is not None


def test_decimate_keeps_the_texture_mapping(tmp_path):
    src = fixture_glb(tmp_path / "ball.glb", sphere=True)
    import_file(src, tmp_path / "ball", "ball")
    d = tmp_path / "ball"
    a0 = build(d)
    y = d / "asset.yaml"
    y.write_text(y.read_text().replace("tags:", "ops: [{type: decimate, ratio: 0.3}]\n    tags:", 1))
    a1 = build(d)
    m0, m1 = a0.parts[0].mesh, a1.parts[0].mesh
    assert m1.n_tris < 0.4 * m0.n_tris and "uv" in m1.cattr and "uv" not in m1.invalidated

    def colours(m):
        cu = m.cattr["uv"].mean(1)
        return QUADRANTS[np.clip(((1 - cu[:, 1] % 1) * 32).astype(int), 0, 31), np.clip(((cu[:, 0] % 1) * 32).astype(int), 0, 31)] / 255

    from scipy.spatial import cKDTree

    _, near = cKDTree(m0.triangles().mean(1)).query(m1.triangles().mean(1))
    same = (np.abs(colours(m1) - colours(m0)[near]).sum(1) < 0.1).mean()
    assert same > 0.85  # the decimated surface shows the same texture colours at the same places


def test_clean_repairs_and_keeps_uvs(make_asset, tmp_path):
    import trimesh

    box = trimesh.creation.box(extents=[0.4, 0.4, 0.4])
    F = np.asarray(box.faces).copy()
    F[0] = F[0][::-1]  # one flipped face
    F = np.vstack([F, F[3:4], [[0, 0, 1]]])  # a duplicate and a degenerate face
    F = F[1:]  # and a hole (one face missing)
    V = np.asarray(box.vertices)
    uv = np.c_[V[:, 0] + 0.5, V[:, 1] + 0.5]
    t = trimesh.Trimesh(V, F, visual=trimesh.visual.TextureVisuals(uv=uv), process=False)
    (tmp_path / "rep").mkdir()
    t.export(tmp_path / "rep" / "broken.obj")
    p = make_asset("materials: {m: {color: '#888888'}}\nparts:\n  a: {shape: {type: mesh_file, path: broken.obj, "
                   "ops: [{type: clean, fill_holes: true}]}, material: m}\n", "rep")
    (p.parent / "broken.obj").write_bytes((tmp_path / "rep" / "broken.obj").read_bytes())
    a = build(p)
    m = a.parts[0].mesh
    codes = {i["code"] for i in run_validation(a, build_surface(a))["issues"] if i["severity"] != "info"}
    assert m.n_tris == 12 and m.volume() > 0 and "uv" in m.cattr
    assert not codes & {"GEO_DEGENERATE_FACES", "GEO_DUPLICATE_FACES", "GEO_OPEN_EDGES", "GEO_WINDING_INCONSISTENT", "GEO_INVERTED"}


def test_import_warns_about_units(tmp_path):
    src = fixture_glb(tmp_path / "tiny.glb", extents=(0.02, 0.01, 0.015))
    res = import_file(src, tmp_path / "tiny", "tiny")
    assert any("--scale" in h for h in res["hints"])


@pytest.mark.parametrize("mode", ["textured", "albedo", "roughness"])
def test_authored_parts_render_their_own_textures(tmp_path, mode):
    from shapewright.render.views import render

    _, d = imported(tmp_path)
    a = build(d)
    img = np.asarray(render(a, build_surface(a), "front", mode, 128)).reshape(-1, 3)
    if mode == "albedo":  # the quadrant colours from the texture appear, not a flat grey
        assert (np.abs(img.astype(int) - [255, 0, 0]).sum(1) < 60).any() or (np.abs(img.astype(int) - [0, 0, 255]).sum(1) < 60).any()


def test_variant_reads_the_base_assets_files(tmp_path):
    """FRESH_AGENT_07: a variant had to copy 7 MB of its base's source files."""
    _, d = imported(tmp_path)
    v = tmp_path / "crate_red"
    v.mkdir()
    (v / "asset.yaml").write_text("extends: ../crate\nmaterials: {paint_mat: {color: '#ff8080'}}\n")
    a = build(v)
    s = build_surface(a)
    assert run_validation(a, s)["status"] != "FAIL"
    out = tmp_path / "v.glb"
    write_glb(a, s, out)
    assert len(read_glb(out)[4]) == 2  # the base's texture files were found and embedded
    (v / "asset.yaml").write_text("extends: ../crate\nparts: {crate_body: {shape: {type: mesh_file, path: ../../x.glb}}}\n")
    from shapewright.report import SourceError

    with pytest.raises(SourceError):
        build(v)  # still sandboxed


def test_compare_works_for_imported_assets(tmp_path):
    from shapewright.history import compare, snapshot

    _, d = imported(tmp_path)
    snapshot(d / "asset.yaml", "as imported")
    stats, _ = compare(d / "asset.yaml", "1", "current")
    assert stats is not None


def test_part_named_like_the_asset_round_trips(tmp_path):
    from shapewright.export.verify import roundtrip

    _, d = imported(tmp_path)
    y = d / "asset.yaml"
    y.write_text(y.read_text().replace("crate_body:", "crate:", 1))
    a = build(d)
    out = tmp_path / "same.glb"
    write_glb(a, build_surface(a), out)
    assert roundtrip(a, out) == []


def test_clean_fill_holes_collapses_slit_fans(tmp_path):
    """A zero-width slit filled by a fan leaves needles; clean collapses them and the shell stays closed."""
    import trimesh

    from shapewright import backend
    from shapewright.assemble import apply_ops
    from shapewright.mesh import Mesh
    from shapewright.source import Ctx

    box = trimesh.creation.box(extents=[1, 1, 1])
    V, F = np.asarray(box.vertices, float), np.asarray(box.faces)
    m = Mesh(np.vstack([V, V[[0]] + [1e-9, 0, 0]]), F.copy())
    m.F[0, 0] = len(V)  # a vertex split by 1 nm: a slit hole that needs a zero-area fan
    out = apply_ops(m, [{"type": "clean", "fill_holes": True}], {}, Ctx(), "ops")
    assert backend.is_closed_manifold(out)
    _, area = out.face_normals()
    assert (area >= (np.linalg.norm(out.size()) * 1e-5) ** 2).all()
